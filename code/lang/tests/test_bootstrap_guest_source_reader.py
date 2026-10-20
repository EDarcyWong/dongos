"""Actual Dong callback source loader, against an independent Python model.

The production module is compiled twice (debug/release) and driven through a
native C harness that supplies a scripted SysV read_at callback (short reads,
callback errors, protocol violations) and verifies status, size, phase, code,
call count, the exact published bytes and every canary.
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

ROOT = Path(__file__).resolve().parents[2]
WORKS = ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

SOURCE = ROOT / 'lang/bootstrap/guest_source_reader.dg'
OK, INVALID, CAPACITY, IO, PROTOCOL = 0, 1, 2, 3, 4
PHASE_NONE, PHASE_DESCRIPTOR, PHASE_READ, PHASE_PROBE = 0, 1, 2, 3
MAX_SOURCE = 131072
SENTINEL = 0x5a5a5a5a5a5a5a5a
NO_CALL = 2 ** 64 - 1
PREFLIGHTS = 14
WRAPPER = '''module probe.guest_reader_export;
import bootstrap.guest_source_reader as r;
export("dong_guest_source_load") pub unsafe fn load(context:u64,read_at:r.ReadAt,scratch:*u8,sn:usize,out:*u8,on:usize,result:*r.Result)u64{unsafe{
 return r.load(context,read_at,slice_from_raw_parts(scratch,sn),slice_from_raw_parts(out,on),result);
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
typedef struct {uint64_t status,size,phase,code;} Result;
typedef uint64_t (__attribute__((sysv_abi)) *ReadAt)(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
extern uint64_t ABI dong_guest_source_load(uint64_t,ReadAt,uint8_t*,uint64_t,uint8_t*,uint64_t,Result*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
typedef struct {const uint8_t*data;uint64_t len,chunk,fail_call,fail_code,oversize_call,calls;} Source;
// Scripted callback: chunked short reads, optional error or protocol violation.
static uint64_t ABI source_read(uint64_t context,uint64_t offset,uint8_t*destination,uint64_t capacity,uint64_t*moved){
 Source*s=(Source*)(uintptr_t)context;
 uint64_t call=s->calls++;
 if(call==s->fail_call){*moved=capacity;return s->fail_code;}
 if(call==s->oversize_call){*moved=capacity+1;if(capacity)memset(destination,0xee,(size_t)capacity);return 0;}
 if(offset>=s->len){*moved=0;return 0;}
 uint64_t n=s->len-offset;if(n>capacity)n=capacity;if(s->chunk&&n>s->chunk)n=s->chunk;
 if(n)memcpy(destination,s->data+offset,(size_t)n);
 *moved=n;return 0;
}
static unsigned invalid(void){
 static uint8_t arena[640] __attribute__((aligned(64))),saved[640];
 static const uint8_t content[]="module x;";
 const unsigned total=14;
 uint8_t*scratch=arena+64;uint8_t*out=arena+256;Result*res=(Result*)(arena+384);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  memcpy(scratch,content,10);memset(out,'p',8);
  Source src={content,10,0,UINT64_MAX,0x1234,UINT64_MAX,0};
  memcpy(saved,arena,sizeof(arena));
  uint8_t*sp=scratch;uint64_t sn=97;uint8_t*op=out;uint64_t on=96;Result*r=res;
  switch(i){
   case 0:r=NULL;break;
   case 1:r=(Result*)(arena+385);break;
   case 2:r=(Result*)(uintptr_t)(UINT64_MAX-7);break;
   case 3:sp=NULL;break;
   case 4:sp=(uint8_t*)(uintptr_t)(UINT64_MAX-1);break;
   case 5:op=NULL;break;
   case 6:op=(uint8_t*)(uintptr_t)(UINT64_MAX-1);break;
   case 7:sp=out;break;
   case 8:r=(Result*)out;break;
   case 9:r=(Result*)scratch;break;
   case 10:sn=96;break;
   case 11:on=131073;break;
   case 12:sn=131074;break;
   default:sn=0;on=0;break;
  }
  uint64_t s=dong_guest_source_load((uint64_t)(uintptr_t)&src,source_read,sp,sn,op,on,r);
  if(s!=1||src.calls!=0||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u calls %llu\n",i,(unsigned)s,(unsigned long long)src.calls);exit(93);}
 }
 memset(arena,0xa5,sizeof(arena));
 memcpy(scratch,content,10);
 Source src={content,10,0,UINT64_MAX,0x1234,UINT64_MAX,0};
 Result*r=res;
 uint64_t s=dong_guest_source_load((uint64_t)(uintptr_t)&src,source_read,scratch,65,out,64,r);
 if(s!=0||r->status!=0||r->size!=10||r->phase!=0||r->code!=0||src.calls!=2
    ||memcmp(out,content,10)||!filled(out+10,54)){fprintf(stderr,"baseline status %u size %llu calls %llu\n",(unsigned)s,(unsigned long long)r->size,(unsigned long long)src.calls);exit(93);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,count,preflights=0;read_exact(&flag,8);if(flag)preflights=invalid();read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[7];read_exact(h,sizeof(h));
  uint64_t on=h[0],sn=h[1],clen=h[2],chunk=h[3],fail=h[4],fcode=h[5],over=h[6];
  if(on>1000000||sn>1000000||clen>1000000)exit(94);
  uint8_t*d=malloc(clen?clen:1),*copy=malloc(clen?clen:1),*sb=malloc(sn+64),*ob=malloc(on+64);
  if(!d||!copy||!sb||!ob)exit(95);
  read_exact(d,clen);memcpy(copy,d,clen);
  memset(sb,0xa5,sn+64);memset(ob,0xa5,on+64);
  Source src={d,clen,chunk,fail,fcode,over,0};
  typedef struct {uint64_t pre[4];Result r;uint64_t post[4];} Box;
  Box box;memset(&box,0xa5,sizeof(box));
  uint64_t s=dong_guest_source_load((uint64_t)(uintptr_t)&src,source_read,sb+32,sn,ob+32,on,&box.r);
  uint64_t guard=1;
  if(!filled(sb,32)||!filled(sb+32+sn,32))guard=0;
  if(!filled(ob,32)||!filled(ob+32+on,32))guard=0;
  if(!filled(box.pre,32)||!filled(box.post,32))guard=0;
  if(clen&&memcmp(d,copy,clen))guard=0;
  uint64_t resp[3]={s,guard,src.calls};write_exact(resp,24);write_exact(&box.r,32);write_exact(ob+32,on);
  free(d);free(copy);free(sb);free(ob);
 }return 0;
}
'''


def model(content, out_len, chunk=0, fail_call=None, fail_code=0x1234, oversize_call=None):
    """Independent model of the documented callback contract and call sequence."""
    calls = 0
    total = 0

    def call(capacity, advance):
        nonlocal calls, total
        if fail_call is not None and calls == fail_call:
            calls += 1
            return 'io', fail_code
        if oversize_call is not None and calls == oversize_call:
            calls += 1
            return 'over', capacity + 1
        calls += 1
        if total >= len(content):
            return 'eof', 0
        n = min(capacity, len(content) - total)
        if chunk:
            n = min(n, chunk)
        if advance:
            total += n
        return 'data', n

    while total < out_len:
        kind, n = call(out_len - total, True)
        if kind == 'io':
            return IO, total, PHASE_READ, n, calls
        if kind == 'over':
            return PROTOCOL, total, PHASE_READ, n, calls
        if kind == 'eof':
            return OK, total, PHASE_NONE, 0, calls
    kind, n = call(1, False)
    if kind == 'io':
        return IO, total, PHASE_PROBE, n, calls
    if kind == 'over':
        return PROTOCOL, total, PHASE_PROBE, n, calls
    if kind == 'eof':
        return OK, total, PHASE_NONE, 0, calls
    return CAPACITY, total, PHASE_PROBE, 0, calls


def case(content, out_len, scratch_len=None, chunk=0, fail_call=None, fail_code=0x1234,
         oversize_call=None, status=None, size=None, phase=None, code=None):
    content = content.encode('utf-8') if isinstance(content, str) else bytes(content)
    if scratch_len is None:
        scratch_len = out_len + 1
    expected = model(content, out_len, chunk, fail_call, fail_code, oversize_call)
    if status is not None:
        assert expected[0] == status, (content, out_len, expected, status)
    if size is not None:
        assert expected[1] == size, (content, expected, size)
    if phase is not None:
        assert expected[2] == phase, (content, expected, phase)
    if code is not None:
        assert expected[3] == code, (content, expected, code)
    return dict(content=content, out_len=out_len, scratch_len=scratch_len, chunk=chunk,
                fail_call=NO_CALL if fail_call is None else fail_call, fail_code=fail_code,
                oversize_call=NO_CALL if oversize_call is None else oversize_call,
                status=expected[0], size=expected[1], phase=expected[2], code=expected[3],
                calls=expected[4])


class GuestSourceReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native guest-source reader requires NASM/GCC')
        cls.work = ROOT / 'build/test/guest-integration/GUEST2' / ('run-' + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        (cls.work / 'probe.c').write_text(HARNESS, encoding='utf-8')
        cls.executables = {}
        cls.records = []
        cls.inputs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [SOURCE, SOURCE.with_suffix('.md'), Path(__file__)]}
        cls.src = cls.work / 'src'
        (cls.src / 'bootstrap').mkdir(parents=True)
        (cls.src / 'bootstrap/guest_source_reader.dg').write_bytes(SOURCE.read_bytes())
        cls.wrapper = cls.work / 'wrapper'
        (cls.wrapper / 'probe').mkdir(parents=True)
        (cls.wrapper / 'probe/guest_reader_export.dg').write_text(WRAPPER, encoding='utf-8')
        for mode in ('debug', 'release'):
            cls.executables[mode] = cls.build([cls.src, cls.wrapper], cls.wrapper, mode, mode)

    @classmethod
    def command(cls, cmd, name):
        r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=120)
        (cls.work / (name + '.log')).write_text(r.stdout + r.stderr, encoding='utf-8')
        if r.returncode:
            raise AssertionError((name, r.returncode, r.stdout, r.stderr))

    @classmethod
    def build(cls, roots, wrapper, mode, name):
        compiled = compile_file(wrapper / 'probe/guest_reader_export.dg', roots=roots, mode=mode)
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
    def tearDownClass(cls):
        if not hasattr(cls, 'work'):
            return
        assert cls.inputs == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              [SOURCE, SOURCE.with_suffix('.md'), Path(__file__)]}, 'inputs changed'
        files = {p.relative_to(cls.work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in cls.work.rglob('*') if p.is_file()}
        (cls.work / 'summary.json').write_text(json.dumps(dict(
            source_sha256=cls.inputs, artifact_sha256=files, records=cls.records,
            groups=len(cls.records), integrated=False, OS_VM_built=False), indent=2) + '\n')

    def run_cases(self, exe, cases, label, preflight=True):
        payload = bytearray(struct.pack('<2Q', int(preflight), len(cases)))
        for c in cases:
            payload.extend(struct.pack('<7Q', c['out_len'], c['scratch_len'], len(c['content']),
                                       c['chunk'], c['fail_call'], c['fail_code'], c['oversize_call']))
            payload.extend(c['content'])
        (self.work / (label + '.input')).write_bytes(payload)
        run = subprocess.run([str(exe)], input=bytes(payload), capture_output=True, timeout=120)
        (self.work / (label + '.output')).write_bytes(run.stdout)
        (self.work / (label + '.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode, 0, run.stderr)
        preflights, = struct.unpack_from('<Q', run.stdout, 0)
        self.assertEqual(preflights, PREFLIGHTS if preflight else 0)
        offset = 8
        for index, c in enumerate(cases):
            status, guard, calls = struct.unpack_from('<3Q', run.stdout, offset)
            offset += 24
            got = struct.unpack_from('<4Q', run.stdout, offset)
            offset += 32
            out = run.stdout[offset:offset + c['out_len']]
            offset += c['out_len']
            self.assertEqual(guard, 1, (label, index, 'guard/atomicity'))
            self.assertEqual(status, c['status'], (label, index, 'status'))
            self.assertEqual(got[0], c['status'], (label, index, 'status'))
            self.assertEqual(got[1], c['size'], (label, index, 'size'))
            self.assertEqual(got[2], c['phase'], (label, index, 'phase'))
            self.assertEqual(got[3], c['code'], (label, index, 'code'))
            self.assertEqual(calls, c['calls'], (label, index, 'callback-calls'))
            if status == OK:
                self.assertEqual(len(c['content']), c['size'], (label, index, 'size'))
                self.assertEqual(out[:c['size']], c['content'], (label, index, 'verbatim'))
                self.assertEqual(out[c['size']:], b'\xa5' * (c['out_len'] - c['size']),
                                 (label, index, 'tail-canary'))
            else:
                self.assertEqual(out, b'\xa5' * c['out_len'], (label, index, 'guard/atomicity'))
        self.assertEqual(offset, len(run.stdout))

    def run_both(self, cases, label, preflight=True):
        for mode, exe in self.executables.items():
            self.run_cases(exe, cases, label + '-' + mode, preflight)

    def test_empty_file(self):
        cases = [
            case(b'', 0, status=OK, size=0),
            case(b'', 8, status=OK, size=0),
            case(b'', 16, status=OK, size=0),
        ]
        self.run_both(cases, 'empty')
        self.records.append(dict(test='empty-file', cases=len(cases), modes=2, passed=True))

    def test_small_file(self):
        cases = [
            case(b'module x;', 64, status=OK, size=9),
            case(b'module x;', 16, status=OK, size=9),
            case(b'module x;', 9, status=OK, size=9),
            case(b'module x;', 8, status=CAPACITY, size=8),
        ]
        self.run_both(cases, 'small')
        self.records.append(dict(test='small-file', cases=len(cases), modes=2, passed=True))

    def test_exact_capacity(self):
        cases = [case(b'12345678', 8, status=OK, size=8, phase=PHASE_NONE)]
        self.run_both(cases, 'exact')
        self.records.append(dict(test='exact-capacity', cases=len(cases), modes=2, passed=True))

    def test_capacity_plus_one(self):
        cases = [case(b'123456789', 8, status=CAPACITY, size=8, phase=PHASE_PROBE)]
        self.run_both(cases, 'over1')
        self.records.append(dict(test='capacity-plus-one', cases=len(cases), modes=2, passed=True))

    def test_far_over_capacity(self):
        cases = [case(b'x' * 5000, 16, status=CAPACITY, size=16, phase=PHASE_PROBE)]
        self.run_both(cases, 'farshort')
        self.records.append(dict(test='far-over-capacity', cases=len(cases), modes=2, passed=True))

    def test_short_read_byte_at_a_time(self):
        cases = [case(b'abcdef', 16, chunk=1, status=OK, size=6)]
        self.run_both(cases, 'byte')
        self.records.append(dict(test='byte-at-a-time', cases=len(cases), modes=2, passed=True))

    def test_short_read_exact_capacity(self):
        cases = [case(b'abcdefgh', 8, chunk=1, status=OK, size=8)]
        self.run_both(cases, 'byteexact')
        self.records.append(dict(test='byte-exact-capacity', cases=len(cases), modes=2, passed=True))

    def test_short_read_over_capacity(self):
        cases = [case(b'abcdefghi', 8, chunk=1, status=CAPACITY, size=8, phase=PHASE_PROBE)]
        self.run_both(cases, 'byteover')
        self.records.append(dict(test='byte-over-capacity', cases=len(cases), modes=2, passed=True))

    def test_short_read_patterns(self):
        cases = [
            case(b'0123456789', 16, chunk=3, status=OK, size=10),
            case(b'0123456', 7, chunk=2, status=OK, size=7),
            case(b'0123456789abcdef', 32, chunk=5, status=OK, size=16),
        ]
        self.run_both(cases, 'chunks')
        self.records.append(dict(test='short-read-patterns', cases=len(cases), modes=2, passed=True))

    def test_mid_read_io_failure(self):
        cases = [case(b'0123456789', 16, chunk=4, fail_call=2, fail_code=0x77,
                      status=IO, size=8, phase=PHASE_READ, code=0x77)]
        self.run_both(cases, 'midio')
        self.records.append(dict(test='mid-read-io', cases=len(cases), modes=2, passed=True))

    def test_immediate_io_failure(self):
        cases = [case(b'0123456789', 16, fail_call=0, fail_code=0x55,
                      status=IO, size=0, phase=PHASE_READ, code=0x55)]
        self.run_both(cases, 'immio')
        self.records.append(dict(test='immediate-io', cases=len(cases), modes=2, passed=True))

    def test_probe_io_failure(self):
        cases = [case(b'12345678', 8, fail_call=1, fail_code=0x66,
                      status=IO, size=8, phase=PHASE_PROBE, code=0x66)]
        self.run_both(cases, 'probeio')
        self.records.append(dict(test='probe-io', cases=len(cases), modes=2, passed=True))

    def test_oversize_read(self):
        cases = [case(b'12345678', 16, oversize_call=0, status=PROTOCOL, size=0,
                      phase=PHASE_READ, code=17)]
        self.run_both(cases, 'overread')
        self.records.append(dict(test='oversize-read', cases=len(cases), modes=2, passed=True))

    def test_oversize_probe(self):
        cases = [case(b'12345678', 8, oversize_call=1, status=PROTOCOL, size=8,
                      phase=PHASE_PROBE, code=2)]
        self.run_both(cases, 'overprobe')
        self.records.append(dict(test='oversize-probe', cases=len(cases), modes=2, passed=True))

    def test_eof_at_start(self):
        cases = [case(b'', 16, status=OK, size=0, phase=PHASE_NONE, code=0)]
        self.run_both(cases, 'eofstart')
        self.records.append(dict(test='eof-at-start', cases=len(cases), modes=2, passed=True))

    def test_zero_capacity_output(self):
        cases = [
            case(b'x', 0, status=CAPACITY, size=0, phase=PHASE_PROBE),
            case(b'', 0, status=OK, size=0, phase=PHASE_NONE),
        ]
        self.run_both(cases, 'zeroout')
        self.records.append(dict(test='zero-capacity-output', cases=len(cases), modes=2, passed=True))

    def test_max_source_exact(self):
        content = b'a' * MAX_SOURCE
        cases = [case(content, MAX_SOURCE, scratch_len=MAX_SOURCE + 1, status=OK, size=MAX_SOURCE)]
        self.run_both(cases, 'maxexact')
        self.records.append(dict(test='max-source-exact', cases=len(cases), modes=2, passed=True))

    def test_max_source_over(self):
        content = b'a' * (MAX_SOURCE + 1)
        cases = [case(content, MAX_SOURCE, scratch_len=MAX_SOURCE + 1, status=CAPACITY,
                      size=MAX_SOURCE, phase=PHASE_PROBE)]
        self.run_both(cases, 'maxover')
        self.records.append(dict(test='max-source-over', cases=len(cases), modes=2, passed=True))

    def test_error_code_preserved(self):
        cases = [
            case(b'12345678', 8, fail_call=0, fail_code=0xDEADBEEF,
                 status=IO, size=0, phase=PHASE_READ, code=0xDEADBEEF),
            case(b'12345678', 8, fail_call=1, fail_code=0x123456789ABCDEF,
                 status=IO, size=8, phase=PHASE_PROBE, code=0x123456789ABCDEF),
        ]
        self.run_both(cases, 'codes')
        self.records.append(dict(test='error-code-preserved', cases=len(cases), modes=2, passed=True))

    def test_repeat_deterministic(self):
        cases = [
            case(b'0123456789', 16, chunk=3, status=OK, size=10),
            case(b'0123456789', 16, chunk=3, status=OK, size=10),
            case(b'0123456789', 8, chunk=3, status=CAPACITY, size=8),
        ]
        self.run_both(cases, 'repeat')
        self.records.append(dict(test='repeat-deterministic', cases=len(cases), modes=2, passed=True))

    def bad_build(self, name, old, new):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertEqual(source.count(old), 1, name)
        root = self.work / name
        (root / 'bootstrap').mkdir(parents=True)
        (root / 'bootstrap/guest_source_reader.dg').write_text(source.replace(old, new, 1), encoding='utf-8')
        return {mode: self.build([root, self.wrapper], self.wrapper, mode, name + '-' + mode)
                for mode in ('debug', 'release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls = [
            # Publishes every chunk immediately instead of after EOF: a later
            # callback error leaves a partial file in out.
            ('bad-publish-each-chunk', '  total+=moved;\n',
             '  total+=moved;var q:usize=0;while q<total{out[q]=scratch[q];q+=1;}\n',
             [case(b'01234567', 16, scratch_len=17, chunk=2, fail_call=2, fail_code=0x77,
                   status=IO, size=4, phase=PHASE_READ, code=0x77)], 'guard/atomicity'),
            # Probes with capacity 0 so EOF is always "confirmed" and an
            # over-capacity file is truncated as success.
            ('bad-zero-probe', ',PROBE_CAPACITY,&moved);', ',0,&moved);',
             [case(b'123456789', 8, status=CAPACITY, size=8)], 'status'),
            # Ignores callback errors other than MAX: an I/O failure becomes OK.
            ('bad-ignore-error',
             '=read_at(context,total as u64,&scratch[total],cap,&moved);\n  if code!=0{return publish(result,IO,total,PHASE_READ,code);}',
             '=read_at(context,total as u64,&scratch[total],cap,&moved);\n  if code==MAX{return publish(result,IO,total,PHASE_READ,code);}',
             [case(b'12345678', 8, fail_call=0, fail_code=0x55, status=IO, size=0,
                   phase=PHASE_READ, code=0x55)], 'status'),
            # Reports a probe I/O failure in the READ phase instead of PROBE.
            ('bad-probe-phase', 'return publish(result,IO,total,PHASE_PROBE,code);',
             'return publish(result,IO,total,PHASE_READ,code);',
             [case(b'12345678', 8, fail_call=1, fail_code=0x66, status=IO, size=8,
                   phase=PHASE_PROBE, code=0x66)], 'phase'),
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
