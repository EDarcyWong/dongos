"""Actual Dong assembler, stable source snapshots, native ELF execution and rejected-input atomicity."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

WRAPPER = '''module entry;
import exec.elf as elf;
export("kernel_validate") fn validate(raw:*const u8,n:usize,out:*elf.Plan)u64{unsafe{match elf.validate(slice_from_raw_parts(raw,n),0,out){ok=>{return 0;},err(code)=>{return code;},}}}
import bootstrap.native_assembler as a;
export("assemble_raw") pub unsafe fn assemble(src:*const u8,n:usize,entry:*const u8,en:usize,w:*const a.Workspace,out:*u8,cap:usize,r:*a.Result)u64{unsafe{return a.assemble(slice_from_raw_parts(src,n),slice_from_raw_parts(entry,en),w,slice_from_raw_parts(out,cap),r);}}
'''
HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t U;
typedef struct {void*p;U n;} S;
typedef struct {S labels,table,text,data;} W;
typedef struct {U status,line,detail,text,data,labels,written;} R;
extern U kernel_validate(const void*,U,void*);
extern U assemble_raw(const void*,U,const void*,U,const W*,void*,U,R*);
void __dong_panic(uint32_t k,uint32_t line,const void*p,U n){(void)p;(void)n;fprintf(stderr,"PANIC %u %u\n",k,line);exit(91);}
static void rd(void*p,U n){if(n&&fread(p,1,n,stdin)!=n)exit(92);}
static void wr(const void*p,U n){if(n&&fwrite(p,1,n,stdout)!=n)exit(93);}
static int filled(const void*p,U n){const unsigned char*b=p;for(U i=0;i<n;i++)if(b[i]!=0xa5)return 0;return 1;}
/* Entire numerical capacities, including unused tails, participate in alias checks. */
static U preflights(void){
 static _Alignas(16) unsigned char arena[65536],saved[65536];U count=0;
 for(unsigned scenario=0;scenario<57;scenario++){
  memset(arena,0xa5,sizeof arena);
  W*w=(W*)(arena+8192);R*r=(R*)(arena+57344);
  const void*src=arena;U ns=32;const void*entry=arena+4096;U ne=6;
  *w=(W){{arena+16384,8},{arena+24576,16},{arena+32768,256},{arena+40960,256}};
  void*out=arena+49152;U cap=512;
  void**ptrs[]={&w->labels.p,&w->table.p,&w->text.p,&w->data.p,&out,(void**)&r};
  U sizes[]={256,128,256,256,512,56};
  unsigned c=scenario;
  if(c<18){unsigned o=c/3,i=c%3;void*in[]={arena,arena+4096,w};U len[]={32,6,64};
   *ptrs[o]=(unsigned char*)in[i]+(i==1?0:len[i]-8);
  }else if(c<33){unsigned k=c-18;for(unsigned i=1;i<6;i++)for(unsigned j=0;j<i;j++){
   if(k==0){*ptrs[i]=(unsigned char*)*ptrs[j]+sizes[j]-8;goto configured;}k--;
  }}else if(c<39){*ptrs[c-33]=NULL;}
  else if(c<45){*ptrs[c-39]=(void*)(uintptr_t)(UINT64_MAX-7);}
  else switch(c){
   case 45:w=NULL;break;case 46:w=(W*)(arena+8193);break;
   case 47:w=(W*)(uintptr_t)(UINT64_MAX-7);break;
   case 48:src=NULL;break;case 49:src=(void*)(uintptr_t)(UINT64_MAX-7);break;
   case 50:entry=NULL;break;case 51:entry=(void*)(uintptr_t)(UINT64_MAX-3);break;
   case 52:w->labels.p=arena+16385;break;case 53:w->table.p=arena+24577;break;
   case 54:w->labels.n=UINT64_MAX/32+1;break;
   case 55:w->table.n=UINT64_MAX/8+1;break;case 56:r=(R*)(arena+57345);break;
  }
 configured:
  memcpy(saved,arena,sizeof arena);
  U rc=assemble_raw(src,ns,entry,ne,w,out,cap,r);
  if(rc!=1||memcmp(saved,arena,sizeof arena)){fprintf(stderr,"preflight %u failed: %llu\n",scenario,(unsigned long long)rc);exit(94);}
  count++;
 }
 return count;
}
int main(void){
 U checks=preflights();wr(&checks,8);U cases;rd(&cases,8);
 for(U k=0;k<cases;k++){
  U h[7];rd(h,sizeof h);U ns=h[0],ne=h[1];unsigned char*src=malloc(ns+1),*entry=malloc(ne+1);rd(src,ns);rd(entry,ne);
  U sizes[]={h[2]*32,h[3]*8,h[4],h[5],h[6]};unsigned char*buf[5];
  for(unsigned i=0;i<5;i++){buf[i]=malloc(sizes[i]+32);if(!buf[i])exit(95);memset(buf[i],0xa5,sizes[i]+32);}
  W w={{buf[0]+16,h[2]},{buf[1]+16,h[3]},{buf[2]+16,h[4]},{buf[3]+16,h[5]}};R r;memset(&r,0xa5,sizeof r);
  U rc=assemble_raw(src,ns,entry,ne,&w,buf[4]+16,h[6],&r),guards=1;
  for(unsigned i=0;i<5;i++)if(!filled(buf[i],16)||!filled(buf[i]+16+sizes[i],16))guards=0;
  U suffix=filled(buf[4]+16+(rc?0:r.written),h[6]-(rc?0:r.written));
  U plan[134]={0};U validation=rc?0:kernel_validate(buf[4]+16,r.written,plan);
  U head[]={rc,guards,suffix,validation};wr(head,sizeof head);wr(&r,sizeof r);if(!rc)wr(buf[4]+16,r.written);
  free(src);free(entry);for(unsigned i=0;i<5;i++)free(buf[i]);
 }
 return 0;
}
'''
PREFIX = 'bits 64\ndefault rel\nsection .text\nglobal _start\n_start:\n'
EXIT = 'mov eax, 60\nsyscall\n'


class NativeAssemblerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc or os.name != 'posix':
            raise unittest.SkipTest('native assembler probes require NASM, GCC and POSIX')
        cls.work = ROOT/'build/test/bootstrap-native-assembler'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.records = []
        cls.snapshot = cls.work/'snapshot'
        (cls.snapshot/'bootstrap').mkdir(parents=True)
        cls.hashes = {}
        for name in ('native_assembler', 'x86_encode', 'elf64_image'):
            data = (ROOT/f'lang/bootstrap/{name}.dg').read_bytes()
            cls.hashes[name] = hashlib.sha256(data).hexdigest()
            (cls.snapshot/f'bootstrap/{name}.dg').write_bytes(data)
        (cls.snapshot/'exec').mkdir()
        kernel = (ROOT/'kernel/exec/elf.dg').read_bytes()
        cls.hashes['kernel_elf'] = hashlib.sha256(kernel).hexdigest()
        (cls.snapshot/'exec/elf.dg').write_bytes(kernel)
        (cls.snapshot/'entry.dg').write_text(WRAPPER)
        (cls.work/'probe.c').write_text(HARNESS)
        cls.executables = {}
        for mode in ('debug', 'release'):
            asm = cls.work/(mode+'.asm')
            asm.write_text(compile_file(cls.snapshot/'entry.dg', roots=[cls.snapshot], mode=mode).assembly)
            obj, exe = cls.work/(mode+'.o'), cls.work/mode
            cls.command([cls.nasm, '-f', 'elf64', *nasm_flags(cls.nasm), asm, '-o', obj], mode+'-seed')
            cls.command([cls.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', cls.work/'probe.c', obj, '-o', exe], mode+'-link')
            cls.executables[mode] = exe
        cls.write_receipt()

    @classmethod
    def write_receipt(cls):
        (cls.work/'summary.json').write_text(json.dumps({'source_sha256': cls.hashes, 'records': cls.records,
            'source_snapshot': 'snapshot', 'NASM_role': 'seed and independent semantic oracle only',
            'OS_VM_built': False, 'integrated': False}, indent=2)+'\n')

    @classmethod
    def tearDownClass(cls):
        cls.write_receipt()

    @classmethod
    def command(cls, args, label):
        p = subprocess.run(list(map(str, args)), capture_output=True, timeout=240)
        (cls.work/(label+'.stdout')).write_bytes(p.stdout)
        (cls.work/(label+'.stderr')).write_bytes(p.stderr)
        cls.records.append({'label': label, 'returncode': p.returncode})
        cls.write_receipt()
        if p.returncode:
            raise AssertionError((label, p.returncode, p.stderr.decode(errors='replace')))
        return p

    def cases(self, mode, label, cases):
        payload = bytearray(struct.pack('<Q', len(cases)))
        for source, entry, capacities in cases:
            source, entry = source.encode(), entry.encode()
            payload += struct.pack('<7Q', len(source), len(entry), *capacities)+source+entry
        stem = mode+'-'+label
        (self.work/(stem+'.input')).write_bytes(payload)
        p = subprocess.run([self.executables[mode]], input=payload, capture_output=True, timeout=240)
        (self.work/(stem+'.stdout')).write_bytes(p.stdout)
        (self.work/(stem+'.stderr')).write_bytes(p.stderr)
        self.records.append({'label': stem, 'returncode': p.returncode, 'cases': len(cases)})
        self.write_receipt()
        self.assertEqual(p.returncode, 0, p.stderr.decode(errors='replace'))
        self.assertEqual(struct.unpack_from('<Q', p.stdout)[0], 57)
        pos, results = 8, []
        for _ in cases:
            rc, guards, suffix, validation, status, line, detail, text, data, labels, written = struct.unpack_from('<11Q', p.stdout, pos)
            pos += 88
            self.assertEqual(validation, 0)
            image = p.stdout[pos:pos+written] if rc == 0 else b''
            pos += len(image)
            self.assertEqual((guards, suffix, rc), (1, 1, status), (stem, line, detail))
            if rc:
                self.assertEqual(written, 0)
            results.append((rc, line, detail, text, data, labels, image))
        self.assertEqual(pos, len(p.stdout))
        self.records[-1]['results'] = [dict(status=r[0], line=r[1], detail=r[2], text=r[3], data=r[4], labels=r[5], image_sha256=hashlib.sha256(r[6]).hexdigest() if r[6] else None) for r in results]
        self.write_receipt()
        return results

    def assemble(self, mode, label, source):
        result = self.cases(mode, label, [(source, '_start', (128, 257, 65536, 65536, 131072))])[0]
        self.assertEqual(result[0], 0, result[:6])
        return result

    def execute(self, image, label):
        if platform.machine().lower() not in ('x86_64', 'amd64') or sys.platform != 'linux':
            self.skipTest('ELF execution requires x86-64 Linux')
        path = self.work/label
        path.write_bytes(image)
        path.chmod(0o700)
        p = subprocess.run([path], capture_output=True, timeout=10)
        self.records.append({'label': label, 'returncode': p.returncode, 'stdout_hex': p.stdout.hex()})
        self.write_receipt()
        return p.returncode, p.stdout

    def oracle(self, source, label):
        src, obj, exe = (self.work/(label+s) for s in ('.asm', '.o', '.elf'))
        src.write_text(source)
        self.command([self.nasm, '-f', 'elf64', src, '-o', obj], label+'-nasm')
        self.command(['ld', '-o', exe, obj], label+'-ld')
        p = subprocess.run([exe], capture_output=True, timeout=10)
        return p.returncode, p.stdout

    def test_semantic_execution_and_relocations(self):
        programs = {
            'register_memory': PREFIX+'''sub rsp, 32
mov r12, rsp
mov r8, 0x123456789abcdef0
mov qword [r12+8], r8
mov r9, qword [r12+8]
cmp r9, r8
jne bad
mov ax, -2
movsx r10, ax
cmp r10, -2
jne bad
mov byte [rsp], al
movzx r11, byte [rsp]
cmp r11, 254
jne bad
mov ecx, 1
shl r11, cl
shr r11, cl
lea r13, [r12+r11*2-508]
cmp r13, r12
jne bad
xor edi, edi
jmp done
bad:
mov edi, 71
done:
add rsp, 32
'''+EXIT,
            'calls_branches': PREFIX+'''mov ecx, 4
xor edi, edi
loop:
call add_one
sub ecx, 1
jnz loop
cmp edi, 4
sete al
movzx edi, al
xor edi, 1
jmp finish
add_one:
add edi, 1
ret
finish:
'''+EXIT,
            'backward_indirect': PREFIX.replace('_start:\n', 'helper:\nadd edi, 1\nret\n_start:\n')+'''xor edi, edi
call helper
lea rax, [rel helper]
call rax
cmp edi, 2
jne bad
xor edi, edi
lea rbx, [rel finish]
jmp rbx
bad:
mov edi, 73
finish:
'''+EXIT,
            'data_aliases': PREFIX+'''mov r8, qword [rel pointer]
lea r9, [rel message_alias]
cmp r8, r9
jne bad
mov eax, 1
mov edi, 1
mov rsi, r8
mov edx, 3
syscall
xor edi, edi
jmp finish
bad:
mov edi, 72
finish:
'''+EXIT+'''section .rodata
align 16
pointer: dq message
other: dq _start
message:
message_alias:
db 79, 75, 10
align 16
padding: times 3 db 0
dw 65535, -32768
dd 4294967295, -2147483648
''',
        }
        for label, source in programs.items():
            expected = self.oracle(source, label+'-oracle')
            self.assertEqual(expected, (0, b'OK\n' if label == 'data_aliases' else b''))
            images = []
            for mode in self.executables:
                result = self.assemble(mode, label, source)
                images.append(result[-1])
                self.assertEqual(self.execute(result[-1], mode+'-'+label+'.elf'), expected)
                self.assertEqual(result[-1][:4], b'\x7fELF')
            self.assertEqual(*images)
            if label == 'data_aliases':
                image = images[0]
                phoff = struct.unpack_from('<Q', image, 32)[0]
                phsize, phnum = struct.unpack_from('<HH', image, 54)
                headers = [struct.unpack_from('<II6Q', image, phoff+i*phsize) for i in range(phnum)]
                data_header = next(h for h in headers if h[0] == 1 and h[1] == 6 and h[2] >= 4096)
                offset, address = data_header[2:4]
                self.assertEqual(struct.unpack_from('<QQ', image, offset),
                                 (address+16, struct.unpack_from('<Q', image, 24)[0]))
                self.assertEqual(image[offset+16:offset+32], b'OK\n'+b'\x90'*13)

    def test_whitespace_and_metadata(self):
        source = PREFIX.replace('global _start', 'global _start   ')+ 'mov edi, 0\n'+EXIT
        source += '  %ifidn __OUTPUT_FORMAT__,elf64  ; metadata\n  section .note.GNU-stack noalloc noexec nowrite progbits  \n %endif  \n'
        for mode in self.executables:
            self.assemble(mode, 'whitespace-metadata', source)

    def test_capacity_and_failure_atomicity(self):
        source = PREFIX+'mov edi, 0\n'+EXIT+'section .rodata\nx: dq _start\n'
        capacities = [(0, 17, 64, 64, 16384), (4, 0, 64, 64, 16384), (1, 1, 64, 64, 16384),
                      (4, 17, 1, 64, 16384), (4, 17, 64, 1, 16384), (4, 17, 64, 64, 0),
                      (4, 17, 64, 64, 8199)]
        for mode in self.executables:
            results = self.cases(mode, 'capacity', [(source, '_start', c) for c in capacities])
            self.assertEqual([r[0] for r in results], [2]*len(results))

    def test_reject_malformed_and_unknown_input(self):
        bad_bodies = ['no_such_instruction rax, rbx', 'mov rax, eax', 'mov ah, bl', 'mov rax,',
                      'mov rax, rbx, rcx', 'mov rax, [rbx', 'mov rax, [rbx 4]', 'mov rax, [rbx+]',
                      'mov rax, [rbx+rcx*3]', 'jmp missing', '_start: ret', 'call 123', 'push eax',
                      'ret rax', 'syscall rax', 'shl rax', 'shr eax', 'sar al', 'mov rax, 18446744073709551616',
                      'mov rax, -9223372036854775809', 'mov al, 256', 'add rax, 2147483648',
                      'mov rax, [rbx+2147483648]', 'lea rax, [rbx+rsp*2]', 'align 3',
                      'section .bss', '%include "file"', '%endif', 'bits 32', 'default abs',
                      'global missing', '1bad: ret', 'section .rodata\ndb 256',
                      'section .rodata\ndw -32769', 'section .rodata\ndd 4294967296',
                      'section .rodata\ndq absent', 'section .rodata\ndq 1,',
                      'section .rodata\ntimes -1 db 0', 'section .rodata\nret',
                      '%ifidn __OUTPUT_FORMAT__,elf64', 'section .note.GNU-stack noalloc noexec nowrite progbits']
        for mode in self.executables:
            cases = [(PREFIX+body+'\n', '_start', (128, 257, 4096, 4096, 16384)) for body in bad_bodies]
            results = self.cases(mode, 'invalid', cases)
            for body, result in zip(bad_bodies, results):
                with self.subTest(mode=mode, body=body):
                    self.assertNotEqual(result[0], 0, (body, result[:6]))
                    self.assertGreater(result[1], 0)

    def test_writable_data_section_is_supported(self):
        source = PREFIX+'mov edi, 0\n'+EXIT+'section .data\nword: dq 0x1122334455667788\n'
        for mode in self.executables:
            result = self.assemble(mode, 'writable-data', source)
            self.assertEqual(result[-1][-8:], bytes.fromhex('8877665544332211'))

    def test_exact_capacities_and_data_boundaries(self):
        source = PREFIX+'xor edi, edi\n'+EXIT+'section .rodata\nx: db 255, -128\ndw 65535, -32768\ndd 4294967295, -2147483648\ndq 18446744073709551615, -9223372036854775808\n'
        for mode in self.executables:
            first = self.assemble(mode, 'boundary-baseline', source)
            capacities = (first[5], first[5], first[3], first[4], len(first[-1]))
            exact, short = self.cases(mode, 'exact-capacities', [
                (source, '_start', capacities),
                (source, '_start', capacities[:-1]+(capacities[-1]-1,))])
            self.assertEqual(exact[0], 0)
            self.assertEqual(exact[-1], first[-1])
            self.assertEqual(short[0], 2)

    def test_missing_or_data_entry(self):
        sources = [(PREFIX+'ret\n', 'absent'), ('section .rodata\n_start: dq 0\n', '_start'),
                   ('section .text\n_start:\n', '_start')]
        for mode in self.executables:
            results = self.cases(mode, 'entry', [(s, e, (16, 37, 64, 64, 16384)) for s,e in sources])
            self.assertTrue(all(r[0] != 0 for r in results))

    @unittest.skipUnless(os.environ.get('DONG_ASSEMBLER_FULL_INPUT'), 'set DONG_ASSEMBLER_FULL_INPUT for the large native compiler assembly')
    def test_full_compiler_assembly(self):
        source = Path(os.environ['DONG_ASSEMBLER_FULL_INPUT']).read_text()
        entry = os.environ.get('DONG_ASSEMBLER_FULL_ENTRY', 'dong_frontend_check')
        images = []
        for mode in self.executables:
            r = self.cases(mode, 'full-compiler', [(source, entry, (65536, 131072, 16<<20, 4<<20, 24<<20))])[0]
            self.assertEqual(r[0], 0, r[:6])
            images.append(r[-1])
        self.assertEqual(*images)
        # A compiler function is not a Linux process entry. Never execute this artifact.


if __name__ == '__main__':
    unittest.main()
