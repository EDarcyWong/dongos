"""Pre-BME xHCI authority candidate against trusted independent snapshots."""
from __future__ import annotations
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
def direct_stack(assembly):
 functions={};current=None
 for line in assembly.splitlines():
  if line.startswith('section .rodata'):break
  found=re.fullmatch(r'\$?((?:__dg_|xa_)\w+):',line)
  if found:current=found.group(1);functions[current]=[]
  elif current:functions[current].append(line.strip())
 cache={}
 def visit(name,parents=()):
  if name in cache:return cache[name]
  if name in parents:raise AssertionError('recursive authority call graph')
  depth=0;maximum=16
  for line in functions[name]:
   if line.startswith('push ') and line!='push rbp':raise AssertionError('unexpected stack push')
   change=re.fullmatch(r'(sub|add) rsp, (\d+)',line)
   if change:depth+=int(change[2])*(1 if change[1]=='sub' else -1);maximum=max(maximum,16+depth)
   if line.startswith('call '):
    child=line[5:].lstrip('$')
    if child=='__dong_panic':continue
    if child not in functions:raise AssertionError('unknown authority callee '+child)
    maximum=max(maximum,16+depth+visit(child,(*parents,name)))
  cache[name]=maximum;return maximum
 return visit('xa_permit')

class XhciAuthorityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.source=Path(os.environ.get('DONGOS_XHCI_AUTHORITY_ROOT',str(ROOT/'services'))).resolve();cls.inputs=[cls.source/'drivers/xhci_authority.dg',ROOT/'services/usb/xhci_controller.dg',ROOT/'tests/xhci_authority_probe.dg',ROOT/'tests/xhci_authority_probe.c',Path(__file__)]
  controller=(ROOT/'services/usb/xhci_controller.dg').read_text()
  for name,expected in {'DMA_BYTES':131072,'COMMAND_OFFSET':4096,'EVENT_OFFSET':8192,'ERST_OFFSET':12288}.items():
   found=re.findall(r'pub\s+const\s+'+name+r'\s*:\s*u64\s*=\s*([0-9a-fA-F_x]+)\s*;',controller)
   if len(found)!=1 or int(found[0].replace('_',''),0)!=expected:raise AssertionError('pre-BME authority/controller layout mismatch '+name)
  cls.out=ROOT/'build/test/p8-xhci-authority'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True);cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n');
  if after!=cls.before:raise AssertionError('xHCI authority changed during native execution')
 def command(self,args,d,name):
  r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   with self.subTest(mode=mode,mutation=mutation):
    d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();source=self.source
    if mutation:
     source=d/'services';(source/'drivers').mkdir(parents=True);p=source/'drivers/xhci_authority.dg';s=(self.source/'drivers/xhci_authority.dg').read_text();needle,replacement={
      'old-erstba':('p.erstsz!=1||p.erstba!=0||','p.erstsz!=1||'),
      'binding-owner':('h.binding_owner!=h.owner||',''),
      'dma-pointer':('expected=h.lease_physical+4096;','expected=h.lease_physical+4096+8;'),
      'late-interrupter':('while i<interrupts.len {','while i<1 {'),
      'old-reject-empty':('||first==0||first>(*b).ports+1||count>(*b).ports+1-first',
                          '||first==0||count==0||first>(*b).ports||count>(*b).ports-first+1'),
      'missing-coverage':('expected!=0||covered!=((1 as u64)<<(*b).ports)-1','expected!=0'),
      'missing-overlap':('if (covered&mask)!=0 {return error.Denied;}',''),
     }[mutation];self.assertEqual(1,s.count(needle));p.write_text(s.replace(needle,replacement))
    c=compile_file(ROOT/'tests/xhci_authority_probe.dg',roots=[ROOT/'tests',source],mode=mode);layouts={x['full_name']:x for x in c.layout_manifest['types']};self.assertEqual(248,layouts['drivers.xhci_authority.Header']['size']);self.assertNotRegex(c.assembly.lower(),r'\b(?:invlpg|invpcid|rdmsr|wrmsr|hlt|cli|sti)\b');stack=direct_stack(c.assembly);self.assertLessEqual(stack,2048);(d/'stack.json').write_text(json.dumps(dict(direct_call_stack_bytes=stack,includes_return_saved_rbp_and_stack_arguments=True,panic_path_excluded=True),indent=2)+'\n')
    (d/'probe.asm').write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm and cc)
    r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(d/'probe.asm')],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
    if not mutation:
     other='elf64' if os.name=='nt' else 'win64';r=self.command([nasm,'-f',other,*nasm_flags(nasm),'-o',str(d/(other+'.o')),str(d/'probe.asm')],d,'assemble-'+other);self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/xhci_authority_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    r=self.command([str(exe)],d,'native')
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI authority check failed line',r.stderr)
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI authority native checks passed',r.stdout)
 def test_actual_authority_snapshots_and_dma(self):self.native()
 def test_actual_bad_authority_sources_are_rejected(self):
  for mutation in ('old-erstba','binding-owner','dma-pointer','late-interrupter',
                   'old-reject-empty','missing-coverage','missing-overlap'):self.native(mutation)
