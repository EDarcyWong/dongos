"""Actual Dong guest-source path gate, against an independent Python model.

The production module is compiled twice (debug/release) together with the
mainline strict UTF-8 component (`lang/std/core/utf8.dg`) and driven through a
native C harness. Every case checks the returned status, the full output
buffer, the written count and both input/output canaries, so a rejected call
must leave all caller storage byte-identical.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import uuid

WORKS = Path(__file__).resolve().parents[2]
ROOT = WORKS
if not (ROOT / 'lang').is_dir() and (WORKS / 'project.json').is_file():
    source = Path(json.loads((WORKS / 'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT = (WORKS / source).resolve() if not source.is_absolute() else source
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

SOURCE = WORKS / 'pool-works/lang/bootstrap/guest_source_path.dg'
STD_UTF8 = ROOT / 'lang/std/core/utf8.dg'
OK, INVALID, CAPACITY = 0, 1, 2
MAX_PATH, MAX_SEGMENT = 4096, 255
ROOT_SOURCE, ROOT_INCLUDE = 0, 1
SENTINEL = 0x5a5a5a5a5a5a5a5a
PREFLIGHTS = 16
WRAPPER = '''module probe.guest_path_export;
import bootstrap.guest_source_path as p;
export("dong_guest_source_path") pub unsafe fn validate(root:u64,path:*const u8,n:usize,out:*u8,on:usize,written:*usize)u64{unsafe{
 return p.validate(root,slice_from_raw_parts(path,n),slice_from_raw_parts(out,on),written);
}}'''

# Independent descriptor probe linked against the same compiled Dong object as
# the main harness. It covers the exact holes the first delivery left open:
# the output buffer's *whole declared* range, not just the published prefix.
# Every case asserts both the verdict and byte-identical caller storage.
ALIAS_HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_guest_source_path(uint64_t,const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{(void)k;(void)l;(void)f;(void)n;exit(87);}
#define OK 0ULL
#define INVALID 1ULL
#define SENT 0x5a5a5a5a5a5a5a5aULL
static int all(const uint8_t*p,uint64_t n,uint8_t v){for(uint64_t i=0;i<n;i++)if(p[i]!=v)return 0;return 1;}
static int bad(const char*name,uint64_t s){fprintf(stderr,"probe-alias %s: status %llu\n",name,(unsigned long long)s);return 1;}
static int dirty(const char*name,const char*what){fprintf(stderr,"probe-alias %s: %s\n",name,what);return 1;}
int main(int argc,char**argv){
 const char*sel=argc>1?argv[1]:"all";const int every=!strcmp(sel,"all");
 if(every||!strcmp(sel,"baseline")){
  _Alignas(16) uint8_t out[64];const uint8_t path[]="a.dg";uint64_t w=SENT;
  memset(out,0xb7,sizeof out);
  uint64_t s=dong_guest_source_path(0,path,4,out,64,&w);
  if(s!=OK)return bad("baseline",s);
  if(w!=4||memcmp(out,path,4)||!all(out+4,60,0xb7))return dirty("baseline","publication");
 }
 if(every||!strcmp(sel,"written-tail")){
  _Alignas(16) uint8_t out[64],before[64];const uint8_t path[]="a.dg";
  memset(out,0xb7,sizeof out);uint64_t*w=(uint64_t*)(out+32);*w=SENT;
  memcpy(before,out,sizeof out);
  uint64_t s=dong_guest_source_path(0,path,4,out,64,w);
  if(s!=INVALID)return bad("written-tail",s);
  if(memcmp(out,before,sizeof out))return dirty("written-tail","out changed");
  if(*w!=SENT)return dirty("written-tail","written changed");
  if(memcmp(path,"a.dg",4))return dirty("written-tail","input changed");
 }
 if(every||!strcmp(sel,"path-tail")){
  _Alignas(16) uint8_t out[64],before[64];uint64_t w=SENT;
  memset(out,0xb7,sizeof out);memcpy(out+32,"a.dg",4);
  memcpy(before,out,sizeof out);
  uint64_t s=dong_guest_source_path(0,out+32,4,out,64,&w);
  if(s!=INVALID)return bad("path-tail",s);
  if(w!=SENT)return dirty("path-tail","written changed");
  if(memcmp(out,before,sizeof out))return dirty("path-tail","out changed");
 }
 if(every||!strcmp(sel,"endpoint-wrap")){
  _Alignas(16) uint8_t out[64];const uint8_t path[]="a.dg";uint64_t w=SENT;
  const uint64_t on=(uint64_t)(UINT64_MAX-(uintptr_t)out)+1;
  memset(out,0xb7,sizeof out);
  uint64_t s=dong_guest_source_path(0,path,4,out,on,&w);
  if(s!=INVALID)return bad("endpoint-wrap",s);
  if(w!=SENT||!all(out,64,0xb7))return dirty("endpoint-wrap","caller storage");
 }
 printf("probe-alias ok\n");return 0;
}
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
extern uint64_t ABI dong_guest_source_path(uint64_t,const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t*ro_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static void ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;if(!VirtualProtect(p,n,PAGE_READONLY,&old))exit(98);
#else
 if(mprotect(p,n,PROT_READ))exit(98);
#endif
}
static void ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;if(!VirtualFree(p,0,MEM_RELEASE))exit(98);
#else
 if(munmap(p,n))exit(98);
#endif
}
#define PLEN 96
#define OLEN 96
static unsigned invalid(void){
 static uint8_t arena[512] __attribute__((aligned(64))),saved[512];
 const unsigned total=16;
 uint8_t*path=arena+64;uint8_t*out=arena+256;uint64_t*w=(uint64_t*)(arena+384);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  memset(path,'a',PLEN);memset(out,'b',OLEN);*w=0x5a5a5a5a5a5a5a5aULL;
  memcpy(saved,arena,sizeof(arena));
  const uint8_t*pp=path;uint64_t pn=PLEN;uint8_t*op=out;uint64_t on=OLEN;uint64_t*wp=w;uint64_t root=0;
  switch(i){
   case 0:wp=NULL;break;
   case 1:wp=(uint64_t*)(arena+385);break;
   case 2:wp=(uint64_t*)(uintptr_t)(UINT64_MAX-7);break;
   case 3:root=2;break;
   case 4:root=UINT64_MAX;break;
   case 5:pp=NULL;break;
   case 6:pp=(const uint8_t*)(uintptr_t)(UINT64_MAX-1);pn=8;break;
   case 7:pn=4097;break;
   case 8:op=NULL;break;
   case 9:op=path;break;
   case 10:wp=(uint64_t*)out;break;
   case 11:wp=(uint64_t*)path;break;
   case 12:op=(uint8_t*)(uintptr_t)(UINT64_MAX-1);break;
   /* written sits in the unused tail of out: the whole declared out range
      aliases written, so this must be INVALID even though the published
      prefix out[0..PLEN) would not touch it. */
   case 13:wp=(uint64_t*)(out+32);break;
   /* path sits in the unused tail of out: same full-range alias rule. */
   case 14:pp=out+32;pn=4;break;
   /* declared out range wraps the address space while op stays real and
      op+path.len would be in range: prefix-only checks accept this. */
   default:on=(uint64_t)(UINT64_MAX-(uintptr_t)out)+1;break;
  }
  uint64_t s=dong_guest_source_path(root,pp,pn,op,on,wp);
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 memset(arena,0xa5,sizeof(arena));
 const char*base="bootstrap/main.dg";uint64_t n=(uint64_t)strlen(base);
 memcpy(path,base,n);*w=0x5a5a5a5a5a5a5a5aULL;
 uint64_t s=dong_guest_source_path(0,path,n,out,OLEN,w);
 if(s!=0||*w!=n||memcmp(out,base,n)||!filled(out+n,OLEN-n)){fprintf(stderr,"baseline status %u\n",(unsigned)s);exit(93);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,count,preflights=0;read_exact(&flag,8);if(flag)preflights=invalid();read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[4];read_exact(h,sizeof(h));
  uint64_t root=h[0],plen=h[1],olen=h[2],ro=h[3];
  if(plen>1000000||olen>1000000)exit(94);
  uint8_t*ib=malloc(plen+64),*copy=malloc(plen?plen:1),*ob=malloc(olen+64);
  if(!ib||!copy||!ob)exit(95);
  memset(ib,0xa5,plen+64);read_exact(ib+32,plen);memcpy(copy,ib+32,plen);
  memset(ob,0xa5,olen+64);
  const uint8_t*pp=plen?ib+32:NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&plen){pages=(plen/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,plen);ro_protect(page,pages);pp=page;}
  uint64_t meta[3];memset(meta,0xa5,sizeof(meta));meta[1]=0x5a5a5a5a5a5a5a5aULL;
  uint64_t s=dong_guest_source_path(root,pp,plen,ob+32,olen,(uint64_t*)((uint8_t*)meta+8));
  uint64_t written=*((uint64_t*)((uint8_t*)meta+8));
  int guard=1;
  if(plen){
   if(ro){if(memcmp(page,copy,plen))guard=0;}
   else{if(memcmp(ib+32,copy,plen)||!filled(ib,32)||!filled(ib+32+plen,32))guard=0;}
  }
  if(!filled(ob,32)||!filled(ob+32+olen,32))guard=0;
  if(!filled(meta,8)||!filled((uint8_t*)meta+16,8))guard=0;
  uint64_t resp[3]={s,(uint64_t)guard,written};write_exact(resp,24);write_exact(ob+32,olen);
  if(page)ro_free(page,pages);
  free(ib);free(copy);free(ob);
 }return 0;
}
'''


def reference(root, path, out_len):
    """Independent model of the documented contract; validity precedes capacity."""
    if root >= 2:
        return INVALID
    if not 1 <= len(path) <= MAX_PATH:
        return INVALID
    try:
        path.decode('utf-8')
    except UnicodeDecodeError:
        return INVALID
    if any(b in (0x00, 0x3a, 0x5c) for b in path):
        return INVALID
    for segment in path.split(b'/'):
        if not segment or len(segment) > MAX_SEGMENT or segment in (b'.', b'..'):
            return INVALID
    if out_len < len(path):
        return CAPACITY
    return OK


def case(root, path, out_len=None, readonly=0, status=None):
    if isinstance(path, str):
        path = path.encode('utf-8')
    else:
        path = bytes(path)
    if out_len is None:
        out_len = len(path)
    got = reference(root, path, out_len)
    if status is not None:
        assert got == status, (root, path, out_len, got, status)
    return dict(root=root, path=path, out_len=out_len, readonly=readonly, status=got)


def multibyte_segment():
    # 85 CJK scalars are exactly 255 UTF-8 bytes: the segment-length boundary.
    return ('\u4e2d' * 85).encode('utf-8')


class GuestSourcePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native guest-source path gate requires NASM/GCC')
        cls.work = WORKS / 'pool-works/build/GUEST1' / ('run-' + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        (cls.work / 'probe.c').write_text(HARNESS, encoding='utf-8')
        (cls.work / 'probe_alias.c').write_text(ALIAS_HARNESS, encoding='utf-8')
        cls.executables = {}
        cls.alias = {}
        cls.records = []
        cls.inputs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [SOURCE, SOURCE.with_suffix('.md'), Path(__file__), STD_UTF8]}
        cls.src = cls.work / 'src'
        (cls.src / 'bootstrap').mkdir(parents=True)
        (cls.src / 'bootstrap/guest_source_path.dg').write_bytes(SOURCE.read_bytes())
        cls.wrapper = cls.work / 'wrapper'
        (cls.wrapper / 'probe').mkdir(parents=True)
        (cls.wrapper / 'probe/guest_path_export.dg').write_text(WRAPPER, encoding='utf-8')
        cls.std_root = ROOT / 'lang/std'
        for mode in ('debug', 'release'):
            cls.executables[mode] = cls.build([cls.src, cls.std_root, cls.wrapper], cls.wrapper, mode, mode)
            cls.alias[mode] = cls.link_source(cls.work / 'probe_alias.c', cls.work / (mode + '.o'),
                                              mode + '-alias')

    @classmethod
    def command(cls, cmd, name):
        r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=120)
        (cls.work / (name + '.log')).write_text(r.stdout + r.stderr, encoding='utf-8')
        if r.returncode:
            raise AssertionError((name, r.returncode, r.stdout, r.stderr))

    @classmethod
    def build(cls, roots, wrapper, mode, name):
        compiled = compile_file(wrapper / 'probe/guest_path_export.dg', roots=roots, mode=mode)
        asm = cls.work / (name + '.asm')
        asm.write_text(compiled.assembly, encoding='utf-8')
        native = 'win64' if os.name == 'nt' else 'elf64'
        obj = cls.work / (name + '.o')
        exe = cls.work / (name + ('.exe' if os.name == 'nt' else ''))
        for fmt in ('elf64', 'win64'):
            output = obj if fmt == native else cls.work / (name + '.' + fmt + '.o')
            cls.command([cls.nasm, '-f', fmt, *nasm_flags(cls.nasm), '-o', output, asm], name + '-' + fmt)
        cls.command([cls.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                     cls.work / 'probe.c', obj, '-o', exe], name + '-link')
        return exe

    @classmethod
    def link_source(cls, source, obj, name):
        exe = cls.work / (name + ('.exe' if os.name == 'nt' else ''))
        cls.command([cls.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                     source, obj, '-o', exe], name + '-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, 'work'):
            return
        assert cls.inputs == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              [SOURCE, SOURCE.with_suffix('.md'), Path(__file__), STD_UTF8]}, 'inputs changed'
        files = {p.relative_to(cls.work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in cls.work.rglob('*') if p.is_file()}
        (cls.work / 'summary.json').write_text(json.dumps(dict(
            source_sha256=cls.inputs, artifact_sha256=files, records=cls.records,
            groups=len(cls.records), integrated=False, OS_VM_built=False), indent=2) + '\n')

    def run_cases(self, exe, cases, label, preflight=True):
        payload = bytearray(struct.pack('<2Q', int(preflight), len(cases)))
        for c in cases:
            payload.extend(struct.pack('<4Q', c['root'], len(c['path']), c['out_len'], c['readonly']))
            payload.extend(c['path'])
        (self.work / (label + '.input')).write_bytes(payload)
        run = subprocess.run([str(exe)], input=bytes(payload), capture_output=True, timeout=120)
        (self.work / (label + '.output')).write_bytes(run.stdout)
        (self.work / (label + '.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode, 0, run.stderr)
        preflights, = struct.unpack_from('<Q', run.stdout, 0)
        self.assertEqual(preflights, PREFLIGHTS if preflight else 0)
        offset = 8
        for index, c in enumerate(cases):
            status, guard, written = struct.unpack_from('<3Q', run.stdout, offset)
            offset += 24
            out = run.stdout[offset:offset + c['out_len']]
            offset += c['out_len']
            self.assertEqual(guard, 1, (label, index, 'guard/atomicity'))
            self.assertEqual(status, c['status'], (label, index, 'status'))
            if status == OK:
                self.assertEqual(written, len(c['path']), (label, index, 'written'))
                self.assertEqual(out[:len(c['path'])], c['path'], (label, index, 'verbatim-bytes'))
                self.assertEqual(out[len(c['path']):], b'\xa5' * (c['out_len'] - len(c['path'])),
                                 (label, index, 'tail-canary'))
            else:
                self.assertEqual(written, SENTINEL, (label, index, 'guard/atomicity'))
                self.assertEqual(out, b'\xa5' * c['out_len'], (label, index, 'guard/atomicity'))
        self.assertEqual(offset, len(run.stdout))

    def run_both(self, cases, label, preflight=True):
        for mode, exe in self.executables.items():
            self.run_cases(exe, cases, label + '-' + mode, preflight)

    def test_reuses_mainline_strict_utf8(self):
        self.assertTrue(STD_UTF8.is_file(), STD_UTF8)
        module = STD_UTF8.read_text(encoding='utf-8')
        self.assertIn('module core.utf8;', module)
        self.assertIn('pub fn validate(bytes: []const u8) bool', module)
        self.assertIn('import core.utf8 as utf8;', SOURCE.read_text(encoding='utf-8'))
        self.records.append(dict(test='reuses-mainline-strict-utf8', contract=True, passed=True))

    def test_relative_paths_ascii(self):
        cases = [
            case(ROOT_SOURCE, 'main.dg', status=OK),
            case(ROOT_INCLUDE, 'a', status=OK),
            case(ROOT_SOURCE, 'a/b/c.dg', status=OK),
            case(ROOT_SOURCE, 'src/main.dg', status=OK),
            case(ROOT_INCLUDE, 'bootstrap/lang/modules.dg', status=OK),
            case(ROOT_SOURCE, '...', status=OK),
            case(ROOT_SOURCE, 'a....b', status=OK),
            case(ROOT_SOURCE, 'file name.dg', status=OK),
            case(ROOT_SOURCE, 'a\tb.dg', status=OK),
            case(ROOT_SOURCE, b'x' * 255, status=OK),
        ]
        self.run_both(cases, 'ascii')
        self.records.append(dict(test='relative-paths-ascii', cases=len(cases), modes=2, passed=True))

    def test_utf8_names_and_multibyte(self):
        seg = multibyte_segment()
        self.assertEqual(len(seg), 255)
        cases = [
            case(ROOT_SOURCE, '\u6e90\u7801/\u4e3b\u7a0b\u5e8f.dg', status=OK),
            case(ROOT_INCLUDE, '\u6587\u4ef6 \u540d.dg', status=OK),
            case(ROOT_SOURCE, '\U0001f600/\u6587\u4ef6.dg', status=OK),
            case(ROOT_SOURCE, seg, status=OK),
            case(ROOT_SOURCE, seg + b'/next.dg', status=OK),
            case(ROOT_SOURCE, seg + b'x', status=INVALID),  # 256-byte segment
        ]
        self.run_both(cases, 'utf8')
        self.records.append(dict(test='utf8-names-multibyte', cases=len(cases), modes=2, passed=True))

    def test_same_prefix_sibling_directories(self):
        cases = [
            case(ROOT_SOURCE, 'src/main.dg', status=OK),
            case(ROOT_SOURCE, 'src2/main.dg', status=OK),
            case(ROOT_SOURCE, 'src-evil/main.dg', status=OK),
            case(ROOT_SOURCE, 'src2', status=OK),
            case(ROOT_SOURCE, '../src2/main.dg', status=INVALID),
            case(ROOT_SOURCE, 'src/../src2/main.dg', status=INVALID),
            case(ROOT_SOURCE, '/src2/main.dg', status=INVALID),
            case(ROOT_SOURCE, 'src\\..\\src2\\main.dg', status=INVALID),
            case(ROOT_SOURCE, 'src/../../src2/main.dg', status=INVALID),
        ]
        self.run_both(cases, 'sibling')
        self.records.append(dict(test='same-prefix-sibling', cases=len(cases), modes=2, passed=True))

    def test_absolute_and_separators(self):
        cases = [
            case(ROOT_SOURCE, '/etc/passwd', status=INVALID),
            case(ROOT_SOURCE, '/', status=INVALID),
            case(ROOT_SOURCE, '//srv/share', status=INVALID),
            case(ROOT_SOURCE, '\\\\server\\share', status=INVALID),
            case(ROOT_SOURCE, '\\x', status=INVALID),
            case(ROOT_SOURCE, '/a/b', status=INVALID),
            case(ROOT_SOURCE, 'a//b', status=INVALID),
            case(ROOT_SOURCE, 'a/', status=INVALID),
            case(ROOT_SOURCE, '', out_len=0, status=INVALID),
            case(ROOT_SOURCE, 'a///b', status=INVALID),
        ]
        self.run_both(cases, 'absolute')
        self.records.append(dict(test='absolute-empty-segments', cases=len(cases), modes=2, passed=True))

    def test_drive_and_colon(self):
        cases = [
            case(ROOT_SOURCE, 'C:/x', status=INVALID),
            case(ROOT_SOURCE, 'C:x', status=INVALID),
            case(ROOT_SOURCE, 'c:file', status=INVALID),
            case(ROOT_SOURCE, 'a:b', status=INVALID),
            case(ROOT_SOURCE, 'x:stream', status=INVALID),
            case(ROOT_SOURCE, 'a/b:c', status=INVALID),
            case(ROOT_SOURCE, '\u4e2d\u6587\uff1a\u540d.dg', status=OK),  # full-width colon is not ':'
        ]
        self.run_both(cases, 'colon')
        self.records.append(dict(test='drive-colon', cases=len(cases), modes=2, passed=True))

    def test_nul_bytes(self):
        cases = [
            case(ROOT_SOURCE, b'a\x00b', status=INVALID),
            case(ROOT_SOURCE, b'\x00', status=INVALID),
            case(ROOT_SOURCE, b'a\x00', status=INVALID),
            case(ROOT_SOURCE, b'\x00abc/def', status=INVALID),
        ]
        self.run_both(cases, 'nul')
        self.records.append(dict(test='nul-bytes', cases=len(cases), modes=2, passed=True))

    def test_dot_segments(self):
        cases = [
            case(ROOT_SOURCE, '.', status=INVALID),
            case(ROOT_SOURCE, '..', status=INVALID),
            case(ROOT_SOURCE, './a', status=INVALID),
            case(ROOT_SOURCE, 'a/.', status=INVALID),
            case(ROOT_SOURCE, 'a/..', status=INVALID),
            case(ROOT_SOURCE, 'a/../b', status=INVALID),
            case(ROOT_SOURCE, '../a', status=INVALID),
            case(ROOT_SOURCE, '../../x', status=INVALID),
            case(ROOT_SOURCE, 'a/b/./c', status=INVALID),
            case(ROOT_SOURCE, 'a/b/../c', status=INVALID),
            case(ROOT_SOURCE, 'a./b', status=OK),
            case(ROOT_SOURCE, '.hidden', status=OK),
        ]
        self.run_both(cases, 'dots')
        self.records.append(dict(test='dot-segments', cases=len(cases), modes=2, passed=True))

    def test_segment_length_boundary(self):
        s255 = b'a' * 255
        cases = [
            case(ROOT_SOURCE, s255, status=OK),
            case(ROOT_SOURCE, b'a' * 256, status=INVALID),
            case(ROOT_SOURCE, s255 + b'/' + s255, status=OK),
            case(ROOT_SOURCE, s255 + b'/' + b'b' * 256, status=INVALID),
            case(ROOT_SOURCE, b'a' * 254 + b'/b', status=OK),
        ]
        self.run_both(cases, 'segment')
        self.records.append(dict(test='segment-length-255', cases=len(cases), modes=2, passed=True))

    def test_total_length_boundary(self):
        exact = b'/'.join([b'a' * 255] * 15 + [b'b' * 200, b'c' * 55])
        over = b'/'.join([b'a' * 255] * 15 + [b'b' * 200, b'c' * 56])
        self.assertEqual(len(exact), MAX_PATH)
        self.assertEqual(len(over), MAX_PATH + 1)
        cases = [
            case(ROOT_SOURCE, exact, status=OK),
            case(ROOT_SOURCE, over, status=INVALID),
            case(ROOT_SOURCE, b'a' * (MAX_PATH + 1), status=INVALID),
            case(ROOT_SOURCE, exact, out_len=MAX_PATH + 64, status=OK),
        ]
        self.run_both(cases, 'total')
        self.records.append(dict(test='total-length-4096', cases=len(cases), modes=2, passed=True))

    def test_invalid_utf8(self):
        cases = [
            case(ROOT_SOURCE, b'\x80', status=INVALID),
            case(ROOT_SOURCE, b'\xc0\x80', status=INVALID),
            case(ROOT_SOURCE, b'\xed\xa0\x80', status=INVALID),
            case(ROOT_SOURCE, b'\xf5\x80\x80\x80', status=INVALID),
            case(ROOT_SOURCE, b'\xf4\x90\x80\x80', status=INVALID),
            case(ROOT_SOURCE, '\u4e2d'.encode('utf-8')[:-1], status=INVALID),
            case(ROOT_SOURCE, b'\xff', status=INVALID),
            case(ROOT_SOURCE, b'a\xc3', status=INVALID),
            case(ROOT_SOURCE, b'\xe0\x80\x80', status=INVALID),
            case(ROOT_SOURCE, b'a/\x80b', status=INVALID),
        ]
        self.run_both(cases, 'utf8bad')
        self.records.append(dict(test='invalid-utf8', cases=len(cases), modes=2, passed=True))

    def test_capacity_exact_and_partial(self):
        path = b'a/b/c.dg'
        cases = [
            case(ROOT_SOURCE, path, out_len=8, status=OK),
            case(ROOT_SOURCE, path, out_len=7, status=CAPACITY),
            case(ROOT_SOURCE, path, out_len=0, status=CAPACITY),
            case(ROOT_SOURCE, path, out_len=1, status=CAPACITY),
            case(ROOT_SOURCE, path, out_len=12, status=OK),
        ]
        self.run_both(cases, 'capacity')
        self.records.append(dict(test='capacity-exact', cases=len(cases), modes=2, passed=True))

    def test_invalid_precedes_capacity(self):
        cases = [
            case(ROOT_SOURCE, '..', out_len=0, status=INVALID),
            case(ROOT_SOURCE, b'\xff', out_len=0, status=INVALID),
            case(ROOT_SOURCE, 'C:/x', out_len=0, status=INVALID),
            case(ROOT_SOURCE, '', out_len=0, status=INVALID),
        ]
        self.run_both(cases, 'precedence')
        self.records.append(dict(test='invalid-before-capacity', cases=len(cases), modes=2, passed=True))

    def test_output_canary_and_repeat(self):
        path = b'src/main.dg'
        cases = [
            case(ROOT_SOURCE, path, out_len=64, status=OK),
            case(ROOT_SOURCE, path, out_len=64, status=OK),
            case(ROOT_SOURCE, b'a/../b', out_len=64, status=INVALID),
            case(ROOT_SOURCE, path, out_len=len(path), status=OK),
        ]
        self.run_both(cases, 'canary')
        self.records.append(dict(test='output-canary-repeat', cases=len(cases), modes=2, passed=True))

    def test_readonly_path_pages(self):
        seg = multibyte_segment()
        cases = [
            case(ROOT_SOURCE, b'bootstrap/main.dg', readonly=1, status=OK),
            case(ROOT_SOURCE, b'a/../b', readonly=1, status=INVALID),
            case(ROOT_SOURCE, '\u6e90\u7801/\u4e3b\u7a0b\u5e8f.dg', readonly=1, status=OK),
            case(ROOT_SOURCE, b'\x80', readonly=1, status=INVALID),
            case(ROOT_SOURCE, seg, readonly=1, status=OK),
        ]
        self.run_both(cases, 'readonly')
        self.records.append(dict(test='readonly-path-pages', cases=len(cases), modes=2, passed=True))

    def test_root_identifiers(self):
        path = b'a.dg'
        cases = [
            case(ROOT_SOURCE, path, status=OK),
            case(ROOT_INCLUDE, path, status=OK),
            case(ROOT_SOURCE + 2, path, status=INVALID),
            case(7, path, status=INVALID),
            case(2 ** 64 - 1, path, status=INVALID),
        ]
        self.run_both(cases, 'roots')
        self.records.append(dict(test='root-identifiers', cases=len(cases), modes=2, passed=True))

    def test_full_out_descriptor_is_validated(self):
        selections = ('baseline', 'written-tail', 'path-tail', 'endpoint-wrap')
        for mode, exe in self.alias.items():
            for name in selections:
                run = subprocess.run([str(exe), name], capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, (mode, name, run.stdout, run.stderr))
        self.records.append(dict(test='full-out-descriptor', cases=len(selections), modes=2,
                                 compiled=True, native_executed=True, passed=True))

    def test_prefix_only_out_descriptor_check_is_rejected(self):
        # The first delivery checked only out[0..path.len): a written word or the
        # path itself in out's unused tail, or a wrapping out.len, slipped past.
        # This is the exact regression: compile the prefix-only logic and prove
        # every new probe case rejects it.
        full_out = (
            ' let op=out.ptr as u64;\n'
            ' let on=out.len as u64;\n'
            ' if !span(op,on){return INVALID;}\n'
            ' if overlap(op,on,pp,path.len){return INVALID;}\n'
            ' if overlap(op,on,wp,8){return INVALID;}\n'
            ' if on<path.len{return CAPACITY;}\n')
        prefix_only = (
            ' let op=out.ptr as u64;\n'
            ' if out.len>=path.len{\n'
            '  if !span(op,path.len){return INVALID;}\n'
            '  if overlap(op,path.len,pp,path.len){return INVALID;}\n'
            '  if overlap(op,path.len,wp,8){return INVALID;}\n'
            ' }else{return CAPACITY;}\n')
        root = self.variant_root('bad-prefix-only', full_out, prefix_only)
        rejected = {}
        for mode in ('debug', 'release'):
            build_name = 'bad-prefix-only-' + mode
            self.build([root, self.std_root, self.wrapper], self.wrapper, mode, build_name)
            exe = self.link_source(self.work / 'probe_alias.c', self.work / (build_name + '.o'),
                                   build_name + '-alias')
            observed = {}
            for name in ('written-tail', 'path-tail', 'endpoint-wrap'):
                run = subprocess.run([str(exe), name], capture_output=True, text=True, timeout=60)
                self.assertNotEqual(run.returncode, 0, (mode, name, run.stdout, run.stderr))
                observed[name] = run.returncode
            rejected[mode] = observed
        self.records.append(dict(test='bad-prefix-only', compiled=True, native_executed=True,
                                 modes=2, rejected=rejected))

    def variant_root(self, name, old, new):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertEqual(source.count(old), 1, name)
        root = self.work / name
        (root / 'bootstrap').mkdir(parents=True)
        (root / 'bootstrap/guest_source_path.dg').write_text(source.replace(old, new, 1), encoding='utf-8')
        return root

    def bad_build(self, name, old, new):
        root = self.variant_root(name, old, new)
        return {mode: self.build([root, self.std_root, self.wrapper], self.wrapper, mode, name + '-' + mode)
                for mode in ('debug', 'release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls = [
            # Removes the "."/".." segment checks: parent traversal is accepted.
            ('bad-accept-parent',
             ' if n==1&&path[start]==DOT{return false;}\n if n==2&&path[start]==DOT&&path[start+1]==DOT{return false;}\n',
             '',
             [case(ROOT_SOURCE, b'../secret', out_len=64, status=INVALID)], 'status'),
            # Skips the mainline strict UTF-8 validation: malformed bytes pass.
            ('bad-accept-invalid-utf8', ' if !utf8.validate(path){return false;}\n', '',
             [case(ROOT_SOURCE, b'\x80', out_len=16, status=INVALID)], 'status'),
            # Publishes bytes before any validation: a rejected call dirties out.
            ('bad-early-publish',
             'pub unsafe fn validate(root:u64,path:[]const u8,out:[]u8,written:*usize)u64{unsafe{\n',
             'pub unsafe fn validate(root:u64,path:[]const u8,out:[]u8,written:*usize)u64{unsafe{\n'
             ' var z:usize=0;while z<path.len&&z<out.len{out[z]=path[z];z+=1;}\n',
             [case(ROOT_SOURCE, b'a/../b', out_len=64, status=INVALID)], 'guard/atomicity'),
            # Truncates a short output buffer and still reports CAPACITY/written:
            # a partial path is published instead of nothing.
            ('bad-truncate-capacity', ' if on<path.len{return CAPACITY;}\n',
             ' if on<path.len{var z:usize=0;while z<out.len{out[z]=path[z];z+=1;}*written=path.len;return CAPACITY;}\n',
             [case(ROOT_SOURCE, b'src/main.dg', out_len=8, status=CAPACITY)], 'guard/atomicity'),
            # Rejects every non-ASCII byte: Chinese names wrongly refused.
            ('bad-reject-multibyte', '  let b=path[i];\n',
             '  let b=path[i];if b>=128{return false;}\n',
             [case(ROOT_SOURCE, '\u6e90\u7801/\u4e3b\u7a0b\u5e8f.dg', out_len=64, status=OK)], 'status'),
        ]
        for name, old, new, cases, reason in controls:
            self.run_both(cases, name + '-good', preflight=False)
            for mode, exe in self.bad_build(name, old, new).items():
                with self.assertRaisesRegex(AssertionError, reason):
                    self.run_cases(exe, cases, name + '-' + mode, preflight=False)
            self.records.append(dict(test=name, compiled=True, native_executed=True, modes=2,
                                     rejected_by=reason))


if __name__ == '__main__':
    unittest.main()
