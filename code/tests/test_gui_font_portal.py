"""Production GUI font portal: real four-level RO tables and stopped-root updates."""
from __future__ import annotations
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT
def collect(stage,names,overrides=None):
 paths={}
 for base in (ROOT/'lang/examples',ROOT/'kernel',ROOT/'services',ROOT/'lang/std',CANDIDATE/'kernel',CANDIDATE/'services'):
  for p in base.rglob('*.dg'):
   s=p.read_text(encoding='utf-8');m=re.search(r'^module\s+([\w.]+);',s,re.M)
   if m:paths[m[1]]=p
 seen=set()
 def copy(name):
  if name in seen:return
  seen.add(name);s=(overrides or {}).get(name)
  if s is None:s=paths[name].read_text(encoding='utf-8')
  target=stage/(name.replace('.','/')+'.dg');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(s,encoding='utf-8')
  for child in re.findall(r'\bimport\s+([\w.]+)\s+as\s+',s):copy(child)
 for name in names:copy(name)
def boundaries():
 return {
  'boot.memory_startup':'''module boot.memory_startup;import mm.paging as paging;import mm.phys_buddy as buddy;import boot.runtime_view as runtime;
  pub fn space_pointer()*paging.Space{return null;}pub fn allocator_pointer()*buddy.Allocator{return null;}pub fn runtime_pointer()*const runtime.View{return null;}''',
  'boot.device_memory':'''module boot.device_memory;pub unsafe extern "sysv64" fn runtime_invalidate(address:u64)void;pub unsafe extern "sysv64" fn runtime_flush_root()void;''',
  'boot.service_memory':'''module boot.service_memory;import exec.bundle as bundle;pub error Invalid=0x0f010001;pub const BUNDLE_BASE:u64=0xffff_d800_0000_0000;
  pub struct Block {pub physical:u64,pub virtual:u64,pub pages:usize}pub struct Span {pub physical:u64,pub length:u64}pub struct Plan {pub bundle:Span}
  pub unsafe fn allocate(pages:usize,alignment:usize,out:*Block)!void{return error.Invalid;}pub unsafe fn reserve(pages:usize,alignment:usize,out:*Block)!void{return error.Invalid;}
  pub unsafe fn find(name:[]const u8,out:*bundle.Contents)!void{return error.Invalid;}pub fn plan_pointer()*const Plan{return null;}''',
  'irq.platform':'''module irq.platform;pub struct Report {pub tsc_hz:u64}pub const EMPTY_REPORT:Report=Report {tsc_hz:1000000000};pub unsafe fn describe(out:*Report)!void{unsafe{*out=EMPTY_REPORT;}return;}''',
 }
class GuiFontTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/p7-font-native'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.inputs=[CANDIDATE/'kernel/user/memory.dg',CANDIDATE/'kernel/user/desktop.dg',CANDIDATE/'services/lib/window_broker_abi.dg',ROOT/'kernel/mm/paging.dg',ROOT/'services/gfx/atlas.dg',ROOT/'tests/gui_font_probe.dg',ROOT/'tests/gui_font_probe.c',ROOT/'tests/gui_font_memory_fixture.dg',ROOT/'tests/gui_font_desktop_fixture.dg',ROOT/'tests/gui_font_paging_fixture.dg',Path(__file__)]
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('GUI font source changed during verification')
 def command(self,args,d,name):
  r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();stage=d/'source';overrides=boundaries();s=(CANDIDATE/'kernel/user/memory.dg').read_text();cut=s.index('pub unsafe fn gui_resource_aperture(');end=s.index('// Exclusive two-root allocation transaction.',cut);prefix,body,suffix=s[:cut],s[cut:end],s[end:]
   if mutation:
    old,new={
     'skip-initial-preflight':('try shared_absent(id,0x7200_0000,2048);','let unchecked:u64=0;'),
     'accept-writable':('m.flags!=paging.USER||m.physical!=resource_page(old_physical,old_bytes,offset)','m.physical!=resource_page(old_physical,old_bytes,offset)'),
     'clear-before-barrier':('compiler_fence();devices.runtime_flush_root();user_pcid_flush_all();','RESOURCE_FAILED=false;compiler_fence();devices.runtime_flush_root();user_pcid_flush_all();'),
     'ignore-partial-fault':('if !initial {RESOURCE_FAILED=true;}','if !initial {RESOURCE_FAILED=false;}'),
    }[mutation];self.assertEqual(1,body.count(old));body=body.replace(old,new)
   overrides['user.memory']=prefix+body+suffix+'\n'+(ROOT/'tests/gui_font_memory_fixture.dg').read_text()
   overrides['user.desktop']=(CANDIDATE/'kernel/user/desktop.dg').read_text()+'\n'+(ROOT/'tests/gui_font_desktop_fixture.dg').read_text()
   paging=(ROOT/'kernel/mm/paging.dg').read_text();self.assertEqual(1,paging.count('pub unsafe fn map_live('));self.assertEqual(1,paging.count('pub unsafe fn replace_live('));paging=paging.replace('pub unsafe fn map_live(','unsafe fn font_real_map_live(').replace('pub unsafe fn replace_live(','unsafe fn font_real_replace_live(')
   overrides['mm.paging']=paging+'\n'+(ROOT/'tests/gui_font_paging_fixture.dg').read_text();collect(stage,['user.memory','user.desktop'],overrides)
   c=compile_file(ROOT/'tests/gui_font_probe.dg',roots=[ROOT/'tests',stage],mode=mode);layouts={i['full_name']:i for i in c.layout_manifest['types']};self.assertEqual(72,layouts['lib.window_broker_abi.Font']['size']);self.assertNotRegex(c.assembly.lower(),r'\b(?:invlpg|invpcid|rdmsr|wrmsr|hlt|cli|sti)\b');asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
   r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
   exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/gui_font_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
   scenarios=('normal','dpi','wrong-slot','stale-generation','writable','executable','wrong-physical','initial-collision','initial-abort','late-replacement','bad-font','bad-owner','owned-span','outside-stage','current-root','unmapped-client')
   if mutation:scenarios=({'skip-initial-preflight':'initial-collision','accept-writable':'writable','clear-before-barrier':'dpi','ignore-partial-fault':'late-replacement'}[mutation],)
   for scenario in scenarios:
    r=self.command([exe,scenario],d,scenario)
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertRegex(r.stderr,r'font (?:check failed line|ordering failed)')
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('GUI font native checks passed',r.stdout)
 def test_real_ro_tables_dpi_abort_and_faults(self):self.native()
 def test_actual_wrong_portal_sources_fail(self):
  for mutation in ('skip-initial-preflight','accept-writable','clear-before-barrier','ignore-partial-fault'):self.native(mutation)
 def test_unmodified_module_graph_compiles(self):
  stage=self.out/'unmodified-source';collect(stage,['user.memory','user.desktop'])
  for name in ('user.memory','user.desktop'):
   c=compile_file(stage/(name.replace('.','/')+'.dg'),roots=[stage],mode='release');(self.out/(name+'.asm')).write_text(c.assembly)
