"""Ordered/aliasing memory and fault behavior through actual generated code."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lang.dongc import compile_source, ssa, ssa_lower
from lang.tests.test_dongc import tool, nasm_flags

SOURCE='''module memory;
export("copy_words") unsafe fn copy_words(d:*u64,s:*const u64,n:u64)u64 {unsafe {
    var i:u64=0;while i<n {*(d+i)=*(s+i);i+=1;}return n;
}}
export("sum_words") unsafe fn sum_words(p:*const u64,n:u64)u64 {unsafe {
    var i:u64=0;var total:u64=0;while i<n {total+=p[i];i+=1;}return total;
}}
export("alias_reads") unsafe fn alias_reads(p:*u64,q:*u64)u64 {unsafe {
    let a=*p;*q=7;let b=*p;return a*100+b;
}}
export("compound") unsafe fn compound(p:*u64,q:*u64)u64 {unsafe { *p+=*q;return *p; }}
export("unused_read") unsafe fn unused_read(p:*const u64)u64 {unsafe {let unused=*p;return 17;}}
export("bool_mem") unsafe fn bool_mem(p:*bool,n:u64)bool {unsafe {*p=n==7;return *p;}}
export("pointer_mem") unsafe fn pointer_mem(p:**u64)u64 {unsafe {let q=*p;return *q;}}
export("reverse_sum") unsafe fn reverse_sum(p:*const u64,n:u64)u64 {unsafe {
    var i:u64=0;var t:u64=0;while i<n {t+=*(p-i);i+=1;}return t;
}}
export("ordered_fault") unsafe fn ordered_fault(p:*u64,q:*const u64)u64 {unsafe {*p=99;let unused=*q;*p=101;return 0;}}
export("advance") unsafe fn advance(p:*u64,n:u64)u64 {unsafe {
    var cursor=p;cursor+=n;cursor-=1;return *cursor;
}}
fn narrow(p:*u8)u8 {unsafe {return *p;}}
fn atomic(p:*u64)u64 {unsafe {return atomic_fetch_add(p,1);}}
fn volatile(p:*u64)u64 {unsafe {return volatile_load(p);}}
fn fence(p:*u64)u64 {unsafe {*p=2;compiler_fence();return *p;}}
'''

HARNESS=r'''
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <signal.h>
#include <sys/mman.h>
#include <unistd.h>
#endif
#define ABI __attribute__((sysv_abi))
#define DECLARE(P) \
extern uint64_t ABI P##copy_words(uint64_t*,const uint64_t*,uint64_t); \
extern uint64_t ABI P##sum_words(const uint64_t*,uint64_t); \
extern uint64_t ABI P##reverse_sum(const uint64_t*,uint64_t); \
extern uint64_t ABI P##alias_reads(uint64_t*,uint64_t*); \
extern uint64_t ABI P##compound(uint64_t*,uint64_t*); \
extern uint64_t ABI P##unused_read(const uint64_t*); \
extern uint64_t ABI P##pointer_mem(uint64_t**); \
extern uint8_t ABI P##bool_mem(uint8_t*,uint64_t); \
extern uint64_t ABI P##ordered_fault(uint64_t*,const uint64_t*); \
extern uint64_t ABI P##advance(uint64_t*,uint64_t)
DECLARE();DECLARE(l1_);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{(void)k;(void)l;(void)f;(void)n;exit(96);}
static void *guard;
static uint64_t observed=0;
static int ordered=0;
#ifdef _WIN32
static LONG CALLBACK fault(EXCEPTION_POINTERS *p){
 if(p->ExceptionRecord->ExceptionCode==EXCEPTION_ACCESS_VIOLATION &&
    p->ExceptionRecord->ExceptionInformation[0]==0 &&
    p->ExceptionRecord->ExceptionInformation[1]==(ULONG_PTR)guard){
     ExitProcess(ordered&&observed!=99?78:77);
 }return EXCEPTION_CONTINUE_SEARCH;
}
#else
static void fault(int sig,siginfo_t *info,void *context){
 (void)context;if(sig==SIGSEGV&&info->si_addr==guard)_Exit(ordered&&observed!=99?78:77);
 _Exit(79);
}
#endif
#define CHECK(c) do {if(!(c)){fprintf(stderr,"MEMORY_MISMATCH:%d\n",__LINE__);return 3;}}while(0)
int main(int argc,char**argv){
#ifdef _WIN32
 SetErrorMode(SEM_NOGPFAULTERRORBOX|SEM_FAILCRITICALERRORS);
 guard=VirtualAlloc(NULL,4096,MEM_COMMIT|MEM_RESERVE,PAGE_NOACCESS);
 if(!guard||!AddVectoredExceptionHandler(1,fault))return 91;
#else
 guard=mmap(NULL,4096,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(guard==MAP_FAILED)return 91;
 struct sigaction action;memset(&action,0,sizeof(action));action.sa_sigaction=fault;action.sa_flags=SA_SIGINFO;
 if(sigaction(SIGSEGV,&action,NULL))return 91;
#endif
 if(argc>1){
   if(strcmp(argv[1],"ordered")==0){ordered=1;ordered_fault(&observed,guard);}
   else {unused_read(guard);}
   return 90;
 }
 CHECK(sum_words(guard,0)==0 && copy_words(guard,guard,0)==0);
 CHECK(reverse_sum(guard,0)==0);
 uint64_t a[66],b[66],c[66];
 for(uint64_t n=0;n<=32;n++)for(unsigned delta=0;delta<5;delta++){
  for(unsigned i=0;i<66;i++)a[i]=b[i]=c[i]=UINT64_C(0x9e3779b97f4a7c15)*(i+17);
  uint64_t expected=0;for(uint64_t i=0;i<n;i++)expected+=a[1+i];
  CHECK(sum_words(a+1,n)==expected&&l1_sum_words(a+1,n)==expected);
  CHECK(advance(a+1,n+1)==a[n+1]&&l1_advance(a+1,n+1)==a[n+1]);
  expected=0;for(uint64_t i=0;i<n;i++)expected+=a[40-i];
  CHECK(reverse_sum(a+40,n)==expected&&l1_reverse_sum(a+40,n)==expected);
  for(uint64_t i=0;i<n;i++)c[1+delta+i]=c[1+i];
  CHECK(copy_words(a+1+delta,a+1,n)==n&&l1_copy_words(b+1+delta,b+1,n)==n);
  CHECK(!memcmp(a,c,sizeof(a))&&!memcmp(b,c,sizeof(b)));
 }
 for(unsigned i=0;i<4000;i++){
  uint64_t x=i*UINT64_C(18446744073709551557),y=x+23;
  uint64_t p=x,q=y;CHECK(alias_reads(&p,&q)==x*101&&q==7);
  p=x;CHECK(alias_reads(&p,&p)==x*100+7&&p==7);
  p=x;CHECK(compound(&p,&p)==x+x&&p==x+x);
  p=x;q=y;CHECK(compound(&p,&q)==x+y&&p==x+y&&q==y);
  uint64_t *ptr=&p;CHECK(pointer_mem(&ptr)==p);
  uint8_t bytes[]={0xa5,0,0xa5};CHECK(bool_mem(bytes+1,i)==(i==7));
  CHECK(bytes[0]==0xa5&&bytes[2]==0xa5&&bytes[1]==(i==7));
 }
 return 0;
}
'''


class SSAMemoryTests(unittest.TestCase):
    def test_effects_remain_ordered_and_live_even_when_results_are_unused(self):
        compiled=compile_source(SOURCE,mode='release',optimize=1)
        records={r['symbol']:r for r in compiled.optimization['functions']}
        for name in ('copy_words','sum_words','alias_reads','compound','unused_read','bool_mem','pointer_mem','reverse_sum','ordered_fault','advance'):
            self.assertEqual(records[name]['backend'],'ssa',records[name])
        for name,record in records.items():
            if name not in ('copy_words','sum_words','alias_reads','compound','unused_read','bool_mem','pointer_mem','reverse_sum','ordered_fault','advance'):
                self.assertEqual(record['backend'],'l1')
        for name,ops in [('unused_read',['load']),('ordered_fault',['store','load','store']),('alias_reads',['load','store','load'])]:
            actual=[i['op']for b in records[name]['after']['blocks']for i in b['instructions']if i['op']in ssa.MEMORY]
            self.assertEqual(actual,ops)
        self.execute(compiled)

    def execute(self,compiled,*,fault_expected=77):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        if not nasm or not cc:self.skipTest('native memory checks require NASM/GCC')
        original=compile_source(SOURCE.replace('export("','export("l1_'),mode='release')
        original.assembly=original.assembly.replace('__dg_m','__l1_dg_m')
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);objects=[]
            for name,result in [('ssa',compiled),('l1',original)]:
                asm=root/(name+'.asm');asm.write_text(result.assembly,encoding='utf-8')
                for fmt in ('elf64','win64'):
                    obj=root/(name+fmt+'.o')
                    run=subprocess.run([nasm,'-f',fmt,*nasm_flags(nasm),str(asm),'-o',str(obj)],capture_output=True,text=True)
                    self.assertEqual(run.returncode,0,run.stderr)
                    if fmt==('win64'if os.name=='nt'else'elf64'):objects.append(obj)
            c=root/'probe.c';c.write_text(HARNESS,encoding='utf-8');exe=root/('probe.exe'if os.name=='nt'else'probe')
            run=subprocess.run([cc,'-std=c11','-D_DEFAULT_SOURCE','-O2','-Wall','-Wextra','-Werror',str(c),*map(str,objects),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            for args,expected in [((),0),(('unused',),fault_expected),(('ordered',),77)]:
                run=subprocess.run([str(exe),*args],capture_output=True,text=True,timeout=15)
                self.assertEqual(run.returncode,expected,(args,run.returncode,run.stdout,run.stderr))

    def test_all_spills_and_one_register_preserve_memory_and_phi_cycles(self):
        actual=ssa_lower.assembly
        for registers in ((),('r8',)):
            with self.subTest(registers=registers),patch.object(ssa_lower,'assembly',side_effect=lambda f:actual(f,registers=registers)):
                self.execute(compile_source(SOURCE,mode='release',optimize=1))

    def test_real_compiled_bad_dce_is_caught_by_unused_load_fault(self):
        optimize=ssa.optimize
        def drop(f):
            out=optimize(f)
            if f.name=='unused_read':
                for b in out.blocks:b.instructions=[i for i in b.instructions if i.op!='load']
                present=set(out.params)|{i.result for b in out.blocks for i in b.instructions}
                out.value_types={v:t for v,t in out.value_types.items()if v in present}
            return out
        with patch.object(ssa,'optimize',side_effect=drop):compiled=compile_source(SOURCE,mode='release',optimize=1)
        # Code builds, runs and passes ordinary correctness; only a real read
        # from the guard page can produce the expected access-fault observation.
        self.execute(compiled,fault_expected=90)


if __name__=='__main__':unittest.main()
