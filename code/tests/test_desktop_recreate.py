"""Execute production desktop recreation with an independent mapping model."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
ROOT=Path(__file__).resolve().parents[1]
STUBS={
'user/memory.dg':'''module user.memory;
pub error Failed=0x04060001;pub struct Process{pub ready:u64}pub var RESOURCE_FAILED:bool=false;
unsafe extern "sysv64" ("dt_processes") fn p()*Process;
unsafe extern "sysv64" ("dt_generation") fn g(id:u64)u64;
unsafe extern "sysv64" ("dt_device") fn device(id:u64,va:u64,pa:u64,n:u64)u64;
unsafe extern "sysv64" ("dt_anonymous") fn anon(id:u64,va:u64)u64;
unsafe extern "sysv64" ("dt_share") fn shared(s:u64,t:u64,sv:u64,tv:u64,rw:u64)u64;
unsafe extern "sysv64" ("dt_copy") fn copied(id:u64,va:u64,p:*const u8,n:u64)u64;
unsafe extern "sysv64" ("dt_readonly") fn ro(id:u64,va:u64)u64;
unsafe extern "sysv64" ("dt_alias") fn alias(id:u64,va:u64,rw:u64)u64;
unsafe extern "sysv64" ("dt_range") fn range(id:u64,va:u64,n:u64,rw:u64)u64;
unsafe extern "sysv64" ("dt_aperture") fn aperture(id:u64,va:u64,pa:u64,n:u64)u64;
unsafe extern "sysv64" ("dt_replace") fn replaced(id:u64,va:u64,opa:u64,on:u64,pa:u64,n:u64)u64;
pub fn processes()*Process{unsafe{return p();}}pub fn generation(id:usize)u64{unsafe{return g(id as u64);}}
pub unsafe fn map_device(id:usize,va:u64,pa:u64,n:u64)!void{unsafe{if device(id as u64,va,pa,n)!=0{return error.Failed;}}return;}
pub unsafe fn anonymous(id:usize,va:u64)!u64{unsafe{let v=anon(id as u64,va);if v==0{return error.Failed;}return v;}}
pub unsafe fn share_at(s:usize,t:usize,sv:u64,tv:u64,rw:bool)!void{unsafe{var w:u64=0;if rw{w=1;}if shared(s as u64,t as u64,sv,tv,w)!=0{return error.Failed;}}return;}
pub unsafe fn share(s:usize,t:usize,v:u64,rw:bool)!void{unsafe{return share_at(s,t,v,v,rw);}}
pub unsafe fn copy_out(id:usize,va:u64,p:[]const u8)!void{unsafe{if copied(id as u64,va,p.ptr,p.len as u64)!=0{return error.Failed;}}return;}
pub unsafe fn readonly_data(id:usize,va:u64)!void{unsafe{if ro(id as u64,va)!=0{return error.Failed;}}return;}
pub unsafe fn owned_alias(id:usize,va:u64,rw:bool)!u64{unsafe{var w:u64=0;if rw{w=1;}let v=alias(id as u64,va,w);if v==0{return error.Failed;}return v;}}
pub unsafe fn readonly_alias(id:usize,va:u64)!u64{unsafe{return owned_alias(id,va,false);}}
pub unsafe fn check_range(id:usize,va:u64,n:usize,rw:bool)!void{unsafe{var w:u64=0;if rw{w=1;}if range(id as u64,va,n as u64,w)!=0{return error.Failed;}}return;}
pub unsafe fn resource_aperture(id:usize,va:u64,pa:u64,n:u64)!void{unsafe{if aperture(id as u64,va,pa,n)!=0{return error.Failed;}}return;}
pub unsafe fn replace_resource_aperture(id:usize,va:u64,op:u64,on:u64,pa:u64,n:u64)!void{unsafe{if replaced(id as u64,va,op,on,pa,n)!=0{return error.Failed;}}return;}
''',
'boot/memory_startup.dg':'''module boot.memory_startup;pub struct Display{pub width:u64,pub height:u64,pub stride:u64,pub pixel_format:u64,pub framebuffer_base:u64}pub struct Runtime{pub display:Display}unsafe extern "sysv64" ("dt_runtime") fn p()*Runtime;pub fn runtime_pointer()*Runtime{unsafe{return p();}}''',
'boot/service_memory.dg':'''module boot.service_memory;import exec.bundle as bundle;pub const BUNDLE_BASE:u64=0x30000000;pub struct Block{pub physical:u64}pub struct Plan{pub bundle:Block}pub error Failed=0x04060002;unsafe extern "sysv64" ("dt_plan") fn p()*Plan;unsafe extern "sysv64" ("dt_find") fn f(p:*const u8,n:u64,out:*bundle.Contents)u64;pub fn plan_pointer()*Plan{unsafe{return p();}}pub unsafe fn find(name:[]const u8,out:*bundle.Contents)!void{unsafe{if f(name.ptr,name.len as u64,out)!=0{return error.Failed;}}return;}''',
'exec/bundle.dg':'''module exec.bundle;pub struct Contents{pub pointer:*u8,pub length:usize}''',
'irq/platform.dg':'''module irq.platform;pub struct Report{pub tsc_hz:u64}pub const EMPTY_REPORT:Report=Report{tsc_hz:0};pub error Failed=0x04060003;unsafe extern "sysv64" ("dt_clock") fn f(p:*u64)u64;pub unsafe fn describe(out:*Report)!void{unsafe{if f(&(*out).tsc_hz)!=0{return error.Failed;}}return;}''',
}
SUFFIX='''
export("dtr_prepare") fn native_prepare()u64{unsafe{match prepare(3,4){ok=>{return 0;},err(e)=>{return e;},}}}
export("dtr_recreate") fn native_recreate(id:u64)u64{unsafe{match recreate(id as usize){ok=>{return 0;},err(e)=>{return e;},}}}
export("dtr_font") fn native_font(scale:u64)u64{unsafe{match select_font(scale){ok(v)=>{return 0;},err(e)=>{return e;},}}}
'''


class DesktopRecreateTests(unittest.TestCase):
    def test_actual_generation_gated_recreate_retains_input_descriptor_and_allocates_private_caches(self):
        directory=ROOT/'build/test/desktop-recreate'/('run-'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
        inputs=[ROOT/p for p in ('kernel/user/desktop.dg','services/lib/desktop.dg','tests/desktop_recreate_probe.c','tests/test_desktop_recreate.py')]
        before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        staged=directory/'sources'
        for name,text in STUBS.items():
            target=staged/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
        (staged/'lib').mkdir();(staged/'lib/desktop.dg').write_bytes((ROOT/'services/lib/desktop.dg').read_bytes())
        original=(ROOT/'kernel/user/desktop.dg').read_bytes();target=staged/'user/desktop.dg';target.write_bytes(original+SUFFIX.encode());self.assertEqual(original,target.read_bytes()[:len(original)])
        bad_sources=directory/'bad-writable-descriptor';shutil.copytree(staged,bad_sources)
        bad_text=original.decode().replace('\r\n','\n').replace('module user.desktop;',
            'module user.desktop;\nunsafe extern "sysv64" ("dt_negative_hit") fn native_negative_hit(kind:u64)void;',1)
        needle='try memory.share_at(4,3,api.DESCRIPTOR,api.DESCRIPTOR,false);';self.assertEqual(1,bad_text.count(needle))
        bad_text=bad_text.replace(needle,'native_negative_hit(1);try memory.share_at(4,3,api.DESCRIPTOR,api.DESCRIPTOR,true);',1)
        (bad_sources/'user/desktop.dg').write_text(bad_text+SUFFIX)
        outcomes=[]
        for label,root in (('normal',staged),('bad-writable-descriptor',bad_sources)):
          for mode in ('debug','release'):
            out=directory/label/mode;out.mkdir(parents=True);compiled=compile_file(root/'user/desktop.dg',roots=[root],mode=mode);asm=out/'probe.asm';asm.write_text(compiled.assembly)
            nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
            for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',out/(fmt+'.o'),asm],out,'assemble-'+fmt)
            exe=out/('probe.exe' if os.name=='nt' else 'probe');flags=['-mno-sse'] if os.name=='nt' else ['-no-pie','-D_GNU_SOURCE']
            command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*flags,ROOT/'tests/desktop_recreate_probe.c',out/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',exe],out,'link')
            result=command([exe],out,'native',success=False)
            if label=='normal':
                self.assertEqual(0,result.returncode,result.stdout+result.stderr);self.assertIn('Desktop production recreate passed',result.stdout)
            else:
                self.assertEqual(1,result.returncode,result.stdout+result.stderr);self.assertIn('DESKTOP_RECREATE_NEGATIVE_HIT 1',result.stderr)
                self.assertIn('DESKTOP_RECREATE_ASSERT',result.stderr);self.assertNotIn('unexpected panic',result.stderr)
            outcomes.append(dict(label=label,mode=mode,stdout=result.stdout,stderr=result.stderr))
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs};self.assertEqual(before,after)
        (directory/'validation-summary.json').write_text(json.dumps(dict(source_unchanged=True,source_sha256=after,results=outcomes,
            actual_production_desktop_body=True,actual_memory_page_tables_or_kernel_guest=False),indent=2)+'\n')
        print('DESKTOP_RECREATE_EVIDENCE '+str(directory))


if __name__=='__main__':unittest.main(verbosity=2)
