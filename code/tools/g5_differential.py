"""Bounded source differential runner. Known language gaps are never successes.

Uses the already reviewed L3A process/ABI bridges as bootstrapping utilities;
target programs are compiled independently by Python seed and real Dong code.
No fallback, target IR construction, VM, or coordinator mutation is permitted.
"""
from __future__ import annotations
import argparse
import functools
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
nasm_flags=functools.lru_cache(maxsize=8)(nasm_flags)
BASE_DRIVER=bridge.DRIVER
DEFAULT_BUILD=ROOT/'build/test/G5-full'
CANDIDATE=HERE.parent/'src/bootstrap' if HERE.parent.name=='g5-full' else ROOT/'lang/bootstrap'
CANDIDATES=('semantic_types.dg','program_ir.dg','lower_program.dg','nasm_program.dg','frontend_diagnostics.dg','native_assembler.dg')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):Path(p).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def require(ok,message):
    if not ok:raise AssertionError(message)

def bounded_driver(text):
    # These are caller-owned pools, sized above this matrix's largest input.
    # Retain every exact-minus-one, alias, guard and read-only assertion while
    # avoiding repeated hashes of hundreds of MiB of unused scratch per case.
    sizes={'alloc(64*1024*1024,1)':'alloc(8*1024*1024,1)',
           'alloc(524288,sizeof(Instruction))':'alloc(16384,sizeof(Instruction))',
           'alloc(131072,sizeof(Argument))':'alloc(8192,sizeof(Argument))',
           'alloc(262144,8)':'alloc(8192,8)',
           'alloc(32*1024*1024,1)':'alloc(2*1024*1024,1)',
           'alloc(16*1024*1024,1)':'alloc(2*1024*1024,1)'}
    for old,new in sizes.items():
        require(text.count(old)==1,'unique caller workspace '+old)
        text=text.replace(old,new)
    return text

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
 'for-range':('module gap;pub fn f()u64{var n:u64=1;for i in 1..4{n+=i;}return n;}',7,'scalar'),
 'for-array':('module gap;pub fn f()u64{let a:[3]u64=[1,2,4];var n:u64=0;for x in a{n+=x;}return n;}',7,'scalar'),
 'for-slice':('module gap;pub fn f()u64{let a:[3]u64=[1,2,4];var n:u64=0;for x in a[..]{n+=x;}return n;}',7,'scalar'),
 'bool-match':('module gap;pub fn f()u64{let p:bool=true;match p{true=>{return 7;},false=>{return 0;},}}',7,'scalar'),
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
        self.bindings={}
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
        self.saved_flags=bridge.nasm_flags
        bridge.nasm_flags=nasm_flags
        self.saved_bridge=(bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler,bridge.L3AGlobalsTests.__dict__['build_driver'])
        bridge.BUILD=self.work/'compiler'
        bridge.CAND=CANDIDATE
        bridge.CANDIDATES=CANDIDATES
        original_stage=bridge.stage_compiler
        def stage(work,wrapper=bridge.WRAPPER,mutations=None,extra=('exec.elf',)):
            if mutations is None:
                wrapper=native.WRAPPER.replace('module probe.l3a_native;','module probe.l3a_pipeline;')
            wrapper=wrapper.replace('module probe.l3a_pipeline;','module probe.l3a_pipeline;\nimport bootstrap.frontend_diagnostics as diagnostic;')
            return original_stage(work,wrapper,mutations,extra)
        bridge.stage_compiler=stage
        driver=diagnostic_driver()
        driver=driver.replace('extern U ABI native_lower(', 'extern U ABI dong_frontend_diagnostic(const Source*,U,const FrontResult*,void*,U,U*);\nextern U ABI native_lower(')
        driver=driver.replace('if(rc){fprintf(stderr,"frontend status=',
            'if(rc){REQUIRE(!fr.graph.arena.n&&!fr.graph.units.n&&!fr.graph.nodes.n&&!fr.graph.types.n&&!fr.graph.info.n);'
            'char diagnostic[4096];U dn=0;REQUIRE(dong_frontend_diagnostic(catalog,sources,&fr,diagnostic,sizeof diagnostic,&dn)==0);'
            'fwrite(diagnostic,1,dn,stderr);fprintf(stderr,"frontend status=')
        bridge.DRIVER=bounded_driver(driver)
        bridge.L3AGlobalsTests.setUpClass()
        self.g=bridge.L3AGlobalsTests()
        original_build=self.saved_bridge[-1].__func__
        mutations=[
            ('else{immediate(s,0,(*x).value);}','else{immediate(s,0,(*x).value^1);}'),
            ('i=0;while i<10{put(s,"movdqu xmm");','i=0;while i<9{put(s,"movdqu xmm");'),
            ('addr.emit(0,(*s).frame_base,-((*x).a as i64)','addr.emit(0,(*s).frame_base,-((*x).a as i64)+8'),
            ('immediate(s,7,kind);','immediate(s,7,kind^1);'),
            ('if op==ir.STATIC_ADDRESS{put(s,"lea rax, [rel ");symbol(s,(*x).value);put(s,"]\\n");return slotstore(s,0,(*x).destination);}',
             'if op==ir.STATIC_ADDRESS{put(s,"lea rax, [rel ");symbol(s,(*x).value);if (*g).symbols[(*x).value].kind==names.GLOBAL{put(s,"+8");}put(s,"]\\n");return slotstore(s,0,(*x).destination);}'),
            ('else{store(s,0,11,0,ir.width(g,t));}return (*s).status==0;','else{store(s,0,11,0,64);}return (*s).status==0;')]
        original=(CANDIDATE/'nasm_program.dg').read_bytes().decode('utf-8');bad=original
        for old,new in mutations:
            require(bad.count(old)==1,'unique combined mutant site')
            bad=bad.replace(old,new)
        aliases={'bad-tag','bad-xmm','bad-address','bad-kind','bad-static-address','bad-store'}
        def build_combined(cls,tag,requested=None):
            if tag not in aliases:return original_build(cls,tag,requested)
            if requested:
                require(requested.get('nasm_program.dg') in mutations,'unreviewed mutant request')
            driver=original_build(cls,'combined-mutant',{'nasm_program.dg':(original,bad)})
            cls.drivers[tag]=driver
            cls.provenance[tag]=cls.provenance['combined-mutant']
            return driver
        bridge.L3AGlobalsTests.build_driver=classmethod(build_combined)
        self.mutant_sites=[dict(old=a,new=b) for a,b in mutations]
        self.nasm,self.cc=self.g.nasm,self.g.cc
        self.inputs.update(self.g.inputs)
        self.bindings={}
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
        self.bindings[str(asm)]=dict(compiler_path='dong-frontend-lower-nasm',driver_sha256=sha(self.g.drivers[tag]),driver_path=str(self.g.drivers[tag]),native_compile_returncode=p.returncode,emitted_sha256=sha(asm),variant=tag)
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
        result=dict(path='actual-native-execution',exe=str(exe),assembly_path=str(asm),assembly_sha256=sha(asm),object_sha256=sha(asm.with_suffix('.obj')),exe_sha256=sha(exe),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
        binding=self.bindings.get(str(asm))
        if binding:
            require(binding['native_compile_returncode']==0 and binding['emitted_sha256']==sha(asm),'actual native compile path/output changed')
            result.update(binding)
        return result

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
                native_run=self.command([item['native']['exe'],case,int(mode=='release')],mode+'-dong-runtime-'+case,85 if guarded else 0)
                if guarded:
                    require(re.search(r'PANIC \d+ \d+',seed.stderr) is not None,'seed source guard diagnostic missing')
                    left=re.search(r'PANIC (\d+) (\d+)',seed.stderr);right=re.search(r'PANIC (\d+) (\d+)',native_run.stderr)
                    require(right is not None and left.groups()==right.groups(),'native panic category/source line differs from seed')
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
                if name in GAPS:
                    require(p.returncode==0,name+' supported path regressed; no seed fallback')
                    target=self.observe(asm,obs,name+'-dong-'+mode)
                    target.update(compiler_path='dong-frontend-lower-nasm',driver_sha256=sha(self.g.drivers['good']))
                    require((seed['stdout'],seed['returncode'])==(target['stdout'],target['returncode']),name+' differential mismatch')
                    self.cases.append(dict(name=name,mode=mode,status='supported-pass',seed=seed,native=target))
                    continue
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
        variants=[('bad-static-address','if op==ir.STATIC_ADDRESS{put(s,"lea rax, [rel ");symbol(s,(*x).value);put(s,"]\\n");return slotstore(s,0,(*x).destination);}',
                   'if op==ir.STATIC_ADDRESS{put(s,"lea rax, [rel ");symbol(s,(*x).value);if (*g).symbols[(*x).value].kind==names.GLOBAL{put(s,"+8");}put(s,"]\\n");return slotstore(s,0,(*x).destination);}'),
                  ('bad-store','else{store(s,0,11,0,ir.width(g,t));}return (*s).status==0;',
                   'else{store(s,0,11,0,64);}return (*s).status==0;')]
        store_source='module narrow;pub unsafe fn write(p:*u8)void{unsafe{*p=0x5a;}}'
        store_directory=self.source_directory('narrow-mutant',[('narrow.dg',store_source)])
        store_observer='#include <stdint.h>\n#include <stdio.h>\nextern void __attribute__((sysv_abi)) f(unsigned char*) __asm__("'+bridge.label('narrow','write')+'");\nint main(void){unsigned char b[16];for(int i=0;i<16;i++)b[i]=0xa7;f(b+4);for(int i=0;i<16;i++){if(b[i]!=(i==4?0x5a:0xa7)){fputs("narrow-store-canary\\n",stderr);return 2;}}return 0;}'
        for tag,old,new in variants:
            self.g.build_driver(tag,{'nasm_program.dg':(old,new)})
            for mode in ('debug','release'):
                directory=self.work/'globals' if tag=='bad-static-address' else store_directory
                observer=global_observer() if tag=='bad-static-address' else store_observer
                if tag=='bad-store':
                    self.observe(self.seed(directory,mode),observer,'narrow-seed-'+mode)
                    good,p=self.dong(directory,mode);require(p.returncode==0,'narrow good compile')
                    self.observe(good,observer,'narrow-good-'+mode)
                asm,p=self.dong(directory,mode,tag);require(p.returncode==0,'bad Dong must compile normally')
                observed=self.observe(asm,observer,tag+'-'+mode,expect=2)
                reason='wrong-global-address' if tag=='bad-static-address' else 'narrow-store-canary'
                require(reason in observed['stderr'],'exact semantic oracle did not reject bad Dong')
                self.negatives.append(dict(name=tag,mode=mode,status='rejected-semantic',observed=observed,reason=reason))
        # Exercise a real native CAPACITY failure on a valid same-source case.
        # Only the C caller's instruction pool is shortened; target compiler
        # bytes and all target source remain unchanged.
        stage=Path(self.g.drivers['good']).parent
        c=stage/'capacity-driver.c';text=(stage/'driver.c').read_text()
        needle='alloc(16384,sizeof(Instruction))'
        require(text.count(needle)==1,'unique real instruction pool capacity')
        c.write_text(text.replace(needle,'alloc(0,sizeof(Instruction))'))
        exe=stage/'capacity-driver.exe'
        self.command([self.cc,'-std=c11','-D_GNU_SOURCE','-D__USE_MINGW_ANSI_STDIO=1','-O2','-Wall','-Wextra','-Werror',c,stage/'wrapper.obj','-o',exe],'capacity-driver-link')
        self.g.drivers['capacity']=exe
        for mode in ('debug','release'):
            asm,failed=self.dong(self.work/'globals',mode,'capacity')
            require(failed.returncode==11 and 'lower status=2' in failed.stderr and asm.read_bytes()==b'unchanged','real native capacity rejection missing')
            seed=next(x['seed'] for x in self.cases if x['name']=='globals' and x['mode']==mode)
            rejected=dict(name='real-native-capacity',mode=mode,status='failure',seed=seed,native=dict(returncode=failed.returncode,stderr=failed.stderr))
            forged=self.work/('fallback-bad-'+mode+'.py')
            forged.write_text('import json\nr=json.loads('+repr(json.dumps(rejected))+')\nr["native"]=r["seed"]\nr["status"]="supported-pass"\nprint(json.dumps(r))\n')
            p=self.command([sys.executable,forged],'actual-bad-runner-fallback-'+mode)
            fake=json.loads(p.stdout)
            try:validate_path(fake)
            except AssertionError as e:self.negatives.append(dict(name='seed-fallback',mode=mode,status='rejected-provenance',reason=str(e),body_sha256=sha(forged),real_native_failure=rejected['native']))
            else:raise AssertionError('bad seed fallback was accepted')

    def native_container(self):
        # Relink a second independent C caller against this run's exact cold
        # compiler object, which exports native_assemble and kernel_validate.
        cls=native.L3ANativeRegressionTests
        stage=Path(self.g.drivers['good']).parent
        cls.work=self.work/'container';cls.work.mkdir()
        cls.nasm,cls.cc=self.nasm,self.cc
        cls.stage=stage;cls.provenance=self.g.provenance['good'];cls.inputs=dict(self.g.inputs);cls.records=[]
        c=cls.work/'driver.c'
        raw_failure='if(rc!=0){return 0;}'
        require(native.DRIVER.count(raw_failure)==1,'unique raw failure check')
        checked=native.DRIVER.replace(raw_failure,'if(rc!=0){for(U k=0;k<out.n;k++)REQUIRE(((unsigned char*)out.p)[k]==0xa5);printf("RAW-REJECT unchanged=1\\n");return 0;}')
        c.write_text(checked)
        cls.driver=cls.work/'driver.exe'
        obj=stage/('wrapper.obj' if os.name=='nt' else 'wrapper.elf.o')
        cls.command([self.cc,'-std=c11','-D_GNU_SOURCE','-D__USE_MINGW_ANSI_STDIO=1','-O2','-Wall','-Wextra','-Werror',* ([] if os.name=='nt' else ['-no-pie']),c,obj,'-o',cls.driver],'driver-link')
        mapper=cls.work/'mapper.c';mapper.write_text(native.MAPPER)
        cls.mapper=cls.work/('mapper.exe' if os.name=='nt' else 'mapper')
        cls.command([self.cc,'-std=c11','-D_GNU_SOURCE','-D__USE_MINGW_ANSI_STDIO=1','-O2','-Wall','-Wextra','-Werror',* (['-Wl,--image-base=0x100000000'] if os.name=='nt' else []),mapper,'-o',cls.mapper],'mapper-link')
        n=cls()
        try:
            source='module native;\nexport("__dong_panic")fn panic(k:u32,line:u32,p:*const u8,n:usize)noreturn{loop{}}\npub const fixed:[3]u16=[0x11,0x2233,0x4455];\npub var values:[4]u16=[3,5,7,11];pub struct Bag{pub tag:u8,pub word:u32}\npub var bag:Bag=Bag{tag:0xaa,word:0x12345678};pub var p:*u16=&values[2];pub var q:*u32=&bag.word;\npub var r:*const u16=&fixed[1];pub var obs:[8]u64=[0;8];\npub fn probe()*u64{unsafe{obs[0]=*p as u64;obs[1]=*q as u64;obs[2]=*r as u64;*p=0xbeef;*q=0xaabbccdd;\nobs[3]=values[2]as u64;obs[4]=bag.word as u64;obs[5]=*r as u64;\nif p==&values[2]{obs[6]=4;}else{obs[6]=999;}if q==&bag.word{obs[7]=4;}else{obs[7]=999;}}\nreturn &obs[0];}\n'
            target_dir,asm,elf,_=n.pipeline(source,bridge.label('native','probe'),'g5-fixed-pointers')
            text=asm.read_text()
            require('extern $__dong_panic' not in text and 'global $__dong_panic' in text,'target-provided panic definition was not linked internally')
            for name,offset in [('values',4),('bag',4),('fixed',2)]:require('dq '+bridge.label('native',name)+'+'+str(offset) in text,'static relocation changed')
            require(n.command([n.driver,'validate',elf],'full-kernel-validate').stdout.strip()=='VALIDATE 0','kernel ELF validation failed')
            actual=n.execute(elf,'400000',8)
            require(actual==[7,0x12345678,0x2233,0xbeef,0xaabbccdd,0x2233,4,4],'native ELF pointer/data oracle differs')
            for name,body,success in [
                ('resolved-extern','extern supplied\nsection .text\nglobal _start\n_start:\ncall supplied\nret\nsupplied:\nmov rax, 37\nret\n',True),
                ('unresolved-extern','extern supplied\nsection .text\nglobal _start\n_start:\nmov rax, 37\nret\n',False)]:
                raw=cls.work/(name+'.asm');raw.write_text('bits 64\n'+body)
                output=raw.with_suffix('.elf');output.write_bytes(b'unchanged')
                report=n.command([n.driver,'raw',raw,'_start',output],name).stdout
                if success:
                    require('RAW status=0 ' in report and output.read_bytes()[:4]==b'\x7fELF','resolved runtime definition rejected')
                    require('RAW-CAP status=2 written=0 unchanged=1' in report,'resolved runtime capacity atomicity')
                else:
                    require('RAW status=4 ' in report and 'RAW-REJECT unchanged=1' in report,'unresolved declaration did not reject atomically')
                    require(output.read_bytes()==b'unchanged','unresolved ELF published')
            source_path=target_dir/'native.dg'
            require(source_path.read_text()==source,'native target source changed')
            require(hashlib.sha256(source_path.read_text().encode()).hexdigest()==hashlib.sha256(source.encode()).hexdigest(),'native target source changed')
            self.inputs[str(source_path)]=sha(source_path)
            self.container=dict(passed=True,path=str(n.work),compiler_object_sha256=sha(obj),assembly_sha256=sha(asm),elf_sha256=sha(elf),observations=actual,execution='real native_assembler ELF at original 0x400000, same cold compiler object, target runtime linked, static pointers unchanged')
        finally:
            native.L3ANativeRegressionTests.tearDownClass()

    def finish(self):
        try:
            self.g.tearDownClass()
            after=self.assert_inputs()
        finally:
            bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler,bridge.L3AGlobalsTests.build_driver=self.saved_bridge
            bridge.nasm_flags=self.saved_flags
        compiler=dict(path=str(self.g.drivers['good']),sha256=sha(self.g.drivers['good']),provenance=self.g.provenance,bootstrap_commands=self.g.records)
        result=dict(runner_scope_passed=True,scope_complete=False,remaining=sorted({case['name'] for case in self.gaps}),supported_pass=self.cases,runtime_checks=self.runtime,diagnostic_pass=self.diagnostic_cases,known_gap=self.gaps,negative_controls=self.negatives,combined_mutant_sites=self.mutant_sites,failure=[],skip=[],native_container=getattr(self,'container',dict(passed=False)),source_before=self.inputs,source_after=after,source_stable=True,environment=self.environment,compiler=compiler,commands=self.records)
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
