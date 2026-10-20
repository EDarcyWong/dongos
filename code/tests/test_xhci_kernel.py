"""Current-source regression, not a replay of unavailable candidate snapshots.

Actual current kernel authorization with only physical I/O/allocator boundaries lowered.

This is no full OS build. Low-level hooks are explicit, hashed native transport
substitutions; all grant, binding, capability, gate and quarantine code is the
actual current source. A separate unmodified-source compilation is required too.
"""
from __future__ import annotations
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
SOURCE_ROOT=ROOT

def replace_function(source,name,replacement):
 m=re.search(r'(?m)^(?:pub\s+)?unsafe\s+fn\s+'+name+r'\s*\(',source)
 if not m:raise AssertionError('missing native boundary '+name)
 start=source.index('{',m.start());depth=1;i=start+1
 while depth:
  if source[i]=='{':depth+=1
  elif source[i]=='}':depth-=1
  i+=1
 return source[:m.start()]+replacement+source[i:]

def dependencies(stage,names,overrides=None):
 paths={}
 for base in (ROOT/'lang/examples',ROOT/'kernel',ROOT/'services',ROOT/'lang/std'):
  for p in base.rglob('*.dg'):
   s=p.read_text(encoding='utf-8');m=re.search(r'^module\s+([\w.]+);',s,re.M)
   if m:paths[m[1]]=p
 visited=set()
 def copy(name):
  if name in visited:return
  visited.add(name);s=(overrides or {}).get(name)
  if s is None:s=paths[name].read_text(encoding='utf-8')
  out=stage/(name.replace('.','/')+'.dg');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(s,encoding='utf-8')
  for child in re.findall(r'^import\s+([\w.]+)\s+as\s+',s,re.M):copy(child)
 for name in names:copy(name)

def stubs():
 return {
 'boot.memory_startup':'''module boot.memory_startup;import mm.paging as paging;
 pub struct View {pub raw_map:u64,pub descriptor_size:u64,pub raw_size:u64,pub framebuffer_physical:u64,pub framebuffer_bytes:u64}
 pub fn runtime_pointer()*const View{return null;}pub fn space_pointer()*paging.Space{return null;}
 ''',
 'boot.acpi_startup':'''module boot.acpi_startup;pub struct Region {pub segment:u64,pub base:u64,pub start_bus:u64,pub end_bus:u64}
 pub struct Inventory {pub mcfg_count:u64,pub mcfg_regions:[1]Region}pub fn inventory_pointer()*const Inventory{return null;}
 ''',
 'boot.device_memory':'''module boot.device_memory;pub fn runtime_invalidate(address:u64)void{return;}''',
 'mm.paging':'''module mm.paging;pub const WRITE:u64=1;pub const UNCACHED:u64=8;pub struct Space {pub value:u64}
pub struct Mapping {pub physical:u64,pub flags:u64}
pub error Unmodeled=0x7fff0001;
// The physical-window fast path is outside this native grant fixture.
pub unsafe fn query(s:*const Space,v:u64,out:*Mapping)!void{return error.Unmodeled;}
 pub unsafe fn map_live(s:*Space,v:u64,p:u64,f:u64)!void{return;}pub unsafe fn replace_live(s:*Space,v:u64,p:u64,f:u64)!void{return;}''',
 'cpu.capabilities':'''module cpu.capabilities;pub struct Capabilities {pub physical_bits:u8}
 pub const EMPTY_CAPABILITIES:Capabilities=Capabilities {physical_bits:48};pub unsafe fn detect(c:*Capabilities)!void{return;}''',
 # Keep the real VirtIO PCI types/parser: the trusted reset dependency now
 # uses its callback ABI even though these xHCI cases never invoke reset.
 'drivers.virtio_blk':'''module drivers.virtio_blk;pub const DMA_BYTES:usize=69632;pub struct Lease {pub token:u64,pub physical:u64,pub pointer:*u8,pub length:usize}
 pub const EMPTY_LEASE:Lease=Lease {token:0,physical:0,pointer:null,length:0};''',
 'user.memory':'''module user.memory;pub error Invalid=0x04060003;
 pub struct Frame {pub physical:u64,pub virtual:u64,pub writable:u64}
 unsafe extern "sysv64" fn native_map(id:u64,virtual:u64,physical:u64,bytes:u64)u64;
 unsafe extern "sysv64" fn native_alloc(id:u64,virtual:u64,requested:u64,out:*u64)u64;
 unsafe extern "sysv64" fn native_alias(id:u64,virtual:u64,out:*u64)u64;
 unsafe extern "sysv64" fn native_copy(id:u64,virtual:u64,out:*u8,bytes:u64)u64;
 unsafe extern "sysv64" fn native_frames()*const Frame;
 pub fn frame_count()usize{return 32;}pub fn frames()*const Frame{unsafe{return native_frames();}}
 pub unsafe fn map_device(id:usize,virtual:u64,physical:u64,bytes:u64)!void{unsafe{if native_map(id as u64,virtual,physical,bytes)!=0{return error.Invalid;}}return;}
 pub unsafe fn contiguous(id:usize,virtual:u64,requested:usize)!u64{unsafe{var out:u64=0;if native_alloc(id as u64,virtual,requested as u64,&out)!=0{return error.Invalid;}return out;}}
 pub unsafe fn owned_alias(id:usize,virtual:u64,write:bool)!u64{unsafe{var out:u64=0;if !write||native_alias(id as u64,virtual,&out)!=0{return error.Invalid;}return out;}}
 pub unsafe fn copy_in(id:usize,virtual:u64,out:[]u8)!void{unsafe{if native_copy(id as u64,virtual,out.ptr,out.len as u64)!=0{return error.Invalid;}}return;}
 ''',
 'boot.service_memory':'''module boot.service_memory;pub error Invalid=0x0f000001;pub struct Block{pub physical:u64,pub virtual:u64,pub pages:u64}
 pub struct Arena{pub physical:u64,pub length:u64}pub struct Plan{pub arena:Arena}
 var PLAN:Plan=Plan{arena:Arena{physical:0x30000000,length:43*4096}};pub var ARENA_BASE:u64=0;
 unsafe extern "sysv64" fn native_resources(pages:u64,alignment:u64,out:*Block)u64;
 unsafe extern "sysv64" fn native_arena()u64;
 pub unsafe fn plan_pointer()*const Plan{unsafe{return &PLAN;}}
 pub unsafe fn allocate(pages:usize,alignment:usize,out:*Block)!void{unsafe{
  ARENA_BASE=native_arena();if native_resources(pages as u64,alignment as u64,out)!=0{return error.Invalid;}
 }return;}''',
 'irq.platform':'''module irq.platform;pub struct Route {pub gsi:u64}pub const EMPTY_ISA_ROUTE:Route=Route {gsi:0};
pub struct Report {pub lapic_id:u64}pub const EMPTY_REPORT:Report=Report {lapic_id:0};
pub error Unmodeled=0x7fff0002;
// Binding a physical MSI route is not modeled by these grant/quarantine cases.
pub unsafe fn describe(out:*Report)!void{return error.Unmodeled;}
 pub unsafe fn route_isa(irq:u64,masked:bool,out:*Route)!void{unsafe{(*out).gsi=irq;}return;}
 pub unsafe fn mask_isa(irq:u64,masked:bool)!void{return;}pub unsafe fn device_eoi()!void{return;}''',
 }

def lowered(source):
 hooks='''
unsafe extern "sysv64" fn native_read(physical:u64,out:*u32)u64;
unsafe extern "sysv64" fn native_write(physical:u64,value:u32)u64;
unsafe extern "sysv64" fn native_command(ecam:u64,value:u16)u64;
unsafe extern "sysv64" fn native_write16(physical:u64,value:u16)u64;
unsafe extern "sysv64" fn native_range(physical:u64,bytes:u64,ecam:bool)u64;
unsafe extern "sysv64" fn native_mmio(physical:u64,out:*u32)u64;
export("xk_native_start") fn native_start()void {unsafe{REGION_BASE=0xe0000000;REGION_FIRST=0;REGION_LAST=0;PHYSICAL_BITS=48;PHYSICAL_LIMIT=1<<48;}return;}
'''
 source=source.replace('pub error Invalid =',hooks+'\npub error Invalid =')
 source=replace_function(source,'read32','''unsafe fn read32(physical:u64)!u32{unsafe{var out:u32=0;if native_read(physical,&out)!=0{return error.Invalid;}return out;}}''')
 source=replace_function(source,'write32','''unsafe fn write32(physical:u64,value:u32)!void{unsafe{if native_write(physical,value)!=0{return error.Invalid;}}return;}''')
 source=replace_function(source,'command','''unsafe fn command(ecam:u64,value:u16)!void{unsafe{if native_command(ecam,value)!=0{return error.Invalid;}}return;}''')
 source=replace_function(source,'configuration_write16','''pub unsafe fn configuration_write16(physical:u64,value:u16)!void{unsafe{if native_write16(physical,value)!=0{return error.Invalid;}}return;}''')
 source=replace_function(source,'mmio_range','''unsafe fn mmio_range(physical:u64,bytes:u64,ecam:bool)!void{unsafe{if native_range(physical,bytes,ecam)!=0{return error.Invalid;}}return;}''')
 needle='return volatile_load((WINDOW+(physical&4095)) as *const u32) as u64;'
 if source.count(needle)!=2:raise AssertionError('MMIO native lowering drift')
 return source.replace(needle,'var value:u32=0;if native_mmio(physical,&value)!=0{return error.Invalid;}return value as u64;')

class XhciKernelTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/p8-xhci-kernel'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.inputs=[SOURCE_ROOT/'kernel/user/devices.dg',SOURCE_ROOT/'kernel/user/device_host.dg',SOURCE_ROOT/'kernel/user/virtio_quiesce.dg',SOURCE_ROOT/'services/drivers/virtio_pci.dg',SOURCE_ROOT/'services/drivers/pci.dg',SOURCE_ROOT/'services/drivers/device_manager.dg',SOURCE_ROOT/'services/drivers/xhci_authority.dg',ROOT/'tests/xhci_kernel_probe.dg',ROOT/'tests/xhci_kernel_probe.c',Path(__file__)]
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('xHCI kernel source changed during verification')
 def command(self,args,d,name):
  r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();stage=d/'source';override=stubs();original=(SOURCE_ROOT/'kernel/user/devices.dg').read_text()
   if mutation:
    needle,replacement={
     'wrong-device':('((try read32(XHCI_ADMITTED))!=XHCI_IDENTITY)','false'),
     'stale-owner':('owner!=XHCI_OWNER||incarnation!=XHCI_INCARNATION||',''),
     'late-interrupter':('while i<b.interrupters as usize {','while i<1 {'),
     'reuse-quarantine':('XHCI_QUARANTINED=true;ecam=XHCI_ADMITTED;','ecam=XHCI_ADMITTED;'),
    }[mutation];self.assertEqual(1,original.count(needle));original=original.replace(needle,replacement)
   override['user.devices']=lowered(original);dependencies(stage,['user.devices','user.device_host'],override)
   c=compile_file(ROOT/'tests/xhci_kernel_probe.dg',roots=[ROOT/'tests',stage],mode=mode);(d/'probe.asm').write_text(c.assembly)
   obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm and cc)
   r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(d/'probe.asm')],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
   exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/xhci_kernel_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
   scenarios=('removed-identity','owner','late-interrupter','quarantine') if mutation else ('normal','removed-identity','owner','late-interrupter','quarantine','partial-grant','readback','dma-page','old-erstba','bar-overlap','legacy-isolation','msi','cap-boundary','extension-boundary','removed-before-attach','wrong-slot')
   if mutation:scenarios=({'wrong-device':'removed-identity','stale-owner':'owner','late-interrupter':'late-interrupter','reuse-quarantine':'quarantine'}[mutation],)
   for scenario in scenarios:
    r=self.command([str(exe),scenario],d,scenario)
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI kernel check failed line',r.stderr)
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI kernel native checks passed',r.stdout)
 def test_unmodified_kernel_and_launcher_compile(self):
  stage=self.out/'unmodified-source';dependencies(stage,['user.devices','user.device_host','drivers.device_manager'])
  for mode in ('debug','release'):
   for name in ('user.devices','user.device_host','drivers.device_manager'):
    c=compile_file(stage/(name.replace('.','/')+'.dg'),roots=[stage],mode=mode);p=self.out/(name+'-'+mode+'.asm');p.write_text(c.assembly)
    nasm=tool('nasm','NASM');r=self.command([nasm,'-f','elf64',*nasm_flags(nasm),'-o',str(p.with_suffix('.o')),str(p)],self.out,name+'-'+mode);self.assertEqual(0,r.returncode,r.stderr)
 def test_actual_kernel_grant_gate_and_quarantine(self):self.native()
 def test_actual_bad_kernel_sources_are_rejected(self):
  for mutation in ('wrong-device','stale-owner','late-interrupter','reuse-quarantine'):self.native(mutation)
