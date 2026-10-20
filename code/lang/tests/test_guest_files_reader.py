"""Real Dong files client + bounded loader, with an observed syscall transport."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = '''module probe;
import lib.compiler_source as c;
import lib.files as f;
import bootstrap.guest_source_reader as r;
export("load_source") unsafe fn load(s:*f.Session,token:u64,scratch:*u8,sn:usize,out:*u8,on:usize,result:*r.Result)u64{unsafe{
 return c.load(s,token,slice_from_raw_parts(scratch,sn),slice_from_raw_parts(out,on),result);
}}
'''
HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct { U endpoint,channel,root,rights,request[8],response[8]; } Session;
typedef struct { U status,size,phase,code; } Result;
extern U ABI load_source(Session*,U,void*,U,void*,U,Result*);
static unsigned char channel_backing[73728], scratch[131073], out[131072], saved[131072];
static unsigned char *channel;
static U length,chunk,calls,expected_offset,fail_at,oversize_at,bad_version_at;
static void check(int ok,const char*why){if(!ok){fprintf(stderr,"FAIL %s\n",why);exit(90);}}
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*p,U n){
 (void)k;(void)l;(void)p;(void)n;fputs("unexpected panic\n",stderr);exit(91);
}
U ABI svc_receive(U a,void*b,U*c){(void)a;(void)b;(void)c;abort();}
U ABI svc_reply_wait(U a,U b,const void*c,void*d,U*e){(void)a;(void)b;(void)c;(void)d;(void)e;abort();}
void ABI svc_fence(void){}
U ABI svc_call(U number,U endpoint,U request,U response,U d,U e,U f){
 (void)d;(void)e;(void)f;
 check(number==0x22 && endpoint==77,"only file IPC");
 U*q=(U*)(uintptr_t)request,*r=(U*)(uintptr_t)response;
 check(q[0]==0x206 && q[1]==0x100000101ULL,"H_READ and borrowed token");
 check(q[2]==expected_offset && q[3]>0 && q[3]<=61440,"offset/count");
 check(q[4]==0 && q[5]==0 && q[6]==3 && q[7]==0,"request fields");
 ++calls;memset(r,0,64);r[5]=3;
 if(calls==fail_at){r[0]=0xdead;return 0;}
 if(calls==bad_version_at){r[5]=2;return 0;}
 if(calls==oversize_at){r[1]=q[3]+1;return 0;}
 U n=length-expected_offset;if(n>q[3])n=q[3];if(n>chunk)n=chunk;
 for(U i=0;i<n;i++)channel[4096+i]=(unsigned char)((expected_offset+i)*17+3);
 r[1]=n;expected_offset+=n;return 0;
}
static void run(U size,U cap,U step,U fail,U over,U version,U status,U phase,U code){
 length=size;chunk=step;calls=expected_offset=0;fail_at=fail;oversize_at=over;bad_version_at=version;
 memset(out,0xa5,sizeof out);memcpy(saved,out,sizeof out);memset(scratch,0xa5,sizeof scratch);
 Session s={0};s.endpoint=77;s.channel=(U)(uintptr_t)channel;Result r={99,98,97,96};
 U got=load_source(&s,0x100000101ULL,scratch,cap+1,out,cap,&r);
 check(got==status && r.status==status && r.phase==phase && r.code==code,"result");
 check(calls>0,"calls observed");
 if(status==0){
  check(r.size==size,"confirmed size");
  for(U i=0;i<size;i++)check(out[i]==(unsigned char)(i*17+3),"source bytes");
  check(!memcmp(out+size,saved+size,sizeof out-size),"output tail");
 }else check(!memcmp(out,saved,sizeof out),"failure publication");
}
static void preflight(void){
 for(unsigned i=0;i<9;i++){
  memset(out,0xa5,sizeof out);memcpy(saved,out,sizeof out);calls=0;
  Session s={0};s.endpoint=77;s.channel=(U)(uintptr_t)channel;Session old=s;
  Result r={99,98,97,96},oldr=r;Session*sp=&s;void*sc=scratch,*op=out;Result*rp=&r;U token=0x100000101ULL,sn=65,on=64;
  switch(i){
   case 0:sp=NULL;break;case 1:token=0;break;case 2:s.channel++;break;
   case 3:op=channel+60000;break;case 4:sc=&s;sn=sizeof s;on=1;break;
   case 5:rp=(Result*)(out+32);break;case 6:sn=on;break;
   case 7:sc=out;break;case 8:s.channel=(U)(uintptr_t)&s&~4095ULL;break;
  }
  old=s;
  U got=load_source(sp,token,sc,sn,op,on,rp);
  check(got==1 && calls==0,"invalid before IPC");
  check(!memcmp(&s,&old,sizeof s)&&!memcmp(&r,&oldr,sizeof r)&&!memcmp(out,saved,sizeof out),"invalid atomicity");
 }
}
int main(void){
 channel=(unsigned char*)(((uintptr_t)channel_backing+4095)&~(uintptr_t)4095);
 preflight();
 run(0,0,1,0,0,0,0,0,0);
 run(17,64,3,0,0,0,0,0,0);
 run(64,64,9,0,0,0,0,0,0);
 run(131072,131072,61440,0,0,0,0,0,0);
 run(65,64,9,0,0,0,2,3,0);
 run(17,64,3,2,0,0,3,2,0xdead);
 run(64,64,64,2,0,0,3,3,0xdead);
 run(17,64,3,0,1,0,3,2,0x05130001);
 run(131072,131072,61440,0,1,0,3,2,0x05130001);
 run(64,64,64,0,2,0,3,3,0x05130001);
 run(17,64,3,0,0,1,3,2,0x05080003);
 puts("11 semantic cases, 9 preflights passed");return 0;
}
'''


class GuestFilesReaderTests(unittest.TestCase):
    def test_real_files_client(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'NASM/GCC required; no skipped acceptance')
        work = ROOT / 'build/test/guest-files-reader' / ('run-' + uuid.uuid4().hex[:12])
        work.mkdir(parents=True)
        wrapper = work / 'probe.dg'
        wrapper.write_text(WRAPPER, encoding='utf-8')
        harness = work / 'probe.c'
        harness.write_text(HARNESS, encoding='utf-8')
        inputs = [p for base in ('services/lib', 'services/fs', 'lang/bootstrap', 'lang/dongc')
                  for p in (ROOT / base).rglob('*') if p.suffix in ('.dg', '.py')]
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        records = []
        snapshot = work / 'source'
        # A private closure prevents test mutation from touching production.
        for name in ('services/lib/compiler_source.dg', 'services/lib/files.dg',
                     'services/lib/sys.dg', 'services/lib/abi.dg',
                     'services/fs/protocol.dg', 'services/fs/handles.dg',
                     'lang/bootstrap/guest_source_reader.dg'):
            path = Path(name)
            target = snapshot / Path(*path.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())
        production = (snapshot/'lib/compiler_source.dg').read_text(encoding='utf-8')
        variants = [('good', production),
                    ('bad-length', production.replace('if n>count as u64{return PROTOCOL;}',
                                                       'if false{return PROTOCOL;}')),
                    ('bad-error', production.replace('if status!=0{return status;}',
                                                      'if status!=0{*moved=0;return 0;}'))]
        for mode in ('debug', 'release'):
            for label, source in variants:
                (snapshot/'lib/compiler_source.dg').write_text(source, encoding='utf-8')
                compiled = compile_file(wrapper, roots=[snapshot, work], mode=mode)
                name = mode + '-' + label
                asm = work / (name + '.asm')
                asm.write_text(compiled.assembly, encoding='utf-8')
                obj = work / (name + '.o')
                exe = work / (name + ('.exe' if os.name == 'nt' else ''))
                native = 'win64' if os.name == 'nt' else 'elf64'
                commands = []
                for fmt in ('elf64', 'win64'):
                    target = obj if fmt == native else work / (name + '.' + fmt + '.o')
                    commands.append([nasm, '-f', fmt, *nasm_flags(nasm), '-o', target, asm])
                commands += [[cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', harness, obj, '-o', exe]]
                for i, command in enumerate(commands + [[exe]]):
                    run = subprocess.run(list(map(str, command)), capture_output=True, timeout=120)
                    (work / f'{name}-{i}.stdout').write_bytes(run.stdout)
                    (work / f'{name}-{i}.stderr').write_bytes(run.stderr)
                    expected = 90 if i == len(commands) and label != 'good' else 0
                    self.assertEqual(run.returncode, expected, run.stderr.decode(errors='replace'))
                    if expected:
                        self.assertIn(b'FAIL result', run.stderr)
                    records.append(dict(mode=mode, variant=label, command=list(map(str, command)),
                                        returncode=run.returncode, expected_exit=expected))
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
        artifacts = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in work.rglob('*') if p.is_file()}
        (work/'summary.json').write_text(json.dumps(dict(records=records, inputs=before, artifacts=artifacts,
            source_stable=True, guest_executed=False, full_L3_accepted=False), indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
