"""Actual Dong guest compile memory planner, against an independent Python model.

The production module is compiled in debug and release with a thin export
wrapper and driven through a native C harness. Every case checks the status,
the full Result record, every Placement, the untouched out tail and guard
bytes around all caller storage, plus unchanged inputs. The oracle defines
placement as "lowest aligned offset that collides with no earlier coexisting
region" over an explicit candidate set, independently of the production
retry loop, and successful plans are additionally checked for pairwise
non-overlap of coexisting regions and alignment.
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

SOURCE = WORKS / 'pool-works/lang/bootstrap/guest_compile_memory.dg'
OK, INVALID, CAPACITY, BUDGET, STACK = 0, 1, 2, 3, 4
OVERFLOW_ARENA, OVERFLOW_SUM, OVERFLOW_PEAK, OVERFLOW_MEMORY = 1, 2, 4, 8
MAX = 2 ** 64 - 1
MAX_PHASES = MAX_REGIONS = 64
KIB, MIB = 1024, 1024 * 1024
PREFLIGHTS = 14
WRAPPER = '''module probe.guest_memory_export;
import bootstrap.guest_compile_memory as m;
export("dong_guest_compile_memory") pub unsafe fn plan(budget:*const m.Budget,regions:*const m.Region,rn:usize,out:*m.Placement,on:usize,result:*m.Result)u64{unsafe{
 return m.plan(budget,slice_from_raw_parts(regions,rn),slice_from_raw_parts(out,on),result);
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
extern uint64_t ABI dong_guest_compile_memory(const uint64_t*,const uint64_t*,uint64_t,uint64_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t*page_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static void page_readonly(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;if(!VirtualProtect(p,n,PAGE_READONLY,&old))exit(98);
#else
 if(mprotect(p,n,PROT_READ))exit(98);
#endif
}
static void page_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;if(!VirtualFree(p,0,MEM_RELEASE))exit(98);
#else
 if(munmap(p,n))exit(98);
#endif
}
/* Structural descriptor rejections. Each must return INVALID and leave the
   whole arena (inputs, out, result and the gaps between them) unchanged. */
static unsigned invalid(void){
 static uint64_t arena[160] __attribute__((aligned(64)));static uint64_t saved[160];
 const unsigned total=14;
 uint64_t*budget=arena+4,*regions=arena+16,*out=arena+48,*result=arena+96;
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  budget[0]=4;budget[1]=0;budget[2]=MIB_BUDGET;budget[3]=0;budget[4]=16384;
  for(int r=0;r<2;r++){regions[r*4]=64;regions[r*4+1]=8;regions[r*4+2]=0;regions[r*4+3]=3;}
  memcpy(saved,arena,sizeof(arena));
  const uint64_t*bp=budget,*rp=regions;uint64_t rn=2;uint64_t*op=out;uint64_t on=4;uint64_t*res=result;
  switch(i){
   case 0:res=NULL;break;
   case 1:res=(uint64_t*)((uint8_t*)result+4);break;
   case 2:res=(uint64_t*)(uintptr_t)(UINT64_MAX-7);break;
   case 3:bp=NULL;break;
   case 4:bp=(const uint64_t*)((const uint8_t*)budget+4);break;
   case 5:rn=65;break;
   case 6:rp=NULL;break;
   case 7:rp=(const uint64_t*)((const uint8_t*)regions+4);break;
   case 8:op=NULL;break;
   case 9:on=UINT64_MAX/16+1;break;
   case 10:op=regions+4;break;
   case 11:res=out+2;break;
   case 12:res=budget+2;break;
   default:op=budget;break;
  }
  uint64_t s=dong_guest_compile_memory(bp,rp,rn,op,on,res);
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 /* Same arena, nothing corrupted: the baseline call must succeed. */
 memset(arena,0xa5,sizeof(arena));
 budget[0]=4;budget[1]=0;budget[2]=MIB_BUDGET;budget[3]=0;budget[4]=16384;
 for(int r=0;r<2;r++){regions[r*4]=64;regions[r*4+1]=8;regions[r*4+2]=0;regions[r*4+3]=3;}
 uint64_t s=dong_guest_compile_memory(budget,regions,2,out,4,result);
 if(s!=0||out[0]!=0||out[1]!=64||out[2]!=64||out[3]!=128||result[1]!=128||!filled(out+4,32)){fprintf(stderr,"baseline status %u\n",(unsigned)s);exit(93);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,count,preflights=0;read_exact(&flag,8);if(flag)preflights=invalid();read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[3];read_exact(h,sizeof(h));
  uint64_t rn=h[0],on=h[1],ro=h[2];
  if(rn>1000||on>1000)exit(94);
  uint64_t ib=40+rn*32;
  uint8_t*in=malloc(ib+64),*copy=malloc(ib),*ob=malloc(on*16+64),*rb=malloc(72+64);
  if(!in||!copy||!ob||!rb)exit(95);
  memset(in,0xa5,ib+64);read_exact(in+32,ib);memcpy(copy,in+32,ib);
  memset(ob,0xa5,on*16+64);memset(rb,0xa5,72+64);
  const uint8_t*inputs=in+32;uint8_t*page=NULL;uint64_t pages=0;
  if(ro){pages=(ib/4096+2)*4096;page=page_alloc(pages);if(!page)exit(95);memcpy(page,copy,ib);page_readonly(page,pages);inputs=page;}
  const uint64_t*bp=(const uint64_t*)inputs,*rp=rn?(const uint64_t*)(inputs+40):NULL;
  uint64_t s=dong_guest_compile_memory(bp,rp,rn,on?(uint64_t*)(ob+32):NULL,on,(uint64_t*)(rb+32));
  int guard=1;
  if(ro){if(memcmp(page,copy,ib))guard=0;}
  else if(memcmp(in+32,copy,ib)||!filled(in,32)||!filled(in+32+ib,32))guard=0;
  if(!filled(ob,32)||!filled(ob+32+on*16,32)||!filled(rb,32)||!filled(rb+32+72,32))guard=0;
  uint64_t resp[2]={s,(uint64_t)guard};write_exact(resp,16);write_exact(rb+32,72);write_exact(ob+32,on*16);
  if(page)page_free(page,pages);
  free(in);free(copy);free(ob);free(rb);
 }return 0;
}
'''.replace('MIB_BUDGET', str(MIB) + 'ULL')
UNTOUCHED = b'\xa5' * 8
RESULT_FIELDS = ('status', 'arena_size', 'arena_alignment', 'peak_live', 'peak_phase',
                 'sum_regions', 'memory_required', 'stack_short', 'overflow')


def first_fit(regions):
    """Lowest aligned offset per region (input order) that overlaps no earlier
    coexisting non-empty region; None marks a placement beyond usize."""
    offsets = []
    for i, (size, align, first, last) in enumerate(regions):
        live = [(offsets[j], offsets[j] + regions[j][0]) for j in range(i)
                if regions[j][2] <= last and first <= regions[j][3]]
        found = None
        for base in sorted({0, *(end for _, end in live)}):
            start = -(-base // align) * align
            if start + size > MAX:
                continue
            if size == 0 or all(not (start < e and s < start + size) for s, e in live if e > s):
                if found is None or start < found:
                    found = start
        if found is None:
            return offsets, False
        offsets.append(found)
    return offsets, True


def model(budget, regions, out_len):
    """Documented contract. Returns (status, result dict or None, placements or None)."""
    phases, resident, memory_budget, stack_required, stack_limit = budget
    if not 1 <= phases <= MAX_PHASES or len(regions) > MAX_REGIONS:
        return INVALID, None, None
    for size, align, first, last in regions:
        if align == 0 or align & (align - 1) or first > last or last >= phases:
            return INVALID, None, None
    if out_len < len(regions):
        return CAPACITY, None, None
    overflow = 0
    total = sum(r[0] for r in regions)
    if total > MAX:
        overflow |= OVERFLOW_SUM
        total = MAX
    offsets, placed = first_fit(regions)
    if placed:
        arena = max([o + r[0] for o, r in zip(offsets, regions)], default=0)
    else:
        overflow |= OVERFLOW_ARENA
        arena = MAX
    peak = peak_phase = 0
    for p in range(phases):
        live = sum(r[0] for r in regions if r[2] <= p <= r[3])
        if live > MAX:
            overflow |= OVERFLOW_PEAK
            live = MAX
        if live > peak:
            peak, peak_phase = live, p
    if not placed or resident + arena > MAX:
        overflow |= OVERFLOW_MEMORY
        memory = MAX
    else:
        memory = resident + arena
    short = max(0, stack_required - stack_limit)
    if overflow & OVERFLOW_MEMORY or memory > memory_budget:
        status = BUDGET
    elif short:
        status = STACK
    else:
        status = OK
    result = dict(status=status, arena_size=arena,
                  arena_alignment=max([r[1] for r in regions], default=1), peak_live=peak,
                  peak_phase=peak_phase, sum_regions=total, memory_required=memory,
                  stack_short=short, overflow=overflow)
    # Non-OK plans publish nothing: no Result, no placements.
    if status != OK:
        return status, None, None
    return status, result, [(o, o + r[0]) for o, r in zip(offsets, regions)]


def case(budget, regions, out_len=None, readonly=0, status=None, **expect):
    regions = [tuple(r) for r in regions]
    if out_len is None:
        out_len = len(regions)
    got, result, placements = model(tuple(budget), regions, out_len)
    if status is not None:
        assert got == status, (budget, regions, got, status)
    for key, value in expect.items():
        assert result is not None, ('no result is published for a non-OK status', key)
        assert result[key] == value, (key, result[key], value)
    return dict(budget=tuple(budget), regions=regions, out_len=out_len, readonly=readonly,
                status=got, result=result, placements=placements)


def budget(phases=4, resident=0, memory=64 * MIB, stack_required=0, stack_limit=16 * KIB):
    return (phases, resident, memory, stack_required, stack_limit)


# A frontend -> retained graph -> backend -> assembly pipeline. The sizes are
# test inputs in the order of the measurements recorded in
# code/docs/l3-native-selfhost-progress.md; the planner itself hardcodes none.
PIPELINE = [
    (28 * MIB, 4096, 0, 0),      # frontend scratch, released before backend
    (24 * MIB, 64, 0, 3),        # retained compacted graph, live to the end
    (8 * MIB + 123, 64, 2, 2),   # backend workspace
    (8 * MIB, 4096, 2, 3),       # intermediate assembly text
    (2 * MIB, 4096, 3, 3),       # assembled ELF image
]


class GuestCompileMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native guest compile memory gate requires NASM/GCC')
        cls.work = WORKS / 'pool-works/build/GUEST3' / ('run-' + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        (cls.work / 'probe.c').write_text(HARNESS, encoding='utf-8')
        cls.records = []
        cls.inputs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [SOURCE, SOURCE.with_suffix('.md'), Path(__file__)]}
        cls.src = cls.work / 'src'
        (cls.src / 'bootstrap').mkdir(parents=True)
        (cls.src / 'bootstrap/guest_compile_memory.dg').write_bytes(SOURCE.read_bytes())
        cls.wrapper = cls.work / 'wrapper'
        (cls.wrapper / 'probe').mkdir(parents=True)
        (cls.wrapper / 'probe/guest_memory_export.dg').write_text(WRAPPER, encoding='utf-8')
        cls.executables = {mode: cls.build([cls.src, cls.wrapper], mode, mode) for mode in ('debug', 'release')}

    @classmethod
    def command(cls, cmd, name):
        r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=120)
        (cls.work / (name + '.log')).write_text(r.stdout + r.stderr, encoding='utf-8')
        if r.returncode:
            raise AssertionError((name, r.returncode, r.stdout, r.stderr))

    @classmethod
    def build(cls, roots, mode, name):
        compiled = compile_file(cls.wrapper / 'probe/guest_memory_export.dg', roots=roots, mode=mode)
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
            payload.extend(struct.pack('<3Q', len(c['regions']), c['out_len'], c['readonly']))
            payload.extend(struct.pack('<5Q', *c['budget']))
            for r in c['regions']:
                payload.extend(struct.pack('<4Q', *r))
        (self.work / (label + '.input')).write_bytes(payload)
        run = subprocess.run([str(exe)], input=bytes(payload), capture_output=True, timeout=120)
        (self.work / (label + '.output')).write_bytes(run.stdout)
        (self.work / (label + '.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode, 0, run.stderr)
        preflights, = struct.unpack_from('<Q', run.stdout, 0)
        self.assertEqual(preflights, PREFLIGHTS if preflight else 0)
        offset = 8
        for index, c in enumerate(cases):
            status, guard = struct.unpack_from('<2Q', run.stdout, offset)
            raw_result = run.stdout[offset + 16:offset + 88]
            offset += 88
            out = run.stdout[offset:offset + 16 * c['out_len']]
            offset += 16 * c['out_len']
            where = (label, index)
            self.assertEqual(guard, 1, where + ('guard/atomicity',))
            self.assertEqual(status, c['status'], where + ('status',))
            # Placements first: a reused live region must be rejected by the
            # model-independent overlap check, not only by a changed Result.
            if c['placements'] is None:
                self.assertEqual(out, b'\xa5' * len(out), where + ('guard/atomicity',))
            else:
                n = len(c['placements'])
                got = [struct.unpack_from('<2Q', out, 16 * i) for i in range(n)]
                self.check_layout(c['regions'], got, where)
                self.assertEqual(got, c['placements'], where + ('placement',))
                self.assertEqual(out[16 * n:], b'\xa5' * (len(out) - 16 * n), where + ('tail-canary',))
            if c['result'] is None:
                self.assertEqual(raw_result, b'\xa5' * 72, where + ('guard/atomicity',))
            else:
                self.assertEqual(dict(zip(RESULT_FIELDS, struct.unpack('<9Q', raw_result))), c['result'],
                                 where + ('result',))
        self.assertEqual(offset, len(run.stdout))

    def check_layout(self, regions, placements, where):
        """Model-independent properties of every successful plan."""
        for (size, align, first, last), (start, end) in zip(regions, placements):
            self.assertEqual(start % align, 0, where + ('placement', 'alignment'))
            self.assertEqual(end - start, size, where + ('placement', 'size'))
        for i in range(len(regions)):
            for j in range(i):
                a, b = regions[i], regions[j]
                if a[2] <= b[3] and b[2] <= a[3] and a[0] and b[0]:
                    (s1, e1), (s2, e2) = placements[i], placements[j]
                    self.assertFalse(s1 < e2 and s2 < e1, where + ('placement', 'coexisting-overlap', i, j))

    def run_both(self, cases, label, preflight=True):
        for mode, exe in self.executables.items():
            self.run_cases(exe, cases, label + '-' + mode, preflight)

    def test_pipeline_exclusive_reuse(self):
        c = case(budget(resident=411736), PIPELINE, status=OK)
        self.assertLess(c['result']['peak_live'], c['result']['sum_regions'])
        self.assertLess(c['result']['arena_size'], c['result']['sum_regions'])
        # Backend/assembly reuse the frontend range; the graph is never reused.
        graph = c['placements'][1]
        for k in (0, 2, 3, 4):
            other = c['placements'][k]
            self.assertFalse(other[0] < graph[1] and graph[0] < other[1])
        self.assertLess(c['placements'][2][0], c['placements'][0][1])
        cases = [c, case(budget(resident=411736), PIPELINE + [(1, 1, 3, 3)], status=OK)]
        self.run_both(cases, 'pipeline')
        self.records.append(dict(test='pipeline-exclusive-reuse', cases=len(cases), modes=2, passed=True,
                                 arena=c['result']['arena_size'], peak=c['result']['peak_live'],
                                 sum=c['result']['sum_regions']))

    def test_coexisting_regions_never_overlap(self):
        whole = [(100, 8, 0, 3), (7, 1, 0, 3), (64, 64, 0, 3), (3, 2, 0, 3)]
        chain = [(10, 1, 0, 1), (10, 1, 1, 2), (10, 1, 2, 3), (10, 1, 0, 0)]
        cases = [
            case(budget(), whole, status=OK, arena_size=192, peak_live=174, sum_regions=174),
            case(budget(), chain, status=OK),
            case(budget(phases=1), [(5, 1, 0, 0), (5, 1, 0, 0)], status=OK, arena_size=10),
            case(budget(phases=2), [(5, 1, 0, 0), (5, 1, 1, 1)], status=OK, arena_size=5,
                 peak_live=5, sum_regions=10),
        ]
        self.assertEqual(cases[1]['placements'], [(0, 10), (10, 20), (0, 10), (10, 20)])
        self.run_both(cases, 'coexist')
        self.records.append(dict(test='coexisting-no-overlap', cases=len(cases), modes=2, passed=True))

    def test_zero_length_and_empty(self):
        cases = [
            case(budget(), [], status=OK, arena_size=0, arena_alignment=1, peak_live=0, peak_phase=0),
            case(budget(), [(0, 4096, 0, 3)], status=OK, arena_size=0, arena_alignment=4096),
            case(budget(), [(16, 8, 0, 3), (0, 8, 0, 3), (16, 8, 0, 3)], status=OK, arena_size=32),
            case(budget(memory=0), [(0, 1, 0, 0)], status=OK, memory_required=0),
            case(budget(memory=0), [], out_len=3, status=OK),
        ]
        self.assertEqual(cases[2]['placements'], [(0, 16), (0, 0), (16, 32)])
        self.run_both(cases, 'zero')
        self.records.append(dict(test='zero-length-empty', cases=len(cases), modes=2, passed=True))

    def test_alignment(self):
        cases = [
            case(budget(), [(3, 1, 0, 3), (8, 8, 0, 3), (1, 4096, 0, 3), (5, 2, 0, 3)], status=OK),
            case(budget(memory=MAX), [(1, 1, 0, 3), (1, 2 ** 20, 0, 3), (1, 2 ** 40, 0, 3)], status=OK,
                 arena_size=2 ** 40 + 1, arena_alignment=2 ** 40),
            case(budget(memory=MAX), [(1, 1, 0, 3), (1, 2 ** 63, 0, 3)], status=OK, arena_size=2 ** 63 + 1),
            case(budget(memory=MAX), [(1, 2 ** 63, 0, 3), (2 ** 63, 2 ** 63, 0, 3)], status=BUDGET),
        ]
        self.assertEqual(cases[0]['placements'], [(0, 3), (8, 16), (4096, 4097), (16, 21)])
        self.run_both(cases, 'align')
        self.records.append(dict(test='alignment-power-of-two', cases=len(cases), modes=2, passed=True))

    def test_exact_budget_and_one_byte_over(self):
        need = case(budget(resident=411736), PIPELINE)['result']['memory_required']
        cases = [
            case(budget(resident=411736, memory=need), PIPELINE, status=OK),
            case(budget(resident=411736, memory=need - 1), PIPELINE, status=BUDGET),
            case(budget(resident=411736, memory=0), PIPELINE, status=BUDGET),
            case(budget(resident=MAX - 100, memory=MAX), [(100, 1, 0, 0)], status=OK, memory_required=MAX),
            case(budget(resident=MAX - 99, memory=MAX), [(100, 1, 0, 0)], status=BUDGET),
        ]
        self.run_both(cases, 'budget')
        self.records.append(dict(test='exact-budget-one-byte-over', cases=len(cases), modes=2, passed=True,
                                 memory_required=need))

    def test_stack_budget_reported_separately(self):
        small = [(4096, 8, 0, 3)]
        cases = [
            case(budget(stack_required=16 * KIB), small, status=OK, stack_short=0),
            case(budget(stack_required=16 * KIB + 1), small, status=STACK),
            # Measured frontend need (~60 KiB) against the current 16 KiB guest stack.
            case(budget(stack_required=60 * KIB), small, status=STACK),
            case(budget(memory=4095, stack_required=60 * KIB), small, status=BUDGET),
            case(budget(stack_required=MAX, stack_limit=0), small, status=STACK),
        ]
        self.run_both(cases, 'stack')
        self.records.append(dict(test='stack-separate-16k', cases=len(cases), modes=2, passed=True))

    def test_overflow_saturation(self):
        half = 2 ** 63
        cases = [
            # Disjoint lifetimes: the sum wraps but the arena reuses one range.
            case(budget(memory=MAX), [(half, 1, 0, 0), (half, 1, 1, 1)], status=OK,
                 sum_regions=MAX, overflow=OVERFLOW_SUM, arena_size=half),
            # Coexisting: placement end exceeds usize.
            case(budget(memory=MAX), [(half, 1, 0, 1), (half, 1, 1, 1)], status=BUDGET),
            case(budget(memory=MAX), [(MAX, 1, 0, 0)], status=OK, arena_size=MAX),
            # 1 + (MAX-1) is exactly MAX: the sum fits, the aligned placement does not.
            case(budget(memory=MAX), [(1, 2, 0, 0), (MAX - 1, 2, 0, 0)], status=BUDGET),
            case(budget(memory=MAX), [(1, 1, 0, 0), (MAX, 1, 0, 0)], status=BUDGET),
        ]
        self.run_both(cases, 'overflow')
        self.records.append(dict(test='overflow-saturation', cases=len(cases), modes=2, passed=True))

    def test_peak_versus_sum(self):
        regions = [(30, 1, 0, 1), (50, 1, 1, 2), (20, 1, 3, 3), (50, 1, 2, 3)]
        cases = [
            case(budget(), regions, status=OK, peak_live=100, peak_phase=2, sum_regions=150),
            case(budget(), [(10, 1, 0, 0), (10, 1, 2, 2)], status=OK, peak_live=10, peak_phase=0),
        ]
        self.run_both(cases, 'peak')
        self.records.append(dict(test='peak-vs-sum', cases=len(cases), modes=2, passed=True))

    def test_invalid_contents_precede_capacity(self):
        ok = [(8, 8, 0, 1)]
        cases = [
            case(budget(phases=0), ok, status=INVALID),
            case(budget(phases=65), ok, status=INVALID),
            case(budget(), [(8, 0, 0, 1)], status=INVALID),
            case(budget(), [(8, 3, 0, 1)], status=INVALID),
            case(budget(), [(8, 2 ** 63 + 1, 0, 1)], status=INVALID),
            case(budget(), [(8, 8, 0, 4)], status=INVALID),
            case(budget(), [(8, 8, 2, 1)], status=INVALID),
            case(budget(), [(8, 8, MAX, MAX)], status=INVALID),
            case(budget(), [(8, 8, 0, 0)] * 65, status=INVALID),
            case(budget(), ok + [(8, 3, 0, 1)], out_len=0, status=INVALID),
            case(budget(phases=0), ok, out_len=0, status=INVALID),
        ]
        self.run_both(cases, 'invalid')
        self.records.append(dict(test='invalid-contents-before-capacity', cases=len(cases), modes=2, passed=True))

    def test_capacity_and_out_tail(self):
        regions = [(8, 8, 0, 3), (8, 8, 1, 2), (8, 8, 3, 3)]
        cases = [
            case(budget(), regions, out_len=2, status=CAPACITY),
            case(budget(), regions, out_len=0, status=CAPACITY),
            case(budget(), regions, out_len=3, status=OK),
            case(budget(), regions, out_len=7, status=OK),
            # Capacity is reported before budget: nothing is written at all.
            case(budget(memory=0), regions, out_len=1, status=CAPACITY),
        ]
        self.run_both(cases, 'capacity')
        self.records.append(dict(test='capacity-out-tail', cases=len(cases), modes=2, passed=True))

    def test_maximum_and_determinism(self):
        regions = [((i * 37) % 200, 1 << (i % 13), i % 64, min(63, i % 64 + i % 5)) for i in range(64)]
        c = case(budget(phases=64, memory=MAX), regions, status=OK)
        cases = [c, c, case(budget(phases=64, memory=MAX), regions, out_len=64, readonly=1, status=OK)]
        self.run_both(cases, 'maximum')
        self.records.append(dict(test='max-64-deterministic', cases=len(cases), modes=2, passed=True))

    def test_readonly_inputs(self):
        cases = [
            case(budget(resident=411736), PIPELINE, readonly=1, status=OK),
            case(budget(memory=0), PIPELINE, readonly=1, status=BUDGET),
            case(budget(phases=0), PIPELINE, readonly=1, status=INVALID),
            case(budget(stack_required=60 * KIB), [], readonly=1, status=STACK),
        ]
        self.run_both(cases, 'readonly')
        self.records.append(dict(test='readonly-inputs', cases=len(cases), modes=2, passed=True))

    def bad_build(self, name, old, new):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertEqual(source.count(old), 1, name)
        root = self.work / name
        (root / 'bootstrap').mkdir(parents=True)
        (root / 'bootstrap/guest_compile_memory.dg').write_text(source.replace(old, new, 1), encoding='utf-8')
        return {mode: self.build([root, self.wrapper], mode, name + '-' + mode) for mode in ('debug', 'release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls = [
            # Treats every pair as non-coexisting: the backend is placed over the
            # still-live graph.
            ('bad-reuse-live-graph',
             ' return regions[i].first_phase<=regions[j].last_phase&&regions[j].first_phase<=regions[i].last_phase;\n',
             ' return false;\n',
             [case(budget(resident=411736), PIPELINE, status=OK)], 'placement'),
            # Off by one: a plan that needs exactly the budget is rejected.
            ('bad-exact-budget', 'memory>b.memory_budget', 'memory>=b.memory_budget',
             [case(budget(memory=64), [(64, 8, 0, 0)], status=OK)], 'status'),
            # Ignores alignment: starts at the first free byte.
            ('bad-ignore-alignment', '  let start=(candidate+(r.alignment-1))&mask;\n', '  let start=candidate;\n',
             [case(budget(), [(3, 1, 0, 3), (8, 8, 0, 3)], status=OK)], 'placement'),
            # Publishes placements before the budget decision.
            ('bad-early-publish', ' var status:u64=OK;\n',
             ' i=0;while i<regions.len{out[i]=Placement{offset:offsets[i],end:offsets[i]}; i+=1;}\n var status:u64=OK;\n',
             [case(budget(memory=63), [(64, 8, 0, 0)], status=BUDGET)], 'guard/atomicity'),
            # Publishes a Result before returning BUDGET/STACK (the review finding).
            ('bad-result-on-failure', ' if status!=OK{return status;}\n *result=Result{',
             ' *result=Result{status:0,arena_size:1,arena_alignment:1,peak_live:0,peak_phase:0,sum_regions:0,memory_required:0,stack_short:0,overflow:0};\n if status!=OK{return status;}\n *result=Result{',
             [case(budget(memory=0), [(1, 1, 0, 0)], status=BUDGET),
              case(budget(stack_required=60 * KIB), [(8, 8, 0, 0)], status=STACK)], 'guard/atomicity'),
            # Never reports the stack shortfall.
            ('bad-ignore-stack', ' else if short!=0{status=STACK;}\n', '\n',
             [case(budget(stack_required=60 * KIB), [(8, 8, 0, 0)], status=STACK)], 'status'),
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
