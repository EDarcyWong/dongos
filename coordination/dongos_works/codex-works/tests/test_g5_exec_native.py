"""G5 CPU execution of indirect calls, memory operations and both x64 ABIs."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import unittest
WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS.parents[1]/'code'
sys.path.insert(0,str(ROOT))
from lang.tests import test_l3a_globals as bridge
from tools import g5_differential as g5
import test_g5_tagged_native as tagged

POINTERS='''module tagged;
type Binary=fn(u64,u64)u64;
fn add(a:u64,b:u64)u64{return a+b;}
fn mul(a:u64,b:u64)u64{return a*b;}
pub var chosen:Binary=add;pub var trace:u64=0;
fn fetch()Binary{trace=trace*10+1;return chosen;}
fn first()u64{trace=trace*10+2;chosen=mul;return 3;}
fn second()u64{trace=trace*10+3;return 5;}
pub fn f()u64{trace=0;chosen=add;unsafe{return fetch()(first(),second());}}
pub fn again()u64{unsafe{return chosen(3,5);}}
type PairCall=fn(u64,u64,u64,u64,u64,?u64,u64)?u64;
fn pair(a:u64,b:u64,c:u64,d:u64,e:u64,p:?u64,z:u64)?u64{
 if a+b+c+d+e+z!=22{return null;}return p;
}
pub fn invoke_pair(p:?u64)?u64{let f:PairCall=pair;unsafe{return f(1,2,3,4,5,p,7);}}
struct Table{callback:Binary}
pub fn field()u64{let t=Table{callback:mul};unsafe{return t.callback(6,7);}}
'''

MEMORY='''module tagged;
pub unsafe fn load8(p:*const i8)i8{unsafe{return volatile_load(p);}}
pub unsafe fn store8(p:*i8,n:i8)void{unsafe{volatile_store(p,n);}}
pub unsafe fn load64(p:*const i64)i64{unsafe{return read_unaligned(p);}}
pub unsafe fn store64(p:*i64,n:i64)void{unsafe{write_unaligned(p,n);}}
pub unsafe fn aload32(p:*const u32)u32{unsafe{return atomic_load(p);}}
pub unsafe fn astore32(p:*u32,n:u32)void{unsafe{atomic_store(p,n);}}
pub unsafe fn cas32(p:*u32,e:u32,d:u32)u32{unsafe{return atomic_compare_exchange(p,e,d);}}
pub unsafe fn fetch32(p:*u32,n:u32)u32{unsafe{return atomic_fetch_add(p,n);}}
pub unsafe fn aload64(p:*const u64)u64{unsafe{return atomic_load(p);}}
pub unsafe fn astore64(p:*u64,n:u64)void{unsafe{atomic_store(p,n);}}
pub unsafe fn cas64(p:*u64,e:u64,d:u64)u64{unsafe{return atomic_compare_exchange(p,e,d);}}
pub unsafe fn fetch64(p:*u64,n:u64)u64{unsafe{return atomic_fetch_add(p,n);}}
pub fn safe_asm()u64{unsafe{compiler_fence();asm{pause}asm{sfence}asm{lfence}asm{mfence}}return 7;}
fn privileged()void{unsafe{asm{cli}asm{sti}asm{hlt}asm{int3}}}
'''

WINDOWS='''module tagged;
extern "sysv64" fn host_clobber(n:u64)u64;
extern "win64" fn host_win(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64;
pub extern "win64" fn callback(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64{
 unsafe{return host_clobber(a+2*b+3*c+4*d+5*e+6*f+7*g+8*h);}
}
pub fn direct()u64{unsafe{return callback(1,2,3,4,5,6,7,8)+host_win(2,3,4,5,6,7,8,9);}}
type WinCall=extern "win64" fn(u64,u64,u64,u64,u64,u64,u64,u64)u64;
pub fn indirect()u64{let f:WinCall=callback;unsafe{return f(1,2,3,4,5,6,7,8);}}
pub extern "win64" fn narrow(n:i8)i8{return n;}
pub extern "win64" fn empty()u64{return 55;}
'''

class ExecutionNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved=bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER
        bridge.CAND=WORKS/'codex-works/g5-exec/src/bootstrap'
        bridge.CANDIDATES=('semantic_types.dg','program_ir.dg','lower_program.dg','nasm_program.dg')
        bridge.BUILD=ROOT/'build/test/g5-exec'
        bridge.DRIVER=g5.diagnostic_driver()
        try:bridge.L3AGlobalsTests.setUpClass()
        except BaseException:
            bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER=cls.saved
            raise
        cls.h=bridge.L3AGlobalsTests()
        for p in (Path(__file__),Path(tagged.__file__)):
            cls.h.inputs[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        cls.source_before=dict(cls.h.inputs)
        cls.runner=g5.Runner(cls.h.work/'differential')
        cls.runner.g,cls.runner.nasm,cls.runner.cc=cls.h,cls.h.nasm,cls.h.cc
    @classmethod
    def tearDownClass(cls):
        try:
            cls.runner.assert_inputs()
            after={p:g5.sha(p) for p in cls.source_before}
            g5.write(cls.h.work/'frozen-inputs.json',dict(before=cls.source_before,after=after,source_stable=after==cls.source_before))
            g5.require(after==cls.source_before,'frozen candidate or dependency changed')
            g5.write(cls.runner.work/'execution.json',dict(cases=cls.runner.cases,commands=cls.runner.records,scope_complete=False))
            cls.h.tearDownClass()
        finally:bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER=cls.saved
    differential=tagged.TaggedNativeTests.differential
    def test_callee_once_before_arguments_static_field_and_pair_abi(self):
        self.differential('pointers',POINTERS,tagged.observer([
            ('f','U','void'),('again','U','void'),('field','U','void'),('invoke_pair','Pair','Pair')],
            'CHECK(f_f()==8&&trace==123&&f_again()==15&&f_field()==42);'
            'Pair p=f_invoke_pair((Pair){1,0xfedcba9876543210ULL});CHECK(p.tag==1&&p.value==0xfedcba9876543210ULL);'))
    def test_memory_width_canaries_atomic_old_values_and_asm(self):
        decls=[('load8','int8_t','const int8_t*'),('store8','void','int8_t*,int8_t'),
               ('load64','int64_t','const int64_t*'),('store64','void','int64_t*,int64_t'),('safe_asm','U','void')]
        for n in (32,64):
            c='uint'+str(n)+'_t';p=c+'*';suffix=str(n)
            decls += [('aload'+suffix,c,'const '+p),('astore'+suffix,'void',p+','+c),
                      ('cas'+suffix,c,p+','+c+','+c),('fetch'+suffix,c,p+','+c)]
        self.differential('memory',MEMORY,tagged.observer(decls,
            'unsigned char b[16];memset(b,0xa7,sizeof b);f_store8((int8_t*)b+1,-7);'
            'CHECK(f_load8((int8_t*)b+1)==-7&&b[0]==0xa7&&b[2]==0xa7);'
            'f_store64((int64_t*)(b+3),-1234567890123LL);CHECK(f_load64((int64_t*)(b+3))==-1234567890123LL&&b[2]==0xa7&&b[11]==0xa7);'
            'uint32_t a=17;U z=0x100000005ULL;CHECK(f_cas32(&a,16,23)==17&&a==17);'
            'CHECK(f_cas32(&a,17,23)==17&&a==23&&f_fetch32(&a,0xffffffffU)==23&&a==22);'
            'f_astore32(&a,99);CHECK(f_aload32(&a)==99);'
            'CHECK(f_cas64(&z,5,33)==0x100000005ULL&&z==0x100000005ULL);'
            'CHECK(f_cas64(&z,0x100000005ULL,0xffffffffffffffffULL)==0x100000005ULL);'
            'CHECK(f_fetch64(&z,2)==0xffffffffffffffffULL&&z==1);'
            'f_astore64(&z,0x8877665544332211ULL);CHECK(f_aload64(&z)==0x8877665544332211ULL&&f_safe_asm()==7);'))
        machine=Path(self.runner.cases[-1]['native']['assembly_path']).with_suffix('.obj').read_bytes()
        self.assertIn(bytes.fromhex('fafbf4cc'),machine)
        for instruction in ('f390','0faee8','0faef8','0faef0'):
            self.assertIn(bytes.fromhex(instruction),machine)
    def test_win64_direct_indirect_external_stack_narrow_and_no_args(self):
        obs=tagged.observer([('direct','U','void'),('indirect','U','void'),
            ('callback','U','U,U,U,U,U,U,U,U'),('narrow','int8_t','int8_t'),('empty','U','void')],
            'CHECK(f_callback(1,2,3,4,5,6,7,8)==205&&f_direct()==445&&f_indirect()==205);'
            'CHECK(f_narrow(-101)==-101&&f_empty()==55);')
        for name in ('callback','narrow','empty'):obs=obs.replace('ABI f_'+name,'__attribute__((ms_abi)) f_'+name)
        helpers='U __attribute__((sysv_abi)) host_clobber(U n){__asm__ volatile("'
        helpers+='\\n\\t'.join('pxor %%xmm'+str(i)+',%%xmm'+str(i) for i in range(6,16))
        helpers+='":::'+','.join('"xmm'+str(i)+'"' for i in range(6,16))+');return n+1;}\n'
        code=['.intel_syntax noprefix','.text','.global host_win','host_win:',
              'mov r10,rsp','and r10,15','cmp r10,8','jne .Lwin_bad']
        for i in range(4):code.append('mov qword ptr [rsp+'+str(8+8*i)+'],0x12345678')
        code+=['mov rax,rcx','lea rax,[rax+rdx*2]','imul r10,r8,3','add rax,r10','lea rax,[rax+r9*4]']
        for i in range(4,8):code+=['imul r10,qword ptr [rsp+'+str(40+8*(i-4))+'],'+str(i+1),'add rax,r10']
        code+=['ret','.Lwin_bad:','mov eax,7777','ret','.att_syntax prefix']
        helpers+='__asm__('+json.dumps('\n'.join(code)+'\n')+');\n'
        obs=obs.replace('int main(void){',helpers+'\nint main(void){')
        prefix=getattr(self,'win_prefix','')
        self.differential(prefix+'win64',WINDOWS,obs)
        # Explicit independent SysV checker calls the Win64 entry with all
        # nonvolatile GPRs/XMM6..15 seeded, a DF challenge, stack args and RSP.
        probe=['.intel_syntax noprefix','.text','.global check_win_registers','check_win_registers:',
            'push rbp','mov rbp,rsp','push rbx','push r12','push r13','push r14','push r15','sub rsp,248',
            'mov [rsp+88],rdi','mov [rsp+72],rbp','mov [rsp+80],rsp']
        registers=['rbx','r12','r13','r14','r15','rdi','rsi']
        for i,reg in enumerate(registers):probe.append('mov '+reg+','+str(0x11110000+i))
        for i in range(6,16):probe.append('pcmpeqd xmm'+str(i)+',xmm'+str(i))
        probe+=['mov rcx,1','mov rdx,2','mov r8,3','mov r9,4']
        for i in range(4,8):probe.append('mov qword ptr [rsp+'+str(32+8*(i-4))+'],'+str(i+1))
        probe+=['mov r11,[rsp+88]','std','call r11','cmp rax,205','jne .Lreg_bad',
                'cmp rsp,[rsp+80]','jne .Lreg_bad','cmp rbp,[rsp+72]','jne .Lreg_bad',
                'pushfq','pop rax','test eax,1024','jnz .Lreg_bad']
        for i,reg in enumerate(registers):probe+=['cmp '+reg+','+str(0x11110000+i),'jne .Lreg_bad']
        probe+=['pcmpeqd xmm0,xmm0']
        for i in range(6,16):probe+=['pcmpeqb xmm'+str(i)+',xmm0','pmovmskb eax,xmm'+str(i),'cmp eax,65535','jne .Lreg_bad']
        probe+=['xor eax,eax','jmp .Lreg_done','.Lreg_bad:','mov eax,1','.Lreg_done:','cld','lea rsp,[rbp-40]',
                'pop r15','pop r14','pop r13','pop r12','pop rbx','pop rbp','ret','.att_syntax prefix']
        extra='__asm__('+json.dumps('\n'.join(probe)+'\n')+');\nextern U ABI check_win_registers(void*);\n'
        checked=obs.replace('int main(void){',extra+'int main(void){CHECK(check_win_registers((void*)f_callback)==0);')
        self.win_checked=checked
        self.differential(prefix+'win64-registers',WINDOWS,checked)
    def test_tagged_flow_and_enum_remain_executable(self):
        self.differential('enum-regression',tagged.ENUMS,tagged.observer([('f','U','void')],'CHECK(f_f()==40);'))
    def test_z_real_missing_xmm_restore_is_rejected_after_normal_execution(self):
        self.win_prefix='negative-good-'
        self.test_win64_direct_indirect_external_stack_narrow_and_no_args()
        self.h.build_driver('bad-xmm',{'nasm_program.dg':(
            'i=0;while i<10{put(s,"movdqu xmm");',
            'i=0;while i<9{put(s,"movdqu xmm");')})
        self.differential('bad-xmm',WINDOWS,self.win_checked,tag='bad-xmm',expected=17)

if __name__=='__main__':unittest.main()
