"""Target-provided panic ABI and real frontend diagnostic categories."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import sys
import unittest
WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS.parents[1]/'code'
sys.path.insert(0,str(ROOT))
from lang.tests import test_l3a_globals as bridge
from lang.tests.test_dongc import nasm_flags
from tools import g5_differential as g5
from lang.dongc.model import CompileError

PREFIX='''module tagged;
var trace:u64=0;
fn mark()void{trace=123;}
export("observe_trace")fn observe_trace()u64{return trace;}
'''
CASES=[
    ('overflow', 'let x=a as u8;let y=b as u8;/*site*/return (x+y)as u64;',255,1,2,0),
    ('multiply', 'let x=a as i8;let y=b as i8;/*site*/return (x*y)as u64;',64,2,2,0xffffffffffffff80),
    ('negate', '/*site*/return -a;',1,0,2,0xffffffffffffffff),
    ('divide-zero','/*site*/return a/b;',7,0,3,None),
    ('shift','/*site*/return a<<b;',7,64,4,None),
    ('signed-divide','let x=a as i8;let y=b as i8;/*site*/return (x/y)as u64;',128,255,5,None),
    ('bounds','let x:[2]u64=[17,19];/*site*/return x[a];',2,0,1,None),
    ('slice-bounds','let x:[2]u64=[17,19];/*site*/return x[0..b].len;',0,3,1,None),
    ('wrapping','/*site*/return wrapping_add(a,b);',0xffffffffffffffff,1,0,0),
    ('normal','/*site*/return a+b;',17,19,0,36),
]

class PanicNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved=bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler
        bridge.CAND=WORKS/'codex-works/g5-panic/src/bootstrap'
        bridge.CANDIDATES=('semantic_types.dg','program_ir.dg','lower_program.dg','nasm_program.dg','frontend_diagnostics.dg')
        bridge.BUILD=ROOT/'build/test/g5-panic'
        original_stage=bridge.stage_compiler
        def stage(work,wrapper=bridge.WRAPPER,mutations=None,extra=('exec.elf',)):
            wrapper=wrapper.replace('module probe.l3a_pipeline;','module probe.l3a_pipeline;\nimport bootstrap.frontend_diagnostics as diagnostic;')
            return original_stage(work,wrapper,mutations,extra)
        bridge.stage_compiler=stage
        driver=g5.diagnostic_driver()
        driver=driver.replace('extern U ABI native_lower(',
            'extern U ABI dong_frontend_diagnostic(const Source*,U,const FrontResult*,void*,U,U*);\nextern U ABI native_lower(')
        driver=driver.replace('if(rc){fprintf(stderr,"frontend status=',
            'if(rc){REQUIRE(!fr.graph.arena.n&&!fr.graph.units.n&&!fr.graph.nodes.n&&!fr.graph.types.n&&!fr.graph.info.n);'
            'char diagnostic[4096];U dn=0;REQUIRE(dong_frontend_diagnostic(catalog,sources,&fr,diagnostic,sizeof diagnostic,&dn)==0);'
            'fwrite(diagnostic,1,dn,stderr);fprintf(stderr,"frontend status=')
        bridge.DRIVER=driver
        try:bridge.L3AGlobalsTests.setUpClass()
        except BaseException:
            bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler=cls.saved
            raise
        cls.h=bridge.L3AGlobalsTests()
        cls.h.inputs[str(Path(__file__))]=g5.sha(__file__)
        cls.source_before=dict(cls.h.inputs)
        cls.runner=g5.Runner(cls.h.work/'differential')
        cls.runner.g,cls.runner.nasm,cls.runner.cc=cls.h,cls.h.nasm,cls.h.cc
        cls.cases=[]
    @classmethod
    def tearDownClass(cls):
        try:
            cls.runner.assert_inputs()
            after={p:g5.sha(p) for p in cls.source_before}
            g5.write(cls.h.work/'frozen-inputs.json',dict(before=cls.source_before,after=after,source_stable=after==cls.source_before))
            g5.require(after==cls.source_before,'frozen candidate or dependency changed')
            g5.write(cls.runner.work/'panic.json',dict(cases=cls.cases,commands=cls.runner.records,source_stable=True))
            cls.h.tearDownClass()
        finally:bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler=cls.saved
    def observe(self,asm,a,b,name):
        for fmt,suffix in [('elf64','.o'),('win64','.obj')]:
            self.runner.command([self.h.nasm,'-O0','-f',fmt,*nasm_flags(self.h.nasm),asm,'-o',asm.with_suffix(suffix)],name+'-'+fmt)
        c=asm.parent/(name+'.c')
        c.write_text('''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint64_t U;
#define ABI __attribute__((sysv_abi))
extern U ABI run_case(U,U);
extern U ABI observe_trace(void);
void ABI __dong_panic(uint32_t kind,uint32_t line,const void*path,U n){
 printf("PANIC kind=%u line=%u file=%.*s trace=%llu\\n",kind,line,(int)n,(const char*)path,(unsigned long long)observe_trace());exit(85);
}
int main(void){U n=run_case('''+str(a)+'ULL,'+str(b)+'''ULL);printf("NORMAL=%llu\\n",(unsigned long long)n);return 0;}
''')
        exe=c.with_suffix('.exe')
        self.runner.command([self.h.cc,'-std=c11','-D__USE_MINGW_ANSI_STDIO=1','-O2','-Wall','-Wextra','-Werror',c,asm.with_suffix('.obj'),'-o',exe],name+'-link')
        result=self.runner.command([exe],name+'-execute',expect=None)
        record=dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,assembly_sha256=g5.sha(asm),object_sha256=g5.sha(asm.with_suffix('.obj')),exe_sha256=g5.sha(exe))
        return record
    def test_runtime_guards_exact_panic_kind_line_file_and_no_cleanup(self):
        for name,body,a,b,kind,release in CASES:
            source=PREFIX+'export("run_case")pub fn f(a:u64,b:u64)u64{\n defer mark();\n '+body+'\n}\n'
            line=source[:source.index('/*site*/')].count('\n')+1
            directory=self.runner.source_directory(name,[('tagged.dg',source)])
            for mode in ('debug','release'):
                seed=self.observe(self.runner.seed(directory,mode),a,b,name+'-seed-'+mode)
                asm,p=self.runner.dong(directory,mode)
                self.assertEqual(p.returncode,0,p.stderr)
                target=self.observe(asm,a,b,name+'-dong-'+mode)
                expected_kind=kind
                if mode=='release' and release is not None:expected_kind=0
                if expected_kind:
                    expected=dict(returncode=85,stdout='PANIC kind='+str(expected_kind)+' line='+str(line)+' file=tagged.dg trace=0\n')
                else:
                    expected=dict(returncode=0,stdout='NORMAL='+str(release)+'\n')
                for record in (seed,target):
                    self.assertEqual(record['returncode'],expected['returncode'],record)
                    self.assertEqual(record['stdout'],expected['stdout'],record)
                self.cases.append(dict(name=name,mode=mode,seed=seed,native=target,expected=expected))
    def test_error_number_diagnostic_code_and_source_match_seed(self):
        for name,body in [('zero','error Bad=0;'),('negative','error Bad=-1;'),('large','error Bad=4294967296;'),
                          ('very-large','error Bad=18446744073709551616;'),('duplicate','error A=7;error B=7;')]:
            source='module tagged;\n'+body+'\nfn f()void{}'
            directory=self.runner.source_directory('diagnostic-'+name,[('tagged.dg',source)])
            for mode in ('debug','release'):
                with self.assertRaises(CompileError) as caught:self.runner.seed(directory,mode)
                asm,p=self.runner.dong(directory,mode)
                self.assertEqual(p.returncode,10,p.stderr)
                self.assertEqual(asm.read_bytes(),b'unchanged')
                actual=re.search(r'tagged\.dg:(\d+):(\d+): (E\d{4}):',p.stderr)
                self.assertIsNotNone(actual,p.stderr)
                self.assertEqual(actual[3],caught.exception.code)
                self.assertEqual(int(actual[1]),2)
                self.cases.append(dict(name='diagnostic-'+name,mode=mode,seed=caught.exception.code,native=p.stderr,output_unchanged=True))
    def test_z_wrong_panic_category_mutation_is_rejected(self):
        self.h.build_driver('bad-kind',{'nasm_program.dg':('immediate(s,7,kind);','immediate(s,7,kind^1);')})
        source=PREFIX+'export("run_case")pub fn f(a:u64,b:u64)u64{\n /*site*/return a/b;\n}\n'
        line=source[:source.index('/*site*/')].count('\n')+1
        directory=self.runner.source_directory('bad-kind',[('tagged.dg',source)])
        for mode in ('debug','release'):
            seed=self.observe(self.runner.seed(directory,mode),7,0,'bad-kind-seed-'+mode)
            asm,p=self.runner.dong(directory,mode,'bad-kind')
            self.assertEqual(p.returncode,0,p.stderr)
            target=self.observe(asm,7,0,'bad-kind-dong-'+mode)
            self.assertEqual(seed['returncode'],85)
            self.assertEqual(seed['stdout'],'PANIC kind=3 line='+str(line)+' file=tagged.dg trace=0\n')
            self.assertEqual(target['returncode'],85)
            self.assertEqual(target['stdout'],'PANIC kind=2 line='+str(line)+' file=tagged.dg trace=0\n')
            self.cases.append(dict(name='bad-kind',mode=mode,status='negative-rejected',seed=seed,native=target))

if __name__=='__main__':unittest.main()
