"""Execute the pure pre-BME NVMe authority against independent C snapshots."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
ROOT=Path(__file__).resolve().parents[1]

def call_stack(assembly):
    """Bound direct normal-return paths, including saved RBP/return address."""
    functions={};current=None
    for line in assembly.splitlines():
        found=re.match(r'^(\$?(?:__dg_\w+|nvme_authority_permit)):$',line)
        if found:
            current=found.group(1).lstrip('$');functions[current]=[]
        elif current:
            functions[current].append(line.strip())
    seen={}
    def visit(name,parents=()):
        if name in seen:return seen[name]
        if name in parents:raise AssertionError('recursive policy call graph')
        body=functions[name]
        if [x for x in body if x.startswith('push ')]!=['push rbp']:
            raise AssertionError('unmodelled stack push')
        allocations=[int(m.group(1)) for x in body if (m:=re.fullmatch(r'sub rsp, (\d+)',x))]
        if len(allocations)!=1:raise AssertionError('unmodelled stack allocation')
        children=[]
        for line in body:
            if line.startswith('call '):
                child=line[5:].lstrip('$')
                if child=='__dong_panic':continue
                if child not in functions:raise AssertionError('unresolved policy call '+child)
                children.append(visit(child,(*parents,name)))
        child=max(children,key=lambda p:p[0]) if children else (0,[])
        seen[name]=(allocations[0]+16+child[0],[name,*child[1]])
        return seen[name]
    amount,path=visit('nvme_authority_permit')
    return dict(bytes=amount,path=path,includes_return_and_saved_rbp=True,panic_path_excluded=True)

class NvmeAuthorityTests(unittest.TestCase):
    def test_native_policy_controls_and_object_formats(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        self.assertTrue(nasm and cc,'NASM and SysV-capable GCC are required')
        directory=ROOT/'build/test/nvme-authority'/('run-'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
        names=('services/drivers/nvme_authority.dg','services/drivers/nvme_core.dg',
               'tests/nvme_authority_probe.dg','tests/nvme_authority_probe.c','tests/test_nvme_authority.py')
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names}
        evidence={}
        def command(args,where,label):
            result=subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True,timeout=60)
            (where/(label+'.json')).write_text(json.dumps(dict(command=[str(x) for x in args],returncode=result.returncode,
                stdout=result.stdout,stderr=result.stderr),indent=2)+'\n',encoding='utf-8')
            return result
        controls={
            'interrupts':('h.intms!=0xffff_ffff','false','UNSAFE_INTERRUPT_MASK_ACCEPTED'),
            'admin-base':('h.asq!=h.lease_physical','false','UNSAFE_ADMIN_BASE_ACCEPTED'),
            'doorbells':('0x1000+3*bound.doorbell_stride','0x1000+2*bound.doorbell_stride','UNSAFE_LAST_DOORBELL_ACCEPTED'),
        }
        for mode in ('debug','release'):
            evidence[mode]={}
            for kind in ('normal',*controls):
                where=directory/(mode+'-'+kind);where.mkdir()
                source=ROOT/'services'
                if kind!='normal':
                    source=where/'services';(source/'drivers').mkdir(parents=True)
                    body=(ROOT/names[0]).read_text(encoding='utf-8');old,new,_=controls[kind]
                    self.assertEqual(1,body.count(old));(source/'drivers/nvme_authority.dg').write_text(body.replace(old,new),encoding='utf-8')
                    (source/'drivers/nvme_core.dg').write_bytes((ROOT/names[1]).read_bytes())
                compiled=compile_file(ROOT/names[2],roots=[ROOT/'tests',source],mode=mode)
                layouts={v['full_name']:v for v in compiled.layout_manifest['types']}
                self.assertEqual(128,layouts['drivers.nvme_authority.Header']['size'])
                maximum=max(map(int,re.findall(r'\bsub rsp, (\d+)',compiled.assembly)),default=0)
                self.assertLessEqual(maximum,1024)
                stack=call_stack(compiled.assembly);self.assertLessEqual(stack['bytes'],2048)
                self.assertNotRegex(compiled.assembly.lower(),r'\b(?:invlpg|invpcid|rdmsr|wrmsr|hlt|cli|sti)\b')
                asm=where/'probe.asm';asm.write_text(compiled.assembly,encoding='utf-8')
                obj=where/'probe.o';exe=where/('probe.exe' if os.name=='nt' else 'probe')
                for fmt in ('win64','elf64') if kind=='normal' else ('win64' if os.name=='nt' else 'elf64',):
                    target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else where/(fmt+'.o')
                    r=command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',target,asm],where,'assemble-'+fmt)
                    self.assertEqual(0,r.returncode,r.stderr)
                r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing','-D_DEFAULT_SOURCE','-D__USE_MINGW_ANSI_STDIO=1',
                    *(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/names[3],obj,'-o',exe],where,'link')
                self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe,*([kind] if kind!='normal' else [])],where,'execute')
                if kind!='normal':
                    self.assertEqual(99,r.returncode,r.stdout+r.stderr);self.assertIn(controls[kind][2],r.stdout)
                else:
                    self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertRegex(r.stdout,r'NVMe authority checks=\d{6,} ')
                evidence[mode][kind]=dict(stdout=r.stdout,max_single_frame=maximum,direct_call_stack=stack)
        after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names}
        self.assertEqual(before,after)
        (directory/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,
            actual_device_executed=False,evidence=evidence),indent=2)+'\n',encoding='utf-8')
        print('NVME_AUTHORITY_EVIDENCE',directory)
