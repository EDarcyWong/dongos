"""Execute the optional scalar backend against C and the unchanged L1 path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_source
from lang.tests.test_dongc import tool, nasm_flags


SOURCE = '''module optimized;
fn mix(a:u64,b:u64)u64 { return (a*3) ^ (b+17); }
export("formula") fn formula(a:u64,b:u64)u64 { return mix(a,b) + mix(b,a); }
export("loop_sum") fn loop_sum(n:u64)u64 {
    var i:u64=0; var s:u64=7;
    while i<n { i+=1; if i==3 {continue;} if i==17 {break;} s+=i*9; }
    return s;
}
export("swap_loop") fn swap_loop(n:u64,a:u64,b:u64)u64 {
    var x:u64=a; var y:u64=b; var i:u64=0;
    while i<n {let old=x; x=y; y=old; i+=1;}
    return x*11+y;
}
export("join_value") fn join_value(n:i64,a:i64,b:i64)i64 {
    var x:i64; if n<0 {x=a-b;} else {x=a+b;}
    if (n==0 || a<b) && !(b==0) { x=x ^ b; }
    return x;
}
export("range_sum") fn range_sum(lo:u64,hi:u64)u64 {
    var s:u64=0;
    for i in lo..hi {if i==4 {continue;} if i==23 {break;} s+=i;}
    return s;
}
export("stack_args") fn stack_args(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64 {
    return a+2*b+3*c+4*d+5*e+6*f+7*g+8*h;
}
export("constant_flow") fn constant_flow(n:u64)u64 {
    var s:u64=19; if 1+1==2 {s+=n;} else {s+=n*91;} return s;
}
export("wrap_all") fn wrap_all(a:i64,b:i64)i64 { return ~(a*b) - (-a); }
export("fallback") fn fallback(p:*u64,n:u64)u64 {
    unsafe {volatile_store(p,n);compiler_fence();return volatile_load(p);}
}
export("checked") fn checked(n:u64)u64 {return n/2;}
'''


HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define ABI __attribute__((sysv_abi))
#define D(N) extern uint64_t ABI N(uint64_t,uint64_t)
D(formula);D(l1_formula);
extern uint64_t ABI loop_sum(uint64_t), l1_loop_sum(uint64_t);
extern uint64_t ABI swap_loop(uint64_t,uint64_t,uint64_t), l1_swap_loop(uint64_t,uint64_t,uint64_t);
extern int64_t ABI join_value(int64_t,int64_t,int64_t), l1_join_value(int64_t,int64_t,int64_t);
D(range_sum);D(l1_range_sum);
extern uint64_t ABI stack_args(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
extern uint64_t ABI l1_stack_args(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
extern uint64_t ABI constant_flow(uint64_t), l1_constant_flow(uint64_t);
extern int64_t ABI wrap_all(int64_t,int64_t), l1_wrap_all(int64_t,int64_t);
extern uint64_t ABI fallback(uint64_t*,uint64_t), l1_fallback(uint64_t*,uint64_t);
extern uint64_t ABI checked(uint64_t), l1_checked(uint64_t);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{(void)l;(void)f;(void)n; fprintf(stderr,"unexpected panic %u\n",k);exit(99);}
#define CHECK(C) do { if(!(C)){fprintf(stderr,"SSA native failure line %d\n",__LINE__);return 1;} } while(0)
static uint64_t rng=UINT64_C(0xfedcba9876543210);
static uint64_t next(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
int main(void){
    for(unsigned i=0;i<4000;i++){
        uint64_t a=next(),b=next(),n=i%31;
        uint64_t expected=((a*3)^(b+17))+((b*3)^(a+17));
        CHECK(formula(a,b)==expected && l1_formula(a,b)==expected);
        uint64_t s=7;for(uint64_t j=1;j<=n;j++){if(j==3)continue;if(j==17)break;s+=j*9;}
        CHECK(loop_sum(n)==s && l1_loop_sum(n)==s);
        uint64_t x=(n&1)?b:a,y=(n&1)?a:b;
        CHECK(swap_loop(n,a,b)==x*11+y && l1_swap_loop(n,a,b)==x*11+y);
        int64_t si=(int64_t)n-15,sa=(int64_t)a,sb=(int64_t)b;
        uint64_t j=si<0?a-b:a+b;if((si==0||sa<sb)&&b!=0)j^=b;
        CHECK((uint64_t)join_value(si,sa,sb)==j && (uint64_t)l1_join_value(si,sa,sb)==j);
        uint64_t lo=i%12,hi=i%37;s=0;for(uint64_t k=lo;k<hi;k++){if(k==4)continue;if(k==23)break;s+=k;}
        CHECK(range_sum(lo,hi)==s && l1_range_sum(lo,hi)==s);
        CHECK(stack_args(a,b,3,4,5,6,7,8)==a+2*b+9+16+25+36+49+64);
        CHECK(l1_stack_args(a,b,3,4,5,6,7,8)==stack_args(a,b,3,4,5,6,7,8));
        CHECK(constant_flow(a)==19+a && l1_constant_flow(a)==19+a);
        CHECK((uint64_t)wrap_all(sa,sb)==~(a*b)+a && wrap_all(sa,sb)==l1_wrap_all(sa,sb));
        uint64_t cell=0;CHECK(fallback(&cell,a)==a&&cell==a);CHECK(l1_fallback(&cell,b)==b&&cell==b);
        CHECK(checked(a)==a/2 && l1_checked(a)==a/2);
    }
    puts("SSA C/L1 differential: 4000 cases, loops, phi cycles, signed wrap, 8 arguments, effects fallback passed");
    return 0;
}
'''


class SSANativeTests(unittest.TestCase):
    def test_release_differential_native_and_both_object_formats(self):
        compiled = compile_source(SOURCE, mode="release", optimize=1)
        records = {f["symbol"]: f for f in compiled.optimization["functions"]}
        for symbol in ("formula", "loop_sum", "swap_loop", "join_value", "range_sum", "stack_args", "constant_flow", "wrap_all"):
            self.assertEqual(records[symbol]["backend"], "ssa", records[symbol])
        self.assertEqual(records["formula"]["inlined_calls"], 2)
        self.assertEqual(records["fallback"]["backend"], "l1")
        self.assertEqual(records["checked"]["backend"], "l1")
        self.assert_native(compiled)

    def assert_native(self, compiled, *, expect_wrong_result=False):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native SSA needs NASM and GCC")
        original = compile_source(SOURCE.replace('export("', 'export("l1_'), mode="release")
        # Internal helpers also have to be renamed to avoid duplicate symbols.
        original.assembly = original.assembly.replace("__dg_m", "__l1_dg_m")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            objects = []
            for name, result in (("ssa", compiled), ("l1", original)):
                asm = directory / (name + ".asm")
                asm.write_text(result.assembly, encoding="utf-8")
                for fmt in ("elf64", "win64"):
                    obj = directory / (name + "-" + fmt + ".o")
                    command = [nasm, "-f", fmt, *nasm_flags(nasm), str(asm), "-o", str(obj)]
                    run = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    if fmt == ("win64" if os.name == "nt" else "elf64"):
                        objects.append(obj)
            c = directory / "host.c"
            c.write_text(HARNESS, encoding="utf-8")
            exe = directory / ("host.exe" if os.name == "nt" else "host")
            run = subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(c),
                                  *(str(p) for p in objects), "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            if expect_wrong_result:
                self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
                self.assertIn("SSA native failure line", run.stderr)
            else:
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_debug_checks_and_memory_are_not_silently_optimized(self):
        source = 'module test; export("f") fn f(x:u64)u64 {return x+1;}'
        base = compile_source(source)
        opt = compile_source(source, optimize=1)
        self.assertEqual(base.assembly, opt.assembly)
        self.assertIn("__dong_panic", opt.runtime_symbols)
        self.assertEqual(opt.optimization["functions"][0]["backend"], "l1")
        with self.assertRaises(ValueError):
            compile_source(source, optimize=True)

    def test_spilled_phi_cycles_execute_the_real_backend(self):
        # The independent C test above uses the same backend with real pressure;
        # this additionally forces an empty physical register set.
        from unittest.mock import patch
        from lang.dongc import ssa_lower
        actual = ssa_lower.assembly
        with patch.object(ssa_lower, "assembly", side_effect=lambda f: actual(f, registers=())):
            compiled = compile_source(SOURCE, mode="release", optimize=1)
        for record in compiled.optimization["functions"]:
            if record["backend"] == "ssa":
                self.assertGreater(record["allocation"]["spills"], 0)
        self.assert_native(compiled)

    def test_independent_native_oracle_rejects_a_compiled_wrong_lowering(self):
        from unittest.mock import patch
        from lang.dongc import ssa_lower
        # Both valid SSA and valid object code: only the language behavior is
        # wrong. A build error or absent executable cannot satisfy this test.
        with patch.dict(ssa_lower.OPS, {"+": "sub"}):
            compiled = compile_source(SOURCE, mode="release", optimize=1)
        self.assert_native(compiled, expect_wrong_result=True)


if __name__ == "__main__":
    unittest.main()
