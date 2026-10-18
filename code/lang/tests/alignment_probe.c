/* Independent C address/layout checks; no compiler-generated constants. */
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DG __attribute__((sysv_abi))
struct Slice {uint64_t *ptr;uint64_t len;};
struct __attribute__((aligned(64))) Inner {uint8_t tag;uint64_t data[2];};
struct Outer {uint8_t tag;struct Inner blocks[2];};
_Static_assert(sizeof(struct Inner)==64,"independent Inner size");
_Static_assert(offsetof(struct Inner,data)==8,"independent data offset");
_Static_assert(sizeof(struct Outer)==192,"independent Outer size");
_Static_assert(offsetof(struct Outer,blocks)==64,"independent blocks offset");
extern uint64_t DG dg_align32(uint64_t),dg_align64(uint64_t),dg_align256(uint64_t),dg_align1024(void);
extern uint64_t DG dg_align_temp32(void),dg_align_temp64(void),dg_align_temp256(void),dg_align_temp1024(void);
extern uint64_t DG dg_align_nested(void),dg_align_external(void),dg_align_calls(void);
extern uint64_t DG dg_align_stack(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
extern uint64_t DG dg_align_slice_stack(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,struct Slice,uint64_t);
extern struct Slice DG dg_align_return(struct Slice,uint8_t);
extern uint64_t DG dg_align_panic(uint64_t),dg_align_overflow(uint64_t),alignment_abi_probe(void);
int alignment_panic_entry,alignment_panic_df,alignment_failed;

uint64_t DG alignment_check(const uint8_t *pointer,uint64_t alignment,uint64_t expected){
    uint64_t actual=0;memcpy(&actual,pointer,sizeof actual);
    if(((uintptr_t)pointer & (alignment-1)) || actual!=expected){
        ++alignment_failed;return 0;
    }
    return 100000;
}
uint64_t DG alignment_nested(const uint8_t *pointer){
    const struct Outer *p=(const struct Outer *)pointer;
    if(((uintptr_t)p & 63) || ((uintptr_t)&p->blocks[0] & 63) || ((uintptr_t)&p->blocks[1] & 63)
       || p->tag!=5 || p->blocks[0].tag!=7 || p->blocks[0].data[0]!=11 || p->blocks[0].data[1]!=12
       || p->blocks[1].tag!=9 || p->blocks[1].data[0]!=99 || p->blocks[1].data[1]!=22){
        ++alignment_failed;return 0;
    }
    return 200000;
}
void DG __attribute__((noreturn)) alignment_panic_record(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    if(!line || length!=18 || memcmp(file,"alignment_probe.dg",18) || alignment_panic_entry!=8
       || alignment_panic_df || alignment_failed || (kind!=1 && kind!=2)){
        fprintf(stderr,"bad aligned panic: kind=%u line=%u length=%" PRIu64 " rsp=%d df=%d failed=%d\n",
                kind,line,length,alignment_panic_entry,alignment_panic_df,alignment_failed);exit(100);
    }
    printf("observed aligned panic %u\n",kind);exit(64+(int)kind);
}
#define CHECK(X) do{if(!(X)){fprintf(stderr,"alignment check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
int main(int argc,char **argv){
    uint64_t values[]={11,22,33,44};struct Slice s={values,4},t;
    if(argc>1){
        if(!strcmp(argv[1],"bounds")){(void)dg_align_panic(2);}
        else if(!strcmp(argv[1],"early_bounds")){struct Slice empty={NULL,0};(void)dg_align_return(empty,1);}
        else if(!strcmp(argv[1],"overflow")){(void)dg_align_overflow(UINT64_MAX);}
        fprintf(stderr,"missing aligned panic\n");return 1;
    }
    CHECK(dg_align32(11)==100011 && dg_align64(22)==100022);
    CHECK(dg_align256(33)==100033 && dg_align1024()==100044);
    CHECK(dg_align_temp32()==32 && dg_align_temp64()==64);
    CHECK(dg_align_temp256()==256 && dg_align_temp1024()==1024);
    CHECK(dg_align_nested()==202199);
    CHECK(dg_align_stack(1,2,3,4,5,6,7,8)==100221);
    CHECK(dg_align_slice_stack(1,2,3,4,5,s,9)==109490);
    t=dg_align_return(s,1);CHECK(t.ptr==values+1 && t.len==3);
    t=dg_align_return(s,0);CHECK(t.ptr==values && t.len==2);
    CHECK(dg_align_external()==100417 && dg_align_calls()==200655);
    CHECK(alignment_abi_probe()==1 && alignment_failed==0);
    puts("native aligned locals, temporaries and ABI probes passed");return 0;
}
