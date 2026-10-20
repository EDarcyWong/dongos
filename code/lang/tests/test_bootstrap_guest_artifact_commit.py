"""Actual Dong artifact-commit state machine, against an independent Python model.

The production module is compiled twice (debug/release) and driven through a
native C harness that supplies the write_at/flush callbacks, records the exact
callback event stream, and checks the 64-byte State after every step. The model
below is an independent re-implementation of the documented contract; each
case also carries explicit expectations for its terminal status/state so the
model itself cannot silently share a defect with the module.

The same harness also contains two in-process suites that link the delivered
objects directly: `preflight` (structural descriptors) and `inconsistent` (the
State-consistency invariants, i.e. a forged PENDING_FLUSH must never reach
flush() and never report DURABLE). The inconsistency suite is a permanent
regression for the GUEST5-R1 rework and is itself sensitive: removing the
`state_consistent` preflight from the module makes it fail.
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

SOURCE = ROOT / 'lang/bootstrap/guest_artifact_commit.dg'
DOC = SOURCE.with_suffix('.md')

# step/run return values
COMMIT_STEP, COMMIT_INVALID, COMMIT_FAILED, COMMIT_DONE = 0, 1, 2, 3
# State.status
IDLE, WRITING, PENDING_FLUSH, DURABLE, FAILED = 0, 1, 2, 3, 4
# State.stage
STAGE_NONE, STAGE_WRITE, STAGE_FLUSH = 0, 1, 2
# internal State.code values
E_NONE, E_NO_PROGRESS, E_PROTOCOL, E_INTERNAL = 0, 1, 2, 3
MAX_STALL = 8
MASK64 = (1 << 64) - 1
PREFLIGHTS = 20
CONSISTENCY_CHECKS = 157
DEFAULT_HANDLE = 0x5A5A0000_00000007

WRAPPER = '''module probe.commit_export;
import bootstrap.guest_artifact_commit as c;
export("dong_guest_artifact_commit_init") pub unsafe fn init(st:*c.State,total:u64)u64{unsafe{
 return c.init(st,total);
}}
export("dong_guest_artifact_commit_step") pub unsafe fn step(st:*c.State,h:u64,p:*const u8,n:usize,w:c.WriteAt,f:c.Flush)u64{unsafe{
 return c.step(st,h,slice_from_raw_parts(p,n),w,f);
}}
export("dong_guest_artifact_commit_run") pub unsafe fn run(st:*c.State,h:u64,p:*const u8,n:usize,w:c.WriteAt,f:c.Flush)u64{unsafe{
 return c.run(st,h,slice_from_raw_parts(p,n),w,f);
}}
'''

HARNESS = r'''
#include <stdint.h>
#include <stddef.h>
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
typedef struct { uint64_t status,stage,code,written,total,attempts,stalls,flushes; } State;
_Static_assert(sizeof(State)==64,"State must be exactly 64 bytes");
typedef int64_t (ABI *write_at)(uint64_t,uint64_t,const uint8_t*,uint64_t);
typedef int64_t (ABI *flush_t)(uint64_t);
extern uint64_t ABI dong_guest_artifact_commit_init(State*,uint64_t);
extern uint64_t ABI dong_guest_artifact_commit_step(State*,uint64_t,const uint8_t*,uint64_t,write_at,flush_t);
extern uint64_t ABI dong_guest_artifact_commit_run(State*,uint64_t,const uint8_t*,uint64_t,write_at,flush_t);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}

#define MAXEV 512
typedef struct { uint64_t kind,handle,off,len; int64_t result; uint64_t data_ok; } Event;
static Event events[MAXEV]; static uint64_t nev,overflowed;
static const int64_t *wscript; static uint64_t wcount,widx;
static const int64_t *fscript; static uint64_t fcount,fidx;
static const uint8_t *gsrc; static uint64_t gsrc_len;
static State snaps[512]; static uint64_t rets[512];

static int64_t ABI cb_write(uint64_t h,uint64_t off,const uint8_t*d,uint64_t n){
 int64_t v;
 if(widx<wcount){v=wscript[widx++];}else{v=INT64_MAX;}
 if(v==INT64_MAX){v=(int64_t)n;}
 uint64_t ok=(off<=gsrc_len&&n<=gsrc_len-off&&(n==0||d!=NULL))?1:0;
 if(ok&&n){ok=memcmp(d,gsrc+off,(size_t)n)==0;}
 if(nev<MAXEV){events[nev++]=(Event){1,h,off,n,v,ok};}else{overflowed=1;}
 return v;
}
static int64_t ABI cb_flush(uint64_t h){
 int64_t v=(fidx<fcount)?fscript[fidx++]:0;
 if(nev<MAXEV){events[nev++]=(Event){2,h,0,0,v,1};}else{overflowed=1;}
 return v;
}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,(size_t)n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,(size_t)n,stdout)!=n)exit(92);}
#ifdef _WIN32
static uint8_t*ro_alloc(uint64_t n){
 return (uint8_t*)VirtualAlloc(NULL,(SIZE_T)n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
}
static void ro_protect(void*p,uint64_t n){
 DWORD old;if(!VirtualProtect(p,(SIZE_T)n,PAGE_READONLY,&old))exit(98);
}
static void ro_free(void*p,uint64_t n){(void)n;if(!VirtualFree(p,0,MEM_RELEASE))exit(98);}
#else
static uint8_t*ro_alloc(uint64_t n){
 void*p=mmap(NULL,(size_t)n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 return p==MAP_FAILED?NULL:(uint8_t*)p;
}
static void ro_protect(void*p,uint64_t n){if(mprotect(p,(size_t)n,PROT_READ))exit(98);}
static void ro_free(void*p,uint64_t n){if(munmap(p,(size_t)n))exit(98);}
#endif

static uint64_t preflight(void){
 static _Alignas(64) uint8_t arena[1024];
 static _Alignas(64) uint8_t src[64];
 uint64_t n=0;
 uint8_t before[64];
 State *st=(State*)(arena+64);
 memset(arena,0xa5,sizeof(arena));
 memset(src,0x5c,sizeof(src));
 nev=0;overflowed=0;wcount=widx=0;fcount=fidx=0;gsrc=src;gsrc_len=64;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"preflight %llu failed\n",(unsigned long long)n);exit(80);}n++;}while(0)
 CHECK(dong_guest_artifact_commit_init(NULL,0)==1);
 CHECK(dong_guest_artifact_commit_init((State*)(arena+65),0)==1);
 CHECK(dong_guest_artifact_commit_init((State*)(uintptr_t)(UINT64_MAX-7),0)==1);
 CHECK(dong_guest_artifact_commit_run(NULL,7,src,4,cb_write,cb_flush)==1);
 CHECK(dong_guest_artifact_commit_step(NULL,7,src,4,cb_write,cb_flush)==1);
 CHECK(dong_guest_artifact_commit_init(st,4)==0);
 memcpy(before,st,64);
 CHECK(dong_guest_artifact_commit_step((State*)(arena+65),7,src,4,cb_write,cb_flush)==1);
 CHECK(dong_guest_artifact_commit_step(st,7,NULL,4,cb_write,cb_flush)==1&&memcmp(before,st,64)==0);
 CHECK(dong_guest_artifact_commit_step(st,7,(const uint8_t*)(uintptr_t)(UINT64_MAX-1),4,cb_write,cb_flush)==1&&memcmp(before,st,64)==0);
 CHECK(dong_guest_artifact_commit_step(st,7,(const uint8_t*)st,4,cb_write,cb_flush)==1&&memcmp(before,st,64)==0);
 CHECK(dong_guest_artifact_commit_step(st,7,src,5,cb_write,cb_flush)==1&&memcmp(before,st,64)==0);
 st->status=99;memcpy(before,st,64);
 CHECK(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush)==1&&memcmp(before,st,64)==0);
 CHECK(dong_guest_artifact_commit_init(st,4)==0);
 st->written=5;memcpy(before,st,64);
 CHECK(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush)==1&&memcmp(before,st,64)==0);
 CHECK(dong_guest_artifact_commit_init(st,4)==0);
 st->status=4;st->stage=1;st->code=1;memcpy(before,st,64);
 CHECK(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush)==2&&memcmp(before,st,64)==0);
 st->status=3;st->stage=0;st->code=0;st->written=4;st->flushes=1;st->attempts=4;memcpy(before,st,64);
 CHECK(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush)==3&&memcmp(before,st,64)==0);
 CHECK(dong_guest_artifact_commit_init(st,4)==0);
 memcpy(before,st,64);
 CHECK(dong_guest_artifact_commit_run(st,7,src,5,cb_write,cb_flush)==1&&memcmp(before,st,64)==0);
 CHECK(nev==0&&overflowed==0);
#undef CHECK
 return n;
}

/* Permanent regression for State-consistency rejection: a forged or corrupted
   State must never buy a FLUSH - or a DURABLE report - for bytes that were never
   written. Each rejected case must return COMMIT_INVALID with a byte-identical
   State and zero callbacks; the positive controls prove the same preflight still
   accepts every legitimately reachable State. */
static uint64_t inconsistent(void){
 static _Alignas(64) uint8_t arena[256];
 static uint8_t src[8]={1,2,3,4,5,6,7,8};
 uint8_t before[64];
 uint64_t n=0,r;
 State *st=(State*)(arena+64);
#define ICHECK(x) do{if(!(x)){fprintf(stderr,"inconsistent %llu failed\n",(unsigned long long)n);exit(80);}n++;}while(0)
#define ISETUP(t) do{memset(arena,0xa5,sizeof(arena));nev=0;overflowed=0;wcount=widx=0;fcount=fidx=0;gsrc=src;gsrc_len=(t);\
 ICHECK(dong_guest_artifact_commit_init(st,(t))==0);}while(0)
#define IREJECT(call) do{memcpy(before,st,64);ICHECK((call)==1);ICHECK(memcmp(before,st,64)==0);ICHECK(nev==0);}while(0)
#define IHOLD(call) do{memcpy(before,st,64);ICHECK((call)==2);ICHECK(memcmp(before,st,64)==0);ICHECK(nev==0);}while(0)
#define IDONE(call) do{memcpy(before,st,64);ICHECK((call)==3);ICHECK(memcmp(before,st,64)==0);ICHECK(nev==0);}while(0)
 /* The reported defect: PENDING_FLUSH while 0 of 4 artifact bytes are written. */
 ISETUP(4);st->status=2;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 IREJECT(dong_guest_artifact_commit_run(st,7,src,4,cb_write,cb_flush));
 /* PENDING_FLUSH: partial, over-length, already flushed, failed metadata. */
 ISETUP(4);st->status=2;st->written=3;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=2;st->written=5;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=2;st->written=4;st->flushes=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=2;st->written=4;st->stage=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=2;st->written=4;st->stalls=8;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 /* IDLE carries no progress, no callback and no failure metadata. */
 ISETUP(4);st->written=2;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->attempts=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->flushes=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->stage=2;st->code=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 /* WRITING must still have bytes left, no FLUSH yet, live stall budget. */
 ISETUP(4);st->status=1;st->written=4;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=1;st->flushes=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=1;st->stalls=8;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=1;st->written=2;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=1;st->attempts=1;st->stalls=2;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(0);st->status=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,0,cb_write,cb_flush));
 ISETUP(4);st->status=5;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 /* Terminal states are validated too: no endorsement of corrupted results. */
 ISETUP(4);st->status=3;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=3;st->written=4;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 /* Claiming confirmed bytes without a single write call is a forgery too. */
 ISETUP(4);st->status=2;st->written=4;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=3;st->written=4;st->flushes=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=4;st->code=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=4;st->stage=2;st->code=1;st->flushes=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=4;st->stage=1;st->code=0;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=4;st->stage=1;st->code=1;st->flushes=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 /* Positive controls: every state the module itself publishes is accepted. */
 ISETUP(4);st->status=2;st->written=4;st->attempts=4;
 ICHECK(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush)==3);
 ICHECK(st->status==3&&st->flushes==1&&nev==1);
 ISETUP(0);st->status=2;
 ICHECK(dong_guest_artifact_commit_step(st,7,src,0,cb_write,cb_flush)==3);
 ICHECK(st->status==3&&st->flushes==1&&nev==1);
 ISETUP(4);st->status=3;st->written=4;st->flushes=1;st->attempts=4;
 IDONE(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=4;st->stage=1;st->code=1;st->stalls=8;st->attempts=8;
 IHOLD(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=4;st->stage=2;st->written=4;st->flushes=1;st->attempts=4;st->code=(uint64_t)-5;
 IHOLD(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 /* Partial progress is still accepted, with the exact offset/length. */
 ISETUP(4);st->status=1;st->written=2;st->attempts=1;
 r=dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush);
 ICHECK(r==0&&st->written==4&&st->status==2&&nev==1);
 ICHECK(events[0].off==2&&events[0].len==2&&events[0].result==2&&events[0].data_ok==1);
 /* R2 counters: test the non-overflow forged case first so a mutant is
    rejected by a value assertion, never by a debug arithmetic trap. */
 ISETUP(4);st->status=1;st->attempts=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=1;st->attempts=UINT64_MAX;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=1;st->written=2;st->attempts=5;st->stalls=1;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=2;st->written=4;st->attempts=5;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=3;st->written=4;st->flushes=1;st->attempts=UINT64_MAX;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=4;st->stage=2;st->code=(uint64_t)-5;st->written=4;st->flushes=1;st->attempts=UINT64_MAX;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 ISETUP(4);st->status=4;st->stage=1;st->code=(uint64_t)-5;st->attempts=2;
 IREJECT(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush));
 /* Exact maximum successful-attempt count: w positive bytes plus k stalls.
    The state produced by step must itself be usable by the next run. */
 ISETUP(4);st->status=1;st->written=2;st->attempts=5;st->stalls=3;
 ICHECK(dong_guest_artifact_commit_step(st,7,src,4,cb_write,cb_flush)==0);
 ICHECK(st->written==4&&st->attempts==6&&st->status==2);
 ICHECK(dong_guest_artifact_commit_run(st,7,src,4,cb_write,cb_flush)==3);
 ICHECK(st->status==3&&st->flushes==1&&nev==2);
#undef ICHECK
#undef ISETUP
#undef IREJECT
#undef IHOLD
#undef IDONE
 return n;
}

int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t mask,count,pre=0,inc=0;read_exact(&mask,8);
 if(mask&1)pre=preflight();
 if(mask&2)inc=inconsistent();
 read_exact(&count,8);write_exact(&pre,8);write_exact(&inc,8);
 while(count--){
  uint64_t total,handle,src_len,flags,max_steps,wc,fc,dlen;
  read_exact(&total,8);read_exact(&handle,8);read_exact(&src_len,8);
  read_exact(&flags,8);read_exact(&max_steps,8);read_exact(&wc,8);
  if(wc>4096)exit(94);
  int64_t *ws=wc?(int64_t*)malloc((size_t)wc*8):NULL;if(wc&&!ws)exit(95);
  if(wc)read_exact(ws,wc*8);
  read_exact(&fc,8);if(fc>4096)exit(94);
  int64_t *fs=fc?(int64_t*)malloc((size_t)fc*8):NULL;if(fc&&!fs)exit(95);
  if(fc)read_exact(fs,fc*8);
  read_exact(&dlen,8);if(dlen>src_len||src_len>1000000||dlen>1000000)exit(94);
  uint8_t *expected=(uint8_t*)malloc(src_len?(size_t)src_len:1);
  uint8_t *buf=(uint8_t*)malloc((size_t)src_len+64);
  if(!expected||!buf)exit(95);
  memset(expected,0xcc,src_len?(size_t)src_len:1);
  if(dlen)read_exact(expected,(size_t)dlen);
  memset(buf,0xa5,(size_t)src_len+64);
  memcpy(buf+32,expected,(size_t)src_len);
  const uint8_t *srcp=buf+32;uint8_t*page=NULL;uint64_t pages=0;
  if((flags&1)&&src_len){
   pages=((src_len+4095)/4096)*4096;page=ro_alloc(pages);if(!page)exit(95);
   memcpy(page,expected,(size_t)src_len);ro_protect(page,pages);srcp=page;
  }
  static _Alignas(64) uint8_t sbuf[128];
  memset(sbuf,0xa5,sizeof(sbuf));
  State *st=(State*)(sbuf+32);
  gsrc=srcp;gsrc_len=src_len;wscript=ws;wcount=wc;widx=0;
  fscript=fs;fcount=fc;fidx=0;nev=0;overflowed=0;
  uint64_t init_ret=dong_guest_artifact_commit_init(st,total);
  State after_init=*st;
  uint64_t ret=0,steps=0;
  if((flags&2)==0){
   ret=dong_guest_artifact_commit_run(st,handle,srcp,src_len,cb_write,cb_flush);
  }else{
   uint64_t cap=max_steps?max_steps:512;
   if(cap>512)cap=512;
   while(steps<cap){
    ret=dong_guest_artifact_commit_step(st,handle,srcp,src_len,cb_write,cb_flush);
    snaps[steps]=*st;rets[steps]=ret;steps++;
   }
  }
  State final_state=*st;
  uint64_t guard=(overflowed==0);
  for(uint64_t i=0;i<32;i++)if(sbuf[i]!=0xa5||sbuf[32+64+i]!=0xa5)guard=0;
  if(!(flags&1)){
   for(uint64_t i=0;i<32;i++)if(buf[i]!=0xa5||buf[32+src_len+i]!=0xa5)guard=0;
  }
  if(src_len&&memcmp(srcp,expected,(size_t)src_len))guard=0;
  write_exact(&init_ret,8);write_exact(&ret,8);write_exact(&steps,8);
  write_exact(&nev,8);write_exact(&guard,8);
  write_exact(&final_state,64);write_exact(&after_init,64);
  for(uint64_t i=0;i<steps;i++){
   write_exact(&rets[i],8);write_exact(&snaps[i],64);
  }
  for(uint64_t i=0;i<nev;i++){
   write_exact(&events[i],sizeof(Event));
  }
  if(page)ro_free(page,pages);
  free(ws);free(fs);free(expected);free(buf);
 }
 return 0;
}
'''


def flatten(state):
    return tuple(state)


def make_case(total, writes=(), flushes=(), handle=DEFAULT_HANDLE, mode='run',
              max_steps=0, readonly=0, data=None, src_len=None, check=None):
    if data is None:
        data = bytes(((i * 37 + 11) & 0xFF) for i in range(total if src_len is None else src_len))
    elif isinstance(data, str):
        data = data.encode('utf-8')
    else:
        data = bytes(data)
    if src_len is None:
        src_len = total
    flags = (1 if readonly else 0) | (2 if mode == 'step' else 0)
    return dict(total=total, handle=handle, src_len=src_len, flags=flags,
                max_steps=max_steps, writes=list(writes), flushes=list(flushes),
                data=data, check=check or {})


def simulate(case):
    """Independent model of the documented protocol."""
    total, handle = case['total'], case['handle']
    status, stage, code = IDLE, STAGE_NONE, E_NONE
    written = attempts = stalls = flushes = 0
    events = []
    wis = list(case['writes'])
    wi = fi = 0

    def snapshot():
        return (status, stage, code, written, total, attempts, stalls, flushes)

    init_state = snapshot()

    def do_step():
        nonlocal status, stage, code, written, attempts, stalls, flushes, wi, fi
        if status == DURABLE:
            return COMMIT_DONE
        if status == FAILED:
            return COMMIT_FAILED
        if case['src_len'] != total:
            return COMMIT_INVALID
        if status == IDLE:
            status = PENDING_FLUSH if total == 0 else WRITING
            return COMMIT_STEP
        if status == WRITING:
            off = written
            remaining = total - off
            attempts += 1
            if wi < len(wis):
                value = wis[wi]
                wi += 1
            else:
                value = remaining
            events.append((1, handle, off, remaining, value, 1))
            if value < 0:
                status, stage, code = FAILED, STAGE_WRITE, value & MASK64
                return COMMIT_FAILED
            if value > remaining:
                status, stage, code = FAILED, STAGE_WRITE, E_PROTOCOL
                return COMMIT_FAILED
            if value == 0:
                stalls += 1
                if stalls >= MAX_STALL:
                    status, stage, code = FAILED, STAGE_WRITE, E_NO_PROGRESS
                    return COMMIT_FAILED
                return COMMIT_STEP
            written = off + value
            if written == total:
                status = PENDING_FLUSH
            return COMMIT_STEP
        if status == PENDING_FLUSH:
            flushes += 1
            value = case['flushes'][fi] if fi < len(case['flushes']) else 0
            fi += 1
            events.append((2, handle, 0, 0, value, 1))
            if value < 0:
                status, stage, code = FAILED, STAGE_FLUSH, value & MASK64
                return COMMIT_FAILED
            if value > 0:
                status, stage, code = FAILED, STAGE_FLUSH, E_PROTOCOL
                return COMMIT_FAILED
            status = DURABLE
            return COMMIT_DONE
        raise AssertionError('model entered impossible status %r' % (status,))

    steps = []
    if case['flags'] & 2:
        cap = min(case['max_steps'] or 512, 512)
        for _ in range(cap):
            ret = do_step()
            steps.append((ret, snapshot()))
        ret = steps[-1][0] if steps else COMMIT_STEP
    else:
        ret = do_step()
        cap = MASK64 if total > MASK64 - 16 else total + 16
        count = 0
        while ret == COMMIT_STEP and count < cap:
            ret = do_step()
            count += 1
        if ret == COMMIT_STEP:
            status, stage, code = FAILED, STAGE_WRITE, E_INTERNAL
            ret = COMMIT_FAILED
    return dict(init=init_state, final=snapshot(), ret=ret, steps=steps, events=events)


class GuestArtifactCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native artifact-commit probe requires NASM/GCC')
        cls.work = ROOT / 'build/test/guest-integration/GUEST5' / ('run-' + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        (cls.work / 'probe.c').write_text(HARNESS, encoding='utf-8')
        cls.inputs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [SOURCE, DOC, Path(__file__)]}
        cls.src = cls.work / 'src'
        (cls.src / 'bootstrap').mkdir(parents=True)
        (cls.src / 'bootstrap/guest_artifact_commit.dg').write_bytes(SOURCE.read_bytes())
        cls.wrapper = cls.work / 'wrapper'
        (cls.wrapper / 'probe').mkdir(parents=True)
        (cls.wrapper / 'probe/commit_export.dg').write_text(WRAPPER, encoding='utf-8')
        cls.records = []
        cls.executables = {}
        for mode in ('debug', 'release'):
            cls.executables[mode] = cls.build([cls.src, cls.wrapper], cls.wrapper, mode, mode)

    @classmethod
    def command(cls, cmd, name, timeout=180):
        r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=timeout)
        (cls.work / (name + '.log')).write_text(r.stdout + r.stderr, encoding='utf-8')
        if r.returncode:
            raise AssertionError((name, r.returncode, r.stdout, r.stderr))

    @classmethod
    def build(cls, roots, wrapper, mode, name):
        compiled = compile_file(wrapper / 'probe/commit_export.dg', roots=roots, mode=mode)
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
        current = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in [SOURCE, DOC, Path(__file__)]}
        assert cls.inputs == current, 'inputs changed during the run'
        files = {p.relative_to(cls.work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in cls.work.rglob('*') if p.is_file()}
        (cls.work / 'summary.json').write_text(json.dumps(dict(
            source_sha256=cls.inputs, artifact_sha256=files, records=cls.records,
            groups=len(cls.records), integrated=False, OS_VM_built=False), indent=2) + '\n')

    def expected(self, case):
        model = simulate(case)
        for key, value in case['check'].items():
            if key == 'events':
                self.assertEqual(model['events'], [tuple(e) for e in value],
                                 ('case-contract', key))
            elif key == 'ret':
                self.assertEqual(model['ret'], value, ('case-contract', key))
            elif key == 'status':
                self.assertEqual(model['final'][0], value, ('case-contract', key))
            else:
                names = ('status', 'stage', 'code', 'written', 'total',
                         'attempts', 'stalls', 'flushes')
                self.assertEqual(model['final'][names.index(key)], value,
                                 ('case-contract', key))
        return model

    def run_cases(self, exe, cases, label, preflight=True, consistency=True):
        expected = [self.expected(c) for c in cases]
        mask = (1 if preflight else 0) | (2 if consistency else 0)
        payload = bytearray(struct.pack('<2Q', mask, len(cases)))
        for c in cases:
            payload.extend(struct.pack('<6Q', c['total'], c['handle'], c['src_len'],
                                       c['flags'], c['max_steps'], len(c['writes'])))
            for value in c['writes']:
                payload.extend(struct.pack('<q', value))
            payload.extend(struct.pack('<Q', len(c['flushes'])))
            for value in c['flushes']:
                payload.extend(struct.pack('<q', value))
            payload.extend(struct.pack('<Q', len(c['data'])))
            payload.extend(c['data'])
        (self.work / (label + '.input')).write_bytes(payload)
        run = subprocess.run([str(exe)], input=bytes(payload), capture_output=True, timeout=180)
        (self.work / (label + '.output')).write_bytes(run.stdout)
        (self.work / (label + '.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode, 0, (label, 'crash', run.stderr[-2000:]))
        data = run.stdout
        preflights, inconsistent_checks = struct.unpack_from('<2Q', data, 0)
        self.assertEqual(preflights, PREFLIGHTS if preflight else 0, (label, 'preflights'))
        self.assertEqual(inconsistent_checks, CONSISTENCY_CHECKS if consistency else 0,
                         (label, 'inconsistent-state-checks'))
        offset = 16
        for index, (case, want) in enumerate(zip(cases, expected)):
            init_ret, ret, steps, nev, guard = struct.unpack_from('<5Q', data, offset)
            offset += 40
            final = struct.unpack_from('<8Q', data, offset)
            offset += 64
            init_state = struct.unpack_from('<8Q', data, offset)
            offset += 64
            self.assertEqual(init_ret, COMMIT_STEP, (label, index, 'init'))
            self.assertEqual(init_state, want['init'], (label, index, 'init-state'))
            self.assertEqual(ret, want['ret'], (label, index, 'ret'))
            self.assertEqual(steps, len(want['steps']), (label, index, 'steps'))
            seen = []
            for step in range(steps):
                status, = struct.unpack_from('<Q', data, offset)
                state = struct.unpack_from('<8Q', data, offset + 8)
                offset += 72
                seen.append((status, state))
            if case['flags'] & 2:
                self.assertEqual(seen, want['steps'], (label, index, 'step-states'))
            self.assertEqual(final, want['final'], (label, index, 'state'))
            events = []
            for _ in range(nev):
                kind, handle, off, length, result, data_ok = struct.unpack_from('<QQQQqQ', data, offset)
                offset += 48
                events.append((kind, handle, off, length, result, data_ok))
            self.assertEqual(events, want['events'], (label, index, 'events'))
            self.assertEqual(guard, 1, (label, index, 'guard'))
        self.assertEqual(offset, len(data), (label, 'trailing-output'))
        self.records.append(dict(label=label, cases=len(cases), preflights=preflights,
                                 inconsistent_state_checks=inconsistent_checks,
                                 modes=1, passed=True))

    def run_both(self, cases, label, preflight=True, consistency=True):
        for mode, exe in self.executables.items():
            self.run_cases(exe, cases, label + '-' + mode, preflight, consistency)

    # ---------------------------------------------------------------- vectors

    def test_full_and_short_writes(self):
        cases = [
            make_case(10, check=dict(status=DURABLE, ret=COMMIT_DONE, written=10,
                                     attempts=1, stalls=0, flushes=1,
                                     events=[(1, DEFAULT_HANDLE, 0, 10, 10, 1),
                                             (2, DEFAULT_HANDLE, 0, 0, 0, 1)])),
            make_case(11, writes=[3, 0, 5], check=dict(
                status=DURABLE, ret=COMMIT_DONE, written=11, attempts=4,
                stalls=1, flushes=1,
                events=[(1, DEFAULT_HANDLE, 0, 11, 3, 1),
                        (1, DEFAULT_HANDLE, 3, 8, 0, 1),
                        (1, DEFAULT_HANDLE, 3, 8, 5, 1),
                        (1, DEFAULT_HANDLE, 8, 3, 3, 1),
                        (2, DEFAULT_HANDLE, 0, 0, 0, 1)])),
            make_case(1, check=dict(status=DURABLE, written=1, attempts=1, flushes=1)),
            make_case(33, writes=[1], check=dict(status=DURABLE, written=33, attempts=2)),
        ]
        self.run_both(cases, 'writes')
        self.records.append(dict(test='full-short-writes', cases=len(cases), modes=2, passed=True))

    def test_zero_progress_bounded_retry(self):
        cases = [
            make_case(5, writes=[0] * 7, check=dict(
                status=DURABLE, written=5, attempts=8, stalls=7, flushes=1)),
            make_case(5, writes=[0] * MAX_STALL, check=dict(
                status=FAILED, ret=COMMIT_FAILED, stage=STAGE_WRITE,
                code=E_NO_PROGRESS, written=0, attempts=MAX_STALL,
                stalls=MAX_STALL, flushes=0)),
            make_case(2, writes=[0, 0, 1], check=dict(
                status=DURABLE, written=2, attempts=4, stalls=2)),
        ]
        self.run_both(cases, 'stall')
        self.records.append(dict(test='zero-progress-bounded', cases=len(cases), modes=2, passed=True))

    def test_write_errors_are_terminal(self):
        cases = [
            make_case(8, writes=[3, -9], check=dict(
                status=FAILED, ret=COMMIT_FAILED, stage=STAGE_WRITE,
                code=(-9) & MASK64, written=3, attempts=2, flushes=0,
                events=[(1, DEFAULT_HANDLE, 0, 8, 3, 1),
                        (1, DEFAULT_HANDLE, 3, 5, -9, 1)])),
            make_case(4, writes=[-1], check=dict(
                status=FAILED, stage=STAGE_WRITE, code=MASK64, written=0,
                attempts=1, flushes=0)),
            make_case(6, writes=[2, -1, 2], check=dict(
                status=FAILED, written=2, attempts=2, flushes=0)),
        ]
        self.run_both(cases, 'werr')
        self.records.append(dict(test='write-errors-terminal', cases=len(cases), modes=2, passed=True))

    def test_overlong_and_protocol_results(self):
        cases = [
            make_case(4, writes=[5], check=dict(
                status=FAILED, stage=STAGE_WRITE, code=E_PROTOCOL,
                written=0, attempts=1, flushes=0)),
            make_case(4, writes=[3, 2], check=dict(
                status=FAILED, stage=STAGE_WRITE, code=E_PROTOCOL,
                written=3, attempts=2, flushes=0)),
            make_case(1, writes=[2], check=dict(status=FAILED, code=E_PROTOCOL, written=0)),
        ]
        self.run_both(cases, 'overlong')
        self.records.append(dict(test='overlong-protocol', cases=len(cases), modes=2, passed=True))

    def test_flush_failure_and_false_success(self):
        cases = [
            make_case(5, flushes=[-4], check=dict(
                status=FAILED, ret=COMMIT_FAILED, stage=STAGE_FLUSH,
                code=(-4) & MASK64, written=5, attempts=1, flushes=1,
                events=[(1, DEFAULT_HANDLE, 0, 5, 5, 1),
                        (2, DEFAULT_HANDLE, 0, 0, -4, 1)])),
            make_case(5, flushes=[1], check=dict(
                status=FAILED, stage=STAGE_FLUSH, code=E_PROTOCOL,
                written=5, flushes=1)),
            make_case(5, check=dict(status=DURABLE, written=5, flushes=1, attempts=1)),
        ]
        self.run_both(cases, 'flush')
        self.records.append(dict(test='flush-failure-success', cases=len(cases), modes=2, passed=True))

    def test_empty_artifact(self):
        cases = [
            make_case(0, data=b'', check=dict(
                status=DURABLE, ret=COMMIT_DONE, written=0, attempts=0,
                stalls=0, flushes=1,
                events=[(2, DEFAULT_HANDLE, 0, 0, 0, 1)])),
            make_case(0, data=b'', mode='step', max_steps=4, check=dict(
                status=DURABLE, ret=COMMIT_DONE, written=0, attempts=0, flushes=1)),
            make_case(0, data=b'', flushes=[-1], check=dict(
                status=FAILED, stage=STAGE_FLUSH, code=MASK64, written=0, flushes=1)),
        ]
        self.run_both(cases, 'empty')
        self.records.append(dict(test='empty-artifact', cases=len(cases), modes=2, passed=True))

    def test_step_observes_lifecycle(self):
        cases = [
            make_case(6, writes=[2, 2, 2], mode='step', max_steps=10, check=dict(
                status=DURABLE, ret=COMMIT_DONE, written=6, attempts=3, flushes=1)),
            make_case(3, writes=[-2], mode='step', max_steps=5, check=dict(
                status=FAILED, ret=COMMIT_FAILED, stage=STAGE_WRITE,
                code=(-2) & MASK64, written=0, attempts=1)),
            make_case(0, data=b'', mode='step', max_steps=1, check=dict(
                status=PENDING_FLUSH, attempts=0, flushes=0)),
        ]
        self.run_both(cases, 'lifecycle')
        # explicit step-by-step states for the short-write lifecycle
        want = [
            (COMMIT_STEP, (WRITING, STAGE_NONE, E_NONE, 0, 6, 0, 0, 0)),
            (COMMIT_STEP, (WRITING, STAGE_NONE, E_NONE, 2, 6, 1, 0, 0)),
            (COMMIT_STEP, (WRITING, STAGE_NONE, E_NONE, 4, 6, 2, 0, 0)),
            (COMMIT_STEP, (PENDING_FLUSH, STAGE_NONE, E_NONE, 6, 6, 3, 0, 0)),
            (COMMIT_DONE, (DURABLE, STAGE_NONE, E_NONE, 6, 6, 3, 0, 1)),
            (COMMIT_DONE, (DURABLE, STAGE_NONE, E_NONE, 6, 6, 3, 0, 1)),
        ]
        case = make_case(6, writes=[2, 2, 2], mode='step', max_steps=6)
        self.assertEqual(simulate(case)['steps'], want)
        for mode, exe in self.executables.items():
            self.run_cases(exe, [case], 'lifecycle-detail-' + mode, preflight=False)
        self.records.append(dict(test='step-lifecycle', cases=4, modes=2, passed=True))

    def test_terminal_states_issue_no_callbacks(self):
        failed = make_case(3, writes=[-1], mode='step', max_steps=5, check=dict(
            status=FAILED, ret=COMMIT_FAILED, attempts=1, written=0))
        done = make_case(2, mode='step', max_steps=4, check=dict(
            status=DURABLE, ret=COMMIT_DONE, attempts=1, flushes=1))
        self.run_both([failed, done], 'terminal')
        model = simulate(failed)
        self.assertEqual([r for r, _ in model['steps']][:3],
                         [COMMIT_STEP, COMMIT_FAILED, COMMIT_FAILED])
        self.assertEqual(len(model['events']), 1)
        model = simulate(done)
        self.assertEqual(len(model['events']), 2)
        self.assertEqual([r for r, _ in model['steps']][-2:], [COMMIT_DONE, COMMIT_DONE])
        self.records.append(dict(test='terminal-no-callbacks', cases=2, modes=2, passed=True))

    def test_descriptor_mismatch_rejected_before_callback(self):
        cases = [
            make_case(4, src_len=5, check=dict(status=IDLE, ret=COMMIT_INVALID,
                                               written=0, attempts=0, flushes=0,
                                               events=[])),
            make_case(4, src_len=3, check=dict(status=IDLE, ret=COMMIT_INVALID,
                                               events=[])),
            make_case(4, src_len=5, mode='step', max_steps=2, check=dict(
                status=IDLE, ret=COMMIT_INVALID, events=[])),
        ]
        self.run_both(cases, 'mismatch')
        self.records.append(dict(test='descriptor-mismatch', cases=len(cases), modes=2, passed=True))

    def test_structural_descriptor_preflights(self):
        # The preflight routine runs inside every payload; this batch simply
        # asserts the exact count in a dedicated label.
        self.run_both([make_case(4)], 'preflight-count')
        self.records.append(dict(test='descriptor-preflights', preflights=PREFLIGHTS,
                                 modes=2, passed=True))

    def test_forged_state_cannot_flush_or_report_durable(self):
        # The native suite behind mask bit 2 links the delivered debug/release
        # objects directly and hand-builds States: a PENDING_FLUSH whose bytes
        # were never written must not reach flush() and must not report DURABLE
        # (reported defect), and every other inconsistent combination must be
        # rejected with a byte-identical State and zero callbacks. The positive
        # controls in the same suite keep every reachable State accepted.
        self.run_both([make_case(4, writes=[4])], 'forged-state', preflight=False)
        self.records.append(dict(test='forged-state-rejected', checks=CONSISTENCY_CHECKS,
                                 modes=2, passed=True))

    def test_readonly_artifact_pages(self):
        cases = [
            make_case(9, writes=[4, 0, 5], readonly=1, check=dict(
                status=DURABLE, written=9, attempts=3, stalls=1)),
            make_case(0, data=b'', readonly=1, check=dict(status=DURABLE, flushes=1)),
            make_case(7, writes=[3, -2], readonly=1, check=dict(
                status=FAILED, written=3, attempts=2, flushes=0)),
        ]
        self.run_both(cases, 'readonly')
        self.records.append(dict(test='readonly-pages', cases=len(cases), modes=2, passed=True))

    def test_input_immutability_and_handles(self):
        data = bytes(range(97, 97 + 12))
        cases = [
            make_case(12, data=data, handle=0),
            make_case(12, data=data, handle=MASK64),
            make_case(12, data=data, writes=[1, 2, 3, 6], handle=0x1234),
            make_case(12, data=data, readonly=1, handle=0x1234),
            make_case(12, data=data, writes=[0, 12], handle=7),
        ]
        self.run_both(cases, 'immutable')
        self.records.append(dict(test='input-immutable-handles', cases=len(cases), modes=2, passed=True))

    def test_artifact_content_splits(self):
        # Different split points must pass byte-exact slices; the C oracle
        # compares every write_at payload with the artifact at that offset.
        cases = [
            make_case(20, writes=[1, 2, 3, 4, 5]),
            make_case(20, writes=[10, 10]),
            make_case(20, writes=[20]),
        ]
        self.run_both(cases, 'splits')
        self.records.append(dict(test='content-splits', cases=len(cases), modes=2, passed=True))

    # ------------------------------------------------------- negative controls

    def bad_build(self, name, old, new):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertEqual(source.count(old), 1, name)
        root = self.work / name
        (root / 'bootstrap').mkdir(parents=True)
        (root / 'bootstrap/guest_artifact_commit.dg').write_text(
            source.replace(old, new, 1), encoding='utf-8')
        return {mode: self.build([root, self.wrapper], self.wrapper, mode, name + '-' + mode)
                for mode in ('debug', 'release')}

    def test_actual_bad_implementations_are_rejected(self):
        commit_line = ('  (*st).written=off+take;\n'
                       '  if (*st).written==(*st).total{(*st).status=PENDING_FLUSH;}\n')
        # `suite=True` means the defect has to be caught by the native
        # State-consistency suite (mask bit 2) rather than by a case vector.
        controls = [
            dict(name='bad-false-durable', case=make_case(8, writes=[2, 2, 2, 2]),
                 old=commit_line,
                 new=('  (*st).written=off+take;\n'
                      '  if (*st).written==(*st).total{(*st).status=DURABLE;}\n'),
                 reason='ret|state|events'),  # DURABLE without the required FLUSH
            dict(name='bad-flush-early', case=make_case(4, writes=[2, 2]),
                 old=commit_line,
                 new=('  (*st).written=off+take;\n'
                      '  if (*st).written<(*st).total{flush(handle);(*st).status=DURABLE;}\n'),
                 reason='ret|state|events'),  # flushes before the artifact is complete
            dict(name='bad-repeat-offset', case=make_case(6, writes=[2, 2, 2]),
                 old='  let n:i64=write_at(handle,off,src.ptr+(off as usize),remaining);\n',
                 new='  let n:i64=write_at(handle,0,src.ptr+(off as usize),remaining);\n',
                 reason='events'),  # re-writes already confirmed bytes
            dict(name='bad-ignore-overrun', case=make_case(4, writes=[5]),
                 old='  if take>remaining{return fail(st,STAGE_WRITE,E_PROTOCOL);}\n', new='',
                 reason='ret|state'),  # accepts a count above the requested length
            dict(name='bad-continue-after-error', case=make_case(4, writes=[-3, 4]),
                 old='  if n<0{return fail(st,STAGE_WRITE,n as u64);}\n',
                 new='  if n<0{return COMMIT_STEP;}\n',
                 reason='ret|state'),  # continues after a negative write result
            dict(name='bad-skip-state-check', case=make_case(4, writes=[4]),
                 old=' if !state_consistent(st){return COMMIT_INVALID;}\n', new='',
                 reason='inconsistent', suite=True),  # forged PENDING_FLUSH is honoured
            dict(name='bad-skip-counter-check', case=make_case(4, writes=[4]),
                 old=('  if a<k{return false;}\n'
                      '  let positive=a-k;\n'
                      '  if s==FAILED&&(*st).stage==STAGE_WRITE{\n'
                      '   if positive>w&&positive-w>1{return false;}\n'
                      '  }else{\n'
                      '   if positive>w||(w!=0&&positive==0){return false;}\n'
                      '  }\n'), new='', reason='inconsistent', suite=True),
        ]
        for ctl in controls:
            name, reason = ctl['name'], ctl['reason']
            self.run_both([ctl['case']], name + '-good', preflight=False)
            for mode, exe in self.bad_build(name, ctl['old'], ctl['new']).items():
                with self.assertRaisesRegex(AssertionError, reason):
                    self.run_cases(exe, [ctl['case']], name + '-' + mode, preflight=False,
                                   consistency=ctl.get('suite', False))
            self.records.append(dict(test=name, compiled=True, native_executed=True,
                                     modes=2, rejected_by=reason))

    def test_contract_document_matches_module(self):
        doc = DOC.read_text(encoding='utf-8')
        module = SOURCE.read_text(encoding='utf-8')
        for token in ('MAX_STALL', 'PENDING_FLUSH', 'DURABLE', 'FAILED', 'write_at',
                      'flush', 'E_PROTOCOL', 'E_NO_PROGRESS', 'cannot roll',
                      'empty artifact'):
            self.assertIn(token, module + doc, token)
        self.assertIn('module bootstrap.guest_artifact_commit;', module)
        self.assertNotIn('import ', module)  # standalone: no hidden dependencies
        self.records.append(dict(test='contract-document', passed=True))


if __name__ == '__main__':
    unittest.main()
