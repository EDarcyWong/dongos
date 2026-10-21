"""Bounded source differential runner. Known language gaps are never successes.

Uses the already reviewed L3A process/ABI bridges as bootstrapping utilities;
target programs are compiled independently by Python seed and real Dong code.
No fallback, target IR construction, VM, or coordinator mutation is permitted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import struct
import sys
import uuid

HERE=Path(__file__).resolve()
WORKS=HERE.parents[2]
ROOT=WORKS
if (HERE.parents[1]/'lang/dongc').is_dir():
    ROOT=HERE.parents[1];WORKS=ROOT
elif not (ROOT/'lang').is_dir():
    location=Path(json.loads((WORKS/'project.json').read_text())['source_root'])
    ROOT=location if location.is_absolute() else (WORKS/location).resolve()
sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.tests import test_l3a_globals as bridge
from lang.tests import test_l3a_native_regression as native
from lang.tests import test_bootstrap_native_compiler as audit
from lang.tests.test_dongc import nasm_flags
BASE_DRIVER=bridge.DRIVER
DEFAULT_BUILD=ROOT/'build/test/G5' if WORKS==ROOT else WORKS/'deepseek-works/build/L3'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):Path(p).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def require(ok,message):
    if not ok:raise AssertionError(message)

def diagnostic_driver():
    # Read the real frontend's checked Unit/Node/Token records. This is only
    # diagnostic serialization, never host construction of target AST or IR.
    marker='if(rc){REQUIRE(unpublished(&lr));fprintf(stderr,"lower status='
    addition='''if(rc && lr.unit<fr.graph.units.n){
 U*u=(U*)fr.graph.units.p+lr.unit*9;
 if(lr.node<u[7]){U*n=(U*)fr.graph.nodes.p+(u[6]+lr.node)*8;
  if(u[2]+n[1]<fr.graph.tokens.n){U*t=(U*)fr.graph.tokens.p+(u[2]+n[1])*7;
   fprintf(stderr,"LOCATION source=%llu node=%llu offset=%llu line=%llu column=%llu\\n",(unsigned long long)u[0],(unsigned long long)lr.node,(unsigned long long)t[1],(unsigned long long)t[3],(unsigned long long)t[4]);
  }
 }
}
'''
    require(BASE_DRIVER.count(marker)==1,'single diagnostic wrapper boundary')
    return BASE_DRIVER.replace(marker,addition+marker)

GLOBALS='''module main;
import dep as dep;
pub var before:u64=0x1122334455667788;
pub var a:u8=0x11;pub var b:u8=0x22;
pub var after:u64=0x8877665544332211;
pub struct Bag{pub tag:u8,pub word:u32,pub tail:u16}
pub var bag:Bag=Bag{tag:0x5a,word:0x12345678,tail:0xbeef};
pub var trace:u64=0;
pub const words:[3]u16=[3,5,7];
pub var shared:u64=33;
fn touch()bool{trace+=1;return true;}
pub fn shorted(a:bool)bool{return a&&touch();}
pub fn looped()u64{var i:u64=0;var n:u64=0;while i<10{i+=1;if i==3{continue;}if i==8{break;}n+=i;}return n;}
pub fn read()u64{return before;}
pub fn bump()u64{a+=1;return a as u64;}
pub fn cross()u64{return shared+dep.shared+dep.bump();}
pub fn size()usize{return sizeof(Bag);}
pub fn constant()u64{return (words[0] as u64)+(words[1] as u64)+(words[2] as u64);}
'''
DEP='module dep;pub var shared:u64=11;pub fn bump()u64{shared+=1;return shared;}\n'

def global_observer():
    declarations=[]
    for name in ('read','bump','cross','size','constant','looped'):
        declarations.append('extern U ABI f_'+name+'(void) __asm__("'+bridge.label('main',name)+'");')
    declarations.append('extern _Bool ABI f_shorted(_Bool) __asm__("'+bridge.label('main','shorted')+'");')
    for name in ('before','after','trace'):
        declarations.append('extern U g_'+name+' __asm__("'+bridge.label('main',name)+'");')
    for name in ('a','b','bag'):
        declarations.append('extern unsigned char g_'+name+'[] __asm__("'+bridge.label('main',name)+'");')
    return '''#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t U;
#define ABI __attribute__((sysv_abi))
'''+ '\n'.join(declarations)+r'''
int main(void){
 const unsigned char bag[12]={0x5a,0,0,0,0x78,0x56,0x34,0x12,0xef,0xbe,0,0};
 if(f_read()!=0x1122334455667788ULL){fprintf(stderr,"wrong-global-address\n");return 2;}
 if(f_bump()!=0x12||g_a[0]!=0x12||g_b[0]!=0x22){fprintf(stderr,"narrow-store-canary\n");return 2;}
 if(g_before!=0x1122334455667788ULL||g_after!=0x8877665544332211ULL)return 3;
 if(memcmp(g_bag,bag,12)||f_size()!=12||f_constant()!=15||f_looped()!=25)return 4;
 if(f_shorted(0)||g_trace!=0||!f_shorted(1)||g_trace!=1)return 5;
 if(f_cross()!=56)return 6;
 printf("GLOBAL values=1 padding=12 trace=%llu loops=25 cross=56\n",(unsigned long long)g_trace);return 0;
}'''

GAPS={
 'method':('module gap;struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x;}}pub fn f()u64{var s=S{x:7};return get(&s);}',7,'scalar'),
 'enum':('module gap;enum E{A,B(u64)}pub fn f()u64{let x=E.B(7);match x{E.A=>{return 0;},E.B(n)=>{return n;},}}',7,'scalar'),
 'error':('module gap;error Bad=7;pub fn f()!u64{return error.Bad;}',7,'error'),
 'try':('module gap;fn g()!u64{return 7;}pub fn f()!u64{return try g();}',7,'result'),
 'orelse':('module gap;pub fn f()u64{let x:?u64=null;return x orelse 7;}',7,'scalar'),
 'defer':('module gap;pub var x:u64=0;fn add()void{x+=1;}pub fn f()u64{defer add();return 7;}',7,'scalar'),
 'extern-sysv':('module gap;pub extern "sysv64" fn f()u64{return 7;}',7,'scalar'),
 'extern-win64':('module gap;pub extern "win64" fn f()u64{return 7;}',7,'windows'),
}

class Runner:
    def __init__(self,output=None):
        self.work=Path(output or DEFAULT_BUILD/('run-'+uuid.uuid4().hex[:12])).resolve()
        self.work.mkdir(parents=True,exist_ok=False)
        self.records=[];self.cases=[];self.gaps=[];self.negatives=[];self.runtime=[];self.diagnostic_cases=[]
        self.inputs={str(p):sha(p) for base in [ROOT/'lang/bootstrap',ROOT/'lang/dongc'] for p in base.rglob('*') if p.is_file() and p.suffix in ('.py','.dg')}
        for p in [Path(__file__),Path(bridge.__file__),Path(native.__file__),Path(audit.__file__)]:self.inputs[str(p)]=sha(p)
        self.environment={k:os.environ[k] for k in ('NASM','CC','PYTHONUTF8') if k in os.environ}

    def command(self,args,name,expect=0):
        command=list(map(str,args));timed_out=False
        try:p=subprocess.run(command,capture_output=True,text=True,timeout=600)
        except subprocess.TimeoutExpired as e:
            self.records.append(dict(name=name,command=command,timed_out=True,stdout=str(e.stdout),stderr=str(e.stderr)))
            raise
        self.records.append(dict(name=name,command=command,returncode=p.returncode,timed_out=timed_out,stdout=p.stdout,stderr=p.stderr))
        write(self.work/'processes.json',self.records)
        if expect is not None:require(p.returncode==expect,name+': '+str(p.returncode)+'\n'+p.stdout+p.stderr)
        return p

    def boot(self):
        # Reuse only reviewed host allocation/ABI utilities. The compiler under
        # test is rebuilt from current production Dong sources, with provenance.
        bridge.BUILD=self.work/'compiler'
        bridge.CAND=ROOT/'lang/bootstrap'
        bridge.DRIVER=diagnostic_driver()
        bridge.L3AGlobalsTests.setUpClass()
        self.g=bridge.L3AGlobalsTests()
        self.nasm,self.cc=self.g.nasm,self.g.cc
        objcopy=Path(self.cc).with_name('objcopy.exe' if os.name=='nt' else 'objcopy')
        for program in (self.nasm,self.cc,objcopy):self.command([program,'--version'],'tool-version')
        self.command([sys.executable,'--version'],'python-version')
        self.abi=self.work/'abi.asm';self.abi.write_text(audit.ABI_PROBE)
        self.abi_obj=self.abi.with_suffix('.obj')
        self.command([self.nasm,'-f','win64',*nasm_flags(self.nasm),self.abi,'-o',self.abi_obj],'abi-object')

    def source_directory(self,name,sources):
        directory=self.work/name;directory.mkdir()
        for i,(path,text) in enumerate(sources):
            if path=='main.dg':path=re.search(r'module\s+([\w.]+)\s*;',text)[1].replace('.','/')+'.dg'
            target=directory/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
            self.inputs[str(target)]=sha(target)
            if i==0:(directory/'.entry').write_text(path)
        return directory

    def assert_inputs(self):
        after={p:sha(p) for p in self.inputs}
        require(after==self.inputs,'production compiler or generated target source changed')
        return after

    def seed(self,directory,mode):
        self.assert_inputs()
        before={str(p):sha(p) for p in directory.glob('*.dg')}
        result=compile_file(directory/(directory/'.entry').read_text(),roots=[directory,ROOT/'lang/std'],mode=mode)
        require(before=={p:sha(p) for p in before},'target source changed in seed')
        asm=directory/('seed-'+mode+'.asm');asm.write_text(result.assembly)
        return asm

    def dong(self,directory,mode,tag='good'):
        self.assert_inputs()
        entry=(directory/'.entry').read_text()
        sources=sorted(directory.glob('*.dg'),key=lambda p:(p.name!=entry,p.name))
        listing=directory/'sources.list';listing.write_text(''.join(p.name+'='+str(p)+'\n' for p in sources))
        asm=directory/(tag+'-'+mode+'.asm');asm.write_bytes(b'unchanged')
        p=self.command([self.g.drivers[tag],listing,'multi',asm,int(mode=='release')],directory.name+'-'+tag+'-'+mode,expect=None)
        return asm,p

    def observe(self,asm,observer,name,abi=False,expect=0):
        for fmt,suffix in [('elf64','.o'),('win64','.obj')]:
            self.command([self.nasm,'-O0','-f',fmt,*nasm_flags(self.nasm),asm,'-o',asm.with_suffix(suffix)],name+'-'+fmt)
        if asm.name.startswith('seed-'):
            # The seed keeps ordinary symbols local and uses a different name
            # encoding. Only expose existing object symbols to the observation
            # bridge; never edit the emitted target source/instructions/data.
            text=asm.read_text();mapping={}
            for module,item in re.findall(r'__dong_m([0-9a-f]+)_n([0-9a-f]+)',observer):
                found=[f'__dg_m{module}_{kind}{item}' for kind in ('f','g') if f'$__dg_m{module}_{kind}{item}:' in text]
                require(len(found)==1,'unique seed observation symbol')
                mapping[f'__dong_m{module}_n{item}']=found[0]
            original=asm.with_suffix('.obj').read_bytes()
            asm.with_suffix('.private.obj').write_bytes(original)
            def sections(data):
                count=struct.unpack_from('<H',data,2)[0];optional=struct.unpack_from('<H',data,16)[0];items=[]
                for i in range(count):
                    at=20+optional+i*40;n,p=struct.unpack_from('<II',data,at+16)
                    items.append((data[at:at+8],n,data[p:p+n] if p else b''))
                return items
            objcopy=Path(self.cc).with_name('objcopy.exe' if os.name=='nt' else 'objcopy')
            require(objcopy.is_file(),'objcopy required to expose seed observation symbols')
            self.command([objcopy,*['--globalize-symbol='+s for s in mapping.values()],asm.with_suffix('.obj')],name+'-seed-symbol-visibility')
            before_sections=sections(original);after_sections=sections(asm.with_suffix('.obj').read_bytes())
            require(len(before_sections)==len(after_sections),'observer visibility changed sections')
            for (left,n,a),(right,m,b) in zip(before_sections,after_sections):
                # BFD pads COFF raw section sizes to their existing alignment.
                # Every emitted byte must remain exact; only zero tail padding
                # outside the original compiler section is allowed.
                require(left==right and m>=n and b[:len(a)]==a and not any(b[len(a):]),'observer visibility changed emitted target code/data')
            for old,new in mapping.items():observer=observer.replace(old,new)
        panic='''
#include <stdlib.h>
#include <stdio.h>
#ifdef _WIN32
#include <windows.h>
static LONG WINAPI guard_observer(EXCEPTION_POINTERS*p){
 if(p->ExceptionRecord->ExceptionCode==EXCEPTION_ILLEGAL_INSTRUCTION && *(const unsigned short*)p->ExceptionRecord->ExceptionAddress==0x0b0f){fprintf(stderr,"NATIVE_UD2_GUARD\\n");ExitProcess(86);}
 return EXCEPTION_CONTINUE_SEARCH;
}
static void __attribute__((constructor)) install_observer(void){SetErrorMode(SEM_NOGPFAULTERRORBOX);AddVectoredExceptionHandler(1,guard_observer);}
#endif
void __attribute__((sysv_abi)) __dong_panic(uint32_t kind,uint32_t line,const void*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"PANIC %u %u\\n",kind,line);exit(85);}
'''
        source=asm.parent/(name+'.c');source.write_text(observer+panic)
        exe=source.with_suffix('.exe')
        self.command([self.cc,'-std=c11','-D__USE_MINGW_ANSI_STDIO=1','-O2','-Wall','-Wextra','-Werror',source,asm.with_suffix('.obj'),*([self.abi_obj] if abi else []),'-o',exe],name+'-link')
        p=self.command([exe],name+'-observe',expect)
        return dict(path='actual-native-execution',exe=str(exe),assembly_path=str(asm),assembly_sha256=sha(asm),object_sha256=sha(asm.with_suffix('.obj')),exe_sha256=sha(exe),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)

    def supported(self):
        audit_source=audit.AUDIT+'\npub fn returned_slice(s:[]const u8)[]const u8{return s;}\n'
        observer=audit.AUDIT_OBSERVER
        observer=re.sub(r'extern (int64_t|U|int8_t|uint8_t|_Bool)(\*?) (\w+)\s*\(',r'extern \1\2 __attribute__((sysv_abi)) \3(',observer)
        observer=observer.replace('int main(int argc,char**argv){','extern Slice __attribute__((sysv_abi)) pair(Slice) __asm__("'+bridge.label('audit','returned_slice')+'");\nint main(int argc,char**argv){')
        observer=observer.replace('printf("{\\"audit\\":true', 'Slice returned=pair((Slice){bytes,7});CHECK(returned.p==bytes&&returned.n==7);\n printf("{\\"audit\\":true')
        self.audit_observer=observer
        for name,sources,c_observer,abi in [('audit',[('main.dg',audit_source)],observer,True),('globals',[('main.dg',GLOBALS),('dep.dg',DEP)],global_observer(),False)]:
            directory=self.source_directory(name,sources)
            for mode in ('debug','release'):
                seed=self.observe(self.seed(directory,mode),c_observer,name+'-seed-'+mode,abi)
                asm,p=self.dong(directory,mode)
                require(p.returncode==0,'native supported path failed; never seed fallback')
                target=self.observe(asm,c_observer,name+'-dong-'+mode,abi)
                target.update(compiler_path='dong-frontend-lower-nasm',driver_sha256=sha(self.g.drivers['good']))
                require((seed['stdout'],seed['returncode'])==(target['stdout'],target['returncode']),'differential first output mismatch')
                self.cases.append(dict(name=name,mode=mode,status='supported-pass',sources={p.name:sha(p) for p in directory.glob('*.dg')},seed=seed,native=target))
        for item in [c for c in self.cases if c['name']=='audit']:
            mode=item['mode']
            for case in ('add','sub','neg-one','neg-max','neg-min','neg8','narrow','bounds','shift','divide','divide-zero'):
                guarded=mode=='debug' or case in ('bounds','shift','divide','divide-zero')
                seed=self.command([item['seed']['exe'],case,int(mode=='release')],mode+'-seed-runtime-'+case,85 if guarded else 0)
                native_run=self.command([item['native']['exe'],case,int(mode=='release')],mode+'-dong-runtime-'+case,(86 if os.name=='nt' else -4) if guarded else 0)
                if guarded:
                    require(re.search(r'PANIC \d+ \d+',seed.stderr) is not None,'seed source guard diagnostic missing')
                    if os.name=='nt':require('NATIVE_UD2_GUARD' in native_run.stderr,'native guard was not an exact observed UD2')
                self.runtime.append(dict(case=case,mode=mode,guarded=guarded,seed_returncode=seed.returncode,native_returncode=native_run.returncode,seed_diagnostic=seed.stderr,native_diagnostic=native_run.stderr))
        # Generated numeric vectors use a fixed PRNG seed, independent values.
        import random
        rng=random.Random(20261022)
        vectors=[(rng.randrange(256),rng.randrange(1,16)) for _ in range(12)]
        source='module generated;pub fn f(x:u64,n:u64)u64{return wrapping_add(x,n)*3;}\n'
        calls=''.join('if(f('+str(a)+','+str(b)+')!='+str((a+b)*3)+')return 2;' for a,b in vectors)
        obs='#include <stdint.h>\nextern uint64_t __attribute__((sysv_abi)) f(uint64_t,uint64_t) __asm__("'+bridge.label('generated','f')+'");\nint main(void){'+calls+'return 0;}'
        directory=self.source_directory('generated',[('main.dg',source)])
        for mode in ('debug','release'):
            s=self.observe(self.seed(directory,mode),obs,'generated-seed-'+mode)
            asm,p=self.dong(directory,mode);require(p.returncode==0,'generated native failed')
            n=self.observe(asm,obs,'generated-dong-'+mode)
            n.update(compiler_path='dong-frontend-lower-nasm',driver_sha256=sha(self.g.drivers['good']))
            self.cases.append(dict(name='generated',mode=mode,status='supported-pass',seed=s,native=n,prng_seed=20261022,vectors=vectors))

    def known_gaps(self):
        for name,(source,value,kind) in GAPS.items():
            directory=self.source_directory('gap-'+name,[('main.dg',source)])
            if kind in ('error','result'):
                ret='Pair';check='Pair p=f();return '+('p.tag!=7||p.value!=0;' if kind=='error' else 'p.tag!=0||p.value!=7;')
            else:ret='uint64_t';check='return f()!=7;'
            abi='ms_abi' if kind=='windows' else 'sysv_abi'
            obs='#include <stdint.h>\ntypedef struct{uint64_t tag,value;}Pair;\nextern '+ret+' __attribute__(('+abi+')) f(void) __asm__("'+bridge.label('gap','f')+'");\nint main(void){'+check+'}'
            for mode in ('debug','release'):
                seed=self.observe(self.seed(directory,mode),obs,name+'-seed-'+mode)
                asm,p=self.dong(directory,mode)
                require(p.returncode in (10,11,12),'known gap changed status; review scope explicitly')
                require(asm.read_bytes()==b'unchanged','failed native output was published')
                status=re.search(r'(frontend|lower|emit) status=(\d+)([^\n]*)',p.stderr)
                require(status is not None,'precise native gap diagnostic missing')
                source_bytes=(directory/(directory/'.entry').read_text()).read_bytes()
                if status[1]=='frontend':
                    location=re.search(r'source=(\d+) offset=(\d+)',p.stderr);require(location is not None,'frontend source location missing')
                    source_index,offset=map(int,location.groups());node=None
                    line=source_bytes[:offset].count(b'\n')+1;column=offset-(source_bytes[:offset].rfind(b'\n')+1)+1
                else:
                    location=re.search(r'LOCATION source=(\d+) node=(\d+) offset=(\d+) line=(\d+) column=(\d+)',p.stderr)
                    require(location is not None,'native lower source location missing')
                    source_index,node,offset,line,column=map(int,location.groups())
                require(source_index==0 and offset<len(source_bytes) and line>0 and column>0,'bounded original source diagnostic')
                self.gaps.append(dict(name=name,mode=mode,status='known-gap',source_sha256=sha(directory/(directory/'.entry').read_text()),seed=seed,native=dict(stage=status[1],status=int(status[2]),detail=status[3],returncode=p.returncode,output_unchanged=True,stderr=p.stderr,source=source_index,node=node,offset=offset,line=line,column=column)))

    def diagnostics(self):
        directory=self.source_directory('private-diagnostic',[('main.dg','module main;import dep as dep;pub fn f()u64{return dep.secret;}'),('dep.dg','module dep;var secret:u64=7;')])
        for mode in ('debug','release'):
            try:self.seed(directory,mode)
            except Exception as e:
                require(type(e).__name__=='CompileError','seed private failure must be a compiler diagnostic')
                seed=dict(category=str(getattr(e,'code','')),message=str(e))
            else:raise AssertionError('seed accepted private global access')
            asm,p=self.dong(directory,mode)
            require(p.returncode==10 and 'frontend status=' in p.stderr and asm.read_bytes()==b'unchanged','native private access did not fail closed in frontend')
            self.diagnostic_cases.append(dict(name='private-module-global',mode=mode,status='diagnostic-pass',seed=seed,native=p.stderr))

    def negative_controls(self):
        variants=[('bad-address','if op==ir.STATIC_ADDRESS{put(s,"lea rax, [rel ");symbol(s,(*x).value);put(s,"]\\n");return slotstore(s,0,(*x).destination);}',
                   'if op==ir.STATIC_ADDRESS{put(s,"lea rax, [rel ");symbol(s,(*x).value);if (*g).symbols[(*x).value].kind==names.GLOBAL{put(s,"+8");}put(s,"]\\n");return slotstore(s,0,(*x).destination);}'),
                  ('bad-store','else{store(s,0,11,0,ir.width(g,t));}return (*s).status==0;',
                   'else{store(s,0,11,0,64);}return (*s).status==0;')]
        for tag,old,new in variants:
            self.g.build_driver(tag,{'nasm_program.dg':(old,new)})
            for mode in ('debug','release'):
                asm,p=self.dong(self.work/'globals',mode,tag);require(p.returncode==0,'bad Dong must compile normally')
                observed=self.observe(asm,global_observer(),tag+'-'+mode,expect=2)
                reason='wrong-global-address' if tag=='bad-address' else 'narrow-store-canary'
                require(reason in observed['stderr'],'exact semantic oracle did not reject bad Dong')
                self.negatives.append(dict(name=tag,mode=mode,status='rejected-semantic',observed=observed,reason=reason))
        # A functioning bad runner body actually attempts fallback on a real
        # rejected extern case. Provenance validation must reject its output.
        rejected=self.gaps[-1]
        forged=self.work/'fallback-bad.py'
        forged.write_text('import json\nr=json.loads('+repr(json.dumps(rejected))+')\nr["native"]=r["seed"]\nr["status"]="supported-pass"\nprint(json.dumps(r))\n')
        p=self.command([sys.executable,forged],'actual-bad-runner-fallback')
        fake=json.loads(p.stdout)
        try:validate_path(fake)
        except AssertionError as e:self.negatives.append(dict(name='seed-fallback',status='rejected-provenance',reason=str(e),body_sha256=sha(forged)))
        else:raise AssertionError('bad seed fallback was accepted')

    def native_container(self):
        native.BUILD=self.work/'container';native.CAND=ROOT/'lang/bootstrap'
        native.L3ANativeRegressionTests.setUpClass();n=native.L3ANativeRegressionTests()
        try:
            n.test_fixed_address_static_pointer_initializers_execute()
            self.container=dict(passed=True,path=str(n.work),execution='real native_assembler ELF at original 0x400000, static pointers unchanged')
        finally:native.L3ANativeRegressionTests.tearDownClass()

    def finish(self):
        self.g.tearDownClass()
        after=self.assert_inputs()
        compiler=dict(path=str(self.g.drivers['good']),sha256=sha(self.g.drivers['good']),provenance=self.g.provenance,bootstrap_commands=self.g.records)
        result=dict(runner_scope_passed=True,scope_complete=False,remaining=sorted(GAPS),supported_pass=self.cases,runtime_checks=self.runtime,diagnostic_pass=self.diagnostic_cases,known_gap=self.gaps,negative_controls=self.negatives,failure=[],skip=[],native_container=self.container,source_before=self.inputs,source_after=after,source_stable=True,environment=self.environment,compiler=compiler,commands=self.records)
        write(self.work/'coverage.json',result);return result

    def run(self):
        self.boot();self.supported();self.known_gaps();self.diagnostics();self.negative_controls();self.native_container();return self.finish()

def validate_path(case):
    require(case['status']=='supported-pass','case has no native success')
    n=case['native']
    require(n.get('path')=='actual-native-execution' and n.get('returncode')==0,'native pipeline did not complete')
    require(n.get('compiler_path')=='dong-frontend-lower-nasm' and len(n.get('driver_sha256',''))==64,'native compiler provenance missing; seed fallback forbidden')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    r=Runner(args.output);result=r.run();print(json.dumps(dict(coverage=str(r.work/'coverage.json'),runner_scope_passed=result['runner_scope_passed'],scope_complete=result['scope_complete'],remaining=result['remaining'])))
if __name__=='__main__':main()
