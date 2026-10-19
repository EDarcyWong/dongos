"""Published object alignment and native zero-filled globals, independent of alignb macros."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from lang.dongc import compile_source
from lang.tests.test_dongc import tool, nasm_flags

SOURCE='''module bss_probe;
align(64) struct Block{x:u64}
var prefix:u8=0;
var block:Block=Block{x:0};
export("bss_prefix") pub unsafe fn prefix_address()u64{unsafe{return &prefix as u64;}}
export("bss_block") pub unsafe fn block_address()u64{unsafe{return &block as u64;}}
export("bss_value") pub fn value()u64{return block.x;}
'''
C=r'''
#include <stdint.h>
#include <stdlib.h>
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI bss_prefix(void),bss_block(void),bss_value(void);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{(void)k;(void)l;(void)f;(void)n;exit(90);}
int main(void){
 uint8_t*p=(uint8_t*)(uintptr_t)bss_prefix();uint8_t*b=(uint8_t*)(uintptr_t)bss_block();
 if(((uintptr_t)b&63)!=0||b<=p)return 1;
 if(*p)return 2;
 for(unsigned i=0;i<64;i++)if(b[i])return 3;
 *(uint64_t*)(void*)b=UINT64_C(0xfedcba9876543210);
 if(bss_value()!=UINT64_C(0xfedcba9876543210)||*p)return 4;
 for(unsigned i=8;i<64;i++)if(b[i])return 5;
 return 0;
}
'''


def bss_alignment(raw,fmt):
    if fmt=='win64':
        machine,count=struct.unpack_from('<HH',raw);assert machine==0x8664
        optional=struct.unpack_from('<H',raw,16)[0]
        for i in range(count):
            at=20+optional+40*i
            if raw[at:at+8].rstrip(b'\0')==b'.bss':
                flags=struct.unpack_from('<I',raw,at+36)[0]
                power=(flags>>20)&15
                assert power
                return 1<<(power-1)
    else:
        assert raw[:6]==b'\x7fELF\x02\x01'
        table=struct.unpack_from('<Q',raw,40)[0]
        stride,count,strings=struct.unpack_from('<HHH',raw,58)
        names=struct.unpack_from('<Q',raw,table+stride*strings+24)[0]
        for i in range(count):
            at=table+stride*i;name=names+struct.unpack_from('<I',raw,at)[0]
            if raw[name:raw.index(0,name)]==b'.bss':return struct.unpack_from('<Q',raw,at+48)[0]
    raise AssertionError('missing .bss')


class BssCompatibilityTests(unittest.TestCase):
    def test_object_base_alignment_and_native_zero_fill(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        if not nasm or not cc:self.skipTest('requires NASM/GCC')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);observer=root/'main.c';observer.write_text(C,encoding='utf-8')
            for mode in ('debug','release'):
                asm=root/(mode+'.asm');asm.write_text(compile_source(SOURCE,mode=mode).assembly,encoding='utf-8')
                objects={}
                for fmt in ('elf64','win64'):
                    obj=root/(mode+'-'+fmt+'.o');objects[fmt]=obj
                    r=subprocess.run([nasm,'-f',fmt,*nasm_flags(nasm),'-o',str(obj),str(asm)],capture_output=True,text=True,timeout=30)
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertEqual(bss_alignment(obj.read_bytes(),fmt),64,(mode,fmt))
                native='win64' if os.name=='nt' else 'elf64';exe=root/(mode+('.exe' if os.name=='nt' else ''))
                r=subprocess.run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',str(observer),str(objects[native]),'-o',str(exe)],capture_output=True,text=True,timeout=30)
                self.assertEqual(r.returncode,0,r.stderr)
                r=subprocess.run([str(exe)],capture_output=True,timeout=30)
                self.assertEqual(r.returncode,0,(mode,r.stderr))
