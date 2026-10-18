"""Actual Dong NASM register-indirect call emitter: exact text, dual-format assembly, and native SysV calls."""
import hashlib
import json
import os
from pathlib import Path
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

SOURCE=ROOT/'lang/bootstrap/nasm_indirect_call.dg'
OK,INVALID,CAPACITY=0,1,2
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r%d'%i for i in range(8,16)]
TARGETS=[0,10,11]                 # non-argument caller-saved registers that may hold callee addresses
WRAPPER='''module probe.icall_export;
import bootstrap.nasm_indirect_call as c;
export("dong_icall_emit") pub unsafe fn emit(target:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return c.emit(target,slice_from_raw_parts(out,no),written);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_icall_emit(uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Each preflight keeps every other field valid so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[512],saved[512];const unsigned total=10;
 uint8_t*o=arena+64;uint64_t*w=(uint64_t*)(arena+256);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_icall_emit(0,o,32,NULL);break;                                    /* written NULL */
   case 1:s=dong_icall_emit(0,o,32,(uint64_t*)(arena+257));break;                  /* written odd */
   case 2:s=dong_icall_emit(0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;  /* written end overflow, empty out */
   case 3:s=dong_icall_emit(0,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;      /* out end overflow */
   case 4:s=dong_icall_emit(0,NULL,32,w);break;                                    /* NULL non-empty out */
   case 5:s=dong_icall_emit(0,o,32,(uint64_t*)o);break;                            /* written on out prefix */
   case 6:s=dong_icall_emit(0,o,64,(uint64_t*)(o+56));break;                       /* written in out's unused tail */
   case 7:s=dong_icall_emit(16,NULL,0,w);break;                                    /* bad target, capacity 0 */
   case 8:s=dong_icall_emit(UINT64_MAX,o,32,w);break;
   default:s=dong_icall_emit(17,o,1,w);break;
  }
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[2];read_exact(h,sizeof(h));uint64_t cap=h[1];if(cap>4096)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_icall_emit(h[0],cap?out+32:NULL,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={s,valid,s?0:*written};write_exact(response,24);write_exact(out+32,s?0:*written);
  free(out);
 }return 0;
}
'''
NATIVE_MAIN=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef void ABI (*stub)(uint64_t*);
%DECLS%
static const stub table[]={%TABLE%};
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdout),_O_BINARY);
#endif
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  uint64_t io[6]={0xa5a5a5a5a5a5a5a5ull,0x0fedcba987650000ull+i*0x101,0,0,0,0xa5a5a5a5a5a5a5a5ull};
  table[i](io+1);
  if(io[0]!=0xa5a5a5a5a5a5a5a5ull||io[5]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(io+1,8,4,stdout)!=4)exit(92);
 }return 0;
}
'''


def expected_line(t):
    return ('call %s\n'%NAMES[t]).encode()


MARK={0:0x1000,10:0x2000,11:0x3000}
VECTORS=[0,10,11,0,10,11]          # target register per probe; every probe loads all three with distinct callees


class NasmIndirectCallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C27'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component (no whole lang root) and build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_indirect_call.dg').write_text(text,encoding='utf-8')
        (root/'probe/icall_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/icall_export.dg',roots=[root],mode=mode)
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

    def emit(self,exe,cases,label):
        """cases: (target,cap,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for t,cap,_ in cases:payload.extend(struct.pack('<2Q',t,cap))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],10)
        offset=8;texts=[]
        for index,(t,cap,status) in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,status,(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,lines,targets,label):
        """Each probe loads rax/r10/r11 with three distinct, defined callees, aligns the call site and runs the emitted line."""
        stub=['bits 64','section .text']
        for i,line in enumerate(lines):
            stub+=['global v%d'%i,'v%d:'%i,'push rbx','push r12','sub rsp, 8',          # entry rsp%16==8 -> call site 16-aligned
                   'mov rbx, rdi']
            stub+=['lea %s, [rel c%d_%s]'%(NAMES[r],i,NAMES[r])for r in TARGETS]
            stub+=['mov rdi, [rbx]','mov r12, rsp',line.decode('ascii').rstrip('\n'),
                   'mov [rbx+8], rax','mov [rbx+16], rdx','mov rax, rsp','sub rax, r12','mov [rbx+24], rax',
                   'add rsp, 8','pop r12','pop rbx','ret']
            for r in TARGETS:   # callee: rax = argument + register-specific marker, rdx = entry rsp & 15
                stub+=['c%d_%s:'%(i,NAMES[r]),'mov rax, %d'%(MARK[r]+i),'add rax, rdi','mov rdx, rsp','and rdx, 15','ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%i for i in range(len(lines))))
        main=main.replace('%TABLE%',','.join('v%d'%i for i in range(len(lines))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        run=subprocess.run([str(exe)],capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for i,t in enumerate(targets):
            param,ret,alignment,stack=struct.unpack_from('<4Q',run.stdout,32*i)
            self.assertEqual(param,0x0fedcba987650000+i*0x101,(label,i,'native parameter slot'))
            self.assertEqual(ret,param+MARK[t]+i,(label,i,'native callee return',NAMES[t]))
            self.assertEqual(alignment,8,(label,i,'native callee entry alignment'))
            self.assertEqual(stack,0,(label,i,'native stack restored'))

    def test_exact_text_and_capacity_for_all_registers(self):
        cases=[]
        for t in range(16):
            n=len(expected_line(t));cases+=[(t,n,OK),(t,n+9,OK),(t,n-1,CAPACITY)]
        cases+=[(0,0,CAPACITY),(16,64,INVALID),(2**64-1,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (t,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,expected_line(t),(mode,t))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=10,modes=2,passed=True))

    def test_all_sixteen_registers_assemble_in_both_formats(self):
        cases=[(t,32,OK)for t in range(16)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            source=self.work/('all-registers-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('all-registers-%s.%s.o'%(mode,fmt)),source],'all-registers-%s-%s'%(mode,fmt))
        self.records.append(dict(test='all-registers-assemble',lines=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def test_native_indirect_calls(self):
        for mode,exe in self.executables.items():
            self.native_run(self.emit(exe,[(t,32,OK)for t in VECTORS],'calls-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-indirect-calls',calls_per_mode=len(VECTORS),targets=[NAMES[t]for t in TARGETS],modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        # r10 emitted as r11: both registers hold different, defined, valid callees.
        old='if r==10{return "r10";}';new='if r==10{return "r11";}';self.assertEqual(source.count(old),1)
        targets=[10,10]
        for mode,exe in self.executables.items():
            self.native_run(self.emit(exe,[(t,32,OK)for t in targets],'bad-target-good-'+mode),targets,'bad-target-good-'+mode)
        for mode,exe in self.build_all('bad-target',source.replace(old,new,1)).items():
            texts=self.emit(exe,[(t,32,OK)for t in targets],'bad-target-'+mode)
            with self.assertRaisesRegex(AssertionError,'native callee return'):self.native_run(texts,targets,'bad-target-'+mode)
        self.records.append(dict(test='bad-target-register',compiled=True,native_executed=True,modes=2,rejected_by='native callee return'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=buffer[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(11,4,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
