"""Execute the exact production text() body against a bounded logging callback."""
from __future__ import annotations
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
class ShellOutputTests(unittest.TestCase):
 def test_actual_text_chunks_all_bytes_and_stops_on_error(self):
  source=ROOT/'services/shell/main.dg';before=hashlib.sha256(source.read_bytes()).hexdigest();text=source.read_text(encoding='utf-8');start=text.index('fn text(');end=text.index('fn error_text(',start);body=text[start:end]
  out=ROOT/'build/test/shell-output'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);(out/'lib').mkdir()
  (out/'probe.dg').write_text('module probe; import lib.sys as sys;\n'+body+'\nexport("st_send") fn send(p:*const u8,n:usize)void{unsafe{text(slice_from_raw_parts(p,n));}}\n')
  (out/'lib/sys.dg').write_text('module lib.sys; unsafe extern "sysv64" ("shell_log") fn sink(p:*const u8,n:usize)u64; pub fn log(value:[]const u8)u64{unsafe{return sink(value.ptr,value.len);}}\n')
  csource=out/'probe.c';csource.write_text(r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
extern void SYSV st_send(const uint8_t*,uint64_t);
static uint8_t actual[70000],input[70000];static uint64_t total,calls,failure,bad;
uint64_t SYSV shell_log(const uint8_t*p,uint64_t n){calls++;if(n>4096||!n||n>sizeof(actual)-total){bad++;return 99;}if(calls==failure)return 77;memcpy(actual+total,p,(size_t)n);total+=n;return 0;}
void SYSV __dong_panic(uint64_t e,const uint8_t*p,uint64_t n){(void)e;(void)p;(void)n;exit(9);}
int main(void){const unsigned lengths[]={0,1,4095,4096,4097,8192,61440,65535};for(unsigned i=0;i<sizeof(input);i++)input[i]=(uint8_t)(i*73+19);for(unsigned i=0;i<sizeof(lengths)/sizeof(lengths[0]);i++){
 total=calls=failure=bad=0;memset(actual,0xa5,sizeof(actual));st_send(input,lengths[i]);if(bad||total!=lengths[i]||calls!=(lengths[i]+4095)/4096||memcmp(input,actual,lengths[i])){fprintf(stderr,"shell output byte check failed %u\n",lengths[i]);return 1;}}
 for(unsigned fail=1;fail<=4;fail++){total=calls=bad=0;failure=fail;st_send(input,14000);if(bad||calls!=fail||total!=(uint64_t)(fail-1)*4096||memcmp(input,actual,(size_t)total)){fprintf(stderr,"shell output stop check failed %u\n",fail);return 1;}}
 puts("shell output actual text checks passed 12 cases");return 0;}
''')
  records=[]
  for mode in ('debug','release'):
   d=out/mode;d.mkdir();compiled=compile_file(out/'probe.dg',roots=[out],mode=mode);asm=d/'probe.asm';asm.write_text(compiled.assembly);nasm,gcc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and gcc)
   def run(argv,label):
    r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(command=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');self.assertEqual(0,r.returncode,r.stdout+r.stderr);return r
   for fmt in ('elf64','win64'):run([nasm,'-f',fmt,*nasm_flags(nasm),'-o',str(d/(fmt+'.o')),str(asm)],'assemble-'+fmt)
   exe=d/('probe.exe' if os.name=='nt' else 'probe');flags=[] if os.name=='nt' else ['-no-pie'];run([gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*flags,str(csource),str(d/(('win64' if os.name=='nt' else 'elf64')+'.o')),'-o',str(exe)],'link');r=run([str(exe)],'native');self.assertIn('shell output actual text checks passed',r.stdout);records.append(dict(mode=mode,cases=12,actual_function_sha256=hashlib.sha256(body.encode()).hexdigest()))
  self.assertEqual(before,hashlib.sha256(source.read_bytes()).hexdigest());(out/'validation-summary.json').write_text(json.dumps(dict(source_sha256=before,source_unchanged=True,records=records,actual_guest=False),indent=2)+'\n')
