"""Compose actual Dong frame/address/cast/store/load emitters and execute them."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
import uuid

from lang.tests import test_bootstrap_nasm_function_frame as frame
from lang.tests import test_bootstrap_nasm_integer_memory_load as load
from lang.tests import test_bootstrap_nasm_integer_memory_store as store
from lang.tests import test_bootstrap_nasm_integer_cast as cast
from lang.tests import test_bootstrap_nasm_address_emit as address
from lang.tests.test_dongc import nasm_flags

ROOT = Path(__file__).resolve().parents[2]
MASK = (1 << 64) - 1
MARKER = 0x123456789ABCDEF0
ARITH_FLAGS = 0x8D5
VECTORS = [(8, False, 0xABCDEF0123456780), (8, True, 0xABCDEF0123456780),
           (16, False, 0xDEADBEEF12348000), (16, True, 0xDEADBEEF12348000),
           (32, False, 0xFFFFFFFF80000000), (32, True, 0xFFFFFFFF80000000),
           (64, False, MASK), (64, True, 1 << 63)]
HELPERS = ((frame, 'NasmFunctionFrameTests'), (load, 'NasmIntegerMemoryLoadTests'),
           (store, 'NasmIntegerMemoryStoreTests'), (cast, 'NasmIntegerCastTests'),
           (address, 'NasmAddressEmitTests'))


class FrameMemoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = ROOT/'build/test/bootstrap-frame-memory-integration'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.helpers, cls.records = [], []
        names = ('nasm_function_frame', 'nasm_integer_memory_load', 'nasm_integer_memory_store',
                 'nasm_integer_cast', 'nasm_address_emit')
        cls.sources = [ROOT/'lang/bootstrap'/(n+ext) for n in names for ext in ('.dg', '.md')]
        cls.sources += [ROOT/'lang/bootstrap'/(n+'.dg') for n in ('decimal_integer', 'nasm_memory_operand')]
        cls.sources += [Path(m.__file__) for m, _ in HELPERS]+[Path(__file__)]
        cls.inputs = cls.identities()
        try:
            for module, name in HELPERS:
                helper = getattr(module, name)
                cls.helpers.append(helper)
                helper.setUpClass()
            cls.nasm, cls.cc = cls.helpers[0].nasm, cls.helpers[0].cc
        except BaseException:
            for helper in reversed(cls.helpers):
                helper.tearDownClass()
            cls.helpers = []
            raise

    @classmethod
    def identities(cls):
        return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in cls.sources}

    @classmethod
    def tearDownClass(cls):
        for helper in reversed(cls.helpers):
            helper.tearDownClass()
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,
            source_stable=cls.identities() == cls.inputs, records=cls.records,
            helper_artifacts=[str(h.work) for h in cls.helpers],
            OS_VM_built=False, L3_selfhost_complete=False), indent=2)+'\n', encoding='utf-8')

    def command(self, args, label):
        result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=120)
        (self.work/(label+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (label, result.stderr))

    @staticmethod
    def caller(index):
        # Six pushes plus eight bytes align the nested call. R12 retains the
        # pre-call stack pointer; RBP and each saved mask bit have distinct values.
        return f'''global run_{index}
run_{index}:
 push rbx
 push r12
 push r13
 push r14
 push r15
 push rbp
 sub rsp, 8
 mov r12, rsp
 mov rbp, 0xA1B2C3D4E5F60708
 mov rbx, 0x1111
 mov r13, 0x3333
 mov r15, 0x5555
 call pipeline_{index}
 cmp rsp, r12
 jne .bad_stack
 mov rax, 0xA1B2C3D4E5F60708
 cmp rbp, rax
 jne .bad_rbp
 cmp rbx, 0x1111
 jne .bad_saved
 cmp r13, 0x3333
 jne .bad_saved
 cmp r15, 0x5555
 jne .bad_saved
 xor eax, eax
 jmp .done
.bad_stack:
 mov eax, 1
 jmp .done
.bad_rbp:
 mov eax, 2
 jmp .done
.bad_saved:
 mov eax, 3
.done:
 mov rsp, r12
 add rsp, 8
 pop rbp
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbx
 ret
'''.encode()

    def test_Dong_frame_address_cast_and_memory_compose(self):
        ft, lt, st, ct, at = (h() for h in self.helpers)
        native = 'win64' if os.name == 'nt' else 'elf64'
        for mode in ('debug', 'release'):
            def emitted(helper, case, label):
                return helper.run_cases(helper.executables[mode], [case], mode+'-'+label)[0]
            pro = emitted(ft, frame.item(0, 16, 0b10101), 'pro')
            epi = emitted(ft, frame.item(1, 16, 0b10101), 'epi')
            forward = emitted(at, address.item(8, 7, 16), 'forward')
            back = emitted(at, address.item(11, 8, -16), 'back')
            body = b'bits 64\nsection .text\n'
            for i, (width, signed, _) in enumerate(VECTORS):
                normalize = emitted(ct, cast.item(9, 0, width, signed), f'cast-{i}')
                write = emitted(st, store.item(9, 8, 0, width), f'store-{i}')
                read = emitted(lt, load.item(10, 8, 0, width, signed), f'load-{i}')
                body += f'pipeline_{i}:\n'.encode()+pro
                body += b'mov rbx, rdx\nmov rax, rsi\nmov rcx, 0xA55AA55A\ncmp rcx, rax\n'
                body += b'pushfq\npop qword [rbx+32]\n'+forward+normalize+write+read+back
                body += b'mov [rbx], r10\nmov [rbx+8], r11\npushfq\npop qword [rbx+40]\n'
                body += b'mov [rbx+48], rsi\nmov [rbx+56], rdi\n'
                body += b'mov r13, 0xCCCC\nmov r15, 0xDDDD\nmov rdi, r10\ncall nested_probe\n'
                body += b'mov [rbx+16], rax\nmov [rbx+24], rdx\n'+epi+self.caller(i)
            body += (f'nested_probe:\nmov rax, rdi\nmov rcx, 0x{MARKER:x}\nxor rax, rcx\n'
                     'mov rdx, rsp\nand edx, 15\nret\n').encode()
            asm = self.work/(mode+'.asm')
            asm.write_bytes(body)
            for fmt in ('elf64', 'win64'):
                self.command([self.nasm, '-f', fmt, *nasm_flags(self.nasm), '-o',
                              self.work/(mode+'.'+fmt+'.o'), asm], mode+'-'+fmt)
            declarations = '\n'.join(f'extern uint64_t ABI run_{i}(uint8_t*,uint64_t,uint64_t*);'
                                     for i in range(len(VECTORS)))
            functions = ','.join(f'run_{i}' for i in range(len(VECTORS)))
            main = '''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
'''+declarations+'''
typedef uint64_t (ABI *fn_t)(uint8_t*,uint64_t,uint64_t*);
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 fn_t functions[]={'''+functions+'''};
 for(unsigned i=0;i<sizeof(functions)/sizeof(functions[0]);i++){
  uint64_t value,state[10],out[10];uint8_t mem[48];
  if(fread(&value,1,8,stdin)!=8)return 91;
  memset(mem,0xCC,sizeof(mem));memset(state,0xA5,sizeof(state));
  out[0]=functions[i](mem,value,state+1);out[1]=(uintptr_t)mem;
  if(state[0]!=UINT64_C(0xA5A5A5A5A5A5A5A5)||state[9]!=state[0])return 96;
  memcpy(out+2,state+1,64);
  if(fwrite(out,1,80,stdout)!=80||fwrite(mem,1,48,stdout)!=48)return 92;
 }return 0;
}
'''
            c = self.work/(mode+'.c')
            c.write_text(main, encoding='utf-8')
            exe = self.work/(mode+('.exe' if os.name == 'nt' else ''))
            self.command([self.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', c,
                          self.work/(mode+'.'+native+'.o'), '-o', exe], mode+'-link')
            payload = b''.join(struct.pack('<Q', v) for _, _, v in VECTORS)
            result = subprocess.run([str(exe)], input=payload, capture_output=True, timeout=60)
            (self.work/(mode+'.input')).write_bytes(payload)
            (self.work/(mode+'.output')).write_bytes(result.stdout)
            (self.work/(mode+'.stderr')).write_bytes(result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(result.stdout), len(VECTORS)*128)
            for i, (width, signed, value) in enumerate(VECTORS):
                code, ptr, actual, back_ptr, returned, alignment, flags0, flags1, source, base = \
                    struct.unpack_from('<10Q', result.stdout, i*128)
                normalized = value & ((1 << width)-1)
                if signed and normalized & (1 << (width-1)):
                    normalized -= 1 << width
                normalized &= MASK
                self.assertEqual(code, 0, (mode, i, 'frame/saved registers'))
                self.assertEqual((actual, back_ptr, returned, alignment, source, base),
                                 (normalized, ptr, normalized ^ MARKER, 8, value, ptr), (mode, i))
                self.assertEqual(flags0 & ARITH_FLAGS, flags1 & ARITH_FLAGS, (mode, i, 'flags'))
                memory = result.stdout[i*128+80:(i+1)*128]
                expected = bytearray(b'\xCC'*48)
                expected[16:16+width//8] = (value & ((1 << width)-1)).to_bytes(width//8, 'little')
                self.assertEqual(memory, expected, (mode, i, 'memory and guards'))
            self.records.append(dict(mode=mode, vectors=len(VECTORS), formats=['elf64', 'win64'],
                pipeline='frame -> lea -> cast -> store -> load -> lea -> nested call -> epilogue',
                flags_preserved=True, input_registers_preserved=True, passed=True))
        self.assertEqual(self.identities(), self.inputs, 'source identity changed')


if __name__ == '__main__':
    unittest.main()
