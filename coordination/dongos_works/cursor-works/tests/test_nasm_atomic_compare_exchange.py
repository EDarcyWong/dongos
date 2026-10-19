"""Actual Dong NASM SC atomic compare-exchange emit via LOCK CMPXCHG (32/64)."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
import uuid

WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS
if not (ROOT/'lang').is_dir() and (WORKS/'project.json').is_file():
    source=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT=(WORKS/source).resolve() if not source.is_absolute() else source
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags as _nasm_flags

def nasm_flags(nasm):
    flags=list(_nasm_flags(nasm))
    if '-w-reloc-rel-dword' not in flags:
        flags.append('-w-reloc-rel-dword')
    return flags

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_atomic_compare_exchange.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_atomic_compare_exchange.md'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
W32,W64=32,64
TEXT32=b'mov eax, esi\nmov r10d, edx\nlock cmpxchg dword [rdi], r10d\n'
TEXT64=b'mov rax, rsi\nmov r10, rdx\nlock cmpxchg qword [rdi], r10\n'
ENC32=b'\x89\xf0\x41\x89\xd2\xf0\x44\x0f\xb1\x17\xc3'
ENC64=b'\x48\x89\xf0\x49\x89\xd2\xf0\x4c\x0f\xb1\x17\xc3'
WRAPPER='''module probe.nasm_atomic_compare_exchange_export;
import bootstrap.nasm_atomic_compare_exchange as m;
export("dong_atomic_cmpxchg_emit") pub unsafe fn emit(
 width:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(width,slice_from_raw_parts(out,no),written);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_atomic_cmpxchg_emit(uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=14;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"mov eax, esi\nmov r10d, edx\nlock cmpxchg dword [rdi], r10d\n",58);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_atomic_cmpxchg_emit(32,o,128,NULL);break;
   case 1:st=dong_atomic_cmpxchg_emit(32,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_atomic_cmpxchg_emit(32,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_atomic_cmpxchg_emit(32,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_atomic_cmpxchg_emit(32,NULL,128,w);break;
   case 5:st=dong_atomic_cmpxchg_emit(32,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_atomic_cmpxchg_emit(32,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_atomic_cmpxchg_emit(32,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_atomic_cmpxchg_emit(32,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_atomic_cmpxchg_emit(0,o,128,w);break;
   case 10:st=dong_atomic_cmpxchg_emit(16,o,128,w);break;
   case 11:st=dong_atomic_cmpxchg_emit(128,o,128,w);break;
   case 12:st=dong_atomic_cmpxchg_emit(0,o,0,w);break;
   default:st=dong_atomic_cmpxchg_emit(7,o,0,w);break;
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){
   fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)st);exit(93);
  }
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[3];read_exact(h,sizeof(h));
  uint64_t width=h[0],cap=h[1],nout=h[2];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_atomic_cmpxchg_emit(width,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''
NATIVE_MAIN=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef void ABI (*stub)(uint64_t*);
%DECLS%
static const stub table[]={%TABLE%};
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  /* in: [0]cell [1]expected [2]desired [3]rcx [4]r8 [5]r9 [6]flags_in
     meta: [7]flags [8]rax [9]rdi [10]rsi [11]rcx [12]rdx [13]r8 [14]r9 [15]r10
     object: [16]lo [17]cell [18]hi ; then expected_rdi */
  uint64_t state[24];read_exact(state,56);
  memset(state+7,0xa5,sizeof(state)-56);
  table[i](state);
  uint64_t expected_rdi=(uint64_t)(uintptr_t)&state[17];
  if(fwrite(state,8,19,stdout)!=19)exit(92);
  if(fwrite(&expected_rdi,8,1,stdout)!=1)exit(92);
 }return 0;
}
'''
CONCURRENT_MAIN=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif
#define ABI __attribute__((sysv_abi))
extern void ABI cas_once(uint64_t*);
extern uint64_t shared_lo_guard,shared_cell,shared_hi_guard;
enum{NTHREADS=4,PER_THREAD=256,TOTAL=NTHREADS*PER_THREAD,MAX_RETRY=1<<20};
static uint64_t olds[TOTAL];
static volatile uint32_t old_cursor;
static int worker_fail;
static unsigned width_bits;
#ifdef _WIN32
static DWORD WINAPI worker(void*arg){
#else
static void* worker(void*arg){
#endif
 (void)arg;
 uint64_t local[PER_THREAD];
 unsigned got=0;uint64_t expected=0;uint64_t retries=0;
 uint64_t mask=width_bits==32?0xffffffffull:0xffffffffffffffffull;
 /* Initial shared_cell is 0 (set before threads). No plain C reads of the cell
    during the concurrent window; expected advances from CAS RAX only. */
 while(got<PER_THREAD){
  if(retries++>MAX_RETRY){worker_fail=1;break;}
  uint64_t state[16];
  uint64_t desired=(expected+1)&mask;
  memset(state,0,sizeof(state));
  state[1]=expected;
  state[2]=desired;
  state[3]=0x1111;state[4]=0x2222;state[5]=0x3333;state[6]=0x202;
  cas_once(state);
  uint64_t flags=state[7],rax=state[8]&mask;
  if((flags&0x40)!=0){
   local[got++]=rax;
   expected=(rax+1)&mask;
   retries=0;
  }else{
   expected=rax;
  }
 }
 if(!worker_fail){
  uint32_t base=(uint32_t)__sync_fetch_and_add((volatile int*)&old_cursor,(int)PER_THREAD);
  if(base+PER_THREAD<=TOTAL)memcpy(olds+base,local,sizeof(local));
  else worker_fail=1;
 }
#ifdef _WIN32
 return 0;
#else
 return 0;
#endif
}
int main(int argc,char**argv){
 if(argc<2)return 90;
 width_bits=(unsigned)atoi(argv[1]);
 shared_lo_guard=0xa5a5a5a5a5a5a5a5ull;
 shared_cell=0;
 shared_hi_guard=0xa5a5a5a5a5a5a5a5ull;
 old_cursor=0;worker_fail=0;
#ifdef _WIN32
 HANDLE th[NTHREADS];
 for(int i=0;i<NTHREADS;i++){
  th[i]=CreateThread(NULL,0,worker,NULL,0,NULL);
  if(!th[i])return 91;
 }
 DWORD wr=WaitForMultipleObjects(NTHREADS,th,TRUE,60000);
 for(int i=0;i<NTHREADS;i++)CloseHandle(th[i]);
 if(wr!=WAIT_OBJECT_0)return 92;
#else
 pthread_t th[NTHREADS];
 for(int i=0;i<NTHREADS;i++)if(pthread_create(&th[i],NULL,worker,NULL))return 91;
 for(int i=0;i<NTHREADS;i++)if(pthread_join(th[i],NULL))return 92;
#endif
 if(worker_fail||old_cursor!=TOTAL)return 93;
 uint64_t mask=width_bits==32?0xffffffffull:0xffffffffffffffffull;
 /* Join-after reads only — concurrent window has ended. */
 if((shared_cell&mask)!=(uint64_t)TOTAL)return 94;
 if(shared_lo_guard!=0xa5a5a5a5a5a5a5a5ull||shared_hi_guard!=0xa5a5a5a5a5a5a5a5ull)return 96;
 uint8_t seen[TOTAL];memset(seen,0,sizeof(seen));
 for(unsigned i=0;i<TOTAL;i++){
  if(olds[i]>=TOTAL||seen[olds[i]])return 95;
  seen[olds[i]]=1;
 }
 printf("ok %u %llu\n",width_bits,(unsigned long long)(shared_cell&mask));
 return 0;
}
'''


def expected(width):
    return TEXT32 if width==W32 else TEXT64


def need_total(width):
    return len(expected(width))


def item(width,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if width not in (W32,W64):status=INVALID
        else:
            need=need_total(width)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(width) if status==OK else 64
    text=expected(width) if status==OK else None
    return dict(width=width,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<3Q',c['width'],c['cap'],c.get('nout',0))


# (width, cell, expected, desired) — both widths together <=24 per mode.
def make_vectors(width):
    mask=(1<<width)-1
    hi_bit=1<<(width-1)
    return [
        (width,0,0,1),                                      # success
        (width,0,1,2),                                      # fail
        (width,mask,mask,0),                                # success all1->0
        (width,5,6,7),                                      # fail
        (width,0x42,0x42,0x42),                             # expected==desired
        (width,0x11111111,0x2222222211111111&NONE,0x33333333),  # expected high32 differ
        (width,0x10,0x10,0xAAAABBBBCCCCCCCC&NONE),          # desired high32 nonzero
        (width,0,0,mask),                                   # 0 -> all1
        (width,mask,mask,hi_bit),                           # all1 -> highbit
        (width,hi_bit,hi_bit,1),                            # highbit success
        (width,hi_bit,0,1),                                 # highbit fail
        (width,0xDEADBEEF,0xDEADBEEFDEADBEEF&NONE,0x55AA55AA),  # high32 differ expected
    ]


VECTORS32=make_vectors(W32)
VECTORS64=make_vectors(W64)
assert len(VECTORS32)+len(VECTORS64)<=24
HIGH_GUARD=0xA5A5A5A5
SIDE_GUARD=0xA5A5A5A5A5A5A5A5


class NasmAtomicCompareExchangeTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_atomic_compare_exchange requires NASM/GCC')
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.work=WORKS/'cursor-works/build/CR25'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_atomic_compare_exchange.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_atomic_compare_exchange_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_atomic_compare_exchange_export.dg',roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==cls.native else cls.work/(name+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],name+'-'+fmt)
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],name+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n',encoding='utf-8')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:payload.extend(pack_case(c))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr.decode('utf-8','replace') if run.stderr else '')
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8;outs=[]
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_format_boundaries_and_capacity(self):
        cases=[]
        for width in (W32,W64):
            need=need_total(width)
            self.assertEqual(need,58 if width==W32 else 56)
            cases+=[item(width),
                    item(width,cap=need),
                    item(width,cap=need+3),
                    item(width,cap=need-1),
                    item(width,cap=0,status=CAPACITY)]
        cases+=[item(0,cap=64,status=INVALID),
                item(16,cap=64,status=INVALID),
                item(8,cap=64,status=INVALID),
                item(128,cap=64,status=INVALID),
                item(NONE,cap=64,status=INVALID),
                item(W32,nout=1,cap=64,status=INVALID),
                item(0,nout=0,cap=0,status=INVALID),
                item(7,nout=0,cap=0,status=INVALID),
                item(128,nout=0,cap=0,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_encoding_native_and_concurrent(self):
        samples=[W32,W64]
        cases=[item(w)for w in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,(width,out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\nglobal t\nt:\n'+out+b'ret\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{width}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{width}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,width,fmt,r.stderr,out))
                    assembled+=1
                self._assert_cmpxchg_encoding(mode,width,out)
        dong_texts={}
        for width,vectors in ((W32,VECTORS32),(W64,VECTORS64)):
            texts={mode:self.run_both([item(width)],f'native-text-{width}')[mode][0]
                   for mode in self.executables}
            dong_texts[width]=texts
            for mode in self.executables:
                self._native_batch(mode,width,texts[mode],vectors)
        for width in (W32,W64):
            for mode in self.executables:
                self._concurrent_cas(mode,width,dong_texts[width][mode])
        total=len(VECTORS32)+len(VECTORS64)
        self.assertLessEqual(total,24,(total,'vectors per mode'))
        self.records.append(dict(test='dong-assemble-encoding-native-concurrent',assemble_samples=len(samples),
                                 assembled=assembled,vectors32=len(VECTORS32),vectors64=len(VECTORS64),
                                 vectors_total=total,encoding_checked=True,concurrent=True,
                                 modes=2,formats=2,passed=True))

    def _assert_cmpxchg_encoding(self,mode,width,text:bytes):
        """Assemble emitted text alone and confirm LOCK + CMPXCHG width bytes."""
        body=b'bits 64\nsection .text\nglobal t\nt:\n'+text+b'ret\n'
        d=self.work/'encode';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{width}.asm';obj=d/f'{mode}-{width}.bin'
        asm.write_bytes(body)
        r=subprocess.run([str(self.nasm),'-f','bin','-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        raw=obj.read_bytes()
        if width==W32:
            self.assertEqual(raw,ENC32,(mode,width,'dword lock cmpxchg encoding',raw.hex()))
        else:
            self.assertEqual(raw,ENC64,(mode,width,'qword lock cmpxchg encoding',raw.hex()))
        self.assertIn(b'\xf0',raw[:len(raw)-1],(mode,width,'LOCK prefix 0xF0 present'))
        ndisasm=shutil.which('ndisasm')
        if ndisasm:
            dump=subprocess.run([ndisasm,'-b','64',str(obj)],capture_output=True,text=True,timeout=30)
            (d/f'{mode}-{width}.ndisasm').write_text(dump.stdout,encoding='utf-8')
            low=dump.stdout.lower()
            self.assertIn('cmpxchg',low,(mode,width,dump.stdout))
            self.assertIn('lock',low,(mode,width,dump.stdout))

    def _native_batch(self,mode,width,text:bytes,vectors):
        stub=['bits 64','section .text']
        for k,(w,cell,exp,des) in enumerate(vectors):
            self.assertEqual(w,width)
            stub+=[
                'global v%d'%k,'v%d:'%k,
                'mov r11, rdi',
                'mov rax, 0xa5a5a5a5a5a5a5a5',
                'mov [r11+128], rax',
                'mov [r11+144], rax',
                'mov rax, [r11+0]',
                'mov [r11+136], rax',
                'lea rdi, [r11+136]',
                'mov rsi, [r11+8]',
                'mov rdx, [r11+16]',
                'mov rcx, [r11+24]',
                'mov r8, [r11+32]','mov r9, [r11+40]',
                'push qword [r11+48]','popfq',
            ]
            stub+=text.decode('ascii').rstrip('\n').split('\n')
            stub+=[
                'pushfq','pop qword [r11+56]',
                'mov [r11+64], rax',
                'mov [r11+120], r10',
                'mov [r11+72], rdi','mov [r11+80], rsi',
                'mov [r11+88], rcx','mov [r11+96], rdx',
                'mov [r11+104], r8','mov [r11+112], r9',
                'ret',
            ]
        label=f'{mode}-w{width}-native'
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),
                          '-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],
                         label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(vectors))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(vectors))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                      self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],
                     label+'-native-link')
        rcx_s,r8_s,r9_s=0x2222222222222222,0x4444444444444444,0x5555555555555555
        flags_in=0x202
        payload=bytearray()
        mask=(1<<width)-1
        for w,cell,exp,des in vectors:
            cell_init=((HIGH_GUARD<<32)|(cell&mask)) if width==W32 else (cell&NONE)
            payload.extend(struct.pack('<7Q',cell_init,exp&NONE,des&NONE,rcx_s,r8_s,r9_s,flags_in))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        stride=20*8
        for k,(w,cell,exp,des) in enumerate(vectors):
            words=list(struct.unpack_from('<20Q',run.stdout,stride*k))
            flags_out,rax_out=words[7],words[8]
            rdi_out,rsi_out=words[9],words[10]
            rcx_out,rdx_out,r8_out,r9_out=words[11],words[12],words[13],words[14]
            r10_out=words[15]
            lo_guard,cell_out,hi_guard=words[16],words[17],words[18]
            expected_rdi=words[19]
            old=cell&mask
            exp_low=exp&mask
            des_low=des&mask
            success=(old==exp_low)
            want_mem=des_low if success else old
            zf=(flags_out&0x40)!=0
            self.assertEqual(rdi_out,expected_rdi,(label,k,'rdi equals target',hex(rdi_out),hex(expected_rdi)))
            self.assertEqual(lo_guard,SIDE_GUARD,(label,k,'lo guard',hex(lo_guard)))
            self.assertEqual(hi_guard,SIDE_GUARD,(label,k,'hi guard',hex(hi_guard)))
            self.assertEqual(zf,success,(label,k,'zf',vectors[k],hex(flags_out)))
            self.assertEqual(cell_out&mask,want_mem,(label,k,'mem',vectors[k],hex(cell_out)))
            if width==W32:
                self.assertEqual((cell_out>>32)&0xFFFFFFFF,HIGH_GUARD,
                                 (label,k,'adjacent high dword guard',hex(cell_out)))
            self.assertEqual(rax_out&mask,old,(label,k,'rax old',vectors[k],hex(rax_out)))
            if width==W32:
                self.assertEqual(rax_out>>32,0,(label,k,'rax zero-extend',hex(rax_out)))
            self.assertEqual(r10_out&mask,des_low,(label,k,'r10 desired',hex(r10_out)))
            if width==W32:
                self.assertEqual(r10_out>>32,0,(label,k,'r10 zero-extend',hex(r10_out)))
            self.assertEqual(rsi_out,exp&NONE,(label,k,'rsi preserved',hex(rsi_out)))
            self.assertEqual(rdx_out,des&NONE,(label,k,'rdx preserved',hex(rdx_out)))
            self.assertEqual(rcx_out,rcx_s,(label,k,'rcx preserved'))
            self.assertEqual(r8_out,r8_s,(label,k,'r8 preserved'))
            self.assertEqual(r9_out,r9_s,(label,k,'r9 preserved'))

    def _concurrent_cas(self,mode,width,text:bytes):
        """4 threads × 256 successful CAS increments; olds permutation of 0..1023."""
        label=f'{mode}-w{width}-concurrent'
        stub=[
            'bits 64','section .data','align 8',
            'global shared_lo_guard','shared_lo_guard: dq 0xa5a5a5a5a5a5a5a5',
            'global shared_cell','shared_cell: dq 0',
            'global shared_hi_guard','shared_hi_guard: dq 0xa5a5a5a5a5a5a5a5',
            'section .text','global cas_once','cas_once:',
            'mov r11, rdi',
            'lea rdi, [rel shared_cell]',
            'mov rsi, [r11+8]',
            'mov rdx, [r11+16]',
            'mov rcx, [r11+24]',
            'mov r8, [r11+32]','mov r9, [r11+40]',
            'push qword [r11+48]','popfq',
        ]
        stub+=text.decode('ascii').rstrip('\n').split('\n')
        stub+=[
            'pushfq','pop qword [r11+56]',
            'mov [r11+64], rax',
            'mov [r11+8], r10',
            'mov [r11+72], rdi','mov [r11+80], rsi',
            'mov [r11+88], rcx','mov [r11+96], rdx',
            'mov [r11+104], r8','mov [r11+48], r9',
            'ret',
        ]
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),
                          '-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],
                         label+'-stubs-'+fmt)
        (self.work/(label+'.concurrent.c')).write_text(CONCURRENT_MAIN,encoding='utf-8')
        exe=self.work/(label+'-concurrent'+('.exe'if os.name=='nt'else''))
        link=[self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
              self.work/(label+'.concurrent.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe]
        if os.name!='nt':
            link.append('-pthread')
        self.command(link,label+'-concurrent-link')
        run=subprocess.run([str(exe),str(width)],capture_output=True,text=True,timeout=120)
        (self.work/(label+'.concurrent.stdout')).write_text(run.stdout,encoding='utf-8')
        (self.work/(label+'.concurrent.stderr')).write_text(run.stderr,encoding='utf-8')
        self.assertEqual(run.returncode,0,(label,'concurrent',run.returncode,run.stdout,run.stderr))
        self.assertIn('ok',run.stdout,(label,run.stdout))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_atomic_compare_exchange.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_atomic_compare_exchange_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def _emit_text_from_exe(self,exe,width):
        c=item(width,cap=64)
        payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stderr)
        st,g,w=struct.unpack_from('<3Q',run.stdout,8)
        text=run.stdout[32:32+64][:w]
        self.assertEqual(st,0);self.assertEqual(g,1)
        return text

    def test_actual_compiled_wrong_sources_are_rejected(self):
        des32_old=' at=copy(buffer,at,"mov r10d, edx\\n");'
        des32_new=' at=copy(buffer,at,"mov r10d, esi\\n");'
        des64_old=' at=copy(buffer,at,"mov r10, rdx\\n");'
        des64_new=' at=copy(buffer,at,"mov r10, rsi\\n");'
        zext_old=' at=copy(buffer,0,"mov eax, esi\\n");'
        zext_new=' at=copy(buffer,0,"mov rax, rsi\\n");'
        early_old=' if at>out.len{return CAPACITY;}'
        early_new=' *written=at;if at>out.len{return CAPACITY;}'
        short=item(W32,cap=5)
        MEM_VEC32=[(W32,0x11,0x11,0x99)]
        MEM_VEC64=[(W64,0x11,0x11,0x99)]
        ZEXT_VEC=[(W32,0x11111111,0x2222222211111111,0x33333333)]
        controls=[
            ('bad-desired32',des32_old,des32_new,'mem',W32,MEM_VEC32),
            ('bad-desired64',des64_old,des64_new,'mem',W64,MEM_VEC64),
            ('bad-zext32',zext_old,zext_new,'rax|zero-extend',W32,ZEXT_VEC),
            ('bad-early-written',early_old,early_new,'atomic',W32,None),
        ]
        for name,old,new,kind,width,vec in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            else:
                for mode,exe in self.executables.items():
                    good_text=self._emit_text_from_exe(exe,width)
                    self.assertEqual(good_text,expected(width),(name,mode,'good text'))
                    self._native_batch(mode+'-good-'+name,width,good_text,vec)
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                else:
                    text=self._emit_text_from_exe(exe,width)
                    self.assertNotEqual(text,expected(width),(name,mode,text))
                    with self.assertRaisesRegex(AssertionError,kind):
                        self._native_batch(mode+'-'+name,width,text,vec)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
