"""CR38: actual Dong checked 64-bit SysV function, exact text, two object formats and native call/ret.

Only this module and its integrated import closure are staged. Python supplies both
an independent text oracle and the arbitrary-precision range/value/status oracle.
"""
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

ROOT = Path(__file__).resolve().parents[2]
WORKS = ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags as _nasm_flags

SOURCE = ROOT / 'lang/bootstrap/nasm_checked_u64_function.dg'
DOC = SOURCE.with_suffix('.md')
DEPENDENCIES = [ROOT / 'lang/bootstrap' / (n + '.dg') for n in (
    'nasm_symbol', 'decimal_integer', 'nasm_sysv_function_entry',
    'nasm_function_frame', 'nasm_sysv_incoming_args', 'sysv_integer_args',
    'nasm_memory_operand', 'nasm_integer_load', 'nasm_integer_memory_load',
    'nasm_integer_memory_store', 'nasm_checked_add_sub', 'nasm_checked_multiply',
    'nasm_checked_negate', 'nasm_block_emit', 'nasm_sysv_function_exit',
    'nasm_sysv_return_values', 'sysv_return_plan')]
OK, INVALID, CAPACITY = 0, 1, 2
ADD, SUB, MUL, NEG = 0, 1, 2, 3
MAX = (1 << 64) - 1
MIN = 1 << 63
I64MAX = MIN - 1
HI32 = 1 << 32
PREFLIGHTS = 28

WRAPPER = '''module probe.checked_u64_export;
import bootstrap.nasm_checked_u64_function as f;
export("dong_checked_u64_emit") pub unsafe fn emit(m:*const u8,mn:usize,i:*const u8,inn:usize,
 operation:u64,signed:u64,error_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return f.emit(slice_from_raw_parts(m,mn),slice_from_raw_parts(i,inn),operation,signed!=0,error_block,
  slice_from_raw_parts(out,no),written);
}}
'''
HARNESS = r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef const uint8_t *N;
extern uint64_t ABI dong_checked_u64_emit(N,uint64_t,N,uint64_t,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void rd(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t *ro_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static int ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;return VirtualProtect(p,n,PAGE_READONLY,&old)!=0;
#else
 return mprotect(p,n,PROT_READ)==0;
#endif
}
static int ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;return VirtualFree(p,0,MEM_RELEASE)!=0;
#else
 return munmap(p,n)==0;
#endif
}
#define FAKE(x) ((N)(uintptr_t)(x))
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[8192],saved[8192];unsigned failed=0;
 uint8_t*m=arena+64,*it=arena+192,*o=arena+1024;uint64_t*w=(uint64_t*)(arena+6144);
 for(unsigned k=0;k<28;k++){
  memset(arena,0xa5,sizeof(arena));memset(m,'a',96);memset(it,'b',96);
  N pm=m,pi=it;uint64_t lm=4,li=4,op=0,sg=0,blk=10,cap=4096;uint8_t*po=o;uint64_t*pw=w;
  switch(k){
   case 0:pw=NULL;break;
   case 1:pw=(uint64_t*)(arena+6145);break;
   case 2:pw=(uint64_t*)(uintptr_t)(UINT64_MAX-7);po=NULL;cap=0;break;
   case 3:po=(uint8_t*)(uintptr_t)(UINT64_MAX-2047);break;
   case 4:po=NULL;break;
   case 5:pm=NULL;break;case 6:pi=NULL;break;
   case 7:pm=FAKE(UINT64_MAX-3);lm=8;break;
   case 8:pi=FAKE(UINT64_MAX-1);break;
   case 9:pw=(uint64_t*)o;break;
   case 10:pw=(uint64_t*)(o+4088);break;
   case 11:lm=64;pw=(uint64_t*)m;break;
   case 12:lm=64;pw=(uint64_t*)(m+56);break;
   case 13:li=64;pw=(uint64_t*)it;break;
   case 14:li=64;pw=(uint64_t*)(it+56);break;
   case 15:lm=64;po=m+63;cap=8;break;
   case 16:li=64;po=it+63;cap=8;break;
   case 17:pm=o+4000;lm=64;break;
   case 18:pi=o+4000;li=64;break;
   case 19:lm=0;break;case 20:li=0;break;
   case 21:lm=65;break;case 22:li=65;break;
   case 23:op=4;break;case 24:op=UINT64_MAX;break;
   case 25:op=3;sg=0;cap=0;break;
   case 26:op=3;sg=0;break;
   default:blk=UINT64_MAX;break;
  }
  memcpy(saved,arena,sizeof(arena));
  uint64_t st=dong_checked_u64_emit(pm,lm,pi,li,op,sg,blk,po,cap,pw);
  int same=!memcmp(saved,arena,sizeof(arena));
  if(st!=1||!same){fprintf(stderr,"invalid preflight %u status %u unchanged %d\n",k,(unsigned)st,same);failed++;}
 }
 if(failed){exit(93);}
 return 28;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t pre=invalid(),count;rd(&count,8);wr(&pre,8);
 while(count--){
  uint64_t h[10];rd(h,sizeof(h));uint64_t pool=h[0],flags=h[8],cap=h[9];
  if(pool>4096||cap>8192||h[1]>pool||h[2]>pool-h[1]||h[3]>pool||h[4]>pool-h[3])exit(94);
  uint8_t*in=malloc(pool+64),*copy=malloc(pool+1),*out=malloc(cap+64);
  static _Alignas(8) uint64_t meta[3];if(!in||!copy||!out)exit(95);
  memset(in,0xa5,pool+64);rd(in+32,pool);memcpy(copy,in+32,pool);
  uint8_t*base=in+32,*page=NULL;uint64_t protected_ok=1,pages=16384;
  if(flags&1){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,pool);protected_ok=ro_protect(page,pages);if(!protected_ok)exit(97);base=page;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*w=meta+1;
  uint64_t st=dong_checked_u64_emit(base+h[1],h[2],base+h[3],h[4],h[5],h[6],h[7],cap?out+32:NULL,cap,w);
  uint64_t valid=protected_ok&&!memcmp(copy,base,pool)&&filled(in,32)&&filled(in+32+pool,32)&&
   filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(w,8);
  else valid=valid&&*w<=cap&&filled(out+32+*w,cap-*w);
  uint64_t response[4]={st,valid,st?0:*w,protected_ok};wr(response,32);wr(out+32,response[2]);
  if(page&&!ro_free(page,pages))exit(98);
  free(in);free(copy);free(out);
 }return 0;
}
'''
NATIVE_MAIN = r'''
#include <stdint.h>
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
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 static uint64_t io[STATE+2];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  memset(io,0,sizeof(io));io[0]=io[STATE+1]=0xa5a5a5a5a5a5a5a5ull;
  table[i](io+1);
  if(io[0]!=0xa5a5a5a5a5a5a5a5ull||io[STATE+1]!=0xa5a5a5a5a5a5a5a5ull)return 96;
  if(fwrite(io+1,8,STATE,stdout)!=STATE)return 92;
 }return 0;
}
'''
RAX, RDX, RSP_BEFORE, RSP_AFTER, RBX_BEFORE, RBX_AFTER, RBP_AFTER, R12_AFTER, CANARY_AFTER, ALIGN, STATE = (
    0, 1, 2, 3, 4, 5, 6, 7, 11, 12, 13)
CALLER = {'rbx': 0x0bbb0bbb0bbb0bbb, 'rbp': 0x0b0b0b0b0b0b0b0b,
          'r12': 0x1212121212121212, 'r13': 0x1313131313131313,
          'r14': 0x1414141414141414, 'r15': 0x1515151515151515}
CANARY = 0x5ca1ab1e0ddba11c


def symbol(module, item):
    return '__dong_m' + module.hex() + '_n' + item.hex()


def expected_text(module, item, operation, signed, error_block):
    """Independent literal instruction model, not any production emitter output."""
    lines = [symbol(module, item) + ':', 'push rbp', 'mov rbp, rsp', 'sub rsp, 32',
             'mov qword [rbp - 8], rdi', 'mov qword [rbp - 16], rsi']
    branch = ('jo' if signed else 'jc') + ' __dong_b%d' % error_block
    if operation in (ADD, SUB):
        lines += ['mov rax, qword [rbp - 8]', 'mov rcx, qword [rbp - 16]',
                  ('add' if operation == ADD else 'sub') + ' rax, rcx', branch]
    elif operation == MUL:
        lines += ['mov rdi, qword [rbp - 8]', 'mov rsi, qword [rbp - 16]', 'mov rax, rdi']
        if signed:
            lines += ['imul rax, rsi', 'jo __dong_b%d' % error_block]
        else:
            lines += ['mul rsi', 'jc __dong_b%d' % error_block]
    else:
        lines += ['mov rax, qword [rbp - 8]', 'neg rax', 'jo __dong_b%d' % error_block]
    lines += ['mov qword [rbp - 24], rax', 'mov rax, 0', 'mov qword [rbp - 32], rax',
              'mov rax, qword [rbp - 24]', 'mov rdx, qword [rbp - 32]',
              'add rsp, 32', 'pop rbp', 'ret',
              '__dong_b%d:' % error_block,
              'mov rax, 0', 'mov qword [rbp - 24], rax', 'mov rax, 1', 'mov qword [rbp - 32], rax',
              'mov rax, qword [rbp - 24]', 'mov rdx, qword [rbp - 32]',
              'add rsp, 32', 'pop rbp', 'ret']
    return ('\n'.join(lines) + '\n').encode('ascii')


def to_i64(value):
    return value - (1 << 64) if value >= MIN else value


def interpret(operation, signed, a, b):
    if operation == NEG:
        if a == MIN:
            return 0, 1
        return (-to_i64(a)) & MAX, 0
    if operation == ADD:
        result = (to_i64(a) + to_i64(b)) if signed else a + b
    elif operation == SUB:
        result = (to_i64(a) - to_i64(b)) if signed else a - b
    else:
        result = (to_i64(a) * to_i64(b)) if signed else a * b
    if signed:
        if result < -MIN or result > I64MAX:
            return 0, 1
        return result & MAX, 0
    if result < 0 or result > MAX:
        return 0, 1
    return result, 0


VECTORS = [
    (b'm', b'f0', ADD, False, 10, 1, 2),
    (b'm', b'f1', ADD, False, 11, MAX, 1),
    (b'm', b'f2', SUB, False, 12, 5, 3),
    (b'm', b'f3', SUB, False, 13, 0, 1),
    (b'm', b'f4', MUL, False, 14, 3, 5),
    (b'm', b'f5', MUL, False, 15, MAX, 2),
    (b'm', b'f6', MUL, False, 16, HI32, HI32),
    (b'm', b'f7', ADD, True, 17, 1, 2),
    (b'm', b'f8', ADD, True, 18, MIN, MAX),
    (b'm', b'f9', SUB, True, 19, 5, 3),
    (b'm', b'fa', SUB, True, 20, MIN, 1),
    (b'm', b'fb', MUL, True, 21, 3, 5),
    (b'm', b'fc', MUL, True, 22, MIN, MAX),
    (b'm', b'fd', MUL, True, 23, MAX, 2),
    (b'm', b'fe', NEG, True, 24, 0, 11),
    (b'm', b'ff', NEG, True, 25, 0, 99),
    (b'm', b'fg', NEG, True, 26, MAX, 1),
    (b'm', b'fh', NEG, True, 27, MIN, 2),
    (b'm', b'fi', NEG, True, 28, I64MAX, 3),
    (b'm', b'fj', ADD, False, 29, 0, 0),
    (b'\xff' * 64, bytes(range(64)), MUL, False, MAX - 1, 0, MAX),
    (b'a\x00b', b'c\xffd', ADD, True, 1 << 19, 1 << 62, 1 << 62),
]


def nasm_flags(nasm):
    flags = list(_nasm_flags(nasm))
    if '-w-reloc-rel-dword' not in flags:
        flags.append('-w-reloc-rel-dword')
    return flags


class NasmCheckedU64FunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('CR38 requires native NASM/GCC')
        cls.inputs = cls.digests()
        cls.work = ROOT / 'build/test/bootstrap-nasm-checked-u64-function' / ('run-' + uuid.uuid4().hex)
        cls.work.mkdir(parents=True)
        cls.records = []
        cls.native = 'win64' if os.name == 'nt' else 'elf64'
        (cls.work / 'probe.c').write_text(HARNESS, encoding='utf-8')
        cls.executables = cls.build_all('good', SOURCE.read_text(encoding='utf-8'))

    @staticmethod
    def digests():
        return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [SOURCE, DOC, Path(__file__), *DEPENDENCIES]}

    @classmethod
    def command(cls, cmd, name):
        result = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=180)
        (cls.work / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            raise AssertionError((name, result.returncode, result.stdout, result.stderr))

    @classmethod
    def build_all(cls, name, text):
        root = cls.work / name
        (root / 'bootstrap').mkdir(parents=True)
        (root / 'probe').mkdir()
        (root / 'bootstrap/nasm_checked_u64_function.dg').write_text(text, encoding='utf-8')
        for dep in DEPENDENCIES:
            shutil.copyfile(dep, root / 'bootstrap' / dep.name)
        wrapper = root / 'probe/checked_u64_export.dg'
        wrapper.write_text(WRAPPER, encoding='utf-8')
        executables = {}
        for mode in ('debug', 'release'):
            tag = name + '-' + mode
            assembly = compile_file(wrapper, roots=[root], mode=mode).assembly
            asm, obj = cls.work / (tag + '.asm'), cls.work / (tag + '.o')
            asm.write_text(assembly, encoding='utf-8')
            for fmt in ('elf64', 'win64'):
                output = obj if fmt == cls.native else cls.work / (tag + '.' + fmt + '.o')
                cls.command([cls.nasm, '-f', fmt, *nasm_flags(cls.nasm), '-o', output, asm], tag + '-' + fmt)
            exe = cls.work / (tag + ('.exe' if os.name == 'nt' else ''))
            cls.command([cls.cc, '-std=c11', '-D_GNU_SOURCE', '-O2', '-Wall', '-Wextra', '-Werror',
                         cls.work / 'probe.c', obj, '-o', exe], tag + '-link')
            executables[mode] = exe
        return executables

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, 'work'):
            return
        after = cls.digests()
        artifacts = {p.relative_to(cls.work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in cls.work.rglob('*') if p.is_file()}
        (cls.work / 'summary.json').write_text(json.dumps(dict(
            source_sha256=cls.inputs, source_sha256_after=after, stable=after == cls.inputs,
            artifact_sha256=artifacts, records=cls.records, primary_vectors_per_mode=len(VECTORS),
            formats=['elf64', 'win64'], COFF_is_not_Win64_ABI=True, OS_VM_built=False,
            integrated=False), indent=2) + '\n', encoding='utf-8')
        if after != cls.inputs:
            raise AssertionError(('source/doc/test/dependency SHA256 changed', cls.inputs, after))

    @staticmethod
    def case(module, item, operation, signed, error_block, cap, status=OK, flags=0):
        pool = module + b'\xa5' * 16 + item + b'\xa5' * 16
        return (pool, 0, len(module), len(module) + 16, len(item), operation, int(signed),
                error_block, flags, cap, status)

    def emit(self, exe, cases, label):
        payload = bytearray(struct.pack('<Q', len(cases)))
        for c in cases:
            payload += struct.pack('<10Q', len(c[0]), *c[1:10]) + c[0]
        (self.work / (label + '.input')).write_bytes(payload)
        run = subprocess.run([str(exe)], input=bytes(payload), capture_output=True, timeout=60)
        (self.work / (label + '.output')).write_bytes(run.stdout)
        (self.work / (label + '.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode, 0, (label, run.stderr))
        self.assertEqual(struct.unpack_from('<Q', run.stdout)[0], PREFLIGHTS)
        offset, texts = 8, []
        for k, c in enumerate(cases):
            status, valid, n, protected = struct.unpack_from('<4Q', run.stdout, offset)
            offset += 32
            text = run.stdout[offset:offset + n]
            offset += n
            self.assertEqual(protected, 1, (label, k, 'readonly protection'))
            self.assertEqual(valid, 1, (label, k, 'guard/atomicity'))
            self.assertEqual(status, c[10], (label, k, 'status'))
            if not status:
                self.assertEqual(n, len(text), (label, k, 'exact length'))
            texts.append(text if not status else None)
        self.assertEqual(offset, len(run.stdout))
        return texts

    def generate(self, exe, vectors, label, exact=True):
        texts = self.emit(exe, [self.case(*v[:5], 4096, OK, 1) for v in vectors], label)
        if exact:
            for v, text in zip(vectors, texts):
                self.assertEqual(text, expected_text(*v[:5]), (label, 'exact text', v[:5]))
        return texts

    def native_run(self, texts, vectors, label):
        asm = ['bits 64', 'section .data', 'align 8', 'observation: dq 0',
               'host_anchor: dq 0', 'parked_rax: dq 0', 'parked_rdx: dq 0', 'section .text']
        for k, v in enumerate(vectors):
            asm += ['global v%d' % k, 'v%d:' % k, 'push rbx', 'push rbp', 'push r12', 'push r13',
                    'push r14', 'push r15', 'sub rsp, 8', 'mov [rel observation], rdi',
                    'mov [rel host_anchor], rsp', 'mov r11, rdi',
                    'mov rax, 0x%x' % CANARY, 'mov [rsp], rax',
                    'mov [r11+%d], rsp' % (8 * RSP_BEFORE), 'mov rax, rsp', 'and rax, 15',
                    'mov [r11+%d], rax' % (8 * ALIGN), 'mov rax, 0x%x' % CALLER['rbx'],
                    'mov [r11+%d], rax' % (8 * RBX_BEFORE)]
            asm += ['mov %s, 0x%x' % (r, value) for r, value in CALLER.items()]
            asm += ['mov rdi, 0x%x' % v[5], 'mov rsi, 0x%x' % v[6]]
            asm += ['call ' + symbol(*v[:2]), 'mov [rel parked_rax], rax', 'mov [rel parked_rdx], rdx',
                    'mov rax, [rel observation]',
                    'mov [rax+%d], rsp' % (8 * RSP_AFTER), 'mov [rax+%d], rbx' % (8 * RBX_AFTER),
                    'mov [rax+%d], rbp' % (8 * RBP_AFTER)]
            asm += ['mov [rax+%d], r%d' % (8 * (R12_AFTER + j), 12 + j) for j in range(4)]
            asm += ['mov rcx, [rel parked_rax]', 'mov [rax], rcx', 'mov rcx, [rel parked_rdx]',
                    'mov [rax+8], rcx', 'mov rcx, [rel host_anchor]',
                    'mov rcx, [rcx]', 'mov [rax+%d], rcx' % (8 * CANARY_AFTER),
                    'mov rsp, [rel host_anchor]', 'add rsp, 8', 'pop r15', 'pop r14', 'pop r13',
                    'pop r12', 'pop rbp', 'pop rbx', 'ret']
        asm += [text.decode('latin1') for text in texts]
        asmfile = self.work / (label + '.stubs.asm')
        asmfile.write_text('\n'.join(asm) + '\n', encoding='latin1')
        for fmt in ('elf64', 'win64'):
            self.command([self.nasm, '-f', fmt, *nasm_flags(self.nasm), '-o',
                          self.work / (label + '.stubs.' + fmt + '.o'), asmfile], label + '-stubs-' + fmt)
        main = NATIVE_MAIN.replace('%DECLS%', '#define STATE %d\n' % STATE + '\n'.join(
            'extern void ABI v%d(uint64_t*);' % k for k in range(len(vectors))))
        main = main.replace('%TABLE%', ','.join('v%d' % k for k in range(len(vectors))))
        cfile, exe = self.work / (label + '.native.c'), self.work / (label + '-native' + ('.exe' if os.name == 'nt' else ''))
        cfile.write_text(main, encoding='utf-8')
        self.command([self.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1',
                      cfile, self.work / (label + '.stubs.' + self.native + '.o'), '-o', exe], label + '-native-link')
        run = subprocess.run([str(exe)], capture_output=True, timeout=60)
        (self.work / (label + '.native.output')).write_bytes(run.stdout)
        (self.work / (label + '.native.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode, 0, (label, 'normal native termination', run.stderr))
        self.assertEqual(len(run.stdout), 8 * STATE * len(vectors))
        observations = [struct.unpack_from('<%dQ' % STATE, run.stdout, 8 * STATE * k) for k in range(len(vectors))]
        expected = [interpret(v[2], v[3], v[5], v[6]) for v in vectors]
        self.records.append(dict(native=label, normal_exit=True, observations=observations, expected_pair=expected))
        for k, got in enumerate(observations):
            self.assertEqual(got[ALIGN], 0, (label, k, 'caller alignment'))
            self.assertEqual(got[RSP_AFTER], got[RSP_BEFORE], (label, k, 'balanced rsp'))
            self.assertEqual(got[RBX_BEFORE], CALLER['rbx'], (label, k, 'planted rbx'))
            self.assertEqual(got[RBX_AFTER], CALLER['rbx'], (label, k, 'callee-saved rbx'))
            self.assertEqual((got[RBP_AFTER], *got[R12_AFTER:R12_AFTER + 4]),
                             tuple(value for r, value in CALLER.items() if r != 'rbx'),
                             (label, k, 'callee-saved rbp/r12-r15'))
            self.assertEqual(got[CANARY_AFTER], CANARY, (label, k, 'stack guard'))
        for k, (got, pair) in enumerate(zip(observations, expected)):
            self.assertEqual((got[RAX], got[RDX]), pair, (label, k, 'native rax/rdx'))

    def test_exact_text_capacity_invalid_readonly(self):
        cases = []
        for v in VECTORS:
            n = len(expected_text(*v[:5]))
            for cap, status in ((n, OK), (n + 17, OK), (n - 1, CAPACITY), (0, CAPACITY)):
                cases.append(self.case(*v[:5], cap, status, 1))
        base = (b'mod', b'item', ADD, False, 100)
        bads = [(b'', *base[1:]), (base[0], b'', *base[2:]),
                (b'x' * 65, *base[1:]), (base[0], b'y' * 65, *base[2:]),
                (*base[:2], 4, False, 100), (*base[:2], MAX, False, 100),
                (*base[:2], NEG, False, 100), (*base[:4], MAX)]
        for v in bads:
            cases += [self.case(*v, 4096, INVALID, 1), self.case(*v, 0, INVALID, 1)]
        cases += [(b'modulename', 0, 10, 2, 4, ADD, 0, 900, 1, 4096, OK),
                  (b'same', 0, 4, 0, 4, ADD, 0, 901, 1, 4096, OK)]
        for mode, exe in self.executables.items():
            texts = self.emit(exe, cases, 'text-' + mode)
            for c, text in zip(cases, texts):
                if c[10] == OK:
                    m, it = c[0][c[1]:c[1] + c[2]], c[0][c[3]:c[3] + c[4]]
                    self.assertEqual(text, expected_text(m, it, c[5], bool(c[6]), c[7]))
                    self.assertLessEqual(len(text), 3276)
                    self.assertTrue(all(x == 10 or 32 <= x < 127 for x in text))
                    self.assertNotIn(b'\n\n', text)
                    for token in (b'\x00', b'section', b'global', b'bits', b'extern', b';'):
                        self.assertNotIn(token, text)
        self.records.append(dict(test='exact-text-capacity-invalid-readonly', cases_per_mode=len(cases),
                                 preflights_per_process=PREFLIGHTS, passed=True))

    def test_native_call_ret(self):
        self.assertLessEqual(len(VECTORS), 24)
        self.assertEqual(len({symbol(*v[:2]) for v in VECTORS}), len(VECTORS))
        self.assertEqual(len({v[4] for v in VECTORS}), len(VECTORS))
        self.assertTrue(any(len(v[0]) == 1 and len(v[1]) == 2 for v in VECTORS))
        self.assertTrue(any(len(v[0]) == 64 and len(v[1]) == 64 for v in VECTORS))
        self.assertTrue(any(0 in v[0] or 0 in v[1] for v in VECTORS))
        self.assertTrue(any(v[4] >= 10 ** 19 for v in VECTORS))
        self.assertNotEqual(interpret(MUL, False, MAX, 2), interpret(MUL, True, MAX, 2))
        self.assertEqual(interpret(NEG, True, 0, 11), interpret(NEG, True, 0, 99))
        for mode, exe in self.executables.items():
            self.native_run(self.generate(exe, VECTORS, 'vectors-' + mode), VECTORS, 'native-' + mode)
        self.records.append(dict(test='native-call-ret', vectors_per_mode=len(VECTORS),
                                 functions_per_file=len(VECTORS), passed=True))

    def test_real_rbx_control(self):
        source = SOURCE.read_text(encoding='utf-8')
        bad = source
        for helper in ('ok_exit', 'err_exit'):
            old = 'if !' + helper + '(buffer,&at){return false;}'
            new = 'if !put(buffer,&at,"add rbx, 8\\n")||!' + helper + '(buffer,&at){return false;}'
            self.assertEqual(bad.count(old), 1)
            bad = bad.replace(old, new, 1)
        fixtures = [VECTORS[0], VECTORS[1]]
        for mode, exe in self.executables.items():
            self.native_run(self.generate(exe, fixtures, 'rbx-good-' + mode), fixtures, 'rbx-good-' + mode)
        for mode, exe in self.build_all('bad-rbx', bad).items():
            for k, v in enumerate(fixtures):
                label = 'rbx-bad-%s-%d' % (mode, k)
                with self.assertRaisesRegex(AssertionError, 'callee-saved rbx'):
                    self.native_run(self.generate(exe, [v], label, exact=False), [v], label)
        self.records.append(dict(test='bad-rbx', compiled=True, linked=True, normal_native_exit=True,
                                 modes=2, exits=2, rejected_by='callee-saved rbx'))

    def test_real_bad_dong(self):
        source = SOURCE.read_text(encoding='utf-8')
        mul = 'if mul.emit(signed,error_block,slice_from_raw_parts(&buffer[0],64),&n)!=mul.OK{return false;}'
        pair = 'if ex.emit(PAIR,FRAME,0,24,32,slice_from_raw_parts(&piece[*at],192),&n)!=ex.OK{return false;}'
        capacity = 'if total>on{return CAPACITY;}'
        for snippet in (mul, pair, capacity):
            self.assertEqual(source.count(snippet), 1, snippet)
        unsigned_mul = [v for v in VECTORS if v[2] == MUL and not v[3] and v[5] == MAX and v[6] == 2]
        success = [v for v in VECTORS if interpret(v[2], v[3], v[5], v[6]) == (3, 0)]
        self.assertEqual(len(unsigned_mul), 1)
        self.assertTrue(success)
        fixtures_mul, fixtures_pair = unsigned_mul, success[:1]
        bad_mul = source.replace(mul, mul.replace('signed', 'true', 1), 1)
        bad_pair = source.replace(pair, pair.replace('0,24,32', '0,32,24', 1), 1)
        for name, bad, fixtures, key in (
                ('bad-unsigned-mul-as-signed', bad_mul, fixtures_mul, 'native rax/rdx'),
                ('bad-success-pair-slots', bad_pair, fixtures_pair, 'native rax/rdx')):
            for mode, exe in self.executables.items():
                self.native_run(self.generate(exe, fixtures, name + '-good-' + mode), fixtures, name + '-good-' + mode)
            for mode, exe in self.build_all(name, bad).items():
                texts = self.generate(exe, fixtures, name + '-' + mode, exact=False)
                with self.assertRaisesRegex(AssertionError, key):
                    self.native_run(texts, fixtures, name + '-' + mode)
            self.records.append(dict(test=name, compiled=True, linked=True, normal_native_exit=True,
                                     modes=2, rejected_by=key + ' (ABI/guard checks passed first)'))
        early = ('if total>on{var badn:usize=0;'
                 'if piece(0,module_name,item_name,operation,signed,error_block,'
                 'slice_from_raw_parts(&buffer[0],268),&badn){'
                 'var j:usize=0;while j<badn&&j<on{out[j]=buffer[j];j+=1;}}return CAPACITY;}')
        v = VECTORS[20]
        short = [self.case(*v[:5], len(expected_text(*v[:5])) - 1, CAPACITY)]
        for mode, exe in self.executables.items():
            self.native_run(self.generate(exe, [v], 'bad-early-header-good-native-' + mode), [v],
                            'bad-early-header-good-native-' + mode)
            self.emit(exe, short, 'bad-early-header-good-short-' + mode)
        for mode, exe in self.build_all('bad-early-header', source.replace(capacity, early, 1)).items():
            with self.assertRaisesRegex(AssertionError, 'guard/atomicity'):
                self.emit(exe, short, 'bad-early-header-' + mode)
        self.records.append(dict(test='bad-early-header', compiled=True, linked=True, modes=2,
                                 rejected_by='guard/atomicity', bad_generated_function_executed=False,
                                 good_generated_function_executed_first=True))


if __name__ == '__main__':
    unittest.main()
