"""Actual Dong conditional-branch / fallthrough-edge plan, with independent Python simulation."""
import hashlib
import json
import os
from pathlib import Path
import random
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
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=WORKS/'cursor-works/src/bootstrap/branch_plan.dg'
DOC=WORKS/'cursor-works/src/bootstrap/branch_plan.md'
OK,INVALID=0,1
MAX=0xffff_ffff_ffff_ffff
EQ,NE,ULT,ULE,UGT,UGE,SLT,SLE,SGT,SGE=range(10)
INVERT={EQ:NE,NE:EQ,ULT:UGE,ULE:UGT,UGT:ULE,UGE:ULT,SLT:SGE,SLE:SGT,SGT:SLE,SGE:SLT}
WRAPPER='''module probe.branch_plan_export;
import bootstrap.branch_plan as b;
export("dong_branch_plan") pub unsafe fn plan(
 condition:u64,yes:u64,no:u64,fallthrough:u64,out:*b.Plan)u64{unsafe{
 return b.plan(condition,yes,no,fallthrough,out);
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
typedef struct {
 uint64_t has_cond,condition,cond_target,has_jump,jump_target;
} Plan;
_Static_assert(sizeof(Plan)==40&&__builtin_offsetof(Plan,condition)==8
 &&__builtin_offsetof(Plan,cond_target)==16
 &&__builtin_offsetof(Plan,has_jump)==24
 &&__builtin_offsetof(Plan,jump_target)==32,"layout");
extern uint64_t ABI dong_branch_plan(uint64_t,uint64_t,uint64_t,uint64_t,Plan*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Null / unaligned / non-span out → INVALID, arena unchanged. */
static unsigned invalid(void){
 static uint8_t arena[512],saved[512];const unsigned total=8;
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_branch_plan(0,1,2,3,NULL);break;
   case 1:st=dong_branch_plan(0,1,2,3,(Plan*)(arena+68));break;
   case 2:st=dong_branch_plan(0,1,2,3,(Plan*)(arena+65));break;
   case 3:st=dong_branch_plan(0,1,2,3,(Plan*)(uintptr_t)1);break;
   case 4:st=dong_branch_plan(0,1,2,3,(Plan*)(uintptr_t)4);break;
   case 5:st=dong_branch_plan(0,1,2,3,(Plan*)(uintptr_t)(UINT64_MAX-31));break;
   case 6:st=dong_branch_plan(0,1,2,3,(Plan*)(uintptr_t)(UINT64_MAX-39));break;
   default:st=dong_branch_plan(0,1,2,3,(Plan*)(uintptr_t)(UINT64_MAX-7));break;
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)st);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[4];read_exact(h,sizeof(h));
  uint8_t buf[40+64];memset(buf,0xa5,sizeof(buf));Plan*out=(Plan*)(buf+32);
  uint64_t st=dong_branch_plan(h[0],h[1],h[2],h[3],out);
  uint64_t valid=filled(buf,32)&&filled(buf+32+40,32);
  if(st)valid=valid&&filled(out,40);
  uint64_t response[7]={st,valid,
   st?0:out->has_cond,st?0:out->condition,st?0:out->cond_target,
   st?0:out->has_jump,st?0:out->jump_target};
  write_exact(response,56);
 }return 0;
}
'''


def as_i64(v):
    v&=MAX
    return v-0x1_0000_0000_0000_0000 if v>=0x8000_0000_0000_0000 else v


def pred_true(cond,a,b):
    a&=MAX;b&=MAX
    if cond==EQ:return a==b
    if cond==NE:return a!=b
    if cond==ULT:return a<b
    if cond==ULE:return a<=b
    if cond==UGT:return a>b
    if cond==UGE:return a>=b
    ia,ib=as_i64(a),as_i64(b)
    if cond==SLT:return ia<ib
    if cond==SLE:return ia<=ib
    if cond==SGT:return ia>ib
    if cond==SGE:return ia>=ib
    raise ValueError(cond)


def expected_plan(condition,yes,no,fallthrough):
    """Independent Python expectation of bootstrap.branch_plan.plan."""
    if condition>9:return INVALID,None
    if yes==MAX or no==MAX:return INVALID,None
    has_cond=cond=ct=has_jump=jt=0
    if yes==no:
        if fallthrough==MAX or yes!=fallthrough:
            has_jump,jt=1,yes
    elif no==fallthrough:
        has_cond,cond,ct=1,condition,yes
    elif yes==fallthrough:
        has_cond,cond,ct=1,INVERT[condition],no
    else:
        has_cond,cond,ct=1,condition,yes
        has_jump,jt=1,no
    return OK,(has_cond,cond,ct,has_jump,jt)


def simulate(plan,condition,yes,no,fallthrough,a,b):
    """Follow Plan fields with independent u64/i64 predicate truth → destination block."""
    has_cond,cond,ct,has_jump,jt=plan
    if has_cond:
        if pred_true(cond,a,b):return ct
        if has_jump:return jt
        return fallthrough
    if has_jump:return jt
    return fallthrough


def expect_dest(condition,yes,no,a,b):
    return yes if pred_true(condition,a,b) else no


def item(condition,yes,no,fallthrough,status=None):
    st,plan=expected_plan(condition,yes,no,fallthrough)
    if status is not None:assert st==status,(status,st,condition,yes,no,fallthrough)
    return dict(condition=condition,yes=yes,no=no,fallthrough=fallthrough,status=st,plan=plan)


class BranchPlanTests(unittest.TestCase):
    PREFLIGHTS=8

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native branch_plan requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR6'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        (cls.src_root/'bootstrap'/'branch_plan.dg').write_bytes(SOURCE.read_bytes())
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/branch_plan_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/branch_plan_export.dg',roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==native else cls.work/(name+'.'+fmt+'.o')
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
        for c in cases:
            payload.extend(struct.pack('<4Q',c['condition'],c['yes'],c['no'],c['fallthrough']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8
        for index,c in enumerate(cases):
            status,guard,hc,cond,ct,hj,jt=struct.unpack_from('<7Q',run.stdout,offset);offset+=56
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c))
            if not status:
                self.assertEqual((hc,cond,ct,hj,jt),c['plan'],(label,index,'plan',c))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_python_expectation_and_simulation(self):
        """Independent planning rules + u64/i64 truth for all 10 predicates."""
        # structural cases: yes==no, no==ft, yes==ft, neither, no fallthrough
        structs=[
            (EQ,10,10,10),          # yes==no==ft → no edges
            (EQ,10,10,20),          # yes==no != ft → jump
            (EQ,10,10,MAX),         # yes==no, no ft → jump
            (NE,1,2,2),             # no==ft → cond yes
            (ULT,1,2,1),            # yes==ft → invert to no
            (ULE,1,2,3),            # neither → cond+jump
            (UGT,5,7,MAX),          # no ft, neither → cond+jump
            (UGE,9,9,MAX),          # yes==no, no ft
        ]
        pairs=[
            (0,0),(0,1),(1,0),
            (0x8000_0000_0000_0000,0),
            (0,0x8000_0000_0000_0000),
            (0xffff_ffff_ffff_ffff,0),
            (0xffff_ffff_ffff_ffff,0xffff_ffff_ffff_ffff),
            (0x7fff_ffff_ffff_ffff,0x8000_0000_0000_0000),
            (0x8000_0000_0000_0000,0x8000_0000_0000_0001),
            (5,5),(5,6),(100,50),
        ]
        sim=0
        for cond in range(10):
            for yes,no,ft in [(1,2,2),(1,2,1),(1,2,3),(1,1,1),(1,1,9),(4,5,MAX),(7,7,MAX)]:
                st,plan=expected_plan(cond,yes,no,ft)
                self.assertEqual(st,OK)
                for a,b in pairs:
                    dest=simulate(plan,cond,yes,no,ft,a,b)
                    self.assertEqual(dest,expect_dest(cond,yes,no,a,b),(cond,yes,no,ft,a,b,plan,dest))
                    # invert consistency: inverted predicate flips truth
                    self.assertEqual(pred_true(INVERT[cond],a,b),not pred_true(cond,a,b),(cond,a,b))
                    sim+=1
        for c,y,n,f in structs:
            st,plan=expected_plan(c,y,n,f)
            self.assertEqual(st,OK)
            for a,b in pairs[:4]:
                self.assertEqual(simulate(plan,c,y,n,f,a,b),expect_dest(c,y,n,a,b))
                sim+=1
        # illegal
        for bad in (10,11,99,MAX,0x8000_0000_0000_0000):
            self.assertEqual(expected_plan(bad,1,2,3),(INVALID,None))
        self.assertEqual(expected_plan(0,MAX,2,3),(INVALID,None))
        self.assertEqual(expected_plan(0,1,MAX,3),(INVALID,None))
        self.records.append(dict(test='python-expectation-simulation',simulations=sim,
                                 predicates=10,passed=True))

    def test_native_rules_invalid_and_seeded(self):
        cases=[]
        # cover rule shapes × all predicates
        shapes=[
            (10,10,10),(10,10,20),(10,10,MAX),
            (1,2,2),(1,2,1),(1,2,3),(1,2,MAX),
            (100,100,50),(0,1,0),(0,1,1),
        ]
        for cond in range(10):
            for y,n,f in shapes:cases.append(item(cond,y,n,f))
        # illegal enum / targets
        for bad in (10,11,99,0xff,0x8000_0000_0000_0000,MAX):
            cases.append(item(bad,1,2,3,status=INVALID))
        cases+=[item(0,MAX,2,3,status=INVALID),item(0,1,MAX,3,status=INVALID),
                item(SLT,MAX,MAX,MAX,status=INVALID)]
        # sign-bit boundary structural plans
        for cond in (SLT,SLE,SGT,SGE,ULT,UGE):
            cases+=[item(cond,0,1,1),item(cond,0,1,0),item(cond,0,1,2),
                    item(cond,0x8000_0000_0000_0000,1,2),
                    item(cond,1,2,MAX)]
        rng=random.Random(0x0C86001)
        for _ in range(100):
            cond=rng.randrange(0,14)
            yes=rng.randrange(0,40)
            no=rng.randrange(0,40)
            ft=MAX if rng.randrange(0,6)==0 else rng.randrange(0,40)
            cases.append(item(cond,yes,no,ft))
        self.run_both(cases,'rules-seeded')
        self.records.append(dict(test='native-rules-invalid-seeded',cases=len(cases),
                                 preflights=self.PREFLIGHTS,modes=2,passed=True))

    def test_dong_asm_elf64_and_win64(self):
        """Dong object assembled for both ELF64 and Win64; smoke-check plans."""
        native='win64'if os.name=='nt'else'elf64'
        for mode in ('debug','release'):
            for fmt in ('elf64','win64'):
                path=self.work/(mode+'.o') if fmt==native else self.work/(mode+'.'+fmt+'.o')
                self.assertTrue(path.is_file(),path)
                self.assertGreater(path.stat().st_size,0)
        self.run_both([item(EQ,1,2,2),item(SLT,3,4,3),item(NE,5,5,MAX)],'asm-smoke')
        self.records.append(dict(test='dong-asm-elf64-win64',modes=2,formats=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'branch_plan.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'branch_plan_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',ROOT/'lang',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # 1) wrong signed invert: SLT should invert to SGE, corrupt to SLE
        # 2) missing unconditional jump when no fallthrough (else branch)
        controls=[
            ('bad-signed-invert',
             'if c==SLT{return SGE;}',
             'if c==SLT{return SLE;}',
             [item(SLT,1,2,1)],  # yes==fallthrough → uses invert(SLT)
             'plan'),
            ('bad-missing-no-fallthrough-jump',
             'has_cond=1;cond=condition;ct=yes;has_jump=1;jt=no;',
             'has_cond=1;cond=condition;ct=yes;',
             [item(EQ,1,2,MAX)],  # neither equals MAX fallthrough → must emit jump
             'plan'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            # confirm the good plan differs from the buggy expectation shape
            if name=='bad-signed-invert':
                st,plan=expected_plan(SLT,1,2,1)
                self.assertEqual(plan,(1,SGE,2,0,0))
            else:
                st,plan=expected_plan(EQ,1,2,MAX)
                self.assertEqual(plan,(1,EQ,1,1,2))
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
