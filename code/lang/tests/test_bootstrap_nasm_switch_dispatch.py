"""Actual Dong i64 switch dispatch emitter (C11 + CR9 + CR4): exact text, assembly, native routing."""
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
WORKS=ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/nasm_switch_dispatch.dg'
DEPENDENCIES=[ROOT/'lang/bootstrap'/n for n in ('switch_cases.dg','nasm_integer_load.dg','decimal_integer.dg')]  # C11, CR9, CR4
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
MIN,MAX=-2**63,2**63-1
PRESERVED=['rdi','rcx','rdx','rsi','r8','r9','r10','r11','r12','r13','r14','r15','rbp']
SENTINEL={r:0x0101010101010101*(i+3)for i,r in enumerate(PRESERVED)if r!='rdi'}
PREFLIGHTS=15
WRAPPER='''module probe.switch_export;
import bootstrap.switch_cases as cases;
import bootstrap.nasm_switch_dispatch as d;
export("dong_switch_emit") pub unsafe fn emit(input:*const cases.Case,n:usize,default_target:u64,out:*u8,nout:usize,written:*usize)u64{unsafe{
 return d.emit(slice_from_raw_parts(input,n),default_target,slice_from_raw_parts(out,nout),written);
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
typedef struct {int64_t value;uint64_t label;} Case;
_Static_assert(sizeof(Case)==16&&__builtin_offsetof(Case,label)==8,"Case layout");
extern uint64_t ABI dong_switch_emit(const Case*,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
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
static void ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree(p,0,MEM_RELEASE);
#else
 munmap(p,n);
#endif
}
#define FAKE(x) ((void*)(uintptr_t)(x))
/* Each preflight keeps every other field valid (default 9) so only the target check can reject it: all 16
   cases are legal with distinct values (5, -5, then 100*k) before the snapshot, so the len=16 declared-tail
   alias cases 10/11 cannot be masked by C11 rejecting a duplicate value. Every failure is reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[4096],saved[4096];const unsigned total=15;unsigned failed=0;
 Case*c=(Case*)arena;uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+3584);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));c[0].value=5;c[0].label=1;c[1].value=-5;c[1].label=2;
  for(unsigned k=2;k<16;k++){c[k].value=100*(int64_t)k;c[k].label=k;}
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_switch_emit(c,2,9,o,2048,NULL);break;                                /* written NULL */
   case 1:s=dong_switch_emit(c,2,9,o,2048,(uint64_t*)(arena+3585));break;             /* written odd */
   case 2:s=dong_switch_emit(c,2,9,NULL,0,FAKE(UINT64_MAX-7));break;                  /* written end overflow, legal empty out */
   case 3:s=dong_switch_emit(c,2,9,FAKE(UINT64_MAX-15),32,w);break;                   /* out end overflow */
   case 4:s=dong_switch_emit(c,2,9,NULL,16,w);break;                                  /* NULL non-empty out */
   case 5:s=dong_switch_emit(NULL,2,9,o,2048,w);break;                                /* NULL non-empty input */
   case 6:s=dong_switch_emit((Case*)(arena+4),2,9,o,2048,w);break;                    /* input misaligned */
   case 7:s=dong_switch_emit(c,UINT64_MAX/16+1,9,o,2048,w);break;                     /* input length multiplication overflow */
   case 8:s=dong_switch_emit(FAKE(UINT64_MAX-31),2,9,o,2048,w);break;                 /* input end overflow */
   case 9:s=dong_switch_emit(c,2,9,o,2048,(uint64_t*)c);break;                        /* written on input aligned prefix */
   case 10:s=dong_switch_emit(c,16,9,o,2048,(uint64_t*)(arena+248));break;            /* written in input's declared tail */
   case 11:s=dong_switch_emit(c,16,9,arena+200,64,w);break;                           /* out over input tail */
   case 12:s=dong_switch_emit(c,2,9,o,2048,(uint64_t*)o);break;                       /* written on out prefix */
   case 13:s=dong_switch_emit(c,2,9,o,2048,(uint64_t*)(o+2040));break;                /* written in out's unused tail */
   default:s=dong_switch_emit(c,2,9,arena+16,64,w);break;                             /* out over input's second case */
  }
  int same=!memcmp(saved,arena,sizeof(arena));
  if(s!=1||!same){fprintf(stderr,"invalid preflight %u status %u unchanged %d\n",i,(unsigned)s,same);failed++;}
 }
 if(failed)exit(93);
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[4];read_exact(h,sizeof(h));uint64_t n=h[0],deflt=h[1],cap=h[2],ro=h[3];
  if(n>64||cap>8192)exit(94);
  Case*in=malloc(n*16+64);Case*copy=malloc(n*16+1);uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  read_exact(in,n*16);memcpy(copy,in,n*16);
  const Case*c=in;uint8_t*page=NULL;uint64_t pages=4096,protected_ok=1;
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,in,n*16);protected_ok=ro_protect(page,pages);c=(const Case*)page;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));
  uint64_t s=dong_switch_emit(n?c:NULL,n,deflt,cap?out+32:NULL,cap,meta+1);
  uint64_t w=s?0:meta[1];
  uint64_t valid=protected_ok&&filled(meta,8)&&filled(meta+2,8)&&!memcmp(copy,c,n*16)&&filled(out,32)&&filled(out+32+cap,32);
  if(s)valid=valid&&filled(meta+1,8)&&filled(out+32,cap);else valid=valid&&w<=cap&&filled(out+32+w,cap-w);
  uint64_t response[3]={s,valid,w};write_exact(response,24);write_exact(out+32,w);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
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
 uint64_t count;read_exact(&count,8);
 while(count--){
  uint64_t io[24],which;read_exact(&which,8);if(which>=sizeof(table)/sizeof(table[0]))exit(94);
  memset(io,0xa5,sizeof(io));read_exact(io,8);io[23]=0x5a5a5a5a5a5a5a5aull;
  table[which](io);
  if(io[23]!=0x5a5a5a5a5a5a5a5aull)exit(96);
  if(fwrite(io,8,18,stdout)!=18)exit(92);
 }return 0;
}
'''


def expected_text(cases,default):
    lines=[]
    for value,label in sorted(cases):
        lines+=['mov rax, %d'%value,'cmp rdi, rax','je __dong_b%d'%label]
    lines.append('jmp __dong_b%d'%default)
    return ''.join(l+'\n'for l in lines).encode()


def route(cases,default,selector):
    """Independent routing: the label of the case whose i64 value equals the selector, else default."""
    return {value:label for value,label in cases}.get(selector,default)


LONG=[(MIN+i,U64-1-i)for i in range(16)]                  # 16 longest cases: 20-character values and labels
FULL=[(MAX,7),(MIN,U64-1),(-1,3),(0,4),(1,3),(2**62,10**19),(-2**62,12),(2**32,13),(-2**32,14),(255,15),
      (-256,16),(MAX-1,17),(MIN+1,18),(123456789,4),(-987654321,20),(2**31,U64-2)]
SMALL=[(1,5),(MIN,6),(MAX,7),(-1,8),(0,6)]
VECTORS=[(FULL,99),(SMALL,0),([],42),(LONG,U64-1),([(0,0)],U64-1),([(MIN,1),(MAX,1)],2)]


class NasmSwitchDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'build/test/bootstrap-nasm-switch-dispatch'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,*DEPENDENCIES,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and the integrated C11/CR9/CR4 modules, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_switch_dispatch.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/switch_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/switch_export.dg',roots=[root],mode=mode)
            asm=cls.work/(tag+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
            obj=cls.work/(tag+'.o');exe=cls.work/(tag+('.exe'if os.name=='nt'else''))
            for fmt in ('elf64','win64'):
                output=obj if fmt==cls.native else cls.work/(tag+'.'+fmt+'.o')
                cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],tag+'-'+fmt)
            cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],tag+'-link')
            result[mode]=exe
        return result

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        """cases: (cases, default, cap, readonly, status). Returns the emitted text (None on failure) per case."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for items,default,cap,ro,_ in cases:
            payload.extend(struct.pack('<4Q',len(items),default,cap,ro))
            for value,lab in items:payload.extend(struct.pack('<qQ',value,lab))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        offset=8;results=[]
        for index,c in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,c[-1],(label,index,'status',c[1:4]))
            results.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return results

    def native_run(self,texts,vectors,selectors,label):
        """One assembly file per vector (block labels repeat across vectors); each block records registers then its label."""
        objects=[]
        for k,(text,(cases,default)) in enumerate(zip(texts,vectors)):
            stub=['bits 64','section .text','global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15',
                  'mov rbx, rdi','mov [rbx+%d], rsp'%(8*17)]
            stub+=['mov %s, 0x%x'%(r,v)for r,v in SENTINEL.items()]+['mov rdi, [rbx]']
            stub+=text.decode('ascii').rstrip('\n').split('\n')
            stub+=['mov qword [rbx+8], 0','jmp v%d_done'%k]                                  # unreachable after the final jmp
            for lab in sorted({l for _,l in cases}|{default}):
                stub+=['__dong_b%d:'%lab]+['mov [rbx+%d], %s'%(8*(2+j),r)for j,r in enumerate(PRESERVED)]
                stub+=['mov [rbx+%d], rsp'%(8*15),'mov rax, %d'%lab,'mov [rbx+8], rax','jmp v%d_done'%k]
            stub+=['v%d_done:'%k,'pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
            asm=self.work/('%s.v%d.asm'%(label,k));asm.write_text('\n'.join(stub)+'\n',encoding='ascii')
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('%s.v%d.%s.o'%(label,k,fmt)),asm],'%s-v%d-%s'%(label,k,fmt))
            objects.append(self.work/('%s.v%d.%s.o'%(label,k,self.native)))
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),*objects,'-o',exe],label+'-native-link')
        payload=bytearray(struct.pack('<Q',len(selectors)))
        for k,sel in selectors:payload.extend(struct.pack('<Qq',k,sel))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        self.assertEqual(len(run.stdout),18*8*len(selectors))
        for n,(k,sel) in enumerate(selectors):
            got=struct.unpack_from('<18Q',run.stdout,18*8*n);cases,default=vectors[k]
            self.assertEqual(got[1],route(cases,default,sel),(label,k,sel,'native route'))
            regs=dict(zip(PRESERVED,got[2:15]))
            self.assertEqual(regs['rdi'],sel&U64,(label,k,sel,'native rdi preserved'))
            for r,v in SENTINEL.items():self.assertEqual(regs[r],v,(label,k,sel,'native register preserved',r))
            self.assertEqual(got[15],got[17],(label,k,sel,'native rsp preserved'))

    def selectors(self):
        """At most 24 per mode: every FULL case value, misses around signed/unsigned boundaries, and the other vectors."""
        hits=[(0,v)for v,_ in FULL]
        misses=[(0,v)for v in (2,-2,MAX-2,MIN+2)]
        return hits+misses+[(1,0),(2,MIN),(3,MIN+15),(5,MAX)]

    def test_exact_text_capacity_and_invalid(self):
        cases=[]
        for k,(items,default) in enumerate(VECTORS):
            n=len(expected_text(items,default))
            cases+=[(items,default,n,int(k%2==0),OK),(items,default,n+11,0,OK),(items,default,n-1,0,CAPACITY),(items,default,0,0,CAPACITY)]
        self.assertEqual(len(expected_text(LONG,U64-1)),16*75+33)
        cases+=[(list(reversed(LONG)),U64-1,1233,1,OK)]
        bad=[([(i,i)for i in range(17)],0),(SMALL,U64),([],U64),([(1,2),(3,U64)],0),
             ([(5,1),(9,2),(5,1)],0),([(MIN,1),(0,2),(MIN,3)],0),(LONG[:15]+[(MIN,5)],0)]
        for items,default in bad:cases+=[(items,default,4096,1,INVALID),(items,default,0,0,INVALID)]
        for mode,exe in self.executables.items():
            results=self.run_cases(exe,cases,'text-'+mode)
            for c,text in zip(cases,results):
                if c[-1]==OK:self.assertEqual(text,expected_text(c[0],c[1]),(mode,c[1:4]))
        self.records.append(dict(test='exact-text-capacity-invalid',cases=len(cases),preflights_per_native=PREFLIGHTS,
                                 longest_bytes=1233,modes=2,passed=True))

    def test_text_assembles_in_both_formats(self):
        for mode,exe in self.executables.items():
            texts=self.run_cases(exe,[(i,d,2048,0,OK)for i,d in VECTORS],'asm-'+mode)
            for k,(text,(items,default)) in enumerate(zip(texts,VECTORS)):
                labels=''.join('__dong_b%d:\n'%l for l in sorted({l for _,l in items}|{default}))
                source=self.work/('switch-%s-%d.asm'%(mode,k));source.write_bytes(b'bits 64\nsection .text\n'+text+labels.encode())
                for fmt in ('elf64','win64'):
                    self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('switch-%s-%d.%s.o'%(mode,k,fmt)),source],'switch-%s-%d-%s'%(mode,k,fmt))
        self.records.append(dict(test='switch-assemble',formats=['elf64','win64'],vectors=len(VECTORS),modes=2,passed=True))

    def test_native_routing(self):
        selectors=self.selectors();self.assertLessEqual(len(selectors),24)
        for mode,exe in self.executables.items():
            texts=self.run_cases(exe,[(i,d,2048,0,OK)for i,d in VECTORS],'vectors-'+mode)
            self.native_run(texts,VECTORS,selectors,'native-'+mode)
        self.records.append(dict(test='native-routing',selectors_per_mode=len(selectors),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='branch(text,&at,"je ",';new='branch(text,&at,"jne ",';self.assertEqual(source.count(old),1)
        vectors=[VECTORS[1]];selectors=[(0,v)for v,_ in SMALL]
        for mode,exe in self.executables.items():
            texts=self.run_cases(exe,[(i,d,2048,0,OK)for i,d in vectors],'bad-jne-good-'+mode)
            self.native_run(texts,vectors,selectors,'bad-jne-good-'+mode)
        for mode,exe in self.build_all('bad-jne',source.replace(old,new,1)).items():
            texts=self.run_cases(exe,[(i,d,2048,0,OK)for i,d in vectors],'bad-jne-'+mode)
            with self.assertRaisesRegex(AssertionError,'native route'):self.native_run(texts,vectors,selectors,'bad-jne-'+mode)
        self.records.append(dict(test='bad-jne',compiled=True,native_executed=True,modes=2,rejected_by='native route'))
        old='if at>out.len{return CAPACITY;}\n i=0;while i<at{out[i]=buffer[i];i+=1;}'
        new='i=0;while i<at&&i<out.len{out[i]=buffer[i];i+=1;}\n if at>out.len{return CAPACITY;}'
        self.assertEqual(source.count(old),1);case=[(SMALL,0,20,0,CAPACITY)]
        for mode,exe in self.executables.items():self.run_cases(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_prefix_only_input_alias_is_rejected(self):
        """Preflight sensitivity: a real Dong that checks only the first two cases (32 bytes) for input aliasing."""
        source=SOURCE.read_text(encoding='utf-8')
        old='overlap(ip,inn,op,out.len)||overlap(ip,inn,wp,8)';self.assertEqual(source.count(old),1)
        for mode,exe in self.executables.items():self.run_cases(exe,[],'prefix-good-'+mode)  # same harness passes all
        for mode,exe in self.build_all('bad-prefix-alias',source.replace(old,'overlap(ip,32,op,out.len)||overlap(ip,32,wp,8)',1)).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-prefix-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))                                   # normal exit from the preflight check
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,[10,11],(mode,err))                                      # exactly the two declared-tail cases
        self.records.append(dict(test='bad-prefix-alias',compiled=True,native_executed=True,modes=2,rejected_by='preflight 10/11'))


if __name__=='__main__':unittest.main()
