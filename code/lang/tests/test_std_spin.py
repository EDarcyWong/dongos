"""Independent four-thread contention checks for sync.spin."""
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
import sync.spin as spin;
export("spin_try_lock") fn try_lock(l:*spin.Lock)bool{unsafe{return spin.try_lock(l);}}
export("spin_lock") fn lock(l:*spin.Lock)void{unsafe{spin.lock(l);}}
export("spin_unlock") fn unlock(l:*spin.Lock)void{unsafe{spin.unlock(l);}}
"""


C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"sync.spin check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
struct Lock {uint32_t state;};
extern uint8_t DG spin_try_lock(struct Lock*);
extern void DG spin_lock(struct Lock*);
extern void DG spin_unlock(struct Lock*);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected sync.spin panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
#define ITERATIONS 4000
static uint64_t shared_counter;
static void worker_body(struct Lock *lock){
    for(unsigned i=0;i<ITERATIONS;++i){
        spin_lock(lock);
        shared_counter += 1;
        spin_unlock(lock);
    }
}
#ifdef _WIN32
static DWORD WINAPI worker(LPVOID ctx){worker_body((struct Lock *)ctx);return 0;}
#else
static void *worker(void *ctx){worker_body((struct Lock *)ctx);return NULL;}
#endif
int main(void){
    struct Lock lock={0};
    CHECK(spin_try_lock(&lock));
    CHECK(!spin_try_lock(&lock));
    spin_unlock(&lock);
    CHECK(spin_try_lock(&lock));
    spin_unlock(&lock);
    struct Lock contended={0};
    shared_counter=0;
#ifdef _WIN32
    HANDLE threads[4];
    for(int i=0;i<4;++i){threads[i]=CreateThread(NULL,0,worker,&contended,0,NULL);CHECK(threads[i]!=NULL);}
    CHECK(WaitForMultipleObjects(4,threads,TRUE,INFINITE)==WAIT_OBJECT_0);
    for(int i=0;i<4;++i)CHECK(CloseHandle(threads[i])!=0);
#else
    pthread_t threads[4];
    for(int i=0;i<4;++i)CHECK(pthread_create(&threads[i],NULL,worker,&contended)==0);
    for(int i=0;i<4;++i)CHECK(pthread_join(threads[i],NULL)==0);
#endif
    CHECK(shared_counter==(uint64_t)4*ITERATIONS);
    CHECK(spin_try_lock(&contended));
    spin_unlock(&contended);
    puts("native sync.spin probes passed");return 0;
}
"""


class StdSpinTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "sync" / "spin.dg", roots=[STD])
        self.assertEqual(["sync.spin"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "spin.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_spin(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native sync.spin checks require NASM and a SysV-capable GCC host compiler")
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
                    command = [cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        command += ["-no-pie", "-pthread"]
                    result = subprocess.run(command + [str(c_path), str(obj), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native sync.spin probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
