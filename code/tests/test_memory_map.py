"""Independent C reference-model checks for mm.memory_map."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "kernel"
STD = ROOT / "lang" / "std"

WRAPPER = """module probe;
import mm.memory_map as mm;
import mm.phys_buddy as bud;
export("mmap_normalize") fn normalize(raw:[]const u8,descriptor_size:usize,descriptor_version:u64,arena_base:u64,arena_pages:usize,reserved:[]const mm.ReservedRange,scratch:[]u8,output:[]mm.PageRange)!usize{unsafe{return mm.normalize(raw,descriptor_size,descriptor_version,arena_base,arena_pages,reserved,scratch,output);}}
export("rr_size") fn rr_size()usize{return sizeof(mm.ReservedRange);}
export("pr_size") fn pr_size()usize{return sizeof(mm.PageRange);}
export("bud_allocator_size") fn bud_allocator_size()usize{return sizeof(bud.Allocator);}
export("bud_meta_size") fn bud_meta_size()usize{return sizeof(bud.PageMeta);}
export("bud_init_empty") fn bud_init_empty(state:*bud.Allocator)void{unsafe{*state=bud.EMPTY_ALLOCATOR;}}
export("bud_init") fn bud_init(state:*bud.Allocator,base:u64,page_count:usize,metadata:[]bud.PageMeta)!void{unsafe{return bud.init(state,base,page_count,metadata);}}
export("bud_add_usable") fn bud_add_usable(state:*bud.Allocator,start:usize,count:usize)!void{unsafe{return bud.add_usable(state,start,count);}}
export("bud_alloc") fn bud_alloc(state:*bud.Allocator,order:usize)!u64{unsafe{return bud.alloc(state,order);}}
export("bud_free_pages") fn bud_free_pages(state:*const bud.Allocator)!usize{unsafe{return bud.free_pages(state);}}
"""

C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"memory_map check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
#define E_INVALID_ARG 0x02000003ULL
#define E_META_SMALL 0x02000004ULL
#define E_BUFFER_SMALL 0x01000001ULL
struct Result {uint64_t code;uint64_t value;};
struct Bytes {const uint8_t *ptr;uint64_t len;};
struct RRange {uint64_t base;uint64_t length;};
struct RSlice {const struct RRange *ptr;uint64_t len;};
struct PRange {uint64_t start_page;uint64_t page_count;};
struct PSlice {struct PRange *ptr;uint64_t len;};
extern struct Result DG mmap_normalize(struct Bytes,uint64_t,uint64_t,uint64_t,uint64_t,struct RSlice,struct Bytes,struct PSlice);
extern uint64_t DG rr_size(void),pr_size(void);
extern uint64_t DG bud_allocator_size(void),bud_meta_size(void);
extern void DG bud_init_empty(uint8_t*);
extern struct Result DG bud_init(uint8_t*,uint64_t,uint64_t,struct Bytes);
extern struct Result DG bud_add_usable(uint8_t*,uint64_t,uint64_t);
extern struct Result DG bud_alloc(uint8_t*,uint64_t);
extern struct Result DG bud_free_pages(const uint8_t*);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected memory_map panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
/* Independent C reference: per-page predicate "the whole page is inside a
 * qualifying descriptor AND has no intersection with any reserved byte". */
static int ref_page_usable(uint64_t page,uint64_t arena_base,const uint8_t *raw,uint64_t stride,uint64_t count,const struct RRange *reserved,uint64_t res_count){
    uint64_t page_base=arena_base+page*4096,page_end=page_base+4096;
    int in_desc=0;
    for(uint64_t i=0;i<count;i++){
        const uint8_t *d=raw+i*stride;
        uint32_t type;memcpy(&type,d,4);
        uint64_t phys;memcpy(&phys,d+8,8);
        uint64_t pages;memcpy(&pages,d+24,8);
        uint64_t attr;memcpy(&attr,d+32,8);
        if(type==7 && !(attr&(1ULL<<63))){
            uint64_t dstart=phys,dend=phys+pages*4096;
            if(dstart<=page_base && page_end<=dend){in_desc=1;break;}
        }
    }
    if(!in_desc)return 0;
    for(uint64_t r=0;r<res_count;r++){
        uint64_t rb=reserved[r].base,rl=reserved[r].length;
        if(rl!=0){uint64_t rend=rb+rl;if(page_base<rend && rb<page_end)return 0;}
    }
    return 1;
}
static uint64_t ref_segments(uint64_t arena_pages,uint64_t arena_base,const uint8_t *raw,uint64_t stride,uint64_t count,const struct RRange *reserved,uint64_t res_count,struct PRange *out){
    uint64_t n=0,p=0;
    while(p<arena_pages){
        if(ref_page_usable(p,arena_base,raw,stride,count,reserved,res_count)){
            uint64_t s=p;while(p<arena_pages && ref_page_usable(p,arena_base,raw,stride,count,reserved,res_count))p++;
            out[n].start_page=s;out[n].page_count=p-s;n++;
        }else p++;
    }
    return n;
}
/* descriptor builder: fill a 40/48/56-byte descriptor at d */
static void put_desc(uint8_t *d,uint32_t type,uint64_t phys,uint64_t pages,uint64_t attr){
    memset(d,0,40);
    memcpy(d,&type,4);memcpy(d+8,&phys,8);memcpy(d+24,&pages,8);memcpy(d+32,&attr,8);
}
static uint64_t rng_state;
static uint64_t rng(void){rng_state^=rng_state<<13;rng_state^=rng_state>>7;rng_state^=rng_state<<17;return rng_state;}
int main(void){
    CHECK(rr_size()==sizeof(struct RRange));
    CHECK(pr_size()==sizeof(struct PRange));
    /* basic deterministic scenario */
    {
        uint64_t stride=40;
        uint8_t raw_g[3*56+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0x1000,4,0);               /* pages 1-4 conventional */
        put_desc(raw+stride,7,0x5000,2,1ULL<<63);  /* pages 5-6 runtime -> reserved */
        put_desc(raw+2*stride,2,0x7000,2,0);       /* pages 7-8 loader -> reserved */
        uint8_t raw_snap[3*56]; memcpy(raw_snap,raw,3*56);
        uint64_t arena_base=0x0;uint64_t arena_pages=16;
        struct RRange reserved[]={{0x3000,0x1000}}; /* reserve page 3 */
        uint8_t scratch_g[16+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[8*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        struct Result r=mmap_normalize((struct Bytes){raw,3*stride},stride,1,arena_base,arena_pages,(struct RSlice){reserved,1},(struct Bytes){scratch,16},(struct PSlice){out,8});
        CHECK(r.code==0);
        /* expected: pages 1-2 and 4 usable (page 3 reserved, 5-6 runtime, 7-8 loader) */
        CHECK(r.value==2);
        CHECK(out[0].start_page==1&&out[0].page_count==2);
        CHECK(out[1].start_page==4&&out[1].page_count==1);
        CHECK(!memcmp(raw,raw_snap,3*56));
        for(int i=2;i<8;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[3*56+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[16+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc && out_g[8+8*16+i]==0xcc);
    }
    /* randomized cross-check against the independent reference */
    {
        uint64_t arena_pages=64;uint64_t arena_base=0x100000000ULL;
        uint64_t stride=40;
        uint8_t raw_g[8*40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        uint64_t used[64];memset(used,0,sizeof(used));
        rng_state=0x9e3779b97f4a7c15ULL;
        uint64_t actual_ndesc=0;
        for(int attempt=0;attempt<8;attempt++){
            uint64_t page=rng()%arena_pages;uint64_t pages=(rng()%5)+1;
            if(page+pages>arena_pages)pages=arena_pages-page;
            int ok=1;
            for(uint64_t k=0;k<pages;k++)if(used[page+k]){ok=0;break;}
            if(!ok)continue;
            for(uint64_t k=0;k<pages;k++)used[page+k]=1;
            uint32_t type=(rng()%10)==0?7:2;
            uint64_t attr=(rng()%5)==0?(1ULL<<63):0;
            put_desc(raw+actual_ndesc*stride,type,arena_base+page*4096,pages,attr);
            actual_ndesc++;
        }
        struct RRange reserved[4];
        for(int i=0;i<4;i++){reserved[i].base=arena_base+(rng()%arena_pages)*4096;reserved[i].length=(rng()%3)*4096;}
        uint8_t raw_snap[8*40]; memcpy(raw_snap,raw,8*40);
        uint8_t scratch_g[64+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[64*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        struct PRange refout[64];
        memset(out_g,0xcc,sizeof(out_g));
        struct Result r=mmap_normalize((struct Bytes){raw,actual_ndesc*stride},stride,1,arena_base,arena_pages,(struct RSlice){reserved,4},(struct Bytes){scratch,64},(struct PSlice){out,64});
        CHECK(r.code==0);
        uint64_t rn=ref_segments(arena_pages,arena_base,raw,stride,actual_ndesc,reserved,4,refout);
        CHECK(r.value==rn);
        for(uint64_t i=0;i<rn;i++)CHECK(out[i].start_page==refout[i].start_page&&out[i].page_count==refout[i].page_count);
        for(uint64_t i=rn;i<64;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        CHECK(!memcmp(raw,raw_snap,8*40));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[8*40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[64+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc && out_g[8+64*16+i]==0xcc);
    }
    /* stride 48/56 extended tail must not be written; empty map */
    {
        uint8_t raw_g[56+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        memset(raw,0xa7,56);
        put_desc(raw,7,0,8,0);
        uint8_t raw_snap[56]; memcpy(raw_snap,raw,56);
        uint8_t scratch_g[8+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[8*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        #define GCHK() do{for(int _i=0;_i<8;_i++)CHECK(raw_g[_i]==0xaa && raw_g[56+8+_i]==0xaa);for(int _i=0;_i<8;_i++)CHECK(scratch_g[_i]==0xbb && scratch_g[8+8+_i]==0xbb);for(int _i=0;_i<8;_i++)CHECK(out_g[_i]==0xcc && out_g[8+8*16+_i]==0xcc);}while(0)
        CHECK(mmap_normalize((struct Bytes){raw,48},48,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==0);
        CHECK(!memcmp(raw,raw_snap,56));
        CHECK(out[0].start_page==0&&out[0].page_count==8);
        for(int i=1;i<8;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        GCHK();
        memset(out_g,0xcc,sizeof(out_g));
        CHECK(mmap_normalize((struct Bytes){raw,56},56,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==0);
        CHECK(!memcmp(raw,raw_snap,56));
        CHECK(out[0].start_page==0&&out[0].page_count==8);
        for(int i=1;i<8;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        GCHK();
        memset(out_g,0xcc,sizeof(out_g));
        CHECK(mmap_normalize((struct Bytes){NULL,0},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==0);
        for(int i=0;i<8*16;i++)CHECK(((uint8_t*)out)[i]==0xcc);
        GCHK();
        #undef GCHK
    }
    /* error cases */
    {
        uint8_t raw_g[48+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0,4,0);
        uint8_t raw_snap[48]; memcpy(raw_snap,raw,48);
        uint8_t scratch_g[16+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[8*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        #define FCHK() do{CHECK(!memcmp(raw,raw_snap,48));for(int _i=0;_i<8;_i++)CHECK(raw_g[_i]==0xaa && raw_g[48+8+_i]==0xaa);for(int _i=0;_i<8;_i++)CHECK(scratch_g[_i]==0xbb && scratch_g[16+8+_i]==0xbb);for(int _i=0;_i<8*16;_i++)CHECK(((uint8_t*)out)[_i]==0xcc);for(int _i=0;_i<8;_i++)CHECK(out_g[_i]==0xcc && out_g[8+8*16+_i]==0xcc);}while(0)
        /* bad arena_pages (not power of two) */
        CHECK(mmap_normalize((struct Bytes){raw,40},40,1,0,12,(struct RSlice){NULL,0},(struct Bytes){scratch,12},(struct PSlice){out,8}).code==E_INVALID_ARG);
        FCHK();
        /* bad version */
        CHECK(mmap_normalize((struct Bytes){raw,40},40,2,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);
        FCHK();
        /* bad descriptor_size */
        CHECK(mmap_normalize((struct Bytes){raw,40},36,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);
        FCHK();
        /* raw.len not multiple of stride */
        CHECK(mmap_normalize((struct Bytes){raw,41},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);
        FCHK();
        /* scratch too small */
        CHECK(mmap_normalize((struct Bytes){raw,40},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,7},(struct PSlice){out,8}).code==E_META_SMALL);
        FCHK();
        /* zero pages descriptor */
        {uint8_t r2_g[40+16];uint8_t *r2=r2_g+8;memset(r2_g,0xaa,sizeof(r2_g));put_desc(r2,7,0,0,0);
         uint8_t r2_snap[40];memcpy(r2_snap,r2,40);
         CHECK(mmap_normalize((struct Bytes){r2,40},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);
         CHECK(!memcmp(r2,r2_snap,40));for(int i=0;i<8;i++)CHECK(r2_g[i]==0xaa&&r2_g[40+8+i]==0xaa);}
        FCHK();
        /* unaligned PhysicalStart */
        {uint8_t r2_g[40+16];uint8_t *r2=r2_g+8;memset(r2_g,0xaa,sizeof(r2_g));put_desc(r2,7,1,4,0);
         uint8_t r2_snap[40];memcpy(r2_snap,r2,40);
         CHECK(mmap_normalize((struct Bytes){r2,40},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);
         CHECK(!memcmp(r2,r2_snap,40));for(int i=0;i<8;i++)CHECK(r2_g[i]==0xaa&&r2_g[40+8+i]==0xaa);}
        FCHK();
        /* overlapping descriptors */
        {uint8_t r2_g[80+16];uint8_t *r2=r2_g+8;memset(r2_g,0xaa,sizeof(r2_g));put_desc(r2,7,0,4,0);put_desc(r2+40,7,0x2000,4,0);
         uint8_t r2_snap[80];memcpy(r2_snap,r2,80);
         CHECK(mmap_normalize((struct Bytes){r2,80},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);
         CHECK(!memcmp(r2,r2_snap,80));for(int i=0;i<8;i++)CHECK(r2_g[i]==0xaa&&r2_g[80+8+i]==0xaa);}
        FCHK();
        /* reserved endpoint overflow */
        {struct RRange rr[]={{0xfffffffffffff000ULL,0x2000}};CHECK(mmap_normalize((struct Bytes){raw,40},40,1,0,8,(struct RSlice){rr,1},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);}
        FCHK();
        /* output too small (BufferTooSmall) */
        {uint8_t r2_g[40+16];uint8_t *r2=r2_g+8;memset(r2_g,0xaa,sizeof(r2_g));put_desc(r2,7,0,16,0);
         uint8_t r2_snap[40];memcpy(r2_snap,r2,40);
         CHECK(mmap_normalize((struct Bytes){r2,40},40,1,0,16,(struct RSlice){NULL,0},(struct Bytes){scratch,16},(struct PSlice){out,0}).code==E_BUFFER_SMALL);
         CHECK(!memcmp(r2,r2_snap,40));for(int i=0;i<8;i++)CHECK(r2_g[i]==0xaa&&r2_g[40+8+i]==0xaa);}
        FCHK();
        #undef FCHK
        /* every failure above must leave the whole output unchanged */
        for(int i=0;i<8*16;i++)CHECK(((uint8_t*)out)[i]==0xcc);
        CHECK(!memcmp(raw,raw_snap,48));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[48+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[16+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc && out_g[8+8*16+i]==0xcc);
    }
    /* R1: multi-round randomized coverage + D8 publish/exhaust integration */
    {
        uint64_t arena_pages=64;uint64_t arena_base=0x200000000ULL;
        uint64_t stride=40;
        rng_state=0xdeadbeefcafebabeULL;
        int saw_usable=0,saw_multiseg=0;
        for(int round=0;round<40;round++){
            uint8_t raw_g[8*40+16]; uint8_t *raw=raw_g+8;
            memset(raw_g,0xaa,sizeof(raw_g));
            uint64_t used[64];memset(used,0,sizeof(used));
            uint64_t ndesc=0;
            for(int attempt=0;attempt<8;attempt++){
                uint64_t page=rng()%arena_pages;uint64_t pages=(rng()%5)+1;
                if(page+pages>arena_pages)pages=arena_pages-page;
                int ok=1;for(uint64_t k=0;k<pages;k++)if(used[page+k]){ok=0;break;}
                if(!ok)continue;
                for(uint64_t k=0;k<pages;k++)used[page+k]=1;
                uint32_t type=(rng()%3)==0?7:2;   /* ~1/3 conventional */
                uint64_t attr=(rng()%4)==0?(1ULL<<63):0;
                put_desc(raw+ndesc*stride,type,arena_base+page*4096,pages,attr);
                ndesc++;
            }
            struct RRange reserved[3];
            for(int i=0;i<3;i++){reserved[i].base=arena_base+(rng()%arena_pages)*4096;reserved[i].length=(rng()%3)*4096;}
            uint8_t raw_snap[8*40];memcpy(raw_snap,raw,8*40);
            uint8_t scratch_g[64+16]; uint8_t *scratch=scratch_g+8;
            memset(scratch_g,0xbb,sizeof(scratch_g));
            uint8_t out_g[64*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
            struct PRange refout[64];
            memset(out_g,0xcc,sizeof(out_g));
            struct Result r=mmap_normalize((struct Bytes){raw,ndesc*stride},stride,1,arena_base,arena_pages,(struct RSlice){reserved,3},(struct Bytes){scratch,64},(struct PSlice){out,64});
            CHECK(!memcmp(raw,raw_snap,8*40));
            for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[8*40+8+i]==0xaa);
            CHECK(r.code==0);
            uint64_t rn=ref_segments(arena_pages,arena_base,raw,stride,ndesc,reserved,3,refout);
            CHECK(r.value==rn);
            for(uint64_t i=0;i<rn;i++)CHECK(out[i].start_page==refout[i].start_page&&out[i].page_count==refout[i].page_count);
            for(uint64_t i=rn;i<64;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
            for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[64+8+i]==0xbb);
            for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc && out_g[8+64*16+i]==0xcc);
            if(rn>0)saw_usable=1;
            if(rn>1)saw_multiseg=1;
            /* D8 publish + exhaust: allocated page set must equal the reference set */
            uint64_t asz=bud_allocator_size(),msz=bud_meta_size();
            uint8_t *st=malloc(asz),*mt=malloc(msz*arena_pages);
            bud_init_empty(st);
            CHECK(bud_init(st,arena_base,arena_pages,(struct Bytes){mt,arena_pages}).code==0);
            for(uint64_t i=0;i<rn;i++)CHECK(bud_add_usable(st,out[i].start_page,out[i].page_count).code==0);
            /* collect reference-usable page set */
            uint8_t refset[64];memset(refset,0,64);
            for(uint64_t pg=0;pg<arena_pages;pg++)if(ref_page_usable(pg,arena_base,raw,stride,ndesc,reserved,3))refset[pg]=1;
            uint64_t expected_pages=0;for(uint64_t pg=0;pg<arena_pages;pg++)if(refset[pg])expected_pages++;
            CHECK(bud_free_pages(st).value==expected_pages);
            /* allocate order-0 to exhaustion, verify the set matches */
            uint8_t got[64];memset(got,0,64);uint64_t got_n=0;
            for(;;){
                struct Result ar=bud_alloc(st,0);
                if(ar.code!=0)break;
                uint64_t pg=((uint64_t)ar.value-arena_base)/4096;
                CHECK(pg<arena_pages);CHECK(got[pg]==0);got[pg]=1;got_n++;
            }
            CHECK(got_n==expected_pages);
            for(uint64_t pg=0;pg<arena_pages;pg++)CHECK(got[pg]==refset[pg]);
            free(st);free(mt);
        }
        CHECK(saw_usable && saw_multiseg);
    }
    /* R2: input/scratch/output front+back sentinel protection */
    {
        uint8_t raw_g[3*40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0x1000,4,0);
        put_desc(raw+40,7,0x8000,4,0);
        put_desc(raw+80,2,0xd000,2,0);
        uint8_t raw_snap[3*40]; memcpy(raw_snap,raw,3*40);
        uint8_t scratch_g[16+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t arena[8*16+16+16]; struct PRange *o=(struct PRange*)(arena+16);
        memset(arena,0xcc,sizeof(arena));
        struct Result r=mmap_normalize((struct Bytes){raw,120},40,1,0,16,(struct RSlice){NULL,0},(struct Bytes){scratch,16},(struct PSlice){o,8});
        CHECK(r.code==0 && r.value==2);
        CHECK(o[0].start_page==1&&o[0].page_count==4&&o[1].start_page==8&&o[1].page_count==4);
        CHECK(!memcmp(raw,raw_snap,3*40));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[3*40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[16+8+i]==0xbb);
        for(int i=0;i<16;i++)CHECK(arena[i]==0xcc);              /* output front */
        for(int i=16+32;i<8*16+16+16;i++)CHECK(arena[i]==0xcc);  /* tail + back guard */
        /* failure: output too small -> entire output unchanged */
        memset(arena,0xcc,sizeof(arena));
        r=mmap_normalize((struct Bytes){raw,120},40,1,0,16,(struct RSlice){NULL,0},(struct Bytes){scratch,16},(struct PSlice){o,1});
        CHECK(r.code==E_BUFFER_SMALL);
        for(int i=0;i<8*16+16+16;i++)CHECK(arena[i]==0xcc);
        CHECK(!memcmp(raw,raw_snap,3*40));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[3*40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[16+8+i]==0xbb);
    }
    /* R2: non-aligned raw buffer (misaligned by 1 byte) */
    {
        uint8_t storage[8+40+8+1]; uint8_t *raw=storage+8+1; /* raw stays odd */
        memset(storage,0xaa,sizeof(storage));
        put_desc(raw,7,0x1000,4,0);
        uint64_t vs = 0x1234abcd5678ef90ULL; memcpy(raw+16,&vs,8);
        uint8_t raw_snap[40]; memcpy(raw_snap,raw,40);
        uint8_t scratch_g[16+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[8*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        struct Result r=mmap_normalize((struct Bytes){raw,40},40,1,0,16,(struct RSlice){NULL,0},(struct Bytes){scratch,16},(struct PSlice){out,8});
        CHECK(r.code==0 && r.value==1);
        CHECK(out[0].start_page==1&&out[0].page_count==4);
        CHECK(!memcmp(raw,raw_snap,40));
        for(int i=1;i<8;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        for(int i=0;i<8;i++)CHECK(storage[i]==0xaa);                  /* raw front region */
        CHECK(storage[8]==0xaa);                                        /* byte immediately before raw */
        for(int i=0;i<8;i++)CHECK(storage[8+40+1+i]==0xaa);           /* raw back guard */
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[16+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc && out_g[8+8*16+i]==0xcc);
    }
    /* R2: partial/duplicate/cross-boundary reserved + arena-outside overlap */
    {
        uint8_t raw_g[40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0,16,0);
        uint8_t raw_snap[40]; memcpy(raw_snap,raw,40);
        uint8_t scratch_g[16+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[8*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        struct RRange reserved[] = {{0x200,0x100},{0x200,0x100},{0xff00,0x200}};
        memset(out_g,0xcc,sizeof(out_g));
        struct Result r=mmap_normalize((struct Bytes){raw,40},40,1,0,16,(struct RSlice){reserved,3},(struct Bytes){scratch,16},(struct PSlice){out,8});
        CHECK(r.code==0 && r.value==1);
        CHECK(out[0].start_page==1 && out[0].page_count==14);
        CHECK(!memcmp(raw,raw_snap,40));
        for(int i=1;i<8;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[16+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc && out_g[8+8*16+i]==0xcc);
    }
    {
        uint8_t raw_g[80+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xab,sizeof(raw_g));
        put_desc(raw,7,0x100000,4,0);
        put_desc(raw+40,7,0x101000,4,0);
        uint8_t raw_snap[80]; memcpy(raw_snap,raw,80);
        uint8_t scratch_g[8+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xcd,sizeof(scratch_g));
        uint8_t out_g[8*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xc3,sizeof(out_g));
        CHECK(mmap_normalize((struct Bytes){raw,80},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);
        for(int i=0;i<8*16;i++)CHECK(((uint8_t*)out)[i]==0xc3);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xc3&&out_g[8+8*16+i]==0xc3);
        CHECK(!memcmp(raw,raw_snap,80));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xab&&raw_g[80+8+i]==0xab);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xcd&&scratch_g[8+8+i]==0xcd);
    }
    /* R2: u64 extreme arena_base + large arena heap scratch */
    {
        uint64_t arena_base = 0xfffffffffff00000ULL;
        uint8_t raw_g[40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,arena_base,1,0);
        uint8_t raw_snap[40]; memcpy(raw_snap,raw,40);
        uint8_t scratch_g[1+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[4*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        struct Result r=mmap_normalize((struct Bytes){raw,40},40,1,arena_base,1,(struct RSlice){NULL,0},(struct Bytes){scratch,1},(struct PSlice){out,4});
        CHECK(r.code==0 && r.value==1);
        CHECK(out[0].start_page==0 && out[0].page_count==1);
        CHECK(!memcmp(raw,raw_snap,40));
        for(int i=1;i<4;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa&&raw_g[40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb&&scratch_g[1+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc&&out_g[8+4*16+i]==0xcc);
    }
    {
        uint64_t arena_pages = 1024;
        uint8_t *scratch_all = malloc(arena_pages+16); uint8_t *scratch = scratch_all+8;
        memset(scratch_all,0xcd,arena_pages+16);
        struct PRange *out_all = malloc(arena_pages * sizeof(struct PRange)+16); struct PRange *out = (struct PRange*)((uint8_t*)out_all+8);
        memset(out_all,0xcc,arena_pages*sizeof(struct PRange)+16);
        uint8_t raw_g[40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0,1024,0);
        uint8_t raw_snap[40]; memcpy(raw_snap,raw,40);
        struct Result r=mmap_normalize((struct Bytes){raw,40},40,1,0,arena_pages,(struct RSlice){NULL,0},(struct Bytes){scratch,arena_pages},(struct PSlice){out,arena_pages});
        CHECK(r.code==0 && r.value==1);
        CHECK(out[0].start_page==0 && out[0].page_count==1024);
        CHECK(!memcmp(raw,raw_snap,40));
        for(uint64_t i=1;i<arena_pages;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(((uint8_t*)out_all)[i]==0xcc && ((uint8_t*)out_all)[8+arena_pages*sizeof(struct PRange)+i]==0xcc);
        for(int i=0;i<8;i++)CHECK(scratch_all[i]==0xcd && scratch_all[8+arena_pages+i]==0xcd);
        free(scratch_all); free(out_all);
    }
    /* R2: raw input body (incl. ignored VirtualStart) must stay byte-for-byte unchanged */
    {
        uint8_t raw_g[40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0x1000,4,0);
        uint64_t vs = 0xaaaa5555bbbbccccULL; memcpy(raw+16,&vs,8);
        uint8_t raw_snap[40]; memcpy(raw_snap,raw,40);
        uint8_t scratch_g[16+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[8*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        struct Result r=mmap_normalize((struct Bytes){raw,40},40,1,0,16,(struct RSlice){NULL,0},(struct Bytes){scratch,16},(struct PSlice){out,8});
        CHECK(r.code==0 && r.value==1);
        CHECK(out[0].start_page==1 && out[0].page_count==4);
        CHECK(!memcmp(raw,raw_snap,40));
        for(int i=1;i<8;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[16+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc && out_g[8+8*16+i]==0xcc);
    }
    /* R2: cross-arena clip, unknown type, descriptor endpoint overflow, capacity exact */
    {
        /* cross-arena clip: descriptor spans both arena edges */
        uint8_t raw_g[40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0x3000,6,0);
        uint8_t raw_snap[40]; memcpy(raw_snap,raw,40);
        uint8_t scratch_g[4+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[4*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        struct Result r=mmap_normalize((struct Bytes){raw,40},40,1,0x4000,4,(struct RSlice){NULL,0},(struct Bytes){scratch,4},(struct PSlice){out,4});
        CHECK(r.code==0 && r.value==1 && out[0].start_page==0 && out[0].page_count==4);
        CHECK(!memcmp(raw,raw_snap,40));
        for(int i=1;i<4;i++)CHECK(out[i].start_page==0xccccccccccccccccULL&&out[i].page_count==0xccccccccccccccccULL);
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa && raw_g[40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb && scratch_g[4+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc && out_g[8+4*16+i]==0xcc);
    }
    {
        /* unknown type -> reserved */
        uint8_t raw_g[40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,99,0,4,0);
        uint8_t raw_snap[40]; memcpy(raw_snap,raw,40);
        uint8_t scratch_g[4+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xcd,sizeof(scratch_g));
        uint8_t out_g[4*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        struct Result r=mmap_normalize((struct Bytes){raw,40},40,1,0,4,(struct RSlice){NULL,0},(struct Bytes){scratch,4},(struct PSlice){out,4});
        CHECK(r.code==0 && r.value==0);
        for(int i=0;i<4*16;i++)CHECK(((uint8_t*)out)[i]==0xcc);
        CHECK(!memcmp(raw,raw_snap,40));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa&&raw_g[40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xcd&&scratch_g[4+8+i]==0xcd);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc&&out_g[8+4*16+i]==0xcc);
    }
    {
        /* descriptor endpoint overflow (outside arena too) */
        uint8_t raw_g[40+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0xfffffffffffff000ULL,2,0);
        uint8_t raw_snap[40]; memcpy(raw_snap,raw,40);
        uint8_t scratch_g[8+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xcd,sizeof(scratch_g));
        uint8_t out_g[8*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        CHECK(mmap_normalize((struct Bytes){raw,40},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,8}).code==E_INVALID_ARG);
        for(int i=0;i<8*16;i++)CHECK(((uint8_t*)out)[i]==0xcc);
        CHECK(!memcmp(raw,raw_snap,40));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa&&raw_g[40+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xcd&&scratch_g[8+8+i]==0xcd);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc&&out_g[8+8*16+i]==0xcc);
    }
    {
        /* output capacity exactly / one less */
        uint8_t raw_g[80+16]; uint8_t *raw=raw_g+8;
        memset(raw_g,0xaa,sizeof(raw_g));
        put_desc(raw,7,0,2,0);
        put_desc(raw+40,7,0x4000,2,0);
        uint8_t raw_snap[80]; memcpy(raw_snap,raw,80);
        uint8_t scratch_g[8+16]; uint8_t *scratch=scratch_g+8;
        memset(scratch_g,0xbb,sizeof(scratch_g));
        uint8_t out_g[2*16+16]; struct PRange *out=(struct PRange*)(out_g+8);
        memset(out_g,0xcc,sizeof(out_g));
        uint8_t out1_g[1*16+16]; struct PRange *out1=(struct PRange*)(out1_g+8);
        struct Result r=mmap_normalize((struct Bytes){raw,80},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out,2});
        CHECK(r.code==0 && r.value==2);
        CHECK(out[0].start_page==0&&out[0].page_count==2);
        CHECK(out[1].start_page==4&&out[1].page_count==2);
        CHECK(!memcmp(raw,raw_snap,80));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa&&raw_g[80+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb&&scratch_g[8+8+i]==0xbb);
        for(int i=0;i<8;i++)CHECK(out_g[i]==0xcc&&out_g[8+2*16+i]==0xcc);
        memset(out1_g,0xcc,sizeof(out1_g));
        CHECK(mmap_normalize((struct Bytes){raw,80},40,1,0,8,(struct RSlice){NULL,0},(struct Bytes){scratch,8},(struct PSlice){out1,1}).code==E_BUFFER_SMALL);
        for(int i=0;i<1*16+16;i++)CHECK(out1_g[i]==0xcc);
        CHECK(!memcmp(raw,raw_snap,80));
        for(int i=0;i<8;i++)CHECK(raw_g[i]==0xaa&&raw_g[80+8+i]==0xaa);
        for(int i=0;i<8;i++)CHECK(scratch_g[i]==0xbb&&scratch_g[8+8+i]==0xbb);
    }
    puts("native memory_map probes passed");return 0;
}
"""


class MemoryMapTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(KERNEL / "mm" / "memory_map.dg", roots=[KERNEL, STD])
        self.assertEqual(["core.errors", "mm.errors", "mm.memory_map"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "mmap.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_memory_map(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native memory_map checks require NASM and a SysV-capable GCC host compiler")
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
                        entry.write_text(WRAPPER, encoding="utf-8")
                        compiled = compile_file(entry, roots=[Path(roots), KERNEL, STD], mode=mode)
                    asm.write_text(compiled.assembly, encoding="utf-8")
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    command = [cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        command += ["-no-pie"]
                    result = subprocess.run(command + [str(c_path), str(obj), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native memory_map probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
