"""Independent C bit-by-bit reference checks for core.bitset."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[2]
STD = ROOT / "lang" / "std"


def wrapper_source():
    return """module probe;
import core.bitset as bitset;
export("bitset_storage_bytes") fn storage_bytes(bit_count:usize)usize{return bitset.storage_bytes(bit_count);}
export("bitset_test") fn test(bytes:[]const u8,bit_count:usize,index:usize,out:*bool)bool{unsafe{return bitset.test(bytes,bit_count,index,out);}}
export("bitset_set_range") fn set_range(bytes:[]u8,bit_count:usize,start:usize,count:usize,value:bool)bool{unsafe{return bitset.set_range(bytes,bit_count,start,count,value);}}
export("bitset_find_clear_run") fn find_clear_run(bytes:[]const u8,bit_count:usize,start:usize,count:usize,out:*usize)bool{unsafe{return bitset.find_clear_run(bytes,bit_count,start,count,out);}}
"""


C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"core.bitset check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
struct Bytes {uint8_t *ptr; uint64_t len;};
extern uint64_t DG bitset_storage_bytes(uint64_t);
extern uint8_t DG bitset_test(struct Bytes,uint64_t,uint64_t,uint8_t*);
extern uint8_t DG bitset_set_range(struct Bytes,uint64_t,uint64_t,uint64_t,uint8_t);
extern uint8_t DG bitset_find_clear_run(struct Bytes,uint64_t,uint64_t,uint64_t,uint64_t*);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected core.bitset panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
/* independent bit-by-bit reference model (no mask/word tricks) */
static uint64_t ref_storage(uint64_t n){return n/8 + (n%8!=0);}
static int ref_bit(const uint8_t *b,uint64_t i){return (int)((b[i/8] >> (i%8)) & 1u);}
static void ref_set(uint8_t *b,uint64_t i,int v){uint8_t m=(uint8_t)(1u<<(i%8)); if(v)b[i/8]=(uint8_t)(b[i/8]|m); else b[i/8]=(uint8_t)(b[i/8]&(uint8_t)~m);}
static int ref_find(const uint8_t *b,uint64_t n,uint64_t start,uint64_t count,uint64_t *out){
    if(start>n || count>n-start) return 0;
    if(count==0){*out=start;return 1;}
    for(uint64_t s=start;s<=n-count;s++){
        int ok=1;
        for(uint64_t i=0;i<count;i++){if(ref_bit(b,s+i)){ok=0;break;}}
        if(ok){*out=s;return 1;}
    }
    return 0;
}
static uint64_t rng(uint64_t *s){*s^=*s<<13;*s^=*s>>7;*s^=*s<<17;return *s;}

int main(void){
    /* storage_bytes against reference incl. USIZE_MAX without overflow */
    {uint64_t vs[]={0,1,7,8,9,15,16,63,64,65,1023,1024,UINT64_MAX,UINT64_MAX-1};
     for(size_t i=0;i<sizeof(vs)/sizeof(vs[0]);i++)CHECK(bitset_storage_bytes(vs[i])==ref_storage(vs[i]));}

    /* test: pointwise against reference; out unchanged on failure; input unchanged */
    {
        uint64_t n=77; uint8_t real[16+16]; uint8_t *data=real+8;
        uint8_t exp[16+16]; uint8_t *edata=exp+8;
        memset(real,0xcc,sizeof(real)); memset(exp,0xcc,sizeof(exp));
        memset(data,0xa3,16); memset(edata,0xa3,16);
        data[9]=0xe3; edata[9]=0xe3;   /* high tail bits 77..79 = 1 */
        data[10]=0xa5; edata[10]=0xa5; /* extra bytes non-zero */
        data[15]=0x5a; edata[15]=0x5a;
        struct Bytes B={data,10};
        for(uint64_t i=0;i<n;i++){
            uint8_t got=0x7f; CHECK(bitset_test(B,n,i,&got) && got==(uint8_t)ref_bit(data,i));
            CHECK(!memcmp(data,edata,16));
            for(int g=0;g<8;g++)CHECK(real[g]==0xcc && real[8+16+g]==0xcc);
        }
        #define TCHK() do{CHECK(!memcmp(data,edata,16));for(int g=0;g<8;g++)CHECK(real[g]==0xcc && real[8+16+g]==0xcc);}while(0)
        uint8_t sent=0x5a;
        CHECK(!bitset_test(B,n,n,&sent) && sent==0x5a);
        TCHK();
        sent=0x5a; CHECK(!bitset_test(B,n,UINT64_MAX,&sent) && sent==0x5a);
        TCHK();
        { struct Bytes S={data,9}; uint8_t o=0x11; CHECK(!bitset_test(S,n,72,&o) && o==0x11); }
        TCHK();
        { struct Bytes S={NULL,0}; uint8_t o=0x22; CHECK(!bitset_test(S,0,0,&o) && o==0x22); }
        TCHK();
        #undef TCHK
    }

    /* set_range: full-buffer compare against reference over many ranges */
    {
        uint64_t n=61; uint8_t real[9+16]; uint8_t *data=real+8;
        uint8_t exp[9+16]; uint8_t *edata=exp+8;
        memset(real,0xcc,sizeof(real)); memset(exp,0xcc,sizeof(exp));
        memset(data,0x00,9); memset(edata,0x00,9);
        data[7]=0xe0; edata[7]=0xe0;   /* high tail bits 61..63 = 1 (non-zero) */
        data[8]=0xa5; edata[8]=0xa5;   /* extra byte past storage non-zero */
        struct Bytes B={data,9};
        uint64_t seed=UINT64_C(0x123456789abcdef0);
        for(int k=0;k<40;k++){uint64_t i=rng(&seed)%n; ref_set(edata,i,1);}
        memcpy(data,edata,9);
        for(int trial=0;trial<2000;trial++){
            uint64_t start=rng(&seed)%(n+2);
            uint64_t count=rng(&seed)%(n+2);
            int value=(int)(rng(&seed)&1);
            int valid=(start<=n)&&(count<=n-start);
            uint8_t ret=bitset_set_range(B,n,start,count,(uint8_t)value);
            CHECK(ret==(uint8_t)valid);
            if(valid) for(uint64_t i=start;i<start+count;i++) ref_set(edata,i,value);
            CHECK(!memcmp(data,edata,9));
            for(int g=0;g<8;g++)CHECK(real[g]==0xcc && real[8+9+g]==0xcc);
        }
        #define SCHK() do{for(int g=0;g<8;g++)CHECK(real[g]==0xcc && real[8+9+g]==0xcc);}while(0)
        /* count=0 at legal end succeeds, writes nothing */
        { uint8_t before[9]; memcpy(before,data,9); CHECK(bitset_set_range(B,n,n,0,0) && !memcmp(data,before,9)); }
        SCHK();
        /* invalid storage: whole buffer untouched */
        { struct Bytes S={data,7}; uint8_t before[9]; memcpy(before,data,9);
          CHECK(!bitset_set_range(S,n,0,1,1) && !memcmp(data,before,9)); }
        SCHK();
        #undef SCHK
    }

    /* find_clear_run: against reference; lowest candidate; count=0; not found */
    {
        uint64_t n=57; uint8_t real[8+16]; uint8_t *data=real+8;
        memset(real,0xcc,sizeof(real));
        memset(data,0,8);
        data[7]=0x7e;   /* tail bits 57..63: 57..62 = 1, bit 63 = 0 */
        struct Bytes B={data,8};
        uint64_t seed=UINT64_C(0xdeadbeef);
        for(int k=0;k<25;k++){uint64_t i=rng(&seed)%n; ref_set(data,i,1);}
        for(int trial=0;trial<2000;trial++){
            uint64_t start=rng(&seed)%(n+2);
            uint64_t count=rng(&seed)%(n+2);
            uint64_t refout=UINT64_C(0xf0f0f0f0f0f0f0f0);
            uint64_t got=UINT64_C(0x0f0f0f0f0f0f0f0f);
            int rok=ref_find(data,n,start,count,&refout);
            uint8_t snap[8]; memcpy(snap,data,8);
            uint8_t ret=bitset_find_clear_run(B,n,start,count,&got);
            CHECK(ret==(uint8_t)rok);
            if(rok) CHECK(got==refout); else CHECK(got==UINT64_C(0x0f0f0f0f0f0f0f0f));
            CHECK(!memcmp(data,snap,8));
            for(int g=0;g<8;g++)CHECK(real[g]==0xcc && real[8+8+g]==0xcc);
        }
        #define FK2() do{for(int g=0;g<8;g++)CHECK(real[g]==0xcc && real[8+8+g]==0xcc);}while(0)
        { memset(data,0,8); data[7]=0x7e; ref_set(data,2,1); ref_set(data,5,1);
          uint8_t snap8[8]; memcpy(snap8,data,8);
          uint64_t o=99; CHECK(bitset_find_clear_run(B,n,0,3,&o) && o==6);
          CHECK(!memcmp(data,snap8,8)); FK2();
          o=99; CHECK(bitset_find_clear_run(B,n,1,2,&o) && o==3);
          CHECK(!memcmp(data,snap8,8)); FK2();
          o=99; CHECK(bitset_find_clear_run(B,n,7,0,&o) && o==7);
          CHECK(!memcmp(data,snap8,8)); FK2();
          o=99; CHECK(bitset_find_clear_run(B,n,n,0,&o) && o==n);
          CHECK(!memcmp(data,snap8,8)); FK2();
          o=99; CHECK(!bitset_find_clear_run(B,n,n+1,0,&o) && o==99);
          CHECK(!memcmp(data,snap8,8)); FK2(); }
        { memset(data,0,8); data[7]=0x7e; for(uint64_t i=0;i<n;i++)ref_set(data,i,1);
          uint8_t snap8[8]; memcpy(snap8,data,8);
          uint64_t o=99; CHECK(!bitset_find_clear_run(B,n,0,1,&o) && o==99);
          CHECK(!memcmp(data,snap8,8)); FK2(); }
        /* input unchanged after search */
        { uint8_t snap[8]; memcpy(snap,data,8);
          uint64_t o=99; bitset_find_clear_run(B,n,0,1,&o); CHECK(!memcmp(data,snap,8)); }
        FK2();
        #undef FK2
    }
    /* real 0/1 logical values, odd address, short storage, USIZE_MAX */
    {
        uint8_t buf_g[3+16]; uint8_t *buf=buf_g+8;
        uint8_t e17[3];
        memset(buf_g,0xcc,sizeof(buf_g));
        memset(buf,0,3); buf[2]=0xfe;   /* tail bits 17..23 = 1 */
        memcpy(e17,buf,3);
        struct Bytes B={buf,3};
        #define B17() do{CHECK(!memcmp(buf,e17,3));for(int _g=0;_g<8;_g++)CHECK(buf_g[_g]==0xcc&&buf_g[8+3+_g]==0xcc);}while(0)
        uint8_t b=0;
        CHECK(bitset_set_range(B,17,5,1,1)); ref_set(e17,5,1); B17();
        CHECK(bitset_test(B,17,5,&b) && b==1); B17();
        CHECK(bitset_set_range(B,17,5,1,0)); ref_set(e17,5,0); B17();
        CHECK(bitset_test(B,17,5,&b) && b==0); B17();
        memset(buf,0,3); buf[2]=0xfe; memset(e17,0,3); e17[2]=0xfe;
        CHECK(bitset_set_range(B,17,0,1,1)); ref_set(e17,0,1); B17();
        CHECK(bitset_test(B,17,0,&b) && b==1); B17();
        CHECK(bitset_set_range(B,17,16,1,1)); ref_set(e17,16,1); B17();
        CHECK(bitset_test(B,17,16,&b) && b==1); B17();
        memset(buf,0,3); buf[2]=0xfe; memset(e17,0,3); e17[2]=0xfe;
        CHECK(bitset_set_range(B,17,0,5,1)); for(int _i=0;_i<5;_i++)ref_set(e17,_i,1); B17();
        uint64_t o=99; CHECK(bitset_find_clear_run(B,17,0,3,&o) && o==5); B17();
        #undef B17
        /* logical length 0 for all three interfaces */
        { uint8_t zero_g[8+1+8]; uint8_t *zero_buf=zero_g+8; struct Bytes Z={zero_buf,1}; uint64_t zo=0x55;
          uint8_t zb=0x3c;
          memset(zero_g,0xa9,sizeof(zero_g));
          #define ZC() do{for(int _g=0;_g<8;_g++)CHECK(zero_g[_g]==0xa9&&zero_g[8+1+_g]==0xa9);}while(0)
          CHECK(!bitset_test(Z,0,0,&zb) && zb==0x3c);
          ZC(); CHECK(zero_buf[0]==0xa9);
          CHECK(bitset_set_range(Z,0,0,0,1));
          ZC(); CHECK(zero_buf[0]==0xa9);
          CHECK(!bitset_set_range(Z,0,0,1,1));
          ZC(); CHECK(zero_buf[0]==0xa9);
          CHECK(bitset_find_clear_run(Z,0,0,0,&zo) && zo==0);
          ZC(); CHECK(zero_buf[0]==0xa9);
          zo=0x55; CHECK(!bitset_find_clear_run(Z,0,0,1,&zo) && zo==0x55);
          ZC(); CHECK(zero_buf[0]==0xa9);
          zo=0x55; CHECK(!bitset_find_clear_run(Z,0,1,0,&zo) && zo==0x55);
          ZC(); CHECK(zero_buf[0]==0xa9);
          #undef ZC
          }
        /* logical length 1 for all three interfaces */
        { uint8_t one_g[8+1+8]; uint8_t *one_buf=one_g+8; struct Bytes O1={one_buf,1}; uint64_t zo=0x55; uint8_t zb=0x3c;
          memset(one_g,0xa9,sizeof(one_g));
          memset(one_buf,0,1);
          #define OC() do{for(int _g=0;_g<8;_g++)CHECK(one_g[_g]==0xa9&&one_g[8+1+_g]==0xa9);}while(0)
          CHECK(bitset_test(O1,1,0,&zb) && zb==0);
          OC(); CHECK(one_buf[0]==0x00);
          CHECK(bitset_set_range(O1,1,0,1,1));
          OC(); CHECK(one_buf[0]==0x01);
          CHECK(bitset_test(O1,1,0,&zb) && zb==1);
          OC(); CHECK(one_buf[0]==0x01);
          zo=0x55; CHECK(!bitset_find_clear_run(O1,1,0,1,&zo) && zo==0x55);
          OC(); CHECK(one_buf[0]==0x01);
          CHECK(bitset_set_range(O1,1,0,1,0));
          OC(); CHECK(one_buf[0]==0x00);
          zo=0x55; CHECK(bitset_find_clear_run(O1,1,0,1,&zo) && zo==0);
          OC(); CHECK(one_buf[0]==0x00);
          zb=0x3c; CHECK(!bitset_test(O1,1,1,&zb) && zb==0x3c);
          OC(); CHECK(one_buf[0]==0x00);
          CHECK(bitset_set_range(O1,1,1,0,1));
          OC(); CHECK(one_buf[0]==0x00);
          CHECK(!bitset_set_range(O1,1,0,2,1));
          OC(); CHECK(one_buf[0]==0x00);
          #undef OC
          }
        /* forced odd address works for all three interfaces */
        uint8_t odd_storage[8+4+8+2];
        uint8_t *odd=odd_storage+8+(((uintptr_t)odd_storage&1)?0:1); /* actually odd */
        CHECK(((uintptr_t)odd&1)==1);
        memset(odd_storage,0xa9,sizeof(odd_storage));
        memset(odd,0,4);
        odd[1]=0xfe;   /* n=9: byte1 = bit 8 logical(0) + bits 9..15 tail(non-zero) */
        uint8_t eodd[4]; memcpy(eodd,odd,4);
        struct Bytes OB={odd,4};
        #define OD() do{CHECK(!memcmp(odd,eodd,4));for(int _g=0;_g<8;_g++)CHECK(odd[_g-8]==0xa9&&odd[4+_g]==0xa9);}while(0)
        CHECK(bitset_set_range(OB,9,0,9,1)); for(int _i=0;_i<9;_i++)ref_set(eodd,_i,1); OD();
        CHECK(bitset_test(OB,9,7,&b) && b==1); OD();
        o=99; CHECK(!bitset_find_clear_run(OB,9,0,1,&o) && o==99); OD();
        CHECK(bitset_set_range(OB,9,3,1,0)); ref_set(eodd,3,0); OD();
        o=99; CHECK(bitset_find_clear_run(OB,9,0,1,&o) && o==3); OD();
        /* find short storage: storage_bytes(n) > len -> false, no access, out unchanged */
        { struct Bytes S={odd,3}; o=99; CHECK(!bitset_find_clear_run(S,30,0,1,&o) && o==99); }
        OD();
        { struct Bytes S={odd,0}; uint8_t oo=0x7e; CHECK(!bitset_test(S,30,29,&oo) && oo==0x7e); }
        OD();
        /* USIZE_MAX with real empty/small storage: all three interfaces reject */
        { struct Bytes E={NULL,0}; uint8_t oo=0x7e; uint64_t uu=99;
          CHECK(!bitset_test(E,UINT64_MAX,0,&oo) && oo==0x7e);
          OD();
          CHECK(!bitset_set_range((struct Bytes){(uint8_t*)odd,4},UINT64_MAX,0,1,1));
          OD();
          CHECK(!bitset_find_clear_run(E,UINT64_MAX,0,1,&uu) && uu==99); }
        OD();
        #undef OD
    }

    /* fixed-seed random set/test/search interleave with guards + extra storage */
    {
        uint64_t n=77; uint8_t guard[10+2+16]; uint8_t *data=guard+8;
        uint8_t exp[10+2+16]; uint8_t *edata=exp+8;
        memset(guard,0xa5,sizeof(guard)); memset(exp,0xa5,sizeof(exp));
        memset(data,0,12); memset(edata,0,12);
        data[9]=0xe0; edata[9]=0xe0;   /* high tail bits 77..79 = 1 (non-zero) */
        data[10]=0xa5; edata[10]=0xa5; /* extra bytes past storage non-zero */
        data[11]=0x5a; edata[11]=0x5a;
        struct Bytes B={data,12};
        uint64_t seed=UINT64_C(0x1a2b3c4d5e6f7080);
        for(int t=0;t<3000;t++){
            uint64_t op=rng(&seed)&3;
            if(op==0){
                uint64_t start=rng(&seed)%(n+2);
                uint64_t count=rng(&seed)%(n+2);
                int value=(int)(rng(&seed)&1);
                int valid=(start<=n)&&(count<=n-start);
                uint8_t ret=bitset_set_range(B,n,start,count,(uint8_t)value);
                CHECK(ret==(uint8_t)valid);
                if(valid) for(uint64_t i=start;i<start+count;i++) ref_set(edata,i,value);
            } else if(op==1){
                uint64_t i=rng(&seed)%(n+1);
                uint8_t got=0x3c; int valid=(i<n);
                uint8_t ret=bitset_test(B,n,i,&got);
                CHECK(ret==(uint8_t)valid);
                if(valid) CHECK(got==(uint8_t)ref_bit(edata,i)); else CHECK(got==0x3c);
            } else {
                uint64_t start=rng(&seed)%(n+2);
                uint64_t count=rng(&seed)%(n+2);
                uint64_t refout=UINT64_C(0xf0f0f0f0f0f0f0f0);
                uint64_t got=UINT64_C(0x0f0f0f0f0f0f0f0f);
                int rok=ref_find(edata,n,start,count,&refout);
                uint8_t ret=bitset_find_clear_run(B,n,start,count,&got);
                CHECK(ret==(uint8_t)rok);
                if(rok) CHECK(got==refout); else CHECK(got==UINT64_C(0x0f0f0f0f0f0f0f0f));
            }
            CHECK(!memcmp(data,edata,12));
            for(int g=0;g<8;g++)CHECK(guard[g]==0xa5 && guard[8+12+g]==0xa5);
        }
    }

    puts("native core.bitset probes passed");return 0;
}
"""


class StdBitsetTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "core" / "bitset.dg", roots=[STD])
        self.assertEqual(["core.bitset"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "bitset.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_bitset(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native core.bitset checks require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c_path = directory / "probe.c"
            c_path.write_text(C_SOURCE, encoding="utf-8")
            object_format = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    exe = directory / (mode + (".exe" if os.name == "nt" else ""))
                    with tempfile.TemporaryDirectory() as roots:
                        entry = Path(roots) / "probe.dg"
                        entry.write_text(wrapper_source(), encoding="utf-8")
                        compiled = compile_file(entry, roots=[Path(roots), STD], mode=mode)
                    asm.write_text(compiled.assembly, encoding="utf-8")
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror", str(c_path), str(obj), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native core.bitset probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
