"""Run real block/jump and divide fragments with boundary inputs and preserved args."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
import uuid
from lang.tests import test_bootstrap_nasm_block_emit as block
from lang.tests import test_bootstrap_nasm_integer_divide as divide
from lang.tests.test_dongc import nasm_flags

ROOT = Path(__file__).resolve().parents[2]
MASK, TOP = (1 << 64)-1, 1 << 63
# Every divisor is nonzero; signed MIN/-1 is deliberately excluded.
VECTORS = [(True,False,TOP,1),(True,True,TOP,3),(True,False,TOP,2),
           (True,False,TOP-1,MASK),(True,True,TOP-1,3),
           (True,False,(-7)&MASK,3),(True,True,7,(-3)&MASK),
           (False,False,MASK,1),(False,True,MASK,2),(False,False,TOP,TOP)]
HELPERS = ((block,'NasmBlockEmitTests'),(divide,'NasmIntegerDivideTests'))


class BlockDivideIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = ROOT/'build/test/bootstrap-block-divide-integration'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True); cls.helpers=[]; cls.records=[]
        cls.sources = [ROOT/'lang/bootstrap'/(n+ext) for n in ('nasm_block_emit','nasm_integer_divide') for ext in ('.dg','.md')]
        cls.sources += [ROOT/'lang/bootstrap/decimal_integer.dg',Path(__file__)]
        cls.sources += [Path(m.__file__) for m,_ in HELPERS]
        cls.inputs = cls.identities()
        try:
            for module,name in HELPERS:
                helper=getattr(module,name); cls.helpers.append(helper); helper.setUpClass()
            cls.nasm,cls.cc=cls.helpers[0].nasm,cls.helpers[0].cc
        except BaseException:
            for helper in reversed(cls.helpers): helper.tearDownClass()
            cls.helpers=[]
            raise

    @classmethod
    def identities(cls):
        return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.sources}

    @classmethod
    def tearDownClass(cls):
        for helper in reversed(cls.helpers): helper.tearDownClass()
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,
            source_stable=cls.identities()==cls.inputs,records=cls.records,
            helper_artifacts=[str(h.work) for h in cls.helpers],L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n',encoding='utf-8')

    def command(self,args,label):
        run=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=120)
        (self.work/(label+'.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
        self.assertEqual(run.returncode,0,(label,run.stderr))

    def test_real_jump_reaches_divide_and_preserves_input_registers(self):
        bt,dt=(h() for h in self.helpers)
        native='win64' if os.name=='nt' else 'elf64'
        for mode in ('debug','release'):
            body=b'bits 64\nsection .text\n'
            for i,(signed,remainder,_,_) in enumerate(VECTORS):
                entry,end=100+2*i,101+2*i
                parts=bt.run_cases(bt.executables[mode],[block.item(1,entry),block.item(0,entry),
                    block.item(1,end),block.item(0,end)],f'pipeline-blocks-{mode}-{i}')
                kernel=dt.run_cases(dt.executables[mode],[divide.item(signed,remainder)],f'pipeline-divide-{mode}-{i}')[0]
                body+=f'global pipeline_{i}\npipeline_{i}:\n'.encode()+b'mov r8, rdx\n'+parts[0]
                body+=b'mov qword [r8], 0xBAD\nret\n'+parts[1]+kernel
                body+=b'mov [r8], rax\nmov [r8+8], rdi\nmov [r8+16], rsi\n'+parts[2]
                body+=b'mov qword [r8], 0xBAD\n'+parts[3]+b'ret\n'
            asm=self.work/(mode+'.asm'); asm.write_bytes(body)
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(mode+'.'+fmt+'.o'),asm],mode+'-'+fmt)
            declarations='\n'.join(f'extern void ABI pipeline_{i}(uint64_t,uint64_t,uint64_t*);' for i in range(len(VECTORS)))
            table=','.join(f'pipeline_{i}' for i in range(len(VECTORS)))
            main='''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
'''+declarations+'''
typedef void (ABI *probe)(uint64_t,uint64_t,uint64_t*);
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 probe functions[]={'''+table+'''};
 for(unsigned i=0;i<sizeof(functions)/sizeof(functions[0]);i++){
  uint64_t args[2],out[5];memset(out,0xA5,sizeof(out));
  if(fread(args,1,16,stdin)!=16)return 91;
  functions[i](args[0],args[1],out+1);
  if(out[0]!=UINT64_C(0xA5A5A5A5A5A5A5A5)||out[4]!=out[0])return 96;
  if(fwrite(out+1,1,24,stdout)!=24)return 92;
 }return 0;
}
'''
            c=self.work/(mode+'.c'); c.write_text(main,encoding='utf-8')
            exe=self.work/(mode+('.exe' if os.name=='nt' else ''))
            self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',c,self.work/(mode+'.'+native+'.o'),'-o',exe],mode+'-link')
            payload=b''.join(struct.pack('<2Q',a,b) for _,_,a,b in VECTORS)
            run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=60)
            (self.work/(mode+'.input')).write_bytes(payload); (self.work/(mode+'.output')).write_bytes(run.stdout)
            self.assertEqual(run.returncode,0,run.stderr); self.assertEqual(len(run.stdout),24*len(VECTORS))
            for i,(signed,remainder,a,b) in enumerate(VECTORS):
                if signed:
                    aa=a-(1<<64) if a&TOP else a; bb=b-(1<<64) if b&TOP else b
                    q=abs(aa)//abs(bb)
                    if (aa<0)!=(bb<0): q=-q
                else: aa,bb,q=a,b,a//b
                expected=(aa-q*bb if remainder else q)&MASK
                self.assertEqual(struct.unpack_from('<3Q',run.stdout,24*i),(expected,a,b),(mode,i))
            self.records.append(dict(mode=mode,vectors=len(VECTORS),signed_boundaries=True,
                unsigned_boundaries=True,input_registers_preserved=True,formats=['elf64','win64'],passed=True))
        self.assertEqual(self.identities(),self.inputs,'source identity changed')


if __name__=='__main__': unittest.main()
