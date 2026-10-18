"""Actual Dong NASM branch emit over integrated CR6 branch_plan + CR4 decimals."""
import hashlib
import json
import os
from pathlib import Path
import random
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
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_branch_emit.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_branch_emit.md'
OK,INVALID,CAPACITY=0,1,2
MAX=0xffff_ffff_ffff_ffff
EQ,NE,ULT,ULE,UGT,UGE,SLT,SLE,SGT,SGE=range(10)
INVERT={EQ:NE,NE:EQ,ULT:UGE,ULE:UGT,UGT:ULE,UGE:ULT,SLT:SGE,SLE:SGT,SGT:SLE,SGE:SLT}
MNEM={0:b'je',1:b'jne',2:b'jb',3:b'jbe',4:b'ja',5:b'jae',6:b'jl',7:b'jle',8:b'jg',9:b'jge'}
WRAPPER='''module probe.nasm_branch_emit_export;
import bootstrap.nasm_branch_emit as b;
export("dong_nasm_branch_emit") pub unsafe fn emit(
 condition:u64,yes:u64,no:u64,fallthrough:u64,out:*u8,no_out:usize,written:*usize)u64{unsafe{
 return b.emit(condition,yes,no,fallthrough,slice_from_raw_parts(out,no_out),written);
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
extern uint64_t ABI dong_nasm_branch_emit(uint64_t,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=14;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"je __dong_b1\n",13);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_branch_emit(0,1,2,2,o,128,NULL);break;
   case 1:st=dong_nasm_branch_emit(0,1,2,2,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_branch_emit(0,1,2,2,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_branch_emit(0,1,2,2,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_nasm_branch_emit(0,1,2,2,NULL,128,w);break;
   case 5:st=dong_nasm_branch_emit(0,1,2,2,o,128,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_branch_emit(10,1,2,2,o,128,w);break;
   case 7:st=dong_nasm_branch_emit(0,UINT64_MAX,2,2,o,128,w);break;
   case 8:st=dong_nasm_branch_emit(0,1,UINT64_MAX,2,o,128,w);break;
   case 9:st=dong_nasm_branch_emit(0,1,2,2,FAKE(UINT64_MAX-7),128,w);break;
   case 10:st=dong_nasm_branch_emit(0,1,2,2,o,0,(uint64_t*)(uintptr_t)1);break;
   case 11:st=dong_nasm_branch_emit(10,1,2,2,o,0,w);break;
   case 12:st=dong_nasm_branch_emit(99,1,2,2,o,128,w);break;
   default:st=dong_nasm_branch_emit(0,UINT64_MAX,UINT64_MAX,0,o,0,w);break;
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
  uint64_t h[6];read_exact(h,sizeof(h));
  uint64_t cond=h[0],yes=h[1],no=h[2],ft=h[3],cap=h[4],nout=h[5];
  if(cap>512)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_branch_emit(cond,yes,no,ft,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def plan_fields(condition,yes,no,fallthrough):
    if condition>9 or yes==MAX or no==MAX:return None
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
    return has_cond,cond,ct,has_jump,jt


def lab(n):
    return b'__dong_b'+str(n).encode()


def expected_text(condition,yes,no,fallthrough):
    p=plan_fields(condition,yes,no,fallthrough)
    if p is None:return None
    has_cond,cond,ct,has_jump,jt=p
    parts=[]
    if has_cond:parts.append(MNEM[cond]+b' '+lab(ct)+b'\n')
    if has_jump:parts.append(b'jmp '+lab(jt)+b'\n')
    return b''.join(parts)


def item(condition,yes,no,fallthrough,cap=None,status=None,nout=0):
    text=expected_text(condition,yes,no,fallthrough)
    if nout and cap and status is None and text is not None and len(text)>0:status=INVALID
    if status is None:
        if text is None:status=INVALID
        else:
            need=len(text)
            if cap is None:cap=need if need else 0
            if need==0:
                status=OK
                if cap is None:cap=0
            else:
                if cap is None:cap=need
                status=OK if need<=cap else CAPACITY
    if cap is None:cap=len(text) if text is not None and status==OK else 32
    return dict(condition=condition,yes=yes,no=no,fallthrough=fallthrough,cap=cap,nout=nout,
                status=status,text=text if status==OK else None)


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


def expect_dest(condition,yes,no,fallthrough,a,b):
    """Independent destination using original predicate (not Plan invert)."""
    if yes==no:return yes
    if pred_true(condition,a,b):return yes
    return no


class NasmBranchEmitTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_branch_emit requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR10'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_branch_emit.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),
                              ROOT/'lang/bootstrap/branch_plan.dg',
                              ROOT/'lang/bootstrap/decimal_integer.dg']}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_branch_emit_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_branch_emit_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<6Q',c['condition'],c['yes'],c['no'],c['fallthrough'],c['cap'],c.get('nout',0)))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8;outs=[]
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output',out[:written],c['text']))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_format_predicates_and_capacity(self):
        cases=[]
        # all 10 predicates, no==fallthrough → cond only
        for cond in range(10):
            text=expected_text(cond,10,20,20)
            need=len(text)
            cases+=[item(cond,10,20,20),item(cond,10,20,20,cap=need+2),item(cond,10,20,20,cap=max(0,need-1))]
        # yes==fallthrough → inverted cond
        for cond in range(10):
            cases.append(item(cond,20,10,20))
        # both edges
        cases.append(item(EQ,3,4,5))
        # same target
        cases+=[item(EQ,7,7,7),  # zero lines
                item(EQ,7,7,MAX),item(EQ,7,7,8)]
        # illegal
        cases+=[item(10,1,2,2,cap=64,status=INVALID),
                item(EQ,MAX,2,2,cap=64,status=INVALID),
                item(EQ,1,MAX,2,cap=64,status=INVALID),
                item(EQ,1,2,2,nout=1,cap=64,status=INVALID)]
        # zero-line success with empty out
        cases.append(item(EQ,9,9,9,cap=0))
        self.assertEqual(expected_text(EQ,1,2,2),b'je __dong_b1\n')
        self.assertEqual(expected_text(EQ,2,1,2),b'jne __dong_b1\n')  # invert
        self.assertEqual(expected_text(EQ,3,4,5),b'je __dong_b3\njmp __dong_b4\n')
        self.assertEqual(expected_text(EQ,7,7,7),b'')
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-predicates-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_native_cmp_paths(self):
        # (cond, yes, no, fallthrough, pairs of (a,b))
        scenarios=[]
        for cond in range(10):
            scenarios.append((cond,10,20,20,[(5,5),(5,6),(0,0xffff_ffff_ffff_ffff),(1<<63,(1<<63)-1)]))
        scenarios.append((SLT,1,2,3,[(0,1),(1,0),(1<<63,0),(0,1<<63)]))
        scenarios.append((ULT,1,2,3,[(0,1),(1,0),(1<<63,0)]))
        cases=[item(c,y,n,f)for c,y,n,f,_ in scenarios]
        results=self.run_both(cases,'native')
        checked=0
        for mode,outs in results.items():
            for index,((cond,yes,no,ft,pairs),out) in enumerate(zip(scenarios,outs)):
                self.assertIsNotNone(out,(mode,index))
                for ai,(a,b) in enumerate(pairs):
                    dest=self._probe_branch(mode,index,ai,out,yes,no,ft,a,b)
                    expect=expect_dest(cond,yes,no,ft,a,b)
                    self.assertEqual(dest,expect,(mode,index,ai,cond,a,b,out,dest,expect))
                    checked+=1
                # also assemble both formats once
                for fmt in ('elf64','win64'):
                    asm=self.work/'br-asm'/f'{mode}-{index:02d}-{fmt}.asm'
                    obj=self.work/'br-asm'/f'{mode}-{index:02d}-{fmt}.o'
                    asm.parent.mkdir(exist_ok=True)
                    body=self._wrap_asm(out,yes,no,ft)
                    asm.write_text(body,encoding='utf-8')
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr))
        self.records.append(dict(test='native-cmp-paths',scenarios=len(scenarios),checks=checked,
                                 modes=2,passed=True))

    def _wrap_asm(self,emit_text:bytes,yes,no,ft)->str:
        blocks=sorted({yes,no,ft}-{MAX})
        lines=['bits 64','section .text','global probe_br','probe_br:',
               'cmp rdi, rsi',emit_text.decode().rstrip('\n')]
        # fallthrough label if referenced implicitly: when emit has only cond and no jmp,
        # execution continues to next instruction — place fallthrough block there.
        p=plan_fields  # unused marker
        # After emit text, if no jump and fallthrough is a real block, we need that label next.
        # Simplest: always emit all block labels with returns of block id.
        # If fallthrough follows emit when has_jump=0 and has_cond may fall through.
        emitted=emit_text.decode()
        # Place fallthrough immediately after jumps when it's the natural fallthrough.
        ordered=[]
        if ft!=MAX and ft not in (yes,no):
            pass
        # Always: after jump text, put fallthrough label first if used as fallthrough destination,
        # then other labels. For "no==fallthrough" layout, fallthrough is no.
        fall_first=ft if ft!=MAX else None
        rest=[b for b in blocks if b!=fall_first]
        if fall_first is not None:
            lines.append(f'__dong_b{fall_first}:')
            lines.append(f' mov rax, {fall_first}')
            lines.append(' ret')
        for b in rest:
            lines.append(f'__dong_b{b}:')
            lines.append(f' mov rax, {b}')
            lines.append(' ret')
        # If zero emit lines (yes==no==ft), just return yes
        if not emit_text:
            lines=['bits 64','section .text','global probe_br','probe_br:',
                   f' mov rax, {yes}',' ret']
        return '\n'.join(lines)+'\n'

    def _probe_branch(self,mode,index,ai,emit_text,yes,no,ft,a,b)->int:
        body=self._wrap_asm(emit_text,yes,no,ft)
        d=self.work/'br-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:02d}-{ai}.asm';obj=d/f'{mode}-{index:02d}-{ai}.o'
        exe=d/f"{mode}-{index:02d}-{ai}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        r=subprocess.run([str(self.nasm),'-f',native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        csrc=d/f'{mode}-{index:02d}-{ai}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <inttypes.h>\n'
            'uint64_t __attribute__((sysv_abi)) probe_br(uint64_t,uint64_t);\n'
            f'int main(void){{uint64_t v=probe_br({a}ULL,{b}ULL);'
            'printf("%" PRIu64 "\\n",v);return 0;}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        return int(run.stdout.strip())

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_branch_emit.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_branch_emit_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',ROOT/'lang',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Negatives must fail native branch result assertions (not text-only).
        controls=[
            # jl→jg: 0<1 signed true should take yes=10; bad jg falls to no=20
            ('bad-signed-mnem',
             'if cond==6{out[at]=106;out[at+1]=108;return at+2;}',
             'if cond==6{out[at]=106;out[at+1]=103;return at+2;}',
             SLT,10,20,20,0,1),
            # omit jmp write and report only cond_len: 1!=2 should jmp to 4; without jmp falls wrongly
            ('bad-skip-jmp',
             'if plan.has_jump!=0{\n  out[at]=106;out[at+1]=109;out[at+2]=112;out[at+3]=32;at+=4;\n'
             '  at=write_lab(out,at);\n  at=copy(out,at,slice_from_raw_parts(&jbuf[0],jw));\n'
             '  out[at]=10;at+=1;\n }\n *written=total;return OK;',
             'if plan.has_jump!=0{\n }\n *written=cond_len;return OK;',
             EQ,3,4,5,1,2),
        ]
        for name,old,new,cond,yes,no,ft,a,b in controls:
            self.run_both([item(cond,yes,no,ft)],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                out=self._emit_raw(exe,dict(condition=cond,yes=yes,no=no,fallthrough=ft,cap=128),
                                   name+'-'+mode)
                dest=self._probe_branch(mode,0,0,out,yes,no,ft,a,b)
                expect=expect_dest(cond,yes,no,ft,a,b)
                self.assertNotEqual(dest,expect,(name,mode,'native-branch',dest,expect,out))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,
                                     rejected_by='native-branch-result'))

    def _emit_raw(self,exe,c,label):
        payload=bytearray(struct.pack('<Q',1))
        payload.extend(struct.pack('<6Q',c['condition'],c['yes'],c['no'],c['fallthrough'],c['cap'],0))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stderr)
        status,guard,written=struct.unpack_from('<3Q',run.stdout,8)
        self.assertEqual(guard,1);self.assertEqual(status,0)
        return run.stdout[8+24:8+24+written]


if __name__=='__main__':unittest.main()
