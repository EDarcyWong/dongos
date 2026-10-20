"""D27: actual Dong indexed-memory function, exact text, dual formats and native SysV call/ret.

Only this module and its integrated import closure are staged. Python supplies an
independent text oracle, little-endian/sign-extension and whole-memory oracle.
"""
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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

SOURCE = ROOT / 'lang/bootstrap/nasm_indexed_memory_function.dg'
DOC = SOURCE.with_suffix('.md')
DEPENDENCIES = [ROOT / 'lang/bootstrap' / (n + '.dg') for n in (
    'nasm_symbol', 'decimal_integer', 'nasm_sysv_function_entry',
    'nasm_function_frame', 'nasm_sysv_incoming_args', 'sysv_integer_args',
    'nasm_memory_operand', 'nasm_integer_load', 'nasm_integer_memory_load',
    'nasm_integer_memory_store', 'nasm_block_emit', 'nasm_bounds_guard',
    'nasm_indexed_operand', 'nasm_integer_cast',
    'nasm_sysv_function_exit', 'nasm_sysv_return_values', 'sysv_return_plan')]
OK, INVALID, CAPACITY = 0, 1, 2
MAX = (1 << 64) - 1
TOP = 1 << 63
PREFLIGHTS = 31

WRAPPER = '''module probe.indexed_export;
import bootstrap.nasm_indexed_memory_function as f;
export("dong_indexed_emit") pub unsafe fn emit(m:*const u8,mn:usize,i:*const u8,inn:usize,
 operation:u64,width:u64,signed:bool,error_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return f.emit(slice_from_raw_parts(m,mn),slice_from_raw_parts(i,inn),operation,width,signed,error_block,
  slice_from_raw_parts(out,no),written);
}}
'''
HARNESS = r'''
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
typedef const uint8_t *N;
extern uint64_t ABI dong_indexed_emit(N,uint64_t,N,uint64_t,uint64_t,uint64_t,_Bool,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void rd(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t *ro_alloc(uint64_t n){
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
#define FAKE(x) ((N)(uintptr_t)(x))
/* Reachability layout: names occupy [64,160) and [192,288), out [1024,5120),
   written [6144,6152) in one accessible 8192-byte arena; baseline regions are disjoint.
   Each case resets legal operation0/width32/unsigned/error12 and changes only its
   target, then snapshots after initializing guards. Alias cases deliberately touch
   a full input/out tail; all other descriptors and backing extents remain legal.
   The endpoint-overflow written case uses legal empty out, so omission can safely
   return CAPACITY rather than dereference the forged written pointer. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[8192],saved[8192];unsigned failed=0;
 uint8_t*m=arena+64,*it=arena+192,*o=arena+1024;uint64_t*w=(uint64_t*)(arena+6144);
 for(unsigned k=0;k<31;k++){
  memset(arena,0xa5,sizeof(arena));memset(m,'a',96);memset(it,'b',96);
  N pm=m,pi=it;uint64_t lm=4,li=4,n=0,h=32,b=0,e=12,cap=4096;uint8_t*po=o;uint64_t*pw=w;
  switch(k){
   case 0:pw=NULL;break;
   case 1:pw=(uint64_t*)(arena+6145);break;
   case 2:pw=(uint64_t*)(uintptr_t)(UINT64_MAX-7);po=NULL;cap=0;break;
   case 3:po=(uint8_t*)(uintptr_t)(UINT64_MAX-2047);break;
   case 4:po=NULL;break;
   case 5:pm=NULL;break;case 6:pi=NULL;break;
   case 7:pm=FAKE(UINT64_MAX-3);lm=8;break;
   case 8:pi=FAKE(UINT64_MAX-1);break;
   case 9:pw=(uint64_t*)o;break;
   case 10:pw=(uint64_t*)(o+4088);break;
   case 11:lm=64;pw=(uint64_t*)m;break;
   case 12:lm=64;pw=(uint64_t*)(m+56);break;
   case 13:li=64;pw=(uint64_t*)it;break;
   case 14:li=64;pw=(uint64_t*)(it+56);break;
   case 15:lm=64;po=m+63;cap=8;break;
   case 16:li=64;po=it+63;cap=8;break;
   case 17:pm=o+4000;lm=64;break; /* input entirely in unused out tail */
   case 18:pi=o+4000;li=64;break;
   case 19:n=2;break;case 20:n=UINT64_MAX;break;
   case 21:h=7;break;case 22:h=UINT64_MAX;break;case 23:e=UINT64_MAX;break;
   case 24:h=64;b=1;break;case 25:n=1;b=1;break;case 26:h=0;break;
   case 27:lm=0;break;case 28:li=0;break;
   case 29:lm=65;break;default:li=65;break;
  }
  memcpy(saved,arena,sizeof(arena));
  uint64_t st=dong_indexed_emit(pm,lm,pi,li,n,h,b,e,po,cap,pw);
  int same=!memcmp(saved,arena,sizeof(arena));
  if(st!=1||!same){fprintf(stderr,"invalid preflight %u status %u unchanged %d\n",k,(unsigned)st,same);failed++;}
 }
 if(failed){exit(93);}
 return 31;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t pre=invalid(),count;rd(&count,8);wr(&pre,8);
 while(count--){
  /* pool, module offset/length, item offset/length, operation, width, signed, error block, flags, capacity */
  uint64_t h[11];rd(h,sizeof(h));uint64_t pool=h[0],flags=h[9],cap=h[10];
  if(pool>4096||cap>8192||h[1]>pool||h[2]>pool-h[1]||h[3]>pool||h[4]>pool-h[3])exit(94);
  uint8_t*in=malloc(pool+64),*copy=malloc(pool+1),*out=malloc(cap+64);
  static _Alignas(8) uint64_t meta[3];if(!in||!copy||!out)exit(95);
  memset(in,0xa5,pool+64);rd(in+32,pool);memcpy(copy,in+32,pool);
  uint8_t*base=in+32,*page=NULL;uint64_t protected_ok=1,pages=16384;
  if(flags&1){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,pool);protected_ok=ro_protect(page,pages);if(!protected_ok)exit(97);base=page;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*w=meta+1;
  uint64_t st=dong_indexed_emit(base+h[1],h[2],base+h[3],h[4],h[5],h[6],h[7],h[8],cap?out+32:NULL,cap,w);
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

NATIVE_MAIN = HARNESS[HARNESS.index('#include'):HARNESS.index('#define FAKE')]
NATIVE_MAIN = NATIVE_MAIN[:NATIVE_MAIN.index('typedef const uint8_t *N;')] + NATIVE_MAIN[NATIVE_MAIN.index('static int filled'):]
NATIVE_MAIN=NATIVE_MAIN.replace('static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}','')
NATIVE_MAIN += r"""
typedef void ABI (*stub)(uint64_t*,uint8_t*,uint64_t,uint64_t,uint64_t);
%DECLS%
static const stub table[]={%TABLE%};
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 static uint64_t io[STATE+2];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  uint64_t h[4];uint8_t initial[320];rd(h,sizeof(h));rd(initial,320);
  uint8_t*page=ro_alloc(16384);if(!page)return 95;memcpy(page,initial,320);
  uint64_t protected_ok=1;if(h[3]&1){protected_ok=ro_protect(page,16384);if(!protected_ok)return 97;}
  memset(io,0,sizeof(io));io[0]=io[STATE+1]=0xa5a5a5a5a5a5a5a5ull;
  table[i](io+1,(h[3]&2)?NULL:page+32,h[0],h[1],h[2]);
  if(io[0]!=0xa5a5a5a5a5a5a5a5ull||io[STATE+1]!=0xa5a5a5a5a5a5a5a5ull)return 96;
  wr(&protected_ok,8);wr(io+1,8*STATE);wr(page,320);
  if(!ro_free(page,16384))return 98;
 }return 0;
}
"""
RAX,RDX,RSP_BEFORE,RSP_AFTER,RBX_BEFORE,RBX_AFTER,RBP_AFTER,R12_AFTER,CANARY_AFTER,ALIGN,STATE=0,1,2,3,4,5,6,7,11,12,13
CALLER={'rbx':0x0bbb0bbb0bbb0bbb,'rbp':0x0b0b0b0b0b0b0b0b,'r12':0x1212121212121212,
 'r13':0x1313131313131313,'r14':0x1414141414141414,'r15':0x1515151515151515}
CANARY=0x5ca1ab1e0ddba11c

def symbol(module,item):return '__dong_m'+module.hex()+'_n'+item.hex()
def expected_text(module,item,operation,width,signed,error):
 lines=[symbol(module,item)+':','push rbp','mov rbp, rsp','sub rsp, 48',
 'mov qword [rbp - 8], rdi','mov qword [rbp - 16], rsi','mov qword [rbp - 24], rdx',
 'mov qword [rbp - 32], rcx','mov rax, qword [rbp - 24]','mov rcx, qword [rbp - 16]',
 'cmp rax, rcx','jae __dong_b%d'%error,'mov rdi, qword [rbp - 8]',
 'lea r10, [rdi + rax*%d]'%(width//8)]
 if operation==0:
  lines += [{(8,False):'movzx rax, byte [r10]',(8,True):'movsx rax, byte [r10]',
   (16,False):'movzx rax, word [r10]',(16,True):'movsx rax, word [r10]',
   (32,False):'mov eax, dword [r10]',(32,True):'movsxd rax, dword [r10]',
   (64,False):'mov rax, qword [r10]'}[(width,bool(signed))]]
 else:
  lines += ['mov rax, qword [rbp - 32]', 'mov %s [r10], %s'%({8:'byte',16:'word',32:'dword',64:'qword'}[width],{8:'al',16:'ax',32:'eax',64:'rax'}[width]),
   {8:'movzx rax, al',16:'movzx rax, ax',32:'mov eax, eax',64:'mov rax, rax'}[width]]
 def ret():return ['mov rax, qword [rbp - 40]','mov rdx, qword [rbp - 48]','add rsp, 48','pop rbp','ret']
 lines+=['mov qword [rbp - 40], rax','mov rax, 0','mov qword [rbp - 48], rax']+ret()
 lines+=['__dong_b%d:'%error,'mov rax, 0','mov qword [rbp - 40], rax','mov rax, 1','mov qword [rbp - 48], rax']+ret()
 return ('\n'.join(lines)+'\n').encode('ascii')

FORMS=[(0,w,s) for w in (8,16,32) for s in (False,True)]+[(0,64,False)]+[(1,w,False) for w in (8,16,32,64)]
FUNCTIONS=[(b'm',('f%d'%k).encode(),op,w,s,100+k) for k,(op,w,s) in enumerate(FORMS)]
FUNCTIONS[0]=(b'\xff'*64,bytes(range(64)),*FUNCTIONS[0][2:5],MAX-1)
# Vector: function, logical length, index, value, null base, readonly target.
VECTORS=[(f,4,0 if k%3==0 else 3,0xfedcba9876543281,False,f[2]==0) for k,f in enumerate(FUNCTIONS)]
VECTORS[1]=(FUNCTIONS[1],2,1,0xfedcba9876543281,False,True) # signed byte high bit, last index
VECTORS += [(FUNCTIONS[0],4,0,0,False,True), # LOAD ignores all value bits
 (FUNCTIONS[6],0,0,MAX,True,True),
 (FUNCTIONS[2],2,2,MAX,False,False),(FUNCTIONS[10],2,2,MAX,False,False),
 (FUNCTIONS[3],2,3,TOP,False,True),(FUNCTIONS[7],2,3,TOP,False,False),
 (FUNCTIONS[4],4,TOP,0,False,True),(FUNCTIONS[9],4,MAX,MAX,False,False),
 (FUNCTIONS[5],4,MAX,1,False,True),(FUNCTIONS[10],0,0,MAX,False,False)]
assert len(VECTORS)==21
INITIAL=bytes([0xa5]*32)+bytes(((i*73+0x81)&255) for i in range(256))+bytes([0x5a]*32)
def interpret(v):
 f,length,index,value,null,readonly=v;op,width,signed=f[2:5];memory=bytearray(INITIAL)
 if index>=length:return (0,1),bytes(memory)
 at=32+index*(width//8);n=width//8
 if op==0:result=int.from_bytes(memory[at:at+n],'little',signed=bool(signed))&MAX
 else:
  result=value&((1<<width)-1);memory[at:at+n]=result.to_bytes(n,'little')
 return (result,0),bytes(memory)



class NasmIndexedMemoryFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm','NASM'), tool('gcc','CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('D27 requires native NASM/GCC')
        cls.inputs = cls.digests()
        cls.work = ROOT/'build/test/bootstrap-nasm-indexed-memory-function'/('run-'+uuid.uuid4().hex)
        cls.work.mkdir(parents=True)
        cls.records = []
        cls.native = 'win64' if os.name=='nt' else 'elf64'
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8')
        cls.executables = cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @staticmethod
    def digests():
        return {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [SOURCE,DOC,Path(__file__),*DEPENDENCIES]}

    @classmethod
    def command(cls,cmd,name):
        result = subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=180)
        (cls.work/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:
            raise AssertionError((name,result.returncode,result.stdout,result.stderr))

    @classmethod
    def build_all(cls,name,text):
        root = cls.work/name
        (root/'bootstrap').mkdir(parents=True)
        (root/'probe').mkdir()
        (root/'bootstrap/nasm_indexed_memory_function.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:
            shutil.copyfile(dep,root/'bootstrap'/dep.name)
        wrapper = root/'probe/indexed_export.dg'
        wrapper.write_text(WRAPPER,encoding='utf-8')
        executables = {}
        for mode in ('debug','release'):
            tag = name+'-'+mode
            assembly = compile_file(wrapper,roots=[root],mode=mode).assembly
            asm,obj = cls.work/(tag+'.asm'),cls.work/(tag+'.o')
            asm.write_text(assembly,encoding='utf-8')
            for fmt in ('elf64','win64'):
                output = obj if fmt==cls.native else cls.work/(tag+'.'+fmt+'.o')
                cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],tag+'-'+fmt)
            exe = cls.work/(tag+('.exe' if os.name=='nt' else ''))
            cls.command([cls.cc,'-std=c11','-D_GNU_SOURCE','-O2','-Wall','-Wextra','-Werror',
                         cls.work/'probe.c',obj,'-o',exe],tag+'-link')
            executables[mode] = exe
        return executables

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):
            return
        after = cls.digests()
        artifacts = {p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in cls.work.rglob('*') if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,
            source_sha256_after=after,stable=after==cls.inputs,artifact_sha256=artifacts,
            records=cls.records,primary_vectors_per_mode=len(VECTORS),formats=['elf64','win64'],
            COFF_is_not_Win64_ABI=True,OS_VM_built=False,integrated=False),indent=2)+'\n',encoding='utf-8')
        if after!=cls.inputs:
            raise AssertionError(('source/doc/test/dependency SHA256 changed',cls.inputs,after))

    @staticmethod
    def case(module,item,operation,width,signed,error,cap,status=OK,flags=0):
        pool = module+b'\xa5'*16+item+b'\xa5'*16
        return (pool,0,len(module),len(module)+16,len(item),operation,width,signed,error,flags,cap,status)

    def emit(self,exe,cases,label):
        payload = bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload += struct.pack('<11Q',len(c[0]),*c[1:11])+c[0]
        (self.work/(label+'.input')).write_bytes(payload)
        run = subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout)
        (self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,(label,run.stderr))
        self.assertEqual(struct.unpack_from('<Q',run.stdout)[0],PREFLIGHTS)
        offset,texts = 8,[]
        for k,c in enumerate(cases):
            status,valid,n,protected = struct.unpack_from('<4Q',run.stdout,offset)
            offset += 32
            text = run.stdout[offset:offset+n]
            offset += n
            self.assertEqual(protected,1,(label,k,'readonly protection'))
            self.assertEqual(valid,1,(label,k,'guard/atomicity'))
            self.assertEqual(status,c[11],(label,k,'status'))
            if not status:
                self.assertEqual(n,len(text),(label,k,'exact length'))
            texts.append(text if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def generate(self,exe,vectors,label,exact=True):
        texts = self.emit(exe,[self.case(*v,4096,OK,1) for v in vectors],label)
        if exact:
            for v,text in zip(vectors,texts):
                self.assertEqual(text,expected_text(*v),(label,'exact text'))
        return texts


    def native_run(self,texts,functions,vectors,label):
        definitions={symbol(*f[:2]):text for f,text in zip(functions,texts)}
        asm=['bits 64','section .data','align 8','observation: dq 0','host_anchor: dq 0',
             'parked_rax: dq 0','parked_rdx: dq 0','target: dq 0','count: dq 0','ix: dq 0','val: dq 0','section .text']
        for k,v in enumerate(vectors):
            f=v[0]
            asm+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15',
             'sub rsp, 8','mov [rel observation], rdi','mov [rel target], rsi','mov [rel count], rdx',
             'mov [rel ix], rcx','mov [rel val], r8','mov [rel host_anchor], rsp','mov r11, rdi',
             'mov rax, 0x%x'%CANARY,'mov [rsp], rax','mov [r11+%d], rsp'%(8*RSP_BEFORE),
             'mov rax, rsp','and rax, 15','mov [r11+%d], rax'%(8*ALIGN),
             'mov rax, 0x%x'%CALLER['rbx'],'mov [r11+%d], rax'%(8*RBX_BEFORE)]
            asm+=['mov %s, 0x%x'%(r,value) for r,value in CALLER.items()]
            asm+=['mov rdi, [rel target]','mov rsi, [rel count]','mov rdx, [rel ix]','mov rcx, [rel val]',
             'call '+symbol(*f[:2]),'mov [rel parked_rax], rax','mov [rel parked_rdx], rdx',
             'mov rax, [rel observation]','mov [rax+%d], rsp'%(8*RSP_AFTER),
             'mov [rax+%d], rbx'%(8*RBX_AFTER),'mov [rax+%d], rbp'%(8*RBP_AFTER)]
            asm+=['mov [rax+%d], r%d'%(8*(R12_AFTER+j),12+j) for j in range(4)]
            asm+=['mov rcx, [rel parked_rax]','mov [rax], rcx','mov rcx, [rel parked_rdx]','mov [rax+8], rcx',
             'mov rcx, [rel host_anchor]','mov rcx, [rcx]','mov [rax+%d], rcx'%(8*CANARY_AFTER),
             'mov rsp, [rel host_anchor]','add rsp, 8','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
        asm += [text.decode('ascii') for text in definitions.values()]
        asmfile=self.work/(label+'.stubs.asm');asmfile.write_text('\n'.join(asm)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),asmfile],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','#define STATE %d\n'%STATE+'\n'.join(
            'extern void ABI v%d(uint64_t*,uint8_t*,uint64_t,uint64_t,uint64_t);'%k for k in range(len(vectors))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(vectors))))
        cf=self.work/(label+'.native.c');cf.write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe' if os.name=='nt' else ''))
        self.command([self.cc,'-std=c11','-D_GNU_SOURCE','-O2','-Wall','-Wextra','-Werror',cf,
            self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        payload=b''.join(struct.pack('<4Q',v[1],v[2],v[3],int(v[5])|2*int(v[4]))+INITIAL for v in vectors)
        (self.work/(label+'.native.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout);(self.work/(label+'.native.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,(label,'normal native termination',run.stderr))
        size=8+8*STATE+320;self.assertEqual(len(run.stdout),size*len(vectors))
        observations=[];memories=[]
        for k,v in enumerate(vectors):
            at=k*size;protected,=struct.unpack_from('<Q',run.stdout,at)
            self.assertEqual(protected,1,(label,k,'target readonly protection'))
            got=struct.unpack_from('<%dQ'%STATE,run.stdout,at+8);observations.append(got)
            memories.append(run.stdout[at+8+8*STATE:at+size])
        self.records.append(dict(native=label,normal_exit=True,observations=observations,
            expected_pair=[interpret(v)[0] for v in vectors],memory_sha256=[hashlib.sha256(m).hexdigest() for m in memories]))
        # Every ABI and out-of-target guard observation is checked before semantics.
        for k,(got,memory) in enumerate(zip(observations,memories)):
            self.assertEqual(got[ALIGN],0,(label,k,'caller alignment'))
            self.assertEqual(got[RSP_AFTER],got[RSP_BEFORE],(label,k,'balanced rsp'))
            self.assertEqual(got[RBX_BEFORE],CALLER['rbx'],(label,k,'planted rbx'))
            self.assertEqual(got[RBX_AFTER],CALLER['rbx'],(label,k,'callee-saved rbx'))
            self.assertEqual((got[RBP_AFTER],*got[R12_AFTER:R12_AFTER+4]),tuple(x for r,x in CALLER.items() if r!='rbx'),(label,k,'callee-saved'))
            self.assertEqual(got[CANARY_AFTER],CANARY,(label,k,'stack guard'))
            self.assertEqual(memory[:32],INITIAL[:32],(label,k,'target left guard'))
            self.assertEqual(memory[-32:],INITIAL[-32:],(label,k,'target right guard'))
        for k,(got,memory,v) in enumerate(zip(observations,memories,vectors)):
            pair,expected_memory=interpret(v)
            self.assertEqual((got[RAX],got[RDX]),pair,(label,k,'native pair'))
            self.assertEqual(memory,expected_memory,(label,k,'native whole memory'))

    def test_exact_text_capacity_invalid_readonly(self):
        cases=[]
        for f in FUNCTIONS:
            need=len(expected_text(*f))
            for cap,status in ((need,OK),(need-1,CAPACITY),(0,CAPACITY),(need+19,OK)):
                cases.append(self.case(*f,cap,status,1))
        base=(b'm',b'i',0,32,False,3)
        bads=[(b'',*base[1:]),(base[0],b'',*base[2:]),(b'x'*65,*base[1:]),(base[0],b'y'*65,*base[2:]),
              (*base[:2],2,*base[3:]),(*base[:2],MAX,*base[3:]),(*base[:5],MAX)]
        for op in (0,1):
            for w in (0,7,24,MAX):bads.append((*base[:2],op,w,False,3))
        bads += [(*base[:2],0,64,True,3)]+[(*base[:2],1,w,True,3) for w in (8,16,32,64)]
        for f in bads:
            cases += [self.case(*f,4096,INVALID,1),self.case(*f,0,INVALID,1)]
        cases += [(b'overlapnames',0,8,2,8,0,8,False,4,1,4096,OK),
                  (b'same',0,4,0,4,1,64,False,5,1,4096,OK)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for c,text in zip(cases,texts):
                if c[11]==OK:
                    self.assertEqual(text,expected_text(c[0][c[1]:c[1]+c[2]],c[0][c[3]:c[3]+c[4]],*c[5:9]))
                    self.assertLessEqual(len(text),1297)
                    self.assertTrue(all(x==10 or 32<=x<127 for x in text));self.assertNotIn(b'\n\n',text)
                    for token in (b'\x00',b'section',b'global',b'bits',b'extern',b';'):self.assertNotIn(token,text)
        self.records.append(dict(test='exact-text-capacity-invalid-readonly',cases_per_mode=len(cases),preflights_per_process=PREFLIGHTS,passed=True))

    def test_native_call_ret(self):
        self.assertLessEqual(len(VECTORS),24)
        self.assertEqual({f[2:5] for f in FUNCTIONS},set(FORMS))
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,FUNCTIONS,'vectors-'+mode),FUNCTIONS,VECTORS,'native-'+mode)
        self.records.append(dict(test='native-pair-memory',vectors_per_mode=len(VECTORS),passed=True))

    def test_real_bad_dong(self):
        source=SOURCE.read_text(encoding='utf-8')
        scale='indexed.encode(7,0,width/8,0,'
        gate='bounds.emit(0,1,error_block,'
        capacity='if at>out.len{return CAPACITY;}'
        for snippet in (scale,gate,capacity):self.assertEqual(source.count(snippet),1,snippet)
        # LOAD16 and STORE32 swap legal scales2<->4 at nonzero index3.
        # Both access offsets6/12 inside the reserved256-byte target. STORE's
        # returned narrowed value stays unchanged, so whole-memory must reject it.
        wrongscale=source.replace(scale,'indexed.encode(7,0,8/(width/8),0,',1)
        # Emit real CR9 zero of R11 immediately before the real CR20 gate.
        # RAX remains the true index used by the subsequent LEA.
        badgate=source.replace('if '+gate,
            'if !constant(out,at,11,0){return false;}if bounds.emit(11,1,error_block,',1)
        self.assertNotEqual(badgate,source)
        scalefixtures=[(FUNCTIONS[2],4,3,MAX,False,True),(FUNCTIONS[9],4,3,0xfedcba9876543281,False,False)]
        # Each gate fixture is logically out of bounds but physically accessible;
        # writable, non-NULL targets ensure a bypassed STORE can return safely.
        gatefixtures=[(FUNCTIONS[2],2,2,MAX,False,False),(FUNCTIONS[10],2,2,MAX,False,False)]
        for name,bad,fixtures,rejections in [
            ('bad-scale',wrongscale,scalefixtures,('native pair','native whole memory')),
            ('bad-bounds-index',badgate,gatefixtures,('native (pair|whole memory)','native (pair|whole memory)'))]:
            functions=list(dict.fromkeys(v[0] for v in fixtures))
            for mode,exe in self.executables.items():
                texts=self.generate(exe,functions,name+'-good-'+mode)
                for k,v in enumerate(fixtures):
                    self.native_run(texts,functions,[v],name+'-good-'+mode+'-fixture%d'%k)
            for mode,exe in self.build_all(name,bad).items():
                texts=self.generate(exe,functions,name+'-'+mode,exact=False)
                for k,(v,rejection) in enumerate(zip(fixtures,rejections)):
                    # A separate native run/assertion per fixture prevents LOAD's
                    # first numerical rejection from hiding STORE's memory proof.
                    with self.assertRaisesRegex(AssertionError,rejection):
                        self.native_run(texts,functions,[v],name+'-'+mode+'-fixture%d'%k)
            self.records.append(dict(test=name,compiled=True,linked=True,normal_native_exit=True,modes=2,
                rejected_by=list(rejections),each_fixture_independently_rejected=True,
                all_ABI_and_guards_checked_before_semantics=True,safe_physical_target=256))
        early=('if at>out.len{var badat:usize=0;'
            'while badat<at&&badat<out.len{out[badat]=buffer[badat];'
            'if buffer[badat]==10{break;}badat+=1;}return CAPACITY;}')
        f=FUNCTIONS[0];fixtures=[(f,4,0,MAX,False,True)]
        short=[self.case(*f,len(expected_text(*f))-1,CAPACITY,1)]
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,[f],'bad-early-header-good-'+mode),[f],fixtures,'bad-early-header-good-'+mode)
            self.emit(exe,short,'bad-early-header-good-short-'+mode)
        for mode,exe in self.build_all('bad-early-header',source.replace(capacity,early,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                self.emit(exe,short,'bad-early-header-'+mode)
        self.records.append(dict(test='bad-early-header',compiled=True,linked=True,modes=2,
            rejected_by='guard/atomicity',good_native_same_input_first=True,bad_incomplete_function_executed=False))

if __name__=='__main__':unittest.main()
