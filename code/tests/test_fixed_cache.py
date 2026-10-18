"""Independent C slot-model checks for mm.fixed_cache."""
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
import mm.fixed_cache as fc;
export("fc_cache_size") fn cache_size()usize{return sizeof(fc.Cache);}
export("fc_slot_size") fn slot_size()usize{return sizeof(fc.SlotMeta);}
export("fc_init_empty") fn init_empty(cache:*fc.Cache)void{unsafe{*cache=fc.EMPTY_CACHE;}}
export("fc_init") fn init(cache:*fc.Cache,buffer:[]u8,object_size:usize,alignment:usize,metadata:[]fc.SlotMeta)!void{unsafe{return fc.init(cache,buffer,object_size,alignment,metadata);}}
export("fc_alloc") fn alloc(cache:*fc.Cache)!*u8{unsafe{return fc.alloc(cache);}}
export("fc_free") fn free(cache:*fc.Cache,object:*u8)!void{unsafe{return fc.free(cache,object);}}
export("fc_free_count") fn free_count(cache:*const fc.Cache)!usize{unsafe{return fc.free_count(cache);}}
"""

C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"fixed_cache check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
#define E_NOT_INIT 0x02000001ULL
#define E_ALREADY_INIT 0x02000002ULL
#define E_INVALID_ARG 0x02000003ULL
#define E_META_SMALL 0x02000004ULL
#define E_OOM 0x02000007ULL
#define E_INVALID_FREE 0x02000008ULL
struct Result {uint64_t code;uint64_t value;};
struct Bytes {uint8_t *ptr;uint64_t len;};
extern uint64_t DG fc_cache_size(void),fc_slot_size(void);
extern void DG fc_init_empty(uint8_t*);
extern struct Result DG fc_init(uint8_t*,struct Bytes,uint64_t,uint64_t,struct Bytes);
extern struct Result DG fc_alloc(uint8_t*);
extern struct Result DG fc_free(uint8_t*,uint8_t*);
extern struct Result DG fc_free_count(const uint8_t*);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected fixed_cache panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
static uint8_t *align_up_ptr(uint8_t *p,uint64_t alignment){uintptr_t a=(uintptr_t)p;a=(a+alignment-1)&~(uintptr_t)(alignment-1);return (uint8_t*)a;}
static uint64_t rng_state;static uint64_t rng(void){rng_state^=rng_state<<13;rng_state^=rng_state>>7;rng_state^=rng_state<<17;return rng_state;}
/* Shared helper: Cache + guarded metadata (excess tail + sentinels) + whole buffer unchanged. */
static int fc_unchanged(const uint8_t *cb,const uint8_t *cb_s,uint64_t csz,
                        const uint8_t *mb,const uint8_t *mb_s,uint64_t mbytes,
                        const uint8_t *mb_all,uint64_t tail_bytes,
                        const uint8_t *buf,const uint8_t *buf_s,uint64_t buflen){
    if(memcmp(cb,cb_s,csz)!=0)return 0;
    if(memcmp(mb,mb_s,mbytes)!=0)return 0;
    if(memcmp(buf,buf_s,buflen)!=0)return 0;
    for(int i=0;i<8;i++){if(mb_all[i]!=0xa5)return 0;if(mb[tail_bytes+i]!=0xa5)return 0;}
    return 1;
}
int main(void){
    CHECK(fc_cache_size()>=32 && fc_slot_size()>=4);
    /* basic cycle */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size();
        uint64_t object_size=16,alignment=16,stride=16,capacity=64;
        uint64_t total=capacity+2;
        uint8_t *cb_all=malloc(csz+16), *cb=cb_all+8;
        memset(cb_all,0xa5,8); memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*total+16), *mb=mb_all+8;
        memset(mb_all,0,ssz*total+16); memset(mb_all,0xa5,8); memset(mb+ssz*total,0xa5,8);
        uint8_t *bufbase=malloc(stride*capacity+alignment+32);uint8_t *buf=align_up_ptr(bufbase+8,alignment);
        memset(buf-8,0xa5,8);memset(buf+stride*capacity,0xa5,8);
        memset(buf,0x51,stride*capacity);
        uint8_t expected[64*16]; memset(expected,0x51,64*16);
        uint8_t *cbs=malloc(csz), *mbs=malloc(ssz*total);
        fc_init_empty(cb);
        #define BC() do{for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(mb_all[_i]==0xa5&&mb[ssz*total+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[stride*capacity+_i]==0xa5);}for(uint64_t _j=capacity;_j<total;_j++)for(uint64_t _k=0;_k<ssz;_k++)CHECK(mb[_j*ssz+_k]==0);CHECK(!memcmp(buf,expected,stride*capacity));}while(0)
        struct Result r=fc_init(cb,(struct Bytes){buf,stride*capacity},object_size,alignment,(struct Bytes){mb,capacity});
        CHECK(r.code==0);
        BC();
        CHECK(fc_free_count(cb).value==capacity);
        BC();
        uint8_t *held[64];int held_n=0;
        for(int i=0;i<64;i++){r=fc_alloc(cb);CHECK(r.code==0);uint8_t *p=(uint8_t*)r.value;
            CHECK((uintptr_t)p%alignment==0);CHECK(p>=buf&&p<buf+stride*capacity);
            BC();
            held[held_n++]=p;}
        BC();
        CHECK(fc_free_count(cb).value==0);
        BC();
        memcpy(cbs,cb,csz);memcpy(mbs,mb,ssz*total);
        CHECK(fc_alloc(cb).code==E_OOM);
        CHECK(!memcmp(cb,cbs,csz)&&!memcmp(mb,mbs,ssz*total));
        BC();
        for(int i=0;i<64;i+=2){CHECK(fc_free(cb,held[i]).code==0);BC();}
        CHECK(fc_free_count(cb).value==32);
        BC();
        for(int i=0;i<32;i++){r=fc_alloc(cb);CHECK(r.code==0);BC();}
        CHECK(fc_free_count(cb).value==0);
        BC();
        #undef BC
        free(cb_all);free(mb_all);free(bufbase);free(cbs);free(mbs);
    }
    /* odd object size and randomized cross-check */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size();
        uint64_t object_size=5,alignment=8,stride=8,capacity=37;
        uint64_t total=capacity+2;
        uint8_t *cb_all=malloc(csz+16), *cb=cb_all+8;
        memset(cb_all,0xa5,8); memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*total+16), *mb=mb_all+8;
        uint8_t *bufbase=malloc(stride*capacity+alignment+8+32);uint8_t *buf=align_up_ptr(bufbase+8,alignment);
        memset(buf-8,0xa5,8);memset(buf+stride*capacity,0xa5,8);
        uint8_t *cbs=malloc(csz),*mbs=malloc(ssz*total),*bufs=malloc(stride*capacity);
        memset(mb_all,0,ssz*total+16);
        memset(mb_all,0xa5,8); memset(mb+ssz*total,0xa5,8);
        memset(buf,0x5a,stride*capacity);
        fc_init_empty(cb);
        CHECK(fc_init(cb,(struct Bytes){buf,stride*capacity},object_size,alignment,(struct Bytes){mb,capacity}).code==0);
        #define BF() do{for(int _i=0;_i<8;_i++)CHECK(buf[_i-8]==0xa5&&buf[stride*capacity+_i]==0xa5);}while(0)
        for(int _i=0;_i<8;_i++)CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);
        for(int _i=0;_i<8;_i++)CHECK(mb_all[_i]==0xa5&&mb[ssz*total+_i]==0xa5);
        BF();
        uint8_t *ref_alloc[37];uint8_t ref_used[37];uint8_t ref_tag[37];memset(ref_used,0,37);
        uint8_t expected[37*8]; memset(expected,0x5a,37*8);
        rng_state=0x123456789abcdef0ULL;
        int alive=0;
        for(int t=0;t<4000;t++){
            if(alive>0 && (rng()&3)==0){
                int idx=(int)(rng()%alive);uint8_t *p=ref_alloc[idx];
                uint64_t slot=((uintptr_t)p-(uintptr_t)buf)/stride;
                for(int i=0;i<8;i++)CHECK(p[i]==expected[slot*8+i]);
                CHECK(fc_free(cb,p).code==0);
                CHECK(!memcmp(buf,expected,stride*capacity));
                BF();
                for(int i=0;i<8;i++)CHECK(p[i]==expected[slot*8+i]);
                CHECK(ref_used[slot]==1);ref_used[slot]=0;
                ref_alloc[idx]=ref_alloc[alive-1];alive--;
            }else{
                struct Result r;
                if(alive<37){
                    r=fc_alloc(cb);CHECK(r.code==0);uint8_t *p=(uint8_t*)r.value;
                    uint64_t slot=((uintptr_t)p-(uintptr_t)buf)/stride;
                    CHECK(slot<capacity);CHECK(ref_used[slot]==0);ref_used[slot]=1;
                    for(int i=0;i<8;i++)CHECK(p[i]==expected[slot*8+i]);
                    CHECK(!memcmp(buf,expected,stride*capacity));
                    BF();
                    ref_tag[slot]=(uint8_t)(slot*7+3);
                    for(int i=0;i<5;i++){p[i]=(uint8_t)(ref_tag[slot]+i);expected[slot*8+i]=p[i];}
                    ref_alloc[alive++]=p;
                }else{
                    memcpy(cbs,cb,csz);memcpy(mbs,mb,ssz*total);memcpy(bufs,buf,stride*capacity);
                    r=fc_alloc(cb);
                    CHECK(r.code==E_OOM);
                    CHECK(!memcmp(cb,cbs,csz)&&!memcmp(mb,mbs,ssz*total)&&!memcmp(buf,bufs,stride*capacity));
                    BF();
                }
            }
            CHECK(fc_free_count(cb).value==(uint64_t)(capacity-alive));
            CHECK(!memcmp(buf, expected, stride*capacity));
            for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[stride*capacity+_i]==0xa5);}
            for(int _i=0;_i<8;_i++)CHECK(mb_all[_i]==0xa5&&mb[ssz*total+_i]==0xa5);
            for(uint64_t _j=capacity;_j<total;_j++)for(uint64_t _k=0;_k<ssz;_k++)CHECK(mb[_j*ssz+_k]==0);
        }
        #undef BF
        free(cb_all);free(mb_all);free(bufbase);free(cbs);free(mbs);free(bufs);
    }
    /* boundaries: object_size 1/4096, alignment 1/4096, one slot, tail */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size();
        uint8_t *cb_all=malloc(csz+16), *cb=cb_all+8;
        memset(cb_all,0xa5,8); memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*18+16), *mb=mb_all+8;
        memset(mb_all,0,ssz*18+16); memset(mb_all,0xa5,8); memset(mb+ssz*18,0xa5,8);
        uint8_t *bufbase=malloc(4096*16+4096+32);uint8_t *buf=align_up_ptr(bufbase+8,4096);
        memset(buf-8,0xa5,8);memset(buf+4096,0xa5,8);
        uint8_t expected4096[4096]; memset(expected4096,0x52,4096);
        uint8_t expected16[16]; memset(expected16,0x53,16);
        #define BG() do{for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(mb_all[_i]==0xa5&&mb[ssz*18+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[4096+_i]==0xa5);}for(uint64_t _j=16;_j<18;_j++)for(uint64_t _k=0;_k<ssz;_k++)CHECK(mb[_j*ssz+_k]==0);}while(0)
        memset(buf,0x52,4096);
        fc_init_empty(cb);
        CHECK(fc_init(cb,(struct Bytes){buf,4096},4096,4096,(struct Bytes){mb,1}).code==0);
        CHECK(!memcmp(buf,expected4096,4096));
        BG();
        CHECK(fc_free_count(cb).value==1);
        BG();
        struct Result r=fc_alloc(cb);CHECK(r.code==0);CHECK((uintptr_t)r.value==(uintptr_t)buf);
        CHECK(!memcmp(buf,expected4096,4096));
        BG();
        CHECK(fc_free(cb,(uint8_t*)r.value).code==0);
        CHECK(!memcmp(buf,expected4096,4096));
        BG();
        /* object_size 1, alignment 1 */
        fc_init_empty(cb);
        memset(buf,0x53,16);
        memset(buf+16,0xa5,8);   /* 16B-view back guard */
        CHECK(fc_init(cb,(struct Bytes){buf,16},1,1,(struct Bytes){mb,16}).code==0);
        CHECK(!memcmp(buf,expected16,16));
        for(int _i=0;_i<8;_i++)CHECK(buf[16+_i]==0xa5);
        BG();
        CHECK(fc_free_count(cb).value==16);
        for(int _i=0;_i<8;_i++)CHECK(buf[16+_i]==0xa5);
        BG();
        #undef BG
        free(cb_all);free(mb_all);free(bufbase);
    }
    /* error cases */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size();
        uint8_t *cb_all=malloc(csz+16),*cb=cb_all+8;
        memset(cb_all,0xa5,8);memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*10+16),*mb=mb_all+8;
        memset(mb_all,0,ssz*10+16);memset(mb_all,0xa5,8);memset(mb+ssz*10,0xa5,8);
        uint8_t *bufbase=malloc(128+16+16);uint8_t *buf=align_up_ptr(bufbase+8,16);
        memset(buf-8,0xa5,8);memset(buf+128,0xa5,8);
        fc_init_empty(cb);
        #define EGG() do{for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(mb_all[_i]==0xa5&&mb[ssz*10+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[128+_i]==0xa5);}for(uint64_t _j=8;_j<10;_j++)for(uint64_t _k=0;_k<ssz;_k++)CHECK(mb[_j*ssz+_k]==0);}while(0)
        /* uninitialized */
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8),*bsn=malloc(128);
          memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);memcpy(bsn,buf,128);
          CHECK(fc_alloc(cb).code==E_NOT_INIT);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          CHECK(fc_free(cb,buf).code==E_NOT_INIT);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          CHECK(fc_free_count(cb).code==E_NOT_INIT);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          free(csn);free(msn);free(bsn); }
        EGG();
        /* bad object_size/alignment */
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8),*bsn=malloc(128);
          memset(buf,0x93,128);
          memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);memcpy(bsn,buf,128);
          CHECK(fc_init(cb,(struct Bytes){buf,64},0,16,(struct Bytes){mb,8}).code==E_INVALID_ARG);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          free(csn);free(msn);free(bsn); }
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8),*bsn=malloc(128);
          memset(buf,0x91,128);
          memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);memcpy(bsn,buf,128);
          CHECK(fc_init(cb,(struct Bytes){buf,64},4097,16,(struct Bytes){mb,8}).code==E_INVALID_ARG);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          CHECK(fc_init(cb,(struct Bytes){buf,64},16,3,(struct Bytes){mb,8}).code==E_INVALID_ARG);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          CHECK(fc_init(cb,(struct Bytes){buf,64},16,0,(struct Bytes){mb,8}).code==E_INVALID_ARG);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          free(csn);free(msn);free(bsn); }
        EGG();
        /* empty buffer, NULL buffer, metadata too small */
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8),*bsn=malloc(128);
          memset(buf,0x95,128);
          memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);memcpy(bsn,buf,128);
          CHECK(fc_init(cb,(struct Bytes){buf,0},16,16,(struct Bytes){mb,8}).code==E_INVALID_ARG);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          free(csn);free(msn);free(bsn); }
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8),*bsn=malloc(128);
          memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);memcpy(bsn,buf,128);
          CHECK(fc_init(cb,(struct Bytes){NULL,16},16,16,(struct Bytes){mb,2}).code==E_INVALID_ARG);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          free(csn);free(msn);free(bsn); }
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8),*bsn=malloc(128);
          memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);memcpy(bsn,buf,128);
          CHECK(fc_init(cb,(struct Bytes){buf,64},16,16,(struct Bytes){mb,3}).code==E_META_SMALL);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          free(csn);free(msn);free(bsn); }
        EGG();
        /* valid init */
        memset(buf,0x96,128);
        uint8_t eerr[128]; memset(eerr,0x96,128);
        CHECK(fc_init(cb,(struct Bytes){buf,64},16,16,(struct Bytes){mb,4}).code==0);
        CHECK(!memcmp(buf,eerr,128));
        EGG();
        /* double init */
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8),*bsn=malloc(128);
          memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);memcpy(bsn,buf,128);
          CHECK(fc_init(cb,(struct Bytes){buf,64},16,16,(struct Bytes){mb,4}).code==E_ALREADY_INIT);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));
          EGG();
          free(csn);free(msn);free(bsn); }
        EGG();
        /* invalid free: null, padding, tail, out of range */
        struct Result r=fc_alloc(cb);CHECK(r.code==0);uint8_t *p=(uint8_t*)r.value;
        CHECK(!memcmp(buf,eerr,128));
        EGG();
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8),*bsn=malloc(128);
          #define SNAP() do{memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);memcpy(bsn,buf,128);}while(0)
          #define UNCH() do{CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8)&&!memcmp(buf,bsn,128));EGG();}while(0)
          SNAP();CHECK(fc_free(cb,NULL).code==E_INVALID_FREE);UNCH();
          SNAP();CHECK(fc_free(cb,p+1).code==E_INVALID_FREE);UNCH();
          SNAP();CHECK(fc_free(cb,buf+64).code==E_INVALID_FREE);UNCH();
          SNAP();CHECK(fc_free(cb,p+16).code==E_INVALID_FREE);UNCH();
          CHECK(fc_free(cb,p).code==0);
          CHECK(!memcmp(buf,eerr,128));
          EGG();
          SNAP();CHECK(fc_free(cb,p).code==E_INVALID_FREE);UNCH();
          #undef SNAP
          #undef UNCH
          free(csn);free(msn);free(bsn); }
        EGG();
        #undef EGG
        free(cb_all);free(mb_all);free(bufbase);
    }
    /* R1: address-range overflow, payload integrity, real padding, snapshots */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size();
        uint8_t *cb_all=malloc(csz+16),*cb=cb_all+8;
        memset(cb_all,0xa5,8);memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*10+16),*mb=mb_all+8;
        memset(mb_all,0,ssz*10+16);memset(mb_all,0xa5,8);memset(mb+ssz*10,0xa5,8);
        uint8_t *bufbase=malloc(128+16+16);uint8_t *buf=align_up_ptr(bufbase+8,16);
        memset(buf-8,0xa5,8);memset(buf+128,0xa5,8);
        #define RG() do{for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(mb_all[_i]==0xa5&&mb[ssz*10+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[128+_i]==0xa5);}for(uint64_t _j=8;_j<10;_j++)for(uint64_t _k=0;_k<ssz;_k++)CHECK(mb[_j*ssz+_k]==0);}while(0)
        /* address range overflow near u64 max must be rejected, state unchanged */
        fc_init_empty(cb);
        uint8_t *fake=(uint8_t*)(uintptr_t)0xfffffffffffffff0ULL;
        { uint8_t *csn=malloc(csz),*msn=malloc(ssz*8);
          memcpy(csn,cb,csz);memcpy(msn,mb,ssz*8);
          CHECK(fc_init(cb,(struct Bytes){fake,32},16,16,(struct Bytes){mb,2}).code==E_INVALID_ARG);
          CHECK(!memcmp(cb,csn,csz)&&!memcmp(mb,msn,ssz*8));
          free(csn);free(msn); }
        RG();
        CHECK(fc_free_count(cb).code==E_NOT_INIT);
        RG();
        /* real padding: object_size 5, align 8 -> stride 8, pad bytes 5..7 */
        memset(buf,0xcc,48);
        uint8_t e48[48]; memset(e48,0xcc,48);
        fc_init_empty(cb);
        CHECK(fc_init(cb,(struct Bytes){buf,48},5,8,(struct Bytes){mb,6}).code==0);
        CHECK(!memcmp(buf,e48,48));
        RG();
        struct Result r=fc_alloc(cb);CHECK(r.code==0);uint8_t *p0=(uint8_t*)r.value;
        CHECK((uintptr_t)p0%8==0);
        /* alloc must not write any payload byte or padding: still pre-fill 0xcc */
        CHECK(p0[0]==0xcc&&p0[1]==0xcc&&p0[2]==0xcc&&p0[3]==0xcc&&p0[4]==0xcc&&p0[5]==0xcc&&p0[6]==0xcc&&p0[7]==0xcc);
        CHECK(!memcmp(buf,e48,48));
        RG();
        for(int i=0;i<5;i++){p0[i]=(uint8_t)(0x10+i);e48[i]=p0[i];}
        r=fc_alloc(cb);CHECK(r.code==0);uint8_t *p1=(uint8_t*)r.value;
        CHECK(p1[0]==0xcc&&p1[1]==0xcc&&p1[2]==0xcc&&p1[3]==0xcc&&p1[4]==0xcc&&p1[5]==0xcc&&p1[6]==0xcc&&p1[7]==0xcc);
        CHECK(!memcmp(buf,e48,48));
        RG();
        for(int i=0;i<5;i++){p1[i]=(uint8_t)(0x20+i);e48[8+i]=p1[i];}
        /* payload intact, padding untouched after both allocs */
        CHECK(p0[0]==0x10&&p0[1]==0x11&&p0[2]==0x12&&p0[3]==0x13&&p0[4]==0x14&&p0[5]==0xcc&&p0[6]==0xcc&&p0[7]==0xcc);
        CHECK(p1[0]==0x20&&p1[1]==0x21&&p1[2]==0x22&&p1[3]==0x23&&p1[4]==0x24);
        CHECK(!memcmp(buf,e48,48));
        RG();
        CHECK(fc_free(cb,p0).code==0);
        CHECK(!memcmp(buf,e48,48));
        RG();
        CHECK(fc_free(cb,p1).code==0);
        CHECK(!memcmp(buf,e48,48));
        RG();
        /* freed slots retain object bytes AND padding (free must not write either) */
        CHECK(p0[0]==0x10&&p0[1]==0x11&&p0[2]==0x12&&p0[3]==0x13&&p0[4]==0x14&&p0[5]==0xcc&&p0[6]==0xcc&&p0[7]==0xcc);
        CHECK(p1[0]==0x20&&p1[1]==0x21&&p1[2]==0x22&&p1[3]==0x23&&p1[4]==0x24&&p1[5]==0xcc&&p1[6]==0xcc&&p1[7]==0xcc);
        /* failure snapshots: full Cache/metadata/buffer unchanged */
        uint8_t *cs=malloc(csz),*ms=malloc(ssz*8),*bs=malloc(128);
        fc_init_empty(cb);
        memset(buf,0xcd,128);
        uint8_t e128[128]; memset(e128,0xcd,128);
        CHECK(fc_init(cb,(struct Bytes){buf,128},16,16,(struct Bytes){mb,8}).code==0);
        CHECK(!memcmp(buf,e128,128));
        RG();
        #define S3() do{memcpy(cs,cb,csz);memcpy(ms,mb,ssz*8);memcpy(bs,buf,128);}while(0)
        #define K3() do{CHECK(!memcmp(cb,cs,csz));CHECK(!memcmp(mb,ms,ssz*8));CHECK(!memcmp(buf,bs,128));RG();}while(0)
        r=fc_alloc(cb);CHECK(r.code==0);uint8_t *q=(uint8_t*)r.value;
        CHECK(!memcmp(buf,e128,128));
        RG();
        S3();CHECK(fc_free(cb,q+1).code==E_INVALID_FREE);K3();
        S3();CHECK(fc_free(cb,NULL).code==E_INVALID_FREE);K3();
        CHECK(fc_free(cb,q).code==0);
        CHECK(!memcmp(buf,e128,128));
        RG();
        S3();CHECK(fc_free(cb,q).code==E_INVALID_FREE);K3();
        RG();
        /* OOM snapshot */
        for(int i=0;i<8;i++){r=fc_alloc(cb);CHECK(r.code==0);CHECK(!memcmp(buf,e128,128));RG();}
        RG();
        S3();CHECK(fc_alloc(cb).code==E_OOM);K3();
        free(cs);free(ms);free(bs);free(cb_all);free(mb_all);free(bufbase);
        #undef RG
    }
    /* R1: two independent instances and wrong-instance free */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size();
        uint8_t *c1_all=malloc(csz+16),*c1=c1_all+8;
        uint8_t *c2_all=malloc(csz+16),*c2=c2_all+8;
        memset(c1_all,0xa5,8);memset(c1+csz,0xa5,8);
        memset(c2_all,0xa5,8);memset(c2+csz,0xa5,8);
        uint8_t *m1_all=malloc(ssz*4+16),*m1=m1_all+8;
        uint8_t *m2_all=malloc(ssz*4+16),*m2=m2_all+8;
        memset(m1_all,0xa5,8);memset(m1+ssz*4,0xa5,8);
        memset(m2_all,0xa5,8);memset(m2+ssz*4,0xa5,8);
        uint8_t *b1g=malloc(64+16+16),*b1=align_up_ptr(b1g+8,16);
        uint8_t *b2g=malloc(64+16+16),*b2=align_up_ptr(b2g+8,16);
        memset(b1-8,0xa5,8);memset(b1+64,0xa5,8);
        memset(b2-8,0xa5,8);memset(b2+64,0xa5,8);
        memset(b1,0x61,64);memset(b2,0x62,64);
        uint8_t e1[64],e2[64]; memset(e1,0x61,64); memset(e2,0x62,64);
        #define O2() do{for(int _i=0;_i<8;_i++){CHECK(c1_all[_i]==0xa5&&c1[csz+_i]==0xa5);CHECK(c2_all[_i]==0xa5&&c2[csz+_i]==0xa5);CHECK(m1_all[_i]==0xa5&&m1[ssz*4+_i]==0xa5);CHECK(m2_all[_i]==0xa5&&m2[ssz*4+_i]==0xa5);CHECK(b1[_i-8]==0xa5&&b1[64+_i]==0xa5);CHECK(b2[_i-8]==0xa5&&b2[64+_i]==0xa5);}}while(0)
        fc_init_empty(c1);fc_init_empty(c2);
        CHECK(fc_init(c1,(struct Bytes){b1,64},16,16,(struct Bytes){m1,4}).code==0);
        CHECK(!memcmp(b1,e1,64));
        O2();
        CHECK(fc_init(c2,(struct Bytes){b2,64},16,16,(struct Bytes){m2,4}).code==0);
        CHECK(!memcmp(b2,e2,64));
        O2();
        struct Result r=fc_alloc(c1);CHECK(r.code==0);uint8_t *p=(uint8_t*)r.value;
        CHECK(!memcmp(b1,e1,64));
        O2();
        { uint8_t *c2_s=malloc(csz),*m2_s=malloc(ssz*4),*b2_s=malloc(64);
          memcpy(c2_s,c2,csz);memcpy(m2_s,m2,ssz*4);memcpy(b2_s,b2,64);
          CHECK(fc_free(c2,p).code==E_INVALID_FREE);
          CHECK(!memcmp(c2,c2_s,csz)&&!memcmp(m2,m2_s,ssz*4)&&!memcmp(b2,b2_s,64));
          free(c2_s);free(m2_s);free(b2_s); }
        O2();
        CHECK(fc_free(c1,p).code==0);
        CHECK(!memcmp(b1,e1,64));
        O2();
        #undef O2
        free(c1_all);free(c2_all);free(m1_all);free(m2_all);free(b1g);free(b2g);
    }
    /* R2: real tail remainder + full buffer expectation */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size();
        uint8_t *cb_all=malloc(csz+16),*cb=cb_all+8;
        memset(cb_all,0xa5,8);memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*8+16),*mb=mb_all+8;
        memset(mb_all,0,ssz*8+16);memset(mb_all,0xa5,8);memset(mb+ssz*8,0xa5,8);
        uint8_t *bufbase=malloc(100+16+16);uint8_t *buf=align_up_ptr(bufbase+8,16);
        memset(buf-8,0xa5,8);memset(buf+100,0xa5,8);
        memset(buf,0x5a,100);
        uint8_t expected[100]; memset(expected,0x5a,100);
        fc_init_empty(cb);
        #define TG() do{for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(mb_all[_i]==0xa5&&mb[ssz*8+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[100+_i]==0xa5);}for(uint64_t _j=6;_j<8;_j++)for(uint64_t _k=0;_k<ssz;_k++)CHECK(mb[_j*ssz+_k]==0);CHECK(!memcmp(buf,expected,100));}while(0)
        /* stride 16, capacity 6, tail = 100 - 96 = 4 bytes */
        CHECK(fc_init(cb,(struct Bytes){buf,100},16,16,(struct Bytes){mb,6}).code==0);
        TG();
        CHECK(fc_free_count(cb).value==6);
        TG();
        struct Result r=fc_alloc(cb);CHECK(r.code==0);uint8_t *p=(uint8_t*)r.value;
        for(int i=0;i<16;i++)CHECK(p[i]==0x5a);           /* alloc no write */
        TG();
        for(int i=0;i<16;i++){p[i]=(uint8_t)(0x30+i);expected[i]=p[i];}
        CHECK(fc_free(cb,p).code==0);
        TG();
        for(int i=0;i<16;i++)CHECK(p[i]==(uint8_t)(0x30+i)); /* object retained */
        #undef TG
        free(cb_all);free(mb_all);free(bufbase);
    }
    /* R2: two-instance interleaved operations with guarded data/metadata */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size(),cap=4,total=cap+2;
        uint8_t *c1_all=malloc(csz+16),*c1=c1_all+8;
        uint8_t *c2_all=malloc(csz+16),*c2=c2_all+8;
        memset(c1_all,0xa5,8);memset(c1+csz,0xa5,8);
        memset(c2_all,0xa5,8);memset(c2+csz,0xa5,8);
        uint8_t *m1_all=malloc(ssz*total+16),*m1=m1_all+8;
        uint8_t *m2_all=malloc(ssz*total+16),*m2=m2_all+8;
        uint8_t *b1g=malloc(64+16+16),*b1=align_up_ptr(b1g+8,16);
        uint8_t *b2g=malloc(64+16+16),*b2=align_up_ptr(b2g+8,16);
        memset(b1-8,0xa5,8);memset(b1+64,0xa5,8);
        memset(b2-8,0xa5,8);memset(b2+64,0xa5,8);
        memset(m1_all,0,ssz*total+16);memset(m1_all,0xa5,8);memset(m1+ssz*total,0xa5,8);
        memset(m2_all,0,ssz*total+16);memset(m2_all,0xa5,8);memset(m2+ssz*total,0xa5,8);
        memset(b1,0x71,64);memset(b2,0x72,64);
        uint8_t b1e[64],b2e[64];memset(b1e,0x71,64);memset(b2e,0x72,64);
        uint8_t *c1_s=malloc(csz),*c2_s=malloc(csz),*m1_s=malloc(ssz*total),*m2_s=malloc(ssz*total),*b1_s=malloc(64),*b2_s=malloc(64);
        #define GG() do{for(int _i=0;_i<8;_i++){CHECK(c1_all[_i]==0xa5&&c1[csz+_i]==0xa5);CHECK(c2_all[_i]==0xa5&&c2[csz+_i]==0xa5);CHECK(m1_all[_i]==0xa5&&m1[ssz*total+_i]==0xa5);CHECK(m2_all[_i]==0xa5&&m2[ssz*total+_i]==0xa5);CHECK(b1[_i-8]==0xa5&&b1[64+_i]==0xa5);CHECK(b2[_i-8]==0xa5&&b2[64+_i]==0xa5);}for(uint64_t _j=cap;_j<total;_j++)for(uint64_t _k=0;_k<ssz;_k++){CHECK(m1[_j*ssz+_k]==0);CHECK(m2[_j*ssz+_k]==0);}CHECK(!memcmp(b1,b1e,64));CHECK(!memcmp(b2,b2e,64));}while(0)
        #define FSN() do{memcpy(c1_s,c1,csz);memcpy(c2_s,c2,csz);memcpy(m1_s,m1,ssz*total);memcpy(m2_s,m2,ssz*total);memcpy(b1_s,b1,64);memcpy(b2_s,b2,64);}while(0)
        #define FCH() do{CHECK(!memcmp(c1,c1_s,csz));CHECK(!memcmp(c2,c2_s,csz));CHECK(!memcmp(m1,m1_s,ssz*total));CHECK(!memcmp(m2,m2_s,ssz*total));CHECK(!memcmp(b1,b1_s,64));CHECK(!memcmp(b2,b2_s,64));GG();}while(0)
        fc_init_empty(c1);fc_init_empty(c2);
        CHECK(fc_init(c1,(struct Bytes){b1,64},16,16,(struct Bytes){m1,cap}).code==0);
        GG();
        CHECK(fc_init(c2,(struct Bytes){b2,64},16,16,(struct Bytes){m2,cap}).code==0);
        GG();
        struct Result r1=fc_alloc(c1);CHECK(r1.code==0);uint8_t *p1=(uint8_t*)r1.value;
        for(int i=0;i<16;i++)CHECK(p1[i]==0x71);
        GG();
        struct Result r2=fc_alloc(c2);CHECK(r2.code==0);uint8_t *p2=(uint8_t*)r2.value;
        for(int i=0;i<16;i++)CHECK(p2[i]==0x72);
        GG();
        for(int i=0;i<16;i++){p1[i]=(uint8_t)(0x20+i);p2[i]=(uint8_t)(0x40+i);b1e[i]=p1[i];b2e[i]=p2[i];}
        FSN();CHECK(fc_free(c1,p2).code==E_INVALID_FREE);FCH();
        FSN();CHECK(fc_free(c2,p1).code==E_INVALID_FREE);FCH();
        for(int i=0;i<16;i++)CHECK(p1[i]==(uint8_t)(0x20+i));
        for(int i=0;i<16;i++)CHECK(p2[i]==(uint8_t)(0x40+i));
        CHECK(fc_free(c1,p1).code==0);
        GG();
        CHECK(fc_free(c2,p2).code==0);
        GG();
        for(int i=0;i<16;i++)CHECK(p1[i]==(uint8_t)(0x20+i));
        for(int i=0;i<16;i++)CHECK(p2[i]==(uint8_t)(0x40+i));
        #undef GG
        #undef FSN
        #undef FCH
        free(c1_all);free(c2_all);free(m1_all);free(m2_all);free(b1g);free(b2g);free(c1_s);free(c2_s);free(m1_s);free(m2_s);free(b1_s);free(b2_s);
    }
    /* R2: init failures preserve full buffer + guarded metadata (excess tail + sentinels) */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size();
        uint8_t *cb_all=malloc(csz+16),*cb=cb_all+8;
        memset(cb_all,0xa5,8); memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*(4+2)+16), *mb=mb_all+8;
        uint8_t *bufbase=malloc(64+16+16); uint8_t *buf=align_up_ptr(bufbase+8,16);
        memset(buf-8,0xa5,8); memset(buf+64,0xa5,8);
        uint8_t *cb_s=malloc(csz), *mb_s=malloc(ssz*(4+2)), *buf_s=malloc(64);
        memset(buf,0x7e,64);
        memset(mb_all,0xa5,8); memset(mb+ssz*(4+2),0xa5,8); memset(mb,0,ssz*(4+2));
        fc_init_empty(cb);
        #define SNAPFC() do{memcpy(cb_s,cb,csz);memcpy(mb_s,mb,ssz*(4+2));memcpy(buf_s,buf,64);}while(0)
        #define UNCHFC() do{CHECK(!memcmp(cb,cb_s,csz));CHECK(!memcmp(mb,mb_s,ssz*(4+2)));CHECK(!memcmp(buf,buf_s,64));for(int _i=0;_i<8;_i++){CHECK(mb_all[_i]==0xa5&&mb[ssz*(4+2)+_i]==0xa5);CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[64+_i]==0xa5);}}while(0)
        SNAPFC();
        CHECK(fc_init(cb,(struct Bytes){buf,64},0,16,(struct Bytes){mb,4}).code==E_INVALID_ARG);
        UNCHFC();
        SNAPFC();
        CHECK(fc_init(cb,(struct Bytes){NULL,16},16,16,(struct Bytes){mb,2}).code==E_INVALID_ARG);
        UNCHFC();
        #undef SNAPFC
        #undef UNCHFC
        free(cb_all);free(mb_all);free(cb_s);free(mb_s);free(buf_s);free(bufbase);
    }
    /* R2: all post-init failure kinds preserve Cache/guarded metadata/whole buffer */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size(),cap=4;
        uint64_t tail=ssz*(cap+2);
        uint8_t *cb_all=malloc(csz+16),*cb=cb_all+8;
        memset(cb_all,0xa5,8); memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(tail+16), *mb=mb_all+8;
        uint8_t *bufbase=malloc(64+16+16); uint8_t *buf=align_up_ptr(bufbase+8,16);
        memset(buf-8,0xa5,8); memset(buf+64,0xa5,8);
        uint8_t *cb_s=malloc(csz), *mb_s=malloc(tail), *buf_s=malloc(64);
        memset(buf,0x6d,64);
        memset(mb_all,0xa5,8); memset(mb+tail,0xa5,8); memset(mb,0,tail);
        fc_init_empty(cb);
        #define SNAPX() do{memcpy(cb_s,cb,csz);memcpy(mb_s,mb,tail);memcpy(buf_s,buf,64);}while(0)
        #define UNCHX() do{CHECK(fc_unchanged(cb,cb_s,csz,mb,mb_s,tail,mb_all,tail,buf,buf_s,64));for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[64+_i]==0xa5);}}while(0)
        SNAPX(); CHECK(fc_init(cb,(struct Bytes){buf,64},16,16,(struct Bytes){mb,cap-1}).code==E_META_SMALL); UNCHX();
        CHECK(fc_init(cb,(struct Bytes){buf,64},16,16,(struct Bytes){mb,cap}).code==0);
        CHECK(!memcmp(buf,buf_s,64));
        for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[64+_i]==0xa5);}
        SNAPX(); CHECK(fc_init(cb,(struct Bytes){buf,64},16,16,(struct Bytes){mb,cap}).code==E_ALREADY_INIT); UNCHX();
        SNAPX(); CHECK(fc_free(cb,buf+64).code==E_INVALID_FREE); UNCHX();
        #undef SNAPX
        #undef UNCHX
        free(cb_all);free(mb_all);free(cb_s);free(mb_s);free(buf_s);free(bufbase);
    }
    /* R2: success init/alloc/free leave excess metadata tail (beyond capacity) untouched */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size(),cap=4;
        uint64_t mlen=cap+2;
        uint8_t *cb_all=malloc(csz+16), *cb=cb_all+8;
        memset(cb_all,0xa5,8); memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*mlen+16), *mb=mb_all+8;
        memset(mb_all,0xa5,8); memset(mb+ssz*mlen,0xa5,8);
        uint8_t *bufbase=malloc(64+16+16); uint8_t *buf=align_up_ptr(bufbase+8,16);
        memset(buf-8,0xa5,8); memset(buf+64,0xa5,8);
        memset(buf,0x7a,64);
        uint8_t expected[64]; memset(expected,0x7a,64);
        memset(mb,0,ssz*cap);
        for(uint64_t j=cap;j<mlen;j++)for(uint64_t k=0;k<ssz;k++)mb[j*ssz+k]=0x5c;
        fc_init_empty(cb);
        #define XG() do{for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(mb_all[_i]==0xa5&&mb[ssz*mlen+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[64+_i]==0xa5);}CHECK(!memcmp(buf,expected,64));}while(0)
        CHECK(fc_init(cb,(struct Bytes){buf,64},16,16,(struct Bytes){mb,mlen}).code==0);
        for(uint64_t j=cap;j<mlen;j++)for(uint64_t k=0;k<ssz;k++)CHECK(mb[j*ssz+k]==0x5c);
        XG();
        struct Result r=fc_alloc(cb);CHECK(r.code==0);uint8_t *p=(uint8_t*)r.value;
        for(uint64_t j=cap;j<mlen;j++)for(uint64_t k=0;k<ssz;k++)CHECK(mb[j*ssz+k]==0x5c);
        XG();
        CHECK(fc_free(cb,p).code==0);
        for(uint64_t j=cap;j<mlen;j++)for(uint64_t k=0;k<ssz;k++)CHECK(mb[j*ssz+k]==0x5c);
        XG();
        #undef XG
        free(cb_all);free(mb_all);free(bufbase);
    }
    /* R2: uninitialized + wrong-instance failures keep Cache/metadata/buffer */
    {
        uint64_t csz=fc_cache_size(),ssz=fc_slot_size(),cap=4,total=cap+2;
        uint8_t *cb_all=malloc(csz+16), *cb=cb_all+8;
        memset(cb_all,0xa5,8); memset(cb+csz,0xa5,8);
        uint8_t *mb_all=malloc(ssz*total+16), *mb=mb_all+8;
        uint8_t *bufbase=malloc(64+16+16); uint8_t *buf=align_up_ptr(bufbase+8,16);
        memset(buf-8,0xa5,8); memset(buf+64,0xa5,8);
        uint8_t *cb_s=malloc(csz), *mb_s=malloc(ssz*total), *buf_s=malloc(64);
        memset(mb_all,0,ssz*total+16); memset(mb_all,0xa5,8); memset(mb+ssz*total,0xa5,8);
        memset(buf,0x64,64);
        fc_init_empty(cb);
        #define US() do{memcpy(cb_s,cb,csz);memcpy(mb_s,mb,ssz*total);memcpy(buf_s,buf,64);}while(0)
        #define GS() do{for(int _i=0;_i<8;_i++){CHECK(cb_all[_i]==0xa5&&cb[csz+_i]==0xa5);CHECK(buf[_i-8]==0xa5&&buf[64+_i]==0xa5);}}while(0)
        #define UC() do{CHECK(fc_unchanged(cb,cb_s,csz,mb,mb_s,ssz*total,mb_all,ssz*total,buf,buf_s,64));GS();}while(0)
        US(); CHECK(fc_alloc(cb).code==E_NOT_INIT); UC();
        US(); CHECK(fc_free(cb,buf).code==E_NOT_INIT); UC();
        US(); CHECK(fc_free_count(cb).code==E_NOT_INIT); UC();
        CHECK(fc_init(cb,(struct Bytes){buf,64},16,16,(struct Bytes){mb,cap}).code==0);
        GS(); CHECK(!memcmp(buf,buf_s,64));
        { uint8_t *c2_all=malloc(csz+16), *c2=c2_all+8;
          memset(c2_all,0xa5,8); memset(c2+csz,0xa5,8);
          uint8_t *m2_all=malloc(ssz*total+16), *m2=m2_all+8;
          uint8_t *b2g=malloc(64+16+16); uint8_t *b2=align_up_ptr(b2g+8,16);
          memset(b2-8,0xa5,8); memset(b2+64,0xa5,8);
          uint8_t *c2_s=malloc(csz), *m2_s=malloc(ssz*total), *b2_s=malloc(64);
          uint8_t b2e[64]; memset(b2e,0x65,64);
          memset(m2_all,0,ssz*total+16); memset(m2_all,0xa5,8); memset(m2+ssz*total,0xa5,8);
          memset(b2,0x65,64);
          fc_init_empty(c2);
          CHECK(fc_init(c2,(struct Bytes){b2,64},16,16,(struct Bytes){m2,cap}).code==0);
          /* immediate observation of the actual recipient after its success init */
          for(int _i=0;_i<8;_i++){CHECK(c2_all[_i]==0xa5&&c2[csz+_i]==0xa5);CHECK(b2[_i-8]==0xa5&&b2[64+_i]==0xa5);}
          CHECK(!memcmp(b2,b2e,64));
          struct Result r=fc_alloc(cb);CHECK(r.code==0);
          /* immediate observation of the owner after its alloc */
          GS(); CHECK(!memcmp(buf,buf_s,64));
          /* snapshot both the receiving instance and the owner BEFORE the failing call */
          memcpy(c2_s,c2,csz);memcpy(m2_s,m2,ssz*total);memcpy(b2_s,b2,64);
          US();
          CHECK(fc_free(c2,(uint8_t*)r.value).code==E_INVALID_FREE);
          CHECK(fc_unchanged(c2,c2_s,csz,m2,m2_s,ssz*total,m2_all,ssz*total,b2,b2_s,64));
          for(int _i=0;_i<8;_i++){CHECK(c2_all[_i]==0xa5&&c2[csz+_i]==0xa5);CHECK(b2[_i-8]==0xa5&&b2[64+_i]==0xa5);}
          /* and the owning instance stays isolated */
          UC();
          free(c2_all);free(m2_all);free(b2g);free(c2_s);free(m2_s);free(b2_s); }
        #undef US
        #undef UC
        #undef GS
        free(cb_all);free(mb_all);free(cb_s);free(mb_s);free(buf_s);free(bufbase);
    }
    puts("native fixed_cache probes passed");return 0;
}
"""


class FixedCacheTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(KERNEL / "mm" / "fixed_cache.dg", roots=[KERNEL, STD])
        self.assertEqual(["mm.errors", "mm.fixed_cache"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "cache.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_fixed_cache(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native fixed_cache checks require NASM and a SysV-capable GCC host compiler")
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
                    self.assertIn("native fixed_cache probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
