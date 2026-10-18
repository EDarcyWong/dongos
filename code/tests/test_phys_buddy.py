"""Independent C reference-model checks for mm.phys_buddy."""
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
import mm.phys_buddy as bud;
import mm.errors as mmerr;
import core.errors as coreerr;
export("buddy_allocator_size") fn allocator_size()usize{return sizeof(bud.Allocator);}
export("buddy_meta_size") fn meta_size()usize{return sizeof(bud.PageMeta);}
export("buddy_allocator_align") fn allocator_align()usize{return alignof(bud.Allocator);}
export("buddy_meta_align") fn meta_align()usize{return alignof(bud.PageMeta);}
export("buddy_init_empty") fn init_empty(state:*bud.Allocator)void{unsafe{*state=bud.EMPTY_ALLOCATOR;}}
export("buddy_init") fn init(state:*bud.Allocator,base:u64,page_count:usize,metadata:[]bud.PageMeta)!void{unsafe{return bud.init(state,base,page_count,metadata);}}
export("buddy_add_usable") fn add_usable(state:*bud.Allocator,start:usize,count:usize)!void{unsafe{return bud.add_usable(state,start,count);}}
export("buddy_alloc") fn alloc(state:*bud.Allocator,order:usize)!u64{unsafe{return bud.alloc(state,order);}}
export("buddy_free") fn free(state:*bud.Allocator,address:u64,order:usize)!void{unsafe{return bud.free(state,address,order);}}
export("buddy_free_pages") fn free_pages(state:*const bud.Allocator)!usize{unsafe{return bud.free_pages(state);}}
export("buddy_error_refs") fn error_refs(flag:u64)!u64{if flag==0{return error.mmerr.NotInitialized;}return error.coreerr.BufferTooSmall;}
"""

C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"phys_buddy check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
struct Result {uint64_t code;uint64_t value;};
struct MetaSlice {uint8_t *ptr;uint64_t len;};
extern uint64_t DG buddy_allocator_size(void),buddy_meta_size(void),buddy_allocator_align(void),buddy_meta_align(void);
extern struct Result DG buddy_init(uint8_t*,uint64_t,uint64_t,struct MetaSlice);
extern struct Result DG buddy_add_usable(uint8_t*,uint64_t,uint64_t);
extern struct Result DG buddy_alloc(uint8_t*,uint64_t);
extern struct Result DG buddy_free(uint8_t*,uint64_t,uint64_t);
extern struct Result DG buddy_free_pages(const uint8_t*);
extern void DG buddy_init_empty(uint8_t*);
extern struct Result DG buddy_error_refs(uint64_t);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected phys_buddy panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
#define E_NOT_INIT 0x02000001ULL
#define E_ALREADY_INIT 0x02000002ULL
#define E_INVALID_ARG 0x02000003ULL
#define E_META_SMALL 0x02000004ULL
#define E_RANGE_UNAVAIL 0x02000005ULL
#define E_INVALID_ORDER 0x02000006ULL
#define E_OOM 0x02000007ULL
#define E_INVALID_FREE 0x02000008ULL
#define PAGE 4096ULL

/* reference bitmap model */
static uint64_t rc_page_count, rc_base;
static uint8_t *rc_published, *rc_occupied;
static uint64_t rc_allocated;
static void rc_reset(uint64_t pc, uint64_t base){rc_page_count=pc;rc_base=base;rc_published=calloc(pc,1);rc_occupied=calloc(pc,1);rc_allocated=0;}
static uint64_t rc_free_pages(void){uint64_t n=0;for(uint64_t i=0;i<rc_page_count;i++)if(rc_published[i]&&!rc_occupied[i])n++;return n;}
static int rc_check_alloc(uint64_t addr, uint64_t order){
    if(order>10)return 0;
    if(addr<rc_base)return 0;
    uint64_t off=addr-rc_base;if(off%PAGE)return 0;
    uint64_t p=off/PAGE;if(p>=rc_page_count)return 0;
    uint64_t size=1ULL<<order;if(p & (size-1))return 0;
    if(p+size>rc_page_count)return 0;
    for(uint64_t i=0;i<size;i++){if(!rc_published[p+i]||rc_occupied[p+i])return 0;}
    for(uint64_t i=0;i<size;i++)rc_occupied[p+i]=1;
    rc_allocated+=size;
    return 1;
}
static int rc_check_free(uint64_t addr, uint64_t order){
    if(order>10)return 0;
    if(addr<rc_base)return 0;
    uint64_t off=addr-rc_base;if(off%PAGE)return 0;
    uint64_t p=off/PAGE;if(p>=rc_page_count)return 0;
    uint64_t size=1ULL<<order;if(p & (size-1))return 0;
    if(p+size>rc_page_count)return 0;
    for(uint64_t i=0;i<size;i++){if(!rc_occupied[p+i])return 0;}
    for(uint64_t i=0;i<size;i++)rc_occupied[p+i]=0;
    rc_allocated-=size;
    return 1;
}
static uint64_t rng_state;
static uint64_t rng(void){rng_state^=rng_state<<13;rng_state^=rng_state>>7;rng_state^=rng_state<<17;return rng_state;}

/* Shared guard helper: state/metadata end sentinels and excess metadata tail untouched. */
static int buddy_guards_ok(const uint8_t *st_all,const uint8_t *st,uint64_t asz,
                           const uint8_t *mt_all,const uint8_t *mt,uint64_t msz,
                           uint64_t used,uint64_t total){
    for(int i=0;i<8;i++){if(st_all[i]!=0xa5||st[asz+i]!=0xa5)return 0;}
    for(int i=0;i<8;i++){if(mt_all[i]!=0xa5||mt[msz*total+i]!=0xa5)return 0;}
    for(uint64_t j=used;j<total;j++)for(uint64_t k=0;k<msz;k++)if(mt[j*msz+k]!=0)return 0;
    return 1;
}
int main(void){
    CHECK(buddy_allocator_size()>=64);
    CHECK(buddy_meta_size()>=4);
    CHECK(buddy_allocator_align()>=8);

    /* basic deterministic scenario */
    {
        uint64_t pc=1024; uint64_t base=0x100000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16);
        memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16);
        memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        struct MetaSlice ms={mt,pc};
        #define BG() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        struct Result r=buddy_init(st,base,pc,ms);
        CHECK(r.code==0);
        BG();
        CHECK(buddy_free_pages(st).code==0 && buddy_free_pages(st).value==0);
        BG();
        CHECK(buddy_add_usable(st,0,pc).code==0);
        BG();
        CHECK(buddy_free_pages(st).value==pc);
        rc_reset(pc,base);
        for(uint64_t i=0;i<pc;i++)rc_published[i]=1;
        r=buddy_alloc(st,0);CHECK(r.code==0);CHECK(rc_check_alloc(r.value,0));
        BG();
        CHECK(buddy_free(st,r.value,0).code==0);CHECK(rc_check_free(r.value,0));
        BG();
        CHECK(buddy_free_pages(st).value==pc);
        r=buddy_alloc(st,10);CHECK(r.code==0);CHECK(rc_check_alloc(r.value,10));
        BG();
        CHECK(buddy_free(st,r.value,10).code==0);CHECK(rc_check_free(r.value,10));
        BG();
        CHECK(buddy_free_pages(st).value==pc);
        #undef BG
        free(st_all);free(mt_all);
    }
    /* each order 0..10 allocates one block on a fresh arena */
    for(uint64_t o=0;o<=10;o++){
        uint64_t pc2=(o==0)?1:(1ULL<<o);
        uint64_t base2=0x100000000ULL;
        uint64_t asz2=buddy_allocator_size(), msz2=buddy_meta_size();
        uint64_t total2=pc2+2;
        uint8_t *st2_all=malloc(asz2+16); uint8_t *st2=st2_all+8;
        memset(st2_all,0,asz2+16); memset(st2_all,0xa5,8); memset(st2+asz2,0xa5,8);
        uint8_t *mt2_all=malloc(msz2*total2+16); uint8_t *mt2=mt2_all+8;
        memset(mt2_all,0,msz2*total2+16); memset(mt2_all,0xa5,8); memset(mt2+msz2*total2,0xa5,8);
        buddy_init_empty(st2);
        #define OG() CHECK(buddy_guards_ok(st2_all,st2,asz2,mt2_all,mt2,msz2,pc2,total2))
        struct Result r2=buddy_init(st2,base2,pc2,(struct MetaSlice){mt2,pc2});CHECK(r2.code==0);
        OG();
        CHECK(buddy_add_usable(st2,0,pc2).code==0);
        OG();
        r2=buddy_alloc(st2,o);CHECK(r2.code==0);
        OG();
        CHECK(r2.value==base2);
        CHECK(buddy_free(st2,r2.value,o).code==0);
        OG();
        CHECK(buddy_free_pages(st2).value==pc2);
        #undef OG
        free(st2_all);free(mt2_all);
    }

    /* out-of-order free restores a full arena (split/merge) */
    {
        uint64_t pc=256; uint64_t base=0x200000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16); memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16); memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        #define QG() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        struct Result r=buddy_init(st,base,pc,(struct MetaSlice){mt,pc});CHECK(r.code==0);
        QG();
        CHECK(buddy_add_usable(st,0,pc).code==0);
        QG();
        /* allocate a bunch of order-0 pages, then free in reverse */
        uint64_t addrs[16];
        for(int i=0;i<16;i++){r=buddy_alloc(st,0);CHECK(r.code==0);addrs[i]=r.value;QG();}
        for(int i=15;i>=0;i--){CHECK(buddy_free(st,addrs[i],0).code==0);QG();}
        CHECK(buddy_free_pages(st).value==pc);
        /* allocate order 3, then free and re-alloc order 0 */
        r=buddy_alloc(st,3);CHECK(r.code==0);uint64_t a3=r.value;
        QG();
        CHECK(buddy_free(st,a3,3).code==0);
        QG();
        CHECK(buddy_free_pages(st).value==pc);
        #undef QG
        free(st_all);free(mt_all);
    }

    /* randomized cross-check against the bitmap model */
    {
        uint64_t pc=512; uint64_t base=0x400000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*(pc+2)+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*(pc+2)+16);
        memset(mt_all,0xa5,8); memset(mt+msz*(pc+2),0xa5,8);
        uint8_t *sbs=malloc(asz), *mbs=malloc(msz*(pc+2));
        buddy_init_empty(st);
        struct Result r=buddy_init(st,base,pc,(struct MetaSlice){mt,pc+2});CHECK(r.code==0);
        CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,pc+2));
        CHECK(buddy_add_usable(st,0,pc).code==0);
        CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,pc+2));
        rc_reset(pc,base);for(uint64_t i=0;i<pc;i++)rc_published[i]=1;
        rng_state=0x123456789abcdef0ULL;
        uint64_t held[200];uint64_t held_order[200];int held_n=0;
        for(int trial=0;trial<4000;trial++){
            if(held_n>0 && (rng()&3)==0){
                int idx=(int)(rng()%held_n);
                uint64_t addr=held[idx];uint64_t o=held_order[idx];
                r=buddy_free(st,addr,o);CHECK(r.code==0);
                CHECK(rc_check_free(addr,o));
                held[idx]=held[held_n-1];held_order[idx]=held_order[held_n-1];held_n--;
            }else{
                uint64_t o=rng()%11;
                memcpy(sbs,st,asz);memcpy(mbs,mt,msz*(pc+2));
                r=buddy_alloc(st,o);
                uint64_t want_ok = 0;
                /* reference: is there a free aligned block of size 2^o? */
                uint64_t size=1ULL<<o;
                for(uint64_t p=0;p+size<=pc;p+=size){
                    if(p%size)continue; /* not aligned, but p steps by size so always aligned from 0 */
                    int ok=1;
                    for(uint64_t j=0;j<size;j++)if(!rc_published[p+j]||rc_occupied[p+j]){ok=0;break;}
                    if(ok){want_ok=1;break;}
                }
                if(want_ok){
                    CHECK(r.code==0);CHECK(rc_check_alloc(r.value,o));
                    if(held_n<200){held[held_n]=r.value;held_order[held_n]=o;held_n++;}
                }else{
                    CHECK(r.code==E_OOM);
                    CHECK(!memcmp(st,sbs,asz)&&!memcmp(mt,mbs,msz*(pc+2)));
                }
            }
            CHECK(buddy_free_pages(st).value==rc_free_pages());
            for(int _i=0;_i<8;_i++)CHECK(st_all[_i]==0xa5&&st[asz+_i]==0xa5);
            for(int _i=0;_i<8;_i++)CHECK(mt_all[_i]==0xa5&&mt[msz*(pc+2)+_i]==0xa5);
            for(uint64_t _j=pc;_j<pc+2;_j++)for(uint64_t _k=0;_k<msz;_k++)CHECK(mt[_j*msz+_k]==0);
        }
        free(st_all);free(mt_all);free(sbs);free(mbs);
    }

    /* error cases */
    {
        uint64_t pc=64; uint64_t base=0x1000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16); memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16); memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        uint8_t *sbs=malloc(asz), *mbs=malloc(msz*total);
        #define EG() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        struct Result r;
        #define SNAP() do{memcpy(sbs,st,asz);memcpy(mbs,mt,msz*total);}while(0)
        #define UNCH() do{CHECK(!memcmp(st,sbs,asz)&&!memcmp(mt,mbs,msz*total));EG();}while(0)
        /* not initialized: full state/metadata unchanged */
        SNAP();CHECK(buddy_add_usable(st,0,1).code==E_NOT_INIT);UNCH();
        SNAP();CHECK(buddy_alloc(st,0).code==E_NOT_INIT);UNCH();
        SNAP();CHECK(buddy_free(st,base,0).code==E_NOT_INIT);UNCH();
        SNAP();CHECK(buddy_free_pages(st).code==E_NOT_INIT);UNCH();
        /* invalid page_count */
        SNAP();CHECK(buddy_init(st,base,63,(struct MetaSlice){mt,64}).code==E_INVALID_ARG);UNCH();
        SNAP();CHECK(buddy_init(st,base,0,(struct MetaSlice){mt,64}).code==E_INVALID_ARG);UNCH();
        /* metadata too small */
        SNAP();CHECK(buddy_init(st,base,64,(struct MetaSlice){mt,63}).code==E_META_SMALL);UNCH();
        /* bad base alignment */
        SNAP();CHECK(buddy_init(st,base+4096,64,(struct MetaSlice){mt,64}).code==E_INVALID_ARG);UNCH();
        /* valid init */
        CHECK(buddy_init(st,base,64,(struct MetaSlice){mt,64}).code==0);
        EG();
        /* double init */
        SNAP();CHECK(buddy_init(st,base,64,(struct MetaSlice){mt,64}).code==E_ALREADY_INIT);UNCH();
        /* invalid order: alloc is InvalidOrder, free is InvalidFree */
        SNAP();CHECK(buddy_alloc(st,11).code==E_INVALID_ORDER);UNCH();
        SNAP();CHECK(buddy_free(st,base,11).code==E_INVALID_FREE);UNCH();
        SNAP();CHECK(buddy_free(st,base,UINT64_MAX).code==E_INVALID_FREE);UNCH();
        /* OOM before publish */
        SNAP();CHECK(buddy_alloc(st,0).code==E_OOM);UNCH();
        /* add_usable out of range */
        SNAP();CHECK(buddy_add_usable(st,65,1).code==E_INVALID_ARG);UNCH();
        SNAP();CHECK(buddy_add_usable(st,63,2).code==E_INVALID_ARG);UNCH();
        /* add_usable zero length ok */
        CHECK(buddy_add_usable(st,0,0).code==0);
        EG();
        /* publish half, then overlapping publish fails */
        CHECK(buddy_add_usable(st,0,32).code==0);
        EG();
        SNAP();CHECK(buddy_add_usable(st,16,32).code==E_RANGE_UNAVAIL);UNCH();
        CHECK(buddy_add_usable(st,32,32).code==0);
        EG();
        CHECK(buddy_free_pages(st).value==64);
        /* invalid free: unaligned, wrong order, non-allocated, out of range */
        r=buddy_alloc(st,0);CHECK(r.code==0);uint64_t a0=r.value;
        EG();
        SNAP();CHECK(buddy_free(st,base+4096,0).code==E_INVALID_FREE);UNCH(); /* not allocated */
        SNAP();CHECK(buddy_free(st,a0,1).code==E_INVALID_FREE);UNCH(); /* wrong order */
        SNAP();CHECK(buddy_free(st,a0+4096,0).code==E_INVALID_FREE);UNCH(); /* unaligned (wrong page) */
        SNAP();CHECK(buddy_free(st,base+pc*4096,0).code==E_INVALID_FREE);UNCH(); /* out of range */
        CHECK(buddy_free(st,a0,0).code==0);
        EG();
        #undef SNAP
        #undef UNCH
        #undef EG
        free(st_all);free(mt_all);free(sbs);free(mbs);
    }

    /* holes block merging: two ranges separated by a hole */
    {
        uint64_t pc=128; uint64_t base=0x100000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16); memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16); memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        uint8_t *sbs=malloc(asz), *mbs=malloc(msz*total);
        #define PEG() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        #define SNAP() do{memcpy(sbs,st,asz);memcpy(mbs,mt,msz*total);}while(0)
        #define UNCH() do{CHECK(!memcmp(st,sbs,asz)&&!memcmp(mt,mbs,msz*total));PEG();}while(0)
        CHECK(buddy_init(st,base,pc,(struct MetaSlice){mt,pc}).code==0);
        PEG();
        /* publish pages 0..31 and 64..95, leave 32..63 reserved */
        CHECK(buddy_add_usable(st,0,32).code==0);
        PEG();
        CHECK(buddy_add_usable(st,64,32).code==0);
        PEG();
        CHECK(buddy_free_pages(st).value==64);
        /* cannot alloc order 6 (needs 64 contiguous) */
        SNAP();CHECK(buddy_alloc(st,6).code==E_OOM);UNCH();
        /* can alloc order 5 */
        struct Result r=buddy_alloc(st,5);CHECK(r.code==0);
        PEG();
        CHECK(buddy_free(st,r.value,5).code==0);
        PEG();
        #undef PEG
        #undef SNAP
        #undef UNCH
        free(st_all);free(mt_all);free(sbs);free(mbs);
    }

    /* multiple allocators isolated */
    {
        uint64_t pc=32; uint64_t base=0x1000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *s1_all=malloc(asz+16); uint8_t *s1=s1_all+8;
        memset(s1_all,0,asz+16); memset(s1_all,0xa5,8); memset(s1+asz,0xa5,8);
        uint8_t *m1_all=malloc(msz*total+16); uint8_t *m1=m1_all+8;
        memset(m1_all,0,msz*total+16); memset(m1_all,0xa5,8); memset(m1+msz*total,0xa5,8);
        uint8_t *s2_all=malloc(asz+16); uint8_t *s2=s2_all+8;
        memset(s2_all,0,asz+16); memset(s2_all,0xa5,8); memset(s2+asz,0xa5,8);
        uint8_t *m2_all=malloc(msz*total+16); uint8_t *m2=m2_all+8;
        memset(m2_all,0,msz*total+16); memset(m2_all,0xa5,8); memset(m2+msz*total,0xa5,8);
        uint8_t *sbs2=malloc(asz), *mbs2=malloc(msz*total);
        #define MIG() do{CHECK(buddy_guards_ok(s1_all,s1,asz,m1_all,m1,msz,pc,total));CHECK(buddy_guards_ok(s2_all,s2,asz,m2_all,m2,msz,pc,total));}while(0)
        CHECK(buddy_init(s1,base,pc,(struct MetaSlice){m1,pc}).code==0);
        MIG();
        CHECK(buddy_init(s2,base+pc*4096,pc,(struct MetaSlice){m2,pc}).code==0);
        MIG();
        CHECK(buddy_add_usable(s1,0,pc).code==0);
        MIG();
        CHECK(buddy_add_usable(s2,0,pc).code==0);
        MIG();
        struct Result r=buddy_alloc(s1,5);CHECK(r.code==0);
        MIG();
        CHECK(buddy_free_pages(s1).value==0);
        CHECK(buddy_free_pages(s2).value==pc);
        /* wrong allocator: actual recipient s2/m2 must be fully unchanged */
        memcpy(sbs2,s2,asz);memcpy(mbs2,m2,msz*total);
        CHECK(buddy_free(s2,r.value,5).code==E_INVALID_FREE);
        CHECK(!memcmp(s2,sbs2,asz)&&!memcmp(m2,mbs2,msz*total));
        MIG();
        #undef MIG
        free(s1_all);free(m1_all);free(s2_all);free(m2_all);free(sbs2);free(mbs2);
    }

    /* 2^20-page arena accepted; publish a 1024-page range and allocate order 10 */
    {
        uint64_t pc=(1ULL<<20); uint64_t base=0x1000000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16); memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16); memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        #define LG() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        struct Result r=buddy_init(st,base,pc,(struct MetaSlice){mt,pc});CHECK(r.code==0);
        LG();
        CHECK(buddy_add_usable(st,0,1024).code==0);
        LG();
        CHECK(buddy_free_pages(st).value==1024);
        r=buddy_alloc(st,10);CHECK(r.code==0);CHECK(r.value==base);
        LG();
        CHECK(buddy_free(st,r.value,10).code==0);
        LG();
        CHECK(buddy_free_pages(st).value==1024);
        #undef LG
        free(st_all);free(mt_all);
    }
    /* u64 end overflow: base + page_count*4096 exceeds u64 */
    {
        uint64_t pc=1; uint64_t base=0xfffffffffffff000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*(pc+2)+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*(pc+2)+16);
        memset(mt_all,0xa5,8); memset(mt+msz*(pc+2),0xa5,8);
        uint8_t *sbs=malloc(asz), *mbs=malloc(msz*(pc+2));
        buddy_init_empty(st);
        memcpy(sbs,st,asz);memcpy(mbs,mt,msz*(pc+2));
        struct Result r=buddy_init(st,base,pc,(struct MetaSlice){mt,pc+2});
        CHECK(r.code==E_INVALID_ARG);
        CHECK(!memcmp(st,sbs,asz)&&!memcmp(mt,mbs,msz*(pc+2)));
        for(int i=0;i<8;i++)CHECK(st_all[i]==0xa5&&st[asz+i]==0xa5);
        for(int i=0;i<8;i++)CHECK(mt_all[i]==0xa5&&mt[msz*(pc+2)+i]==0xa5);
        for(uint64_t j=pc;j<pc+2;j++)for(uint64_t k=0;k<msz;k++)CHECK(mt[j*msz+k]==0);
        free(st_all);free(mt_all);free(sbs);free(mbs);
    }
    /* R1: EMPTY init via Dong wrapper + sentinels + trailing metadata untouched */
    {
        uint64_t pc=64; uint64_t base=0x1000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*(pc+4)+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*(pc+4)+16);
        memset(mt_all,0xa5,8); memset(mt+msz*(pc+4),0xa5,8);
        #define GUARDS() do{for(int _i=0;_i<8;_i++){CHECK(st_all[_i]==0xa5&&st[asz+_i]==0xa5);CHECK(mt_all[_i]==0xa5&&mt[msz*(pc+4)+_i]==0xa5);}for(uint64_t _j=pc;_j<pc+4;_j++)for(uint64_t _k=0;_k<msz;_k++)CHECK(mt[_j*msz+_k]==0);}while(0)
        buddy_init_empty(st);
        struct Result r=buddy_init(st,base,pc,(struct MetaSlice){mt,pc+4});CHECK(r.code==0);
        GUARDS();
        CHECK(buddy_add_usable(st,0,pc).code==0);
        GUARDS();
        r=buddy_alloc(st,3);CHECK(r.code==0);
        GUARDS();
        CHECK(buddy_free(st,r.value,3).code==0);
        GUARDS();
        #undef GUARDS
        free(st_all);free(mt_all);
    }

    /* R1: failing ops leave full state+metadata unchanged (byte compare) */
    {
        uint64_t pc=64; uint64_t base=0x1000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16); memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16); memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        uint8_t *sbs=malloc(asz), *mbs=malloc(msz*total);
        buddy_init_empty(st);
        #define FG() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        #define SNAP() do{memcpy(sbs,st,asz);memcpy(mbs,mt,msz*total);}while(0)
        #define UNCH() do{CHECK(!memcmp(st,sbs,asz)&&!memcmp(mt,mbs,msz*total));FG();}while(0)
        CHECK(buddy_init(st,base,pc,(struct MetaSlice){mt,pc}).code==0);
        FG();
        CHECK(buddy_add_usable(st,0,pc).code==0);
        FG();
        struct Result r=buddy_alloc(st,3);CHECK(r.code==0);uint64_t a3=r.value;
        FG();
        CHECK(buddy_free(st,a3,3).code==0);
        FG();
        SNAP();CHECK(buddy_free(st,a3,3).code==E_INVALID_FREE);UNCH();
        r=buddy_alloc(st,0);CHECK(r.code==0);uint64_t a0=r.value;
        FG();
        SNAP();CHECK(buddy_free(st,a0+1,0).code==E_INVALID_FREE);UNCH();
        r=buddy_alloc(st,4);CHECK(r.code==0);uint64_t a4=r.value;
        FG();
        SNAP();CHECK(buddy_free(st,a4+PAGE,0).code==E_INVALID_FREE);UNCH();
        SNAP();CHECK(buddy_free(st,a4,3).code==E_INVALID_FREE);UNCH();
        SNAP();CHECK(buddy_free(st,a4,11).code==E_INVALID_FREE);UNCH();
        CHECK(buddy_free(st,a4,4).code==0);
        FG();
        #undef SNAP
        #undef UNCH
        #undef FG
        free(sbs);free(mbs);free(st_all);free(mt_all);
    }

    /* R1: publish a new reserved segment while an older allocation is held */
    {
        uint64_t pc=64; uint64_t base=0x1000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16); memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16); memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        buddy_init_empty(st);
        #define HG() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        CHECK(buddy_init(st,base,pc,(struct MetaSlice){mt,pc}).code==0);
        HG();
        CHECK(buddy_add_usable(st,0,32).code==0);
        HG();
        struct Result r=buddy_alloc(st,3);CHECK(r.code==0);uint64_t held=r.value;
        HG();
        CHECK(buddy_free_pages(st).value==24);
        CHECK(buddy_add_usable(st,32,32).code==0);
        HG();
        CHECK(buddy_free_pages(st).value==56);
        CHECK(buddy_free(st,held,3).code==0);
        HG();
        CHECK(buddy_free_pages(st).value==64);
        #undef HG
        free(st_all);free(mt_all);
    }

    /* R1: core.errors and mm.errors coexist with distinct codes */
    {
        CHECK(buddy_error_refs(0).code==0x02000001ULL);
        CHECK(buddy_error_refs(1).code==0x01000001ULL);
    }
    /* R2: full snapshot on all failure kinds + merged-block allocation */
    {
        uint64_t pc=64; uint64_t base=0x1000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16); memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16); memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        uint8_t *sbs=malloc(asz), *mbs=malloc(msz*total);
        buddy_init_empty(st);
        #define SNAP() do{memcpy(sbs,st,asz);memcpy(mbs,mt,msz*total);}while(0)
        #define UNCH() do{CHECK(!memcmp(st,sbs,asz));CHECK(!memcmp(mt,mbs,msz*total));CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total));}while(0)
        #define G() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        /* init failures leave state/metadata unchanged */
        SNAP();CHECK(buddy_init(st,base,0,(struct MetaSlice){mt,pc}).code==E_INVALID_ARG);UNCH();
        SNAP();CHECK(buddy_init(st,base,63,(struct MetaSlice){mt,pc}).code==E_INVALID_ARG);UNCH();
        SNAP();CHECK(buddy_init(st,base,64,(struct MetaSlice){mt,63}).code==E_META_SMALL);UNCH();
        CHECK(buddy_init(st,base,pc,(struct MetaSlice){mt,pc}).code==0);
        G();
        /* add_usable failures */
        SNAP();CHECK(buddy_add_usable(st,65,1).code==E_INVALID_ARG);UNCH();
        CHECK(buddy_add_usable(st,0,32).code==0);
        G();
        SNAP();CHECK(buddy_add_usable(st,16,32).code==E_RANGE_UNAVAIL);UNCH();
        CHECK(buddy_add_usable(st,32,32).code==0);
        G();
        /* alloc invalid order leaves state unchanged */
        SNAP();CHECK(buddy_alloc(st,11).code==E_INVALID_ORDER);UNCH();
        /* two 32-page halves merge into an order-6 block */
        struct Result r=buddy_alloc(st,6);CHECK(r.code==0);
        G();
        CHECK(buddy_free(st,r.value,6).code==0);
        G();
        CHECK(buddy_free_pages(st).value==64);
        G();
        #undef G
        free(sbs);free(mbs);free(st_all);free(mt_all);
    }
    /* R3: held allocation blocks larger merge until freed; extra snapshots */
    {
        uint64_t pc=64; uint64_t base=0x1000000ULL;
        uint64_t asz=buddy_allocator_size(), msz=buddy_meta_size();
        uint64_t total=pc+2;
        uint8_t *st_all=malloc(asz+16); uint8_t *st=st_all+8;
        memset(st_all,0,asz+16); memset(st_all,0xa5,8); memset(st+asz,0xa5,8);
        uint8_t *mt_all=malloc(msz*total+16); uint8_t *mt=mt_all+8;
        memset(mt_all,0,msz*total+16); memset(mt_all,0xa5,8); memset(mt+msz*total,0xa5,8);
        uint8_t *sbs=malloc(asz), *mbs=malloc(msz*total);
        buddy_init_empty(st);
        #define HG() CHECK(buddy_guards_ok(st_all,st,asz,mt_all,mt,msz,pc,total))
        CHECK(buddy_init(st,base,pc,(struct MetaSlice){mt,pc}).code==0);
        HG();
        CHECK(buddy_add_usable(st,0,32).code==0);
        HG();
        struct Result r=buddy_alloc(st,3);CHECK(r.code==0);uint64_t held=r.value;
        HG();
        CHECK(buddy_add_usable(st,32,32).code==0);
        HG();
        /* merged order-6 blocked while the early block is still held */
        memcpy(sbs,st,asz);memcpy(mbs,mt,msz*total);
        CHECK(buddy_alloc(st,6).code==E_OOM);
        CHECK(!memcmp(st,sbs,asz)&&!memcmp(mt,mbs,msz*total));HG();
        CHECK(buddy_free(st,held,3).code==0);
        HG();
        r=buddy_alloc(st,6);CHECK(r.code==0);
        HG();
        CHECK(buddy_free(st,r.value,6).code==0);
        HG();
        CHECK(buddy_free_pages(st).value==64);
        HG();
        /* more failure snapshots: bad base, double init, count out of range */
        uint8_t *st2_all=malloc(asz+16), *st2=st2_all+8;
        memset(st2_all,0xa5,8); memset(st2+asz,0xa5,8);
        uint8_t *mt2_all=malloc(msz*(pc+2)+16), *mt2=mt2_all+8;
        uint8_t *mbs2=malloc(msz*(pc+2));
        #define GU2() do{for(int _i=0;_i<8;_i++){CHECK(st2_all[_i]==0xa5&&st2[asz+_i]==0xa5);CHECK(mt2_all[_i]==0xa5&&mt2[msz*(pc+2)+_i]==0xa5);}for(uint64_t _j=pc;_j<pc+2;_j++)for(uint64_t _k=0;_k<msz;_k++)CHECK(mt2[_j*msz+_k]==0);}while(0)
        #define SNAP2() do{memcpy(sbs,st2,asz);memcpy(mbs2,mt2,msz*(pc+2));}while(0)
        #define UNCH2() do{CHECK(!memcmp(st2,sbs,asz));CHECK(!memcmp(mt2,mbs2,msz*(pc+2)));GU2();}while(0)
        memset(mt2_all,0xa5,8); memset(mt2+msz*(pc+2),0xa5,8);
        memset(mt2,0,msz*(pc+2));
        buddy_init_empty(st2);
        SNAP2();
        CHECK(buddy_init(st2,base+4096,pc,(struct MetaSlice){mt2,pc+2}).code==E_INVALID_ARG);
        UNCH2();
        CHECK(buddy_init(st2,base,pc,(struct MetaSlice){mt2,pc+2}).code==0);
        GU2();
        SNAP2();
        CHECK(buddy_init(st2,base,pc,(struct MetaSlice){mt2,pc+2}).code==E_ALREADY_INIT);
        UNCH2();
        SNAP2();
        CHECK(buddy_add_usable(st2,60,8).code==E_INVALID_ARG); /* count out of range */
        UNCH2();
        /* extreme free address / order leave state unchanged */
        SNAP2();
        CHECK(buddy_free(st2,0xffffffffffffffffULL,0).code==E_INVALID_FREE);
        UNCH2();
        SNAP2();
        CHECK(buddy_free(st2,0,0xffffffffffffffffULL).code==E_INVALID_FREE);
        UNCH2();
        /* u64 endpoint init failures leave state unchanged */
        { uint8_t *st3_all=malloc(asz+16),*st3=st3_all+8;
          memset(st3_all,0,asz+16); memset(st3_all,0xa5,8); memset(st3+asz,0xa5,8);
          uint8_t *mt3_all=malloc(msz*total+16),*mt3=mt3_all+8;
          memset(mt3_all,0,msz*total+16); memset(mt3_all,0xa5,8); memset(mt3+msz*total,0xa5,8);
          buddy_init_empty(st3);
          memcpy(sbs,st3,asz);memcpy(mbs,mt3,msz*total);
          CHECK(buddy_init(st3,0xffffffffffffffffULL,pc,(struct MetaSlice){mt3,pc}).code==E_INVALID_ARG);
          CHECK(!memcmp(st3,sbs,asz)&&!memcmp(mt3,mbs,msz*total));CHECK(buddy_guards_ok(st3_all,st3,asz,mt3_all,mt3,msz,pc,total));
          memcpy(sbs,st3,asz);memcpy(mbs,mt3,msz*total);
          CHECK(buddy_init(st3,base,0xffffffffffffffffULL,(struct MetaSlice){mt3,pc}).code==E_INVALID_ARG);
          CHECK(!memcmp(st3,sbs,asz)&&!memcmp(mt3,mbs,msz*total));CHECK(buddy_guards_ok(st3_all,st3,asz,mt3_all,mt3,msz,pc,total));
          free(st3_all);free(mt3_all); }
        #undef HG
        free(st2_all);free(mt2_all);free(mbs2);free(sbs);free(mbs);free(st_all);free(mt_all);
    }
    puts("native phys_buddy probes passed");return 0;
}

"""


class PhysBuddyTests(unittest.TestCase):
    def _roots(self):
        return [KERNEL, STD]

    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(KERNEL / "mm" / "phys_buddy.dg", roots=self._roots())
        self.assertEqual(["mm.errors", "mm.phys_buddy"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "buddy.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_buddy(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native phys_buddy checks require NASM and a SysV-capable GCC host compiler")
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
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native phys_buddy probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
