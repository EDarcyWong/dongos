"""Actual Dong SysV INTEGER return-plan metadata, with independent NASM probes."""
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

ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/sysv_return_plan.dg'
DOC=ROOT/'lang/bootstrap/sysv_return_plan.md'
OK,INVALID=0,1
NONE,ZERO,SIGN=0,1,2
VOID,BOOL,U8,I8,U16,I16,U32,I32,U64,I64,PTR,INTEGER_PAIR=range(12)
TABLE={
    VOID:(0,0,NONE),BOOL:(1,8,ZERO),U8:(1,8,ZERO),I8:(1,8,SIGN),
    U16:(1,16,ZERO),I16:(1,16,SIGN),U32:(1,32,ZERO),I32:(1,32,SIGN),
    U64:(1,64,NONE),I64:(1,64,NONE),PTR:(1,64,NONE),INTEGER_PAIR:(2,64,NONE),
}
WRAPPER='''module probe.sysv_return_export;
import bootstrap.sysv_return_plan as r;
export("dong_sysv_return_plan") pub unsafe fn plan(kind:u64,out:*r.Plan)u64{unsafe{
 return r.plan(kind,out);
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
typedef struct {uint64_t words,width_bits,extension;} Plan;
_Static_assert(sizeof(Plan)==24&&__builtin_offsetof(Plan,width_bits)==8
 &&__builtin_offsetof(Plan,extension)==16,"layout");
extern uint64_t ABI dong_sysv_return_plan(uint64_t,Plan*);
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
   case 0:st=dong_sysv_return_plan(2,NULL);break;
   case 1:st=dong_sysv_return_plan(2,(Plan*)(arena+68));break;
   case 2:st=dong_sysv_return_plan(2,(Plan*)(arena+65));break;
   case 3:st=dong_sysv_return_plan(2,(Plan*)(uintptr_t)1);break;
   case 4:st=dong_sysv_return_plan(2,(Plan*)(uintptr_t)4);break;
   case 5:st=dong_sysv_return_plan(2,(Plan*)(uintptr_t)(UINT64_MAX-15));break;
   case 6:st=dong_sysv_return_plan(2,(Plan*)(uintptr_t)(UINT64_MAX-23));break;
   default:st=dong_sysv_return_plan(0,(Plan*)(uintptr_t)(UINT64_MAX-7));break;
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
  uint64_t kind;read_exact(&kind,8);
  uint8_t buf[24+64];memset(buf,0xa5,sizeof(buf));Plan*out=(Plan*)(buf+32);
  uint64_t st=dong_sysv_return_plan(kind,out);
  uint64_t valid=filled(buf,32)&&filled(buf+32+24,32);
  if(st)valid=valid&&filled(out,24);
  uint64_t response[5]={st,valid,st?0:out->words,st?0:out->width_bits,st?0:out->extension};
  write_exact(response,40);
 }return 0;
}
'''


def expected(kind):
    if kind in TABLE:return OK,TABLE[kind]
    return INVALID,None


def item(kind,status=None):
    st,plan=expected(kind)
    if status is not None:assert st==status,(status,st,kind)
    return dict(kind=kind,status=st,plan=plan)


def extend_value(raw,width_bits,extension):
    """Independent two's-complement / zero-extend interpretation of a narrow return."""
    mask=(1<<width_bits)-1
    v=raw&mask
    if extension==NONE:return v if width_bits==64 else v  # full word already
    if extension==ZERO:return v
    # SIGN
    sign=1<<(width_bits-1)
    if v&sign:return v|((~mask)&((1<<64)-1))
    return v


def nasm_return_asm(words,width_bits,extension,low,high=0):
    """Generate a tiny SysV return probe from Dong plan fields (not production)."""
    lines=['bits 64','default rel','section .text','global probe_ret','probe_ret:']
    if words==0:
        lines+=['xor eax,eax','ret']
        return '\n'.join(lines)+'\n'
    if words==2:
        lines+=[f'mov rax,{low&0xffffffffffffffff}',
                f'mov rdx,{high&0xffffffffffffffff}','ret']
        return '\n'.join(lines)+'\n'
    # one word: place raw low bits then apply plan extension
    lines.append(f'mov rax,{low&0xffffffffffffffff}')
    if extension==ZERO and width_bits<64:
        if width_bits==8:lines.append('movzx rax,al')
        elif width_bits==16:lines.append('movzx rax,ax')
        elif width_bits==32:lines.append('mov eax,eax')
    elif extension==SIGN and width_bits<64:
        if width_bits==8:lines.append('movsx rax,al')
        elif width_bits==16:lines.append('movsx rax,ax')
        elif width_bits==32:lines.append('movsxd rax,eax')
    lines.append('ret')
    return '\n'.join(lines)+'\n'


PROBE_C=r'''
#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>
#ifdef _WIN32
#define ABI __attribute__((sysv_abi))
#else
#define ABI
#endif
extern uint64_t ABI probe_ret(void);
#ifdef PAIR
typedef struct {uint64_t a,b;} Pair;
extern Pair ABI probe_ret_pair(void);
#endif
int main(void){
#ifdef PAIR
 Pair p=probe_ret_pair();
 printf("%" PRIu64 " %" PRIu64 "\n",p.a,p.b);
#else
 printf("%" PRIu64 "\n",probe_ret());
#endif
 return 0;
}
'''


class SysvReturnPlanTests(unittest.TestCase):
    PREFLIGHTS=8

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native sysv_return_plan requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/CR7'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        (cls.src_root/'bootstrap'/'sysv_return_plan.dg').write_bytes(SOURCE.read_bytes())
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/sysv_return_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/sysv_return_export.dg',roots=roots,mode=mode)
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
            records=cls.records,full_sysv_abi=False,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n',
            encoding='utf-8')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:payload.extend(struct.pack('<Q',c['kind']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8
        for index,c in enumerate(cases):
            status,guard,words,width,ext=struct.unpack_from('<5Q',run.stdout,offset);offset+=40
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c['kind']))
            if not status:
                self.assertEqual((words,width,ext),c['plan'],(label,index,'plan',c['kind']))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def plan_via_dong(self,kind):
        """Read one kind through the native debug executable."""
        cases=[item(kind)];exe=self.executables['debug']
        payload=bytearray(struct.pack('<Q',1));payload.extend(struct.pack('<Q',kind))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        status,guard,words,width,ext=struct.unpack_from('<5Q',run.stdout,8)
        self.assertEqual(guard,1);self.assertEqual(status,OK)
        return words,width,ext

    def run_nasm_probe(self,name,asm_text,pair=False,expect_low=None,expect_high=None):
        probe_dir=self.work/'nasm-probe';probe_dir.mkdir(exist_ok=True)
        asm_path=probe_dir/f'{name}.asm';obj=probe_dir/f'{name}.o'
        exe=probe_dir/(name+('.exe'if os.name=='nt'else name))
        c_path=probe_dir/f'{name}.c'
        text=asm_text
        if pair:
            text=text.replace('global probe_ret','global probe_ret_pair').replace('probe_ret:','probe_ret_pair:')
        asm_path.write_text(text,encoding='utf-8')
        c_src=PROBE_C
        if pair:c_src='#define PAIR\n'+c_src
        c_path.write_text(c_src,encoding='utf-8')
        fmt='win64'if os.name=='nt'else'elf64'
        self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',obj,asm_path],name+'-nasm')
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',c_path,obj,'-o',exe],name+'-link')
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,(name,run.stderr,run.stdout))
        parts=[int(x)for x in run.stdout.strip().split()]
        if pair:
            self.assertEqual(len(parts),2,(name,run.stdout))
            self.assertEqual(parts[0],expect_low&((1<<64)-1),(name,'low'))
            self.assertEqual(parts[1],expect_high&((1<<64)-1),(name,'high'))
        else:
            self.assertEqual(len(parts),1,(name,run.stdout))
            self.assertEqual(parts[0],expect_low&((1<<64)-1),(name,'rax'))
        return parts

    def test_all_kinds_invalid_and_seeded(self):
        cases=[item(k)for k in range(12)]
        for bad in (12,13,99,0xff,0x8000000000000000,2**64-1):
            cases.append(item(bad,status=INVALID))
        rng=random.Random(0x0C87001)
        for _ in range(80):
            k=rng.randrange(0,40)
            cases.append(item(k)if k<12 else item(k,status=INVALID))
        self.run_both(cases,'kinds')
        self.records.append(dict(test='all-kinds-invalid-seeded',cases=len(cases),
                                 preflights=self.PREFLIGHTS,modes=2,passed=True))

    def test_nasm_extension_probe_from_dong_plan(self):
        """Python two's-complement + NASM probe driven by live Dong Plan fields."""
        samples=[
            (I8,-1,None),(I8,-128,None),(I16,-1,None),(I16,-32768,None),
            (I32,-1,None),(I32,-(1<<31),None),
            (U8,0xff,None),(U8,0x80,None),(U16,0xffff,None),(U16,0x8000,None),
            (U32,0xffffffff,None),(U32,0x80000000,None),
            (BOOL,1,None),(U64,0x0123456789abcdef,None),(I64,-2,None),(PTR,0x7fffffffffff,None),
            (INTEGER_PAIR,0x1111222233334444,0x5555666677778888),
            (VOID,0,None),
        ]
        checked=0
        for kind,low,high in samples:
            words,width,ext=self.plan_via_dong(kind)
            self.assertEqual((words,width,ext),TABLE[kind],kind)
            if words==0:
                asm=nasm_return_asm(words,width,ext,0)
                self.run_nasm_probe(f'void-{kind}',asm,expect_low=0)
                checked+=1
                continue
            if words==2:
                asm=nasm_return_asm(words,width,ext,low,high)
                self.run_nasm_probe(f'pair-{kind}',asm,pair=True,expect_low=low,expect_high=high)
                checked+=1
                continue
            # place dirty high bits in the register before extension
            dirty=low&((1<<width)-1)
            if width<64:dirty|=0xdeadbeefcafebabe&(~((1<<width)-1)&((1<<64)-1))
            expect=extend_value(dirty if width<64 else low,width,ext)
            if ext==SIGN:self.assertEqual(expect,extend_value(low,width,ext),(kind,'sign'))
            if ext==ZERO:self.assertEqual(expect,low&((1<<width)-1),(kind,'zero'))
            if ext==NONE:expect=low&((1<<64)-1);dirty=expect
            asm=nasm_return_asm(words,width,ext,dirty)
            self.run_nasm_probe(f'k{kind}-w{width}-e{ext}',asm,expect_low=expect)
            checked+=1
        self.assertGreaterEqual(checked,16)
        self.records.append(dict(test='nasm-extension-probe',samples=len(samples),checked=checked,
                                 modes=1,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'sysv_return_plan.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'sysv_return_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-signed-as-zero',
             'else if kind==3{words=1;width=8;ext=SIGN;}',
             'else if kind==3{words=1;width=8;ext=ZERO;}',
             [item(I8)],'plan'),
            ('bad-pair-one-word',
             'else if kind==11{words=2;width=64;ext=NONE;}',
             'else if kind==11{words=1;width=64;ext=NONE;}',
             [item(INTEGER_PAIR)],'plan'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
