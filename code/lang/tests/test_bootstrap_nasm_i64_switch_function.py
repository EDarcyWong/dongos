"""D25: actual Dong whole i64 switch; independent association/text oracle and native SysV ABI observations."""
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

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
SOURCE=ROOT/'lang/bootstrap/nasm_i64_switch_function.dg'
DOC=SOURCE.with_suffix('.md')
DEPENDENCIES=[ROOT/'lang/bootstrap'/(n+'.dg') for n in (
    'nasm_symbol','decimal_integer','nasm_sysv_function_entry','nasm_function_frame',
    'nasm_sysv_incoming_args','sysv_integer_args','nasm_memory_operand',
    'nasm_integer_memory_load','nasm_integer_load','nasm_integer_memory_store',
    'nasm_block_emit','nasm_switch_dispatch','switch_cases','nasm_sysv_function_exit',
    'nasm_sysv_return_values','sysv_return_plan')]
OK,INVALID,CAPACITY=0,1,2
MAX=(1<<64)-1
TOP=1<<63
MIN=-TOP
PREFLIGHTS=43
WRAPPER='''module probe.i64switch_export;
import bootstrap.nasm_i64_switch_function as f;
export("dong_i64switch_emit") pub unsafe fn emit(m:*const u8,mn:usize,i:*const u8,inn:usize,
 arms:*const f.Arm,an:usize,default_block:u64,default_result:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return f.emit(slice_from_raw_parts(m,mn),slice_from_raw_parts(i,inn),slice_from_raw_parts(arms,an),
 default_block,default_result,slice_from_raw_parts(out,no),written);
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
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct{int64_t value;uint64_t block,result;}Arm;
_Static_assert(sizeof(Arm)==24,"Arm layout");
_Static_assert(_Alignof(Arm)==8,"Arm alignment");
extern uint64_t ABI dong_i64switch_emit(const uint8_t*,uint64_t,const uint8_t*,uint64_t,
 const Arm*,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void rd(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t*ro_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static int ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;return VirtualProtect(p,n,PAGE_READONLY,&old)!=0;
#else
 return mprotect(p,n,PROT_READ)==0;
#endif
}
static int ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;return VirtualFree(p,0,MEM_RELEASE)!=0;
#else
 return munmap(p,n)==0;
#endif
}
#define FAKE(T,x) ((T)(uintptr_t)(x))
/* Input-layout reachability review (all offsets in the same accessible arena):
   m[64,160), item[192,288), 17 initialized Arm objects[512,920),
   out[4096,12288), written[24576,24584): baseline regions are disjoint.
   Each iteration resets legal names, three distinct values/blocks and a distinct
   default; it changes only the named target, then snapshots the full arena.
   0..8: NULL/alignment/endpoints, with other descriptors valid. written endpoint
   case2 uses aligned MAX-7 and legal empty out, so a missing endpoint check can
   return CAPACITY safely rather than dereference the fake written pointer.
   9..11: nonempty Arm NULL/endpoint/alignment, legal count3 (case10 count1).
   12: count*24 overflow, deliberately before any Arm read; a count overflowing
   multiplication necessarily also exceeds16 (not an independent legal count).
   13 and37: count17 fits all 17 initialized objects; only the semantic limit fails.
   14..18,38..42: exactly the designated NONE/duplicate/default collision fails;
   empty out in38..42 is legal, proving INVALID precedes CAPACITY.
   19..26: only written alias changes, including unused out tail and final
   Arm.result; names length64 still fit their initialized96-byte regions.
   27..29: out touches only the final input byte, cap8 fits accessible arena.
   30..32: otherwise valid complete input objects moved wholly into unused out
   tail; case32 copies all72 Arm bytes at aligned offset12096 before snapshot.
   33..36: only name length fails (0 or65), initialized backing extent remains96.
   Arm input alignment uses malloc+32 or page-aligned readonly base, plus an
   8-aligned offset; names intentionally may overlap each other or Arm bytes. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[32768],saved[32768];unsigned failed=0;
 uint8_t*m=arena+64,*it=arena+192,*o=arena+4096;Arm*a=(Arm*)(arena+512);
 uint64_t*w=(uint64_t*)(arena+24576);
 for(unsigned k=0;k<43;k++){
  memset(arena,0xa5,sizeof(arena));memset(m,'a',96);memset(it,'b',96);
  for(unsigned j=0;j<17;j++){a[j].value=(int64_t)(7+j*101);a[j].block=100+j*37;a[j].result=0xcafe0000+j;}
  const uint8_t*pm=m,*pi=it;const Arm*pa=a;uint64_t lm=4,li=4,an=3,db=3001,dr=0x12345678,cap=8192;
  uint8_t*po=o;uint64_t*pw=w;
  switch(k){
   case 0:pw=NULL;break;
   case 1:pw=(uint64_t*)(arena+24577);break;
   case 2:pw=FAKE(uint64_t*,UINT64_MAX-7);po=NULL;cap=0;break;
   case 3:po=FAKE(uint8_t*,UINT64_MAX-4095);break;
   case 4:po=NULL;break;
   case 5:pm=NULL;break;case 6:pi=NULL;break;
   case 7:pm=FAKE(const uint8_t*,UINT64_MAX-3);lm=8;break;
   case 8:pi=FAKE(const uint8_t*,UINT64_MAX-1);break;
   case 9:pa=NULL;break;
   case 10:pa=FAKE(const Arm*,UINT64_MAX-7);an=1;break;
   case 11:pa=(const Arm*)((uint8_t*)a+1);break;
   case 12:an=UINT64_MAX/24+1;po=NULL;cap=0;break;
   case 13:an=17;break;
   case 14:db=UINT64_MAX;break;
   case 15:a[2].block=UINT64_MAX;break;
   case 16:a[2].value=a[0].value;break; /* nonadjacent duplicate */
   case 17:a[2].block=a[0].block;break;
   case 18:db=a[2].block;break;
   case 19:pw=(uint64_t*)o;break;
   case 20:pw=(uint64_t*)(o+8184);break;
   case 21:lm=64;pw=(uint64_t*)m;break;
   case 22:lm=64;pw=(uint64_t*)(m+56);break;
   case 23:li=64;pw=(uint64_t*)it;break;
   case 24:li=64;pw=(uint64_t*)(it+56);break;
   case 25:pw=(uint64_t*)a;break;
   case 26:pw=(uint64_t*)((uint8_t*)a+64);break; /* final Arm.result */
   case 27:lm=64;po=m+63;cap=8;break;
   case 28:li=64;po=it+63;cap=8;break;
   case 29:po=(uint8_t*)a+71;cap=8;break; /* last byte of full arms */
   case 30:pm=o+8000;lm=64;break;
   case 31:pi=o+8000;li=64;break;
   case 32:memcpy(o+8000,a,72);pa=(Arm*)(o+8000);break;
   case 33:lm=0;break;case 34:li=0;break;
   case 35:lm=65;break;case 36:li=65;break;
   case 37:an=17;po=NULL;cap=0;break;
   case 38:a[2].value=a[0].value;po=NULL;cap=0;break;
   case 39:a[2].block=a[0].block;po=NULL;cap=0;break;
   case 40:db=a[2].block;po=NULL;cap=0;break;
   case 41:a[1].block=UINT64_MAX;po=NULL;cap=0;break;
   default:db=UINT64_MAX;po=NULL;cap=0;break;
  }
  memcpy(saved,arena,sizeof(arena));
  uint64_t st=dong_i64switch_emit(pm,lm,pi,li,pa,an,db,dr,po,cap,pw);
  int same=!memcmp(saved,arena,sizeof(arena));
  if(st!=1||!same){fprintf(stderr,"invalid preflight %u status %u unchanged %d\n",k,(unsigned)st,same);failed++;}
 }
 if(failed){exit(93);}
 return 43;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t pre=invalid(),count;rd(&count,8);wr(&pre,8);
 while(count--){
  /* pool,moff,ml,ioff,il,armoff,an,default_block,default_result,flags,capacity */
  uint64_t h[11];rd(h,sizeof(h));uint64_t pool=h[0],flags=h[9],cap=h[10];
  if(pool>4096||cap>16384||h[1]>pool||h[2]>pool-h[1]||h[3]>pool||h[4]>pool-h[3]||
   h[5]>pool||h[6]>17||24*h[6]>pool-h[5]||(h[5]&7))exit(94);
  uint8_t*in=malloc(pool+64),*copy=malloc(pool+1),*out=malloc(cap+64);
  static _Alignas(8) uint64_t meta[3];if(!in||!copy||!out)exit(95);
  memset(in,0xa5,pool+64);rd(in+32,pool);memcpy(copy,in+32,pool);
  uint8_t*base=in+32,*page=NULL;uint64_t pages=16384,protected_ok=1;
  if(flags&1){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,pool);protected_ok=ro_protect(page,pages);if(!protected_ok)exit(97);base=page;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*w=meta+1;
  const Arm*a=(flags&2)?NULL:(const Arm*)(base+h[5]);
  uint64_t st=dong_i64switch_emit(base+h[1],h[2],base+h[3],h[4],a,h[6],h[7],h[8],cap?out+32:NULL,cap,w);
  uint64_t valid=protected_ok&&!memcmp(copy,base,pool)&&filled(in,32)&&filled(in+32+pool,32)&&
    filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(w,8);
  else valid=valid&&*w<=cap&&filled(out+32+*w,cap-*w);
  uint64_t response[4]={st,valid,st?0:*w,protected_ok};wr(response,32);wr(out+32,response[2]);
  if(page&&!ro_free(page,pages))exit(98);
  free(in);free(copy);free(out);
 }return 0;
}
'''
NATIVE_MAIN=r'''
#include <stdint.h>
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
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 static uint64_t io[STATE+2];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  memset(io,0,sizeof(io));io[0]=io[STATE+1]=0xa5a5a5a5a5a5a5a5ull;table[i](io+1);
  if(io[0]!=0xa5a5a5a5a5a5a5a5ull||io[STATE+1]!=0xa5a5a5a5a5a5a5a5ull)return 96;
  if(fwrite(io+1,8,STATE,stdout)!=STATE)return 92;
 }return 0;
}
'''
RAX,RSP_BEFORE,RSP_AFTER,RBX_BEFORE,RBX_AFTER,RBP_AFTER,R12_AFTER,CANARY_AFTER,ALIGN,STATE=0,1,2,3,4,5,6,10,11,12
CALLER={'rbx':0x0bbb0bbb0bbb0bbb,'rbp':0x0b0b0b0b0b0b0b0b,'r12':0x1212121212121212,
        'r13':0x1313131313131313,'r14':0x1414141414141414,'r15':0x1515151515151515}
CANARY=0x5ca1ab1e0ddba11c

def symbol(module,item):return '__dong_m'+module.hex()+'_n'+item.hex()

def expected_text(module,item,arms,default_block,default_result):
    """Signed-sorted dispatch; original-input-order blocks and associated full u64 results."""
    lines=[symbol(module,item)+':','push rbp','mov rbp, rsp','sub rsp, 16',
           'mov qword [rbp - 8], rdi','mov rdi, qword [rbp - 8]']
    for value,block,result in sorted(arms,key=lambda a:a[0]):
        lines+=['mov rax, %d'%value,'cmp rdi, rax','je __dong_b%d'%block]
    lines+=['jmp __dong_b%d'%default_block]
    for value,block,result in [*arms,(0,default_block,default_result)]:
        lines+=['__dong_b%d:'%block,'mov rax, %d'%result,'mov qword [rbp - 16], rax',
                'mov rax, qword [rbp - 16]','add rsp, 16','pop rbp','ret']
    return ('\n'.join(lines)+'\n').encode('ascii')

def interpret(function,selector):return dict((v,r) for v,b,r in function[2]).get(selector,function[4])

# Nontrivial deliberately unordered values and independently shuffled blocks/results.
VALUES=[7,MIN,1,0x100000001,-9,TOP-1,-1,0,-0x100000001,0x123456789abcdef,
        -0x123456789abcdef,0x7000000000000001,-0x7000000000000001,0x200000003,-17,42]
RESULTS=[MAX,0xdead000000000001,0xdead000000000002,0xdead000000000003,TOP,
         0xdead000000000005,0xdead000000000006,0xdead000000000007,0xdead000000000008,
         0xdead000000000009,0xdead00000000000a,0xdead00000000000b,0xdead00000000000c,
         0xdead00000000000d,0xdead00000000000e,0xdead00000000000f]
ARMS=tuple((v,MAX-2-((k*7)%16),RESULTS[k]) for k,v in enumerate(VALUES))
MAIN=(b'\xff'*64,bytes(range(64)),ARMS,MAX-1,0xc0dec0dec0dec0de)
EMPTY=(b'e',b'z',(),0,0x1111222233334444)
SINGLE=(b's',b'o',((-0x1234567800000001,9876543210123456789,0x9988776655443322),),
        12345678909876543210,0x778899aabbccddee)
FUNCTIONS=[MAIN,EMPTY,SINGLE]
VECTORS=[(MAIN,v) for v in VALUES]+[(MAIN,99),(EMPTY,MIN),(EMPTY,TOP-1),
          (SINGLE,SINGLE[2][0][0]),(SINGLE,0)]
assert len(VECTORS)==21


class NasmI64SwitchFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('D25 requires native NASM/GCC')
        cls.inputs=cls.digests();cls.records=[];cls.native='win64' if os.name=='nt' else 'elf64'
        cls.work=ROOT/'build/test/bootstrap-nasm-i64-switch-function'/('run-'+uuid.uuid4().hex);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8')
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @staticmethod
    def digests():
        return {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE,DOC,Path(__file__),*DEPENDENCIES]}

    @classmethod
    def tearDownClass(cls):
        after=cls.digests()
        artifacts={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in cls.work.rglob('*') if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,source_sha256_after=after,
          stable=after==cls.inputs,artifact_sha256=artifacts,records=cls.records,
          primary_vectors_per_mode=len(VECTORS),formats=['elf64','win64'],
          COFF_is_not_Win64_ABI=True,OS_VM_built=False,integrated=False),indent=2)+'\n',encoding='utf-8')
        if after!=cls.inputs:raise AssertionError('source/doc/test/dependency SHA256 changed')

    @classmethod
    def command(cls,cmd,name):
        result=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=180)
        (cls.work/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise AssertionError((name,result.returncode,result.stdout,result.stderr))

    @classmethod
    def build_all(cls,name,text):
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_i64_switch_function.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        wrapper=root/'probe/i64switch_export.dg';wrapper.write_text(WRAPPER,encoding='utf-8')
        exes={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;assembly=compile_file(wrapper,roots=[root],mode=mode).assembly
            asm=cls.work/(tag+'.asm');asm.write_text(assembly,encoding='utf-8')
            for fmt in ('elf64','win64'):
                cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',cls.work/(tag+'.'+fmt+'.o'),asm],tag+'-'+fmt)
            exe=cls.work/(tag+('.exe' if os.name=='nt' else ''))
            cls.command([cls.cc,'-std=c11','-D_GNU_SOURCE','-O2','-Wall','-Wextra','-Werror',
                cls.work/'probe.c',cls.work/(tag+'.'+cls.native+'.o'),'-o',exe],tag+'-link');exes[mode]=exe
        return exes

    @staticmethod
    def case(module,item,arms,db,dr,cap,status=OK,flags=1):
        pool=module+b'\xa5'*16+item;io=len(module)+16
        pool+=b'\xa5'*((-len(pool))%8);ao=len(pool)
        pool+=b''.join(struct.pack('<qQQ',*a) for a in arms)+b'\xa5'*16
        return (pool,0,len(module),io,len(item),ao,len(arms),db,dr,flags,cap,status)

    def emit(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:payload+=struct.pack('<11Q',len(c[0]),*c[1:11])+c[0]
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,(label,run.stderr))
        self.assertGreaterEqual(len(run.stdout),8);self.assertEqual(struct.unpack_from('<Q',run.stdout)[0],PREFLIGHTS)
        offset=8;texts=[]
        for k,c in enumerate(cases):
            st,valid,n,protected=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            text=run.stdout[offset:offset+n];offset+=n
            self.assertEqual(protected,1,(label,k,'readonly protection'))
            self.assertEqual(valid,1,(label,k,'guard/atomicity'))
            self.assertEqual(st,c[11],(label,k,'status'))
            self.assertEqual(len(text),n,(label,k,'written length'))
            texts.append(text if st==OK else None)
        self.assertEqual(offset,len(run.stdout));return texts

    def generate(self,exe,functions,label,exact=True):
        texts=self.emit(exe,[self.case(*f,8192) for f in functions],label)
        if exact:
            for f,text in zip(functions,texts):self.assertEqual(text,expected_text(*f),(label,'exact text'))
        return texts

    def native_run(self,texts,functions,vectors,label):
        # A single emitted function definition can be called by 16 distinct selector
        # stubs. Do not duplicate block/function labels for repeated selectors.
        definitions={}
        for f,text in zip(functions,texts):
            key=symbol(*f[:2])
            if key in definitions:self.assertEqual(definitions[key],text)
            definitions[key]=text
        asm=['bits 64','section .data','align 8','observation: dq 0','host_anchor: dq 0','parked_rax: dq 0','section .text']
        for k,(f,selector) in enumerate(vectors):
            asm+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15',
              'sub rsp, 8','mov [rel observation], rdi','mov [rel host_anchor], rsp','mov r11, rdi',
              'mov rax, 0x%x'%CANARY,'mov [rsp], rax','mov [r11+%d], rsp'%(8*RSP_BEFORE),
              'mov rax, rsp','and rax, 15','mov [r11+%d], rax'%(8*ALIGN),
              'mov rax, 0x%x'%CALLER['rbx'],'mov [r11+%d], rax'%(8*RBX_BEFORE)]
            asm+=['mov %s, 0x%x'%(r,v) for r,v in CALLER.items()]
            asm+=['mov rdi, 0x%x'%(selector&MAX),'call '+symbol(*f[:2]),'mov [rel parked_rax], rax',
              'mov rax, [rel observation]','mov [rax+%d], rsp'%(8*RSP_AFTER),'mov [rax+%d], rbx'%(8*RBX_AFTER),
              'mov [rax+%d], rbp'%(8*RBP_AFTER)]
            asm+=['mov [rax+%d], r%d'%(8*(R12_AFTER+j),12+j) for j in range(4)]
            asm+=['mov rcx, [rel parked_rax]','mov [rax], rcx','mov rcx, [rel host_anchor]','mov rcx, [rcx]',
              'mov [rax+%d], rcx'%(8*CANARY_AFTER),'mov rsp, [rel host_anchor]','add rsp, 8',
              'pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
        asm += [text.decode('ascii') for text in definitions.values()]
        asmfile=self.work/(label+'.stubs.asm');asmfile.write_text('\n'.join(asm)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),asmfile],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','#define STATE %d\n'%STATE+'\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(vectors))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(vectors))))
        cf=self.work/(label+'.native.c');cf.write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe' if os.name=='nt' else ''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cf,
          self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        run=subprocess.run([str(exe)],capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout);(self.work/(label+'.native.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,(label,'normal native termination',run.stderr))
        self.assertEqual(len(run.stdout),8*STATE*len(vectors))
        observations=[struct.unpack_from('<%dQ'%STATE,run.stdout,8*STATE*k) for k in range(len(vectors))]
        self.records.append(dict(native=label,normal_exit=True,observations=observations,
           selectors=[s for f,s in vectors],expected_rax=[interpret(f,s) for f,s in vectors],function_definitions=len(definitions)))
        # Check ALL returned ABI observations before the first numerical assertion.
        for k,got in enumerate(observations):
            self.assertEqual(got[ALIGN],0,(label,k,'caller alignment'))
            self.assertEqual(got[RSP_AFTER],got[RSP_BEFORE],(label,k,'balanced rsp'))
            self.assertEqual(got[RBX_BEFORE],CALLER['rbx'],(label,k,'planted rbx'))
            self.assertEqual(got[RBX_AFTER],CALLER['rbx'],(label,k,'callee-saved rbx'))
            self.assertEqual((got[RBP_AFTER],*got[R12_AFTER:R12_AFTER+4]),tuple(v for r,v in CALLER.items() if r!='rbx'),
                (label,k,'callee-saved rbp/r12-r15'))
            self.assertEqual(got[CANARY_AFTER],CANARY,(label,k,'stack guard'))
        for k,(got,(f,s)) in enumerate(zip(observations,vectors)):
            self.assertEqual(got[RAX],interpret(f,s),(label,k,'native rax'))

    def test_exact_text_capacity_invalid_readonly(self):
        cases=[]
        for f in FUNCTIONS:
            need=len(expected_text(*f))
            for cap,st in ((need,OK),(need+37,OK),(need-1,CAPACITY),(0,CAPACITY)):
                cases.append(self.case(*f,cap,st))
        bads=[(b'',*MAIN[1:]),(MAIN[0],b'',*MAIN[2:]),(b'x'*65,*MAIN[1:]),
              (MAIN[0],b'y'*65,*MAIN[2:]),(*MAIN[:2],(*ARMS,(99,123456,789)),*MAIN[3:])]
        dupvalue=list(ARMS);dupvalue[-1]=(dupvalue[0][0],*dupvalue[-1][1:]);bads.append((*MAIN[:2],tuple(dupvalue),*MAIN[3:]))
        dupblock=list(ARMS);dupblock[-1]=(dupblock[-1][0],dupblock[0][1],dupblock[-1][2]);bads.append((*MAIN[:2],tuple(dupblock),*MAIN[3:]))
        noneblock=list(ARMS);noneblock[7]=(noneblock[7][0],MAX,noneblock[7][2]);bads.append((*MAIN[:2],tuple(noneblock),*MAIN[3:]))
        bads += [(*MAIN[:3],ARMS[9][1],MAIN[4]),(*MAIN[:3],MAX,MAIN[4])]
        for f in bads:
            cases += [self.case(*f,8192,INVALID),self.case(*f,0,INVALID)]
        # Empty arms accepts both NULL and non-NULL zero-count pointers.
        cases.append(self.case(*EMPTY,8192,OK,3))
        # Read-only inputs may overlap each other (names inside Arm bytes included).
        c=list(self.case(*SINGLE,8192));c[1],c[2],c[3],c[4]=c[5],8,c[5]+8,8;cases.append(tuple(c))
        c=list(self.case(*EMPTY,8192));c[3],c[4]=c[1],c[2];cases.append(tuple(c))
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for c,text in zip(cases,texts):
                if c[11]==OK:
                    arms=tuple(struct.unpack_from('<qQQ',c[0],c[5]+24*k) for k in range(c[6]))
                    self.assertEqual(text,expected_text(c[0][c[1]:c[1]+c[2]],c[0][c[3]:c[3]+c[4]],arms,c[7],c[8]))
                    self.assertLessEqual(len(text),3897)
                    self.assertTrue(all(x==10 or 32<=x<127 for x in text))
                    self.assertNotIn(b'\n\n',text)
                    for token in (b'\x00',b'section',b'global',b'bits',b'extern',b';'):self.assertNotIn(token,text)
        self.records.append(dict(test='exact-text-capacity-invalid-readonly',cases_per_mode=len(cases),preflights_per_process=PREFLIGHTS,passed=True))

    def test_native_call_ret(self):
        self.assertLessEqual(len(VECTORS),24)
        self.assertEqual({len(f[2]) for f in FUNCTIONS},{0,1,16})
        self.assertTrue({MIN,TOP-1,-1,0,1}<={s for f,s in VECTORS})
        self.assertEqual(len(set(RESULTS)),16)
        for v,b,r in ARMS:self.assertNotEqual(v&MAX,r)
        labels=[b for f in FUNCTIONS for v,b,r in f[2]]+[f[3] for f in FUNCTIONS]
        self.assertEqual(len(set(labels)),len(labels))
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,FUNCTIONS,'vectors-'+mode),FUNCTIONS,VECTORS,'native-'+mode)
        self.records.append(dict(test='native-call-ret',vectors_per_mode=len(VECTORS),functions_per_file=len(FUNCTIONS),passed=True))

    def test_real_bad_dong(self):
        source=SOURCE.read_text(encoding='utf-8')
        label='label:arms[i].block as usize'
        result='return_block(arms[i].block,arms[i].result,'
        capacity='if total>out.len{return CAPACITY;}'
        for snippet in (label,result,capacity):self.assertEqual(source.count(snippet),1,snippet)
        mutations=[('bad-case-label',source.replace(label,'label:arms[(i+1)%arms.len].block as usize',1)),
                   ('bad-arm-result',source.replace(result,'return_block(arms[i].block,arms[(i+1)%arms.len].result,',1))]
        # All16 associations are checked, with selectors not equal to their results.
        fixtures=[(MAIN,value) for value in VALUES]
        for name,bad in mutations:
            for mode,exe in self.executables.items():
                self.native_run(self.generate(exe,[MAIN],name+'-good-'+mode),[MAIN],fixtures,name+'-good-'+mode)
            for mode,exe in self.build_all(name,bad).items():
                texts=self.generate(exe,[MAIN],name+'-'+mode,exact=False)
                with self.assertRaisesRegex(AssertionError,'native rax'):
                    self.native_run(texts,[MAIN],fixtures,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,linked=True,normal_native_exit=True,modes=2,
              rejected_by='native rax (all ABI/guard checks passed first)',all16_selectors_run=True))
        # finish_tail's prefix already contains real CR3/C44/CR12/C35 output.
        # Publish exactly min(prefix.len,out.len) safe bytes then CAPACITY; no new
        # scratch, out-of-range access, panic or malformed ret is needed to expose
        # the complete failure-atomicity violation.
        early=('if total>out.len{var badat:usize=0;'
               'while badat<prefix.len&&badat<out.len{'
               'out[badat]=prefix[badat];badat+=1;}return CAPACITY;}')
        short=[self.case(*MAIN,len(expected_text(*MAIN))-1,CAPACITY)]
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,[MAIN],'bad-early-header-good-native-'+mode),[MAIN],fixtures,
                            'bad-early-header-good-native-'+mode)
            self.emit(exe,short,'bad-early-header-good-short-'+mode)
        for mode,exe in self.build_all('bad-early-header',source.replace(capacity,early,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                self.emit(exe,short,'bad-early-header-'+mode)
        self.records.append(dict(test='bad-early-header',compiled=True,linked=True,modes=2,
          rejected_by='guard/atomicity',bad_generated_function_executed=False,
          good_generated_function_executed_first=True))

if __name__=='__main__':unittest.main()
