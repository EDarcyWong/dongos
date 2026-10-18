"""Cross-language representation checks for every permitted tagged payload."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool


def sources():
    dong = ['module payloads;error Failed=31;fn fallback(n:u64)u64{return n*3;}']
    c = [r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define DG __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fprintf(stderr,"payload check failed line %d: %s\n",__LINE__,#x);return 1;}}while(0)
typedef struct{uint64_t tag,slot;} Pair;
typedef uint64_t (DG *Callback)(uint64_t);
void DG __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t z){(void)k;(void)l;(void)f;(void)z;abort();}
static uint64_t DG triple(uint64_t n){return n*3;}
''']
    checks = []
    for sign in "iu":
        for width in (8,16,32,64):
            typ = f"{sign}{width}"
            ctyp = ("int" if sign == "i" else "uint") + str(width) + "_t"
            for prefix, target in (("opt", "?"), ("res", "!")):
                name = prefix + "_" + typ
                dong += [f'export("{name}") fn {name}(present:bool,value:{typ}){target}{typ}{{if present{{return value;}}return {"null" if prefix=="opt" else "error.Failed"};}}',
                         f'export("unwrap_{name}") fn unwrap_{name}(value:{target}{typ}){typ}{{match value{{{"some" if prefix=="opt" else "ok"}(n)=>{{return n;}},{"null" if prefix=="opt" else "err(code)"}=>{{return 0;}},}}}}']
                c += [f'extern Pair DG {name}(_Bool,{ctyp});',f'extern {ctyp} DG unwrap_{name}(Pair);']
                value = f"(int{width}_t)(INT{width}_MIN+7)" if sign == "i" else f"(uint{width}_t)(UINT{width}_MAX-7)"
                checks += [f'{{{ctyp} value={value};uint64_t bits=(uint{width}_t)value;Pair p={name}(1,value);CHECK(p.tag=={1 if prefix=="opt" else 0} && p.slot==bits);CHECK(unwrap_{name}(p)==value);p={name}(0,value);CHECK(p.tag=={0 if prefix=="opt" else 31} && p.slot==0);CHECK(unwrap_{name}(p)==0);}}']
    for prefix, target in (("opt", "?"), ("res", "!")):
        for suffix, typ, ctyp, fallback, value in (
            ("bool", "bool", "_Bool", "false", "1"),
            ("pointer", "*u64", "uint64_t *", "null", "&storage"),
            ("function", "fn(u64)u64", "Callback", "fallback", "triple"),
        ):
            name = prefix + "_" + suffix
            dong += [f'export("{name}") fn {name}(present:bool,value:{typ}){target}{typ}{{if present{{return value;}}return {"null" if prefix=="opt" else "error.Failed"};}}',
                     f'export("unwrap_{name}") fn unwrap_{name}(value:{target}{typ}){typ}{{match value{{{"some" if prefix=="opt" else "ok"}(n)=>{{return n;}},{"null" if prefix=="opt" else "err(code)"}=>{{return {fallback};}},}}}}']
            c += [f'extern Pair DG {name}(_Bool,{ctyp});',f'extern {ctyp} DG unwrap_{name}(Pair);']
            bits = "1" if suffix == "bool" else f"(uint64_t)(uintptr_t){value}"
            checks += [f'{{{ctyp} value={value};Pair p={name}(1,value);CHECK(p.tag=={1 if prefix=="opt" else 0} && p.slot=={bits});CHECK(unwrap_{name}(p)==value);p={name}(0,value);CHECK(p.tag=={0 if prefix=="opt" else 31} && p.slot==0);}}']
    dong.append('''
        enum Payload{Empty,Pointer(*u64),Function(fn(u64)u64),Boolean(bool)}
        var NUMBER:u64=99;
        const POINTER:Payload=Payload.Pointer(&NUMBER);
        const FUNCTION:Payload=Payload.Function(fallback);
        export("static_pointer") fn static_pointer()Payload{return POINTER;}
        export("static_function") fn static_function()Payload{return FUNCTION;}
        export("static_dispatch") fn static_dispatch()u64{
            var result:u64=0;
            match POINTER{Payload.Pointer(p)=>{unsafe{result+=*p;}},_=>{return 0;},}
            match FUNCTION{Payload.Function(f)=>{unsafe{result+=f(7);}},_=>{return 0;},}
            return result;
        }
        export("saved_pair") fn saved_pair()?i16{var value:i16=-23;defer{value=4;}return value;}
        ''')
    c += ['extern Pair DG static_pointer(void),static_function(void),saved_pair(void);extern uint64_t DG static_dispatch(void);',
          'int main(void){uint64_t storage=123;', *checks,
          'Pair present_null=opt_pointer(1,NULL);CHECK(present_null.tag==1 && present_null.slot==0);',
          'Pair p=static_pointer();CHECK(p.tag==1 && p.slot!=0 && *(uint64_t *)(uintptr_t)p.slot==99);',
          'p=static_function();CHECK(p.tag==2 && p.slot!=0);Callback cb=(Callback)(uintptr_t)p.slot;CHECK(cb(7)==21);',
          'CHECK(static_dispatch()==120);p=saved_pair();CHECK(p.tag==1 && p.slot==0xffe9);',
          'puts("all tagged scalar payloads and zero padding passed");return 0;}']
    return "\n".join(dong), "\n".join(c)


class L1PayloadRuntimeTests(unittest.TestCase):
    def test_all_payload_representations_debug_release(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("payload representation execution requires NASM and GCC")
        dong, c = sources()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            dg, cfile = directory / "payloads.dg", directory / "payloads.c"
            dg.write_text(dong, encoding="utf-8")
            cfile.write_text(c, encoding="utf-8")
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    assembly, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    assembly.write_text(compile_file(dg, roots=[directory], mode=mode).assembly, encoding="utf-8")
                    result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(obj), str(assembly)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror", str(cfile), str(obj), "-o", str(executable)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("all tagged scalar payloads and zero padding passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
