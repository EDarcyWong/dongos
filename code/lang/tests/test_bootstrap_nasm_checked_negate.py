"""Actual Dong NASM signed i64 checked-negate emit (neg/jo)."""
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


SOURCE=ROOT/'lang/bootstrap/nasm_checked_negate.dg'
DOC=ROOT/'lang/bootstrap/nasm_checked_negate.md'
CR4=WORKS/'cursor-works/src/bootstrap/decimal_integer.dg'
if not CR4.is_file():
    CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
TOP=1<<63
SMAX=TOP-1
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
SAFE={0,1,2,6,7,8,9,10,11}
FALL=111
TRAP=222
WRAPPER='''module probe.nasm_checked_negate_export;
import bootstrap.nasm_checked_negate as m;
export("dong_checked_neg_emit") pub unsafe fn emit(
 destination:u64,trap_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(destination,trap_block,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_checked_neg_emit(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=13;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"neg rax\n",8);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_checked_neg_emit(0,0,o,128,NULL);break;
   case 1:st=dong_checked_neg_emit(0,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_checked_neg_emit(0,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_checked_neg_emit(0,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_checked_neg_emit(0,0,NULL,128,w);break;
   case 5:st=dong_checked_neg_emit(0,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_checked_neg_emit(0,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_checked_neg_emit(0,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_checked_neg_emit(0,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_checked_neg_emit(16,0,o,128,w);break;
   case 10:st=dong_checked_neg_emit(0,UINT64_MAX,o,128,w);break;
   case 11:st=dong_checked_neg_emit(16,0,o,0,w);break;
   default:st=dong_checked_neg_emit(0,UINT64_MAX,o,0,w);break;
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){
   fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)st);exit(93);
  }
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
  uint64_t dest=h[0],trap=h[1],cap=h[2],nout=h[3];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_checked_neg_emit(dest,trap,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
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
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  /* [0]value [1]rcx [2]rdx [3]r8 [4]r9 [5]rsi — then out overwrites */
  uint64_t state[10];read_exact(state,48);
  state[6]=state[7]=state[8]=state[9]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state);
  if(fwrite(state,8,8,stdout)!=8)exit(92);
 }return 0;
}
'''


def expected(dest,trap):
    return b'neg '+REGS64[dest]+b'\njo __dong_b'+str(trap).encode()+b'\n'


def need_total(dest,trap):
    return len(expected(dest,trap))


def py_neg(v):
    v&=NONE
    overflow=v==TOP
    return overflow,(-v)&NONE


def item(dest,trap,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if dest>15 or trap==NONE:status=INVALID
        else:
            need=need_total(dest,trap)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(dest,trap) if status==OK else 64
    text=expected(dest,trap) if status==OK else None
    return dict(dest=dest,trap=trap,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<4Q',c['dest'],c['trap'],c['cap'],c.get('nout',0))


# (dest, value, trap) — <=24; must cover RAX and R8 with 0/1/-1/MIN/MIN+1/MAX.
NATIVE_VECTORS=[
    (0,0,10),(0,1,11),(0,NONE,12),(0,TOP,13),(0,TOP+1,14),(0,SMAX,15),
    (8,0,20),(8,1,21),(8,NONE,22),(8,TOP,23),(8,TOP+1,24),(8,SMAX,25),
    (1,TOP,30),(1,0,31),(2,NONE,32),(2,SMAX,33),
    (7,1,34),(7,TOP,35),(9,TOP+1,36),(9,0,37),
    (10,SMAX,38),(10,TOP,39),(11,NONE,40),(6,TOP,41),
]
assert len(NATIVE_VECTORS)<=24
assert {r for r,_,_ in NATIVE_VECTORS}<=SAFE
assert 0 in {r for r,_,_ in NATIVE_VECTORS} and 8 in {r for r,_,_ in NATIVE_VECTORS}


class NasmCheckedNegateTests(unittest.TestCase):
    PREFLIGHTS=13

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_checked_negate requires NASM/GCC')
        cls.work=WORKS/'build/test/bootstrap-nasm-checked-negate'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_checked_negate.dg')
        shutil.copy2(CR4,cls.src_root/'bootstrap'/'decimal_integer.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.native='win64'if os.name=='nt'else'elf64'
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),CR4]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_checked_negate_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_checked_negate_export.dg',roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==cls.native else cls.work/(name+'.'+fmt+'.o')
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
        for c in cases:payload.extend(pack_case(c))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr.decode('utf-8','replace') if run.stderr else '')
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8;outs=[]
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_format_boundaries_and_capacity(self):
        cases=[]
        for dest in range(16):
            for trap in (0,1,42,TOP,NONE-1):
                need=need_total(dest,trap)
                cases+=[item(dest,trap),
                        item(dest,trap,cap=need+3),
                        item(dest,trap,cap=max(0,need-1)),
                        item(dest,trap,cap=need)]
        cases+=[item(16,0,cap=64,status=INVALID),
                item(0,NONE,cap=64,status=INVALID),
                item(0,0,nout=1,cap=64,status=INVALID),
                item(16,0,nout=0,cap=0,status=INVALID),
                item(0,NONE,nout=0,cap=0,status=INVALID),
                item(0,0,cap=0,status=CAPACITY)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_negate(self):
        samples=[(dest,trap)for dest in range(16)for trap in (0,1,42,TOP,NONE-1,100+dest)]
        cases=[item(d,t)for d,t in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((d,t),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=(b'bits 64\nsection .text\n'+out+
                      b'mov rax, 1\n ret\n__dong_b'+str(t).encode()+b':\n mov rax, 2\n ret\n')
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr,out))
                    assembled+=1
        ncases=[item(d,t)for d,_,t in NATIVE_VECTORS]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            self._native_batch(mode,outs,NATIVE_VECTORS)
            probed+=len(NATIVE_VECTORS)
        self.records.append(dict(test='dong-assemble-native-negate',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(NATIVE_VECTORS),probed=probed,
                                 modes=2,formats=2,passed=True))

    def _native_batch(self,mode,texts,vectors):
        stub=['bits 64','section .text']
        defined=set()
        for k,(text,(dest,val,trap)) in enumerate(zip(texts,vectors)):
            rname=REGS64[dest].decode()
            # State pointer must not occupy the written destination.
            sp='r11' if dest!=11 else 'r10'
            loads=['global v%d'%k,'v%d:'%k,'mov %s, rdi'%sp]
            # Load sentinels first, skipping dest; load dest last so it is not overwritten.
            for reg,off in ((1,8),(2,16),(8,24),(9,32),(6,40)):
                if reg==dest:continue
                loads.append('mov %s, [%s+%d]'%(REGS64[reg].decode(),sp,off))
            loads.append('mov %s, [%s+0]'%(rname,sp))
            stub+=loads
            stub+=text.decode('ascii').rstrip('\n').split('\n')
            save=[
                'mov [%s+48], %s'%(sp,rname),
            ]
            for reg,slot in ((1,0),(2,8),(8,16),(9,24),(6,32)):
                if reg==dest:continue
                save.append('mov [%s+%d], %s'%(sp,slot,REGS64[reg].decode()))
            save+=[
                'mov rax, %d'%FALL,
                'mov [%s+40], rax'%sp,
                'ret',
            ]
            stub+=save
            if trap not in defined:
                defined.add(trap)
                tsave=[
                    '__dong_b%d:'%trap,
                    'mov [%s+48], %s'%(sp,rname),
                ]
                for reg,slot in ((1,0),(2,8),(8,16),(9,24),(6,32)):
                    if reg==dest:continue
                    tsave.append('mov [%s+%d], %s'%(sp,slot,REGS64[reg].decode()))
                tsave+=[
                    'mov rax, %d'%TRAP,
                    'mov [%s+40], rax'%sp,
                    'ret',
                ]
                stub+=tsave
        label=mode+'-native'
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),
                          '-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],
                         label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                      self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],
                     label+'-native-link')
        rcx_s=0x1111111111111111
        rdx_s=0x2222222222222222
        r8_s=0x3333333333333333
        r9_s=0x4444444444444444
        rsi_s=0x5555555555555555
        payload=bytearray()
        for dest,val,trap in vectors:
            # Avoid clobbering sentinel when dest is one of the preserved regs:
            # those sentinels are loaded after dest, so OK; dest gets val.
            payload.extend(struct.pack('<6Q',val&NONE,rcx_s,rdx_s,r8_s,r9_s,rsi_s))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,(dest,val,trap) in enumerate(vectors):
            got=list(struct.unpack_from('<8Q',run.stdout,64*k))
            # layout: [0]rcx [1]rdx [2]r8 [3]r9 [4]rsi [5]marker [6]dest_result [7]unused
            overflow,negated=py_neg(val)
            want_marker=TRAP if overflow else FALL
            self.assertEqual(got[5],want_marker,(label,k,'route',vectors[k],overflow))
            self.assertEqual(got[6],negated,(label,k,'dest result',vectors[k]))
            # Preserved regs: skip checking the one that is the destination.
            expect={1:rcx_s,2:rdx_s,8:r8_s,9:r9_s,6:rsi_s}
            slots={1:0,2:1,8:2,9:3,6:4}
            for reg,sentinel in expect.items():
                if reg==dest:continue
                self.assertEqual(got[slots[reg]],sentinel,(label,k,'reg%d preserved'%reg,vectors[k]))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_checked_negate.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_checked_negate_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        jo_old=' at=copy(buffer,at,"jo __dong_b");'
        jo_new=' at=copy(buffer,at,"jno __dong_b");'
        early_old=' if at>out.len{return CAPACITY;}'
        early_new=' *written=at;if at>out.len{return CAPACITY;}'
        short=item(0,0,cap=5)
        controls=[
            ('bad-jo-as-jno',jo_old,jo_new,'native',0,TOP),   # MIN → must trap for good
            ('bad-early-written',early_old,early_new,'atomic',0,0),
        ]
        for name,old,new,kind,dest,val in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            else:
                self.run_both([item(dest,70)],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                else:
                    c=dict(dest=dest,trap=70,cap=64,nout=0,status=OK,text=None)
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+64][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,expected(dest,70),(name,mode,text))
                    # MIN: good traps; jno falls through → route rejection.
                    with self.assertRaisesRegex(AssertionError,r'route'):
                        self._native_batch(mode+'-'+name,[text],[(dest,val,70)])
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
