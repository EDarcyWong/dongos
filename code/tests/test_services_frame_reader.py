"""Physical frame-table validator rejects forged extents before reading."""
import struct,unittest
from tests.run_services_qemu import read_owned_frames,validate_commands
class Tests(unittest.TestCase):
 def test_persistence_commands_require_real_outputs_in_order(self):
  commands=['write PROBE.TXT abc','cat PROBE.TXT','ls','sync','exit']
  serial=b'> write PROBE.TXT abc\r\nWRITE OK\r\n> cat PROBE.TXT\r\nabc\r\n> ls\r\nPROBE.TXT 3\r\n> sync\r\nSYNC OK\r\n> exit\r\nDONGOS_SHELL_EXIT\r\nservices_version='
  validate_commands(serial,commands,5,b'abc')
  mutations=[serial.replace(b'WRITE OK',b'FAIL'),serial.replace(b'SYNC OK',b'FAIL'),
   serial.replace(b'cat PROBE.TXT\r\nabc',b'cat PROBE.TXT\r\nxyz'),
   serial.replace(b'PROBE.TXT 3',b'PROBE.TXT 4'),serial.replace(b'DONGOS_SHELL_EXIT',b'FAIL'),
   serial.replace(b'> sync\r\n',b'> syne\r\n'),serial+b'> cat PROBE.TXT\r\n',
   serial.replace(b'WRITE OK',b'ERROR 0xdead\r\nWRITE OK')]
  for changed in mutations:
   with self.subTest(serial=changed),self.assertRaises(ValueError):validate_commands(changed,commands,5,b'abc')
  with self.assertRaises(ValueError):validate_commands(serial,commands,4,b'abc')
 def test_actual_non_catalog_shell_mark_and_old_rejection(self):
  import hashlib,json,os,subprocess,uuid
  from pathlib import Path
  from lang.dongc import compile_file
  from lang.tests.test_dongc import tool,nasm_flags
  from tests.test_service_ipc_cancellation import block
  root=Path(__file__).resolve().parents[1];source=root/'kernel/user/services.dg'
  digest=hashlib.sha256(source.read_bytes()).hexdigest()
  fragment=block(source.read_text(encoding='utf-8'),'    if code==0x89{')
  fallback=block(fragment,'if CATALOG==null{')
  out=root/'build/test/p5-shell-mark'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
  (out/'user').mkdir();(out/'boot').mkdir()
  (out/'user/abi.dg').write_bytes((root/'kernel/user/abi.dg').read_bytes())
  (out/'user/processes.dg').write_text('module user.processes;pub struct Snapshot{pub generation:u64}pub struct Catalog{pub states:[1]Snapshot}pub unsafe fn current(c:*const Catalog,id:usize)u64{return 0;}')
  (out/'boot/trace_runtime.dg').write_text('module boot.trace_runtime;pub fn mark(c:u64,g:u64,k:u64)u64{return 0xdead;}')
  template='''module mark_probe;import user.abi as abi;import user.processes as procs;import boot.trace_runtime as boot_trace;
pub error Protocol=0x050b_0002;var CURRENT:usize=0;var CATALOG:*procs.Catalog=null;
unsafe fn managed(id:usize)bool{return false;}
unsafe fn mark(frame:*abi.Frame)!usize{unsafe{let code=(*frame).rax;FRAGMENT return error.Protocol;}}
export("mark_test") fn probe(actor:usize,kind:u64,extra:u64)u64{unsafe{
 CURRENT=actor;var frame=abi.EMPTY_FRAME;frame.rax=0x89;frame.rdi=kind;frame.rsi=extra&1;frame.rdx=extra&2;
 frame.r10=extra&4;frame.r8=extra&8;frame.r9=extra&16;
 match mark(&frame){ok(v)=>{return frame.rax;},err(e)=>{return e;},}
}}
'''
  c=out/'probe.c';c.write_text('''#include <stdint.h>
#include <stdio.h>
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI mark_test(uint64_t,uint64_t,uint64_t);
void ABI __dong_panic(void){}
int main(void){
 if(mark_test(0,1,0)!=0){fputs("valid P5 shell mark rejected",stderr);return 90;}
 for(uint64_t i=1;i<16;i++)if(mark_test(i,1,0)!=0x050b0002)return 91;
 for(uint64_t i=0;i<5;i++)if(mark_test(0,1,1ULL<<i)!=0x050b0002)return 92;
 if(mark_test(0,0,0)!=0x050b0002||mark_test(0,2,0)!=0x050b0002||mark_test(0,UINT64_MAX,0)!=0x050b0002)return 93;
 return 0;}
''')
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);records=[]
  for mode in ('debug','release'):
   for variant in ('normal','old-reject-shell-mark'):
    body=fragment if variant=='normal' else fragment.replace(fallback,'if CATALOG==null{return error.Protocol;}')
    p=out/'mark_probe.dg';p.write_text(template.replace('FRAGMENT',body))
    compiled=compile_file(p,roots=[out],mode=mode)
    asm=out/(mode+'-'+variant+'.asm');asm.write_text(compiled.assembly)
    obj=out/(mode+'-'+variant+'.o');exe=out/(mode+'-'+variant+('.exe' if os.name=='nt' else ''))
    commands=[]
    for fmt in ('elf64','win64'):
     target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else out/(mode+'-'+variant+'.'+fmt+'.o')
     commands.append([nasm,'-f',fmt,*nasm_flags(nasm),'-o',target,asm])
    commands.append([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',c,obj,'-o',exe])
    for index,argv in enumerate(commands+[[exe]]):
     r=subprocess.run(list(map(str,argv)),capture_output=True,timeout=60);expected=90 if index==len(commands) and variant!='normal' else 0
     self.assertEqual(r.returncode,expected,r.stderr.decode(errors='replace'))
     records.append(dict(command=list(map(str,argv)),returncode=r.returncode,expected=expected))
  self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)
  (out/'summary.json').write_text(json.dumps(dict(source_sha=digest,records=records,source_stable=True),indent=2)+'\n')
 def test_dynamic_table_and_boundaries(self):
  base=0xffffd40000000000;pa=0x4000000;limit=16384;extent=32768*4096
  for pointer,count in ((base,1),(base+4096,724),(base+extent-limit*24,limit)):
   calls=[];rows=[(pa+i*4096,0xffffd00000000000+i*4096,i%2) for i in range(count)]
   def read(address,n,role):
    calls.append((address,n,role));return b''.join(struct.pack('<3Q',*r) for r in rows)
   self.assertEqual(read_owned_frames(count,pointer,limit,pa,32768,read,lambda va:(pa+va-base)|0x8000000000000003),rows)
   self.assertEqual(calls,[(pa+pointer-base,count*24,'dynamic owned frames')])
 def test_forged_extents_rejected_without_reads(self):
  base=0xffffd40000000000;pa=0x4000000;extent=32768*4096
  good=[724,base+4096,16384,pa,32768]
  cases=[(0,0),(0,16385),(0,-1),(1,0),(1,base-8),(1,base+1),(1,base+extent-16384*24+8),
   (1,base+extent),(1,0xfffffffffffffff8),(2,512),(2,16385),(3,0),(3,pa+1),(3,(1<<48)-4096),
   (3,1<<48),(4,32767),(4,32769)]
  for index,value in cases:
   calls=[];args=good.copy();args[index]=value
   def read(*a):calls.append(a);raise AssertionError('read before validation')
   with self.subTest(index=index,value=value),self.assertRaises(ValueError):read_owned_frames(*args,read)
   self.assertEqual(calls,[])
 def test_truncated_physical_dump_rejected(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):
   read_owned_frames(2,0xffffd40000001000,16384,0x4000000,32768,lambda *a:b'\0'*47,lambda va:(0x4000000+va-0xffffd40000000000)|0x8000000000000003)
 def test_wrong_metadata_mapping_rejected_before_dump(self):
  expected=0x4001000|0x8000000000000003
  for entry in (0,expected^4096,expected^1,expected^2,expected^(1<<63),expected|4,expected|8,expected|16,expected|128):
   calls=[]
   with self.subTest(entry=entry),self.assertRaisesRegex(ValueError,'mapping'):
    read_owned_frames(2,0xffffd40000001000,16384,0x4000000,32768,lambda *a:calls.append(a),lambda va:entry)
   self.assertEqual(calls,[])
 def test_actual_owner_addresses_not_bootstrap_buddy_range(self):
  pa=0x4000000;alias=0xffffd00000000000;extent=32768*4096
  def run(rows):
   return read_owned_frames(len(rows),0xffffd40000001000,16384,pa,32768,
     lambda *a:b''.join(struct.pack('<3Q',*row) for row in rows),lambda va:(pa+va-0xffffd40000000000)|0x8000000000000003)
  # Last service-held page is valid even beyond the old 4MiB buddy arena.
  rows=[(pa+extent-4096,alias,0),(pa+4096,alias+4096,1)]
  self.assertEqual(run(rows),rows)
  for bad in ((pa-4096,alias,0),(pa+extent,alias,0),(pa+1,alias,0),
    (pa,alias+4096,0),(pa,alias,2)):
   with self.subTest(row=bad),self.assertRaises(ValueError):run([bad])
  with self.assertRaisesRegex(ValueError,'duplicate'):run([(pa,alias,0),(pa,alias+4096,1)])
if __name__=='__main__':unittest.main()
