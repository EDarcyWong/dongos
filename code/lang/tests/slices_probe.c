/* Independent SysV two-INTEGER aggregate and Microsoft x64 caller checks. */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define WIN __attribute__((ms_abi))
struct Slice {uint64_t *ptr;uint64_t len;};
struct Bytes {const uint8_t *ptr;uint64_t len;};
extern struct Slice DG dg_slice_return(struct Slice),dg_slice_raw(uint64_t *,uint64_t);
extern struct Slice DG dg_slice_range(struct Slice,uint64_t,uint64_t);
extern struct Bytes DG dg_slice_utf8(void),dg_slice_empty(void);
extern uint64_t DG dg_slice_index(struct Slice,uint64_t),dg_slice_array_range(uint64_t,uint64_t);
extern uint64_t DG dg_slice_effects(void),dg_slice_alias(void),dg_slice_snapshot(void),dg_slice_arg_snapshot(void);
extern uint64_t DG dg_slice_nested(void),dg_slice_null_empty(void),dg_slice_external_asm(void);
extern uint64_t DG dg_slice_snapshot_bounds(uint64_t),dg_slice_range_snapshot(void);
extern uint64_t DG dg_slice_field_bounds(struct Slice,uint64_t);
extern int64_t DG dg_slice_external_c(void);
extern uint64_t DG slices_abi_probe(void),dg_slice_positions(void),dg_slice_scalars(void);
POSITION_DECLARATIONS

int slices_panic_alignment;
void DG __attribute__((noreturn)) slices_panic_record(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    if(kind!=1 || !line || length!=15 || memcmp(file,"slices_probe.dg",15) || slices_panic_alignment!=8){
        fprintf(stderr,"bad slice panic ABI: kind=%u line=%u length=%" PRIu64 " alignment=%d\n",kind,line,length,slices_panic_alignment);exit(100);
    }
    puts("observed slice bounds panic");exit(65);
}
int64_t DG slices_c_sysv(int8_t a,uint16_t b,uint64_t *c,uint64_t d,uint64_t e,uint64_t f,uint64_t g,uint64_t h){
    return a+(int64_t)b+(int64_t)*c+(int64_t)(d*10+e*100+f*1000+g*10000+h*100000);
}
int64_t WIN slices_c_win(int8_t a,uint16_t b,uint64_t *c,uint64_t d,uint64_t e,uint64_t f,uint64_t g,uint64_t h){
    return a+(int64_t)b+(int64_t)*c+(int64_t)(d*10+e*100+f*1000+g*10000+h*100000);
}
#define CHECK(X) do{if(!(X)){fprintf(stderr,"slice check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
#define PANIC(NAME,EXPR) if(!strcmp(argv[1],NAME)){(void)(EXPR);fprintf(stderr,"missing slice panic: %s\n",NAME);return 1;}
int main(int argc,char **argv){
    uint64_t values[]={11,22,33,44};struct Slice s={values,4};
    if(argc>1){
        PANIC("index",dg_slice_index(s,4));PANIC("indexmax",dg_slice_index(s,UINT64_MAX));
        PANIC("reversed",dg_slice_range(s,3,2));PANIC("high",dg_slice_range(s,0,5));
        PANIC("lowmax",dg_slice_range(s,UINT64_MAX,4));PANIC("highmax",dg_slice_range(s,0,UINT64_MAX));
        PANIC("array_high",dg_slice_array_range(0,4));PANIC("array_reversed",dg_slice_array_range(2,1));
        PANIC("snapshot_bounds",dg_slice_snapshot_bounds(2));PANIC("field_bounds",dg_slice_field_bounds(s,5));
        struct Slice zero={NULL,0};PANIC("empty_index",dg_slice_index(zero,0));
        return 1;
    }
    struct Slice t=dg_slice_return(s);CHECK(t.ptr==values+1 && t.len==3);
    t=dg_slice_range(s,1,3);CHECK(t.ptr==values+1 && t.len==2);
    t=dg_slice_range(s,4,4);CHECK(t.ptr==values+4 && t.len==0);
    t=dg_slice_raw(NULL,0);CHECK(t.ptr==NULL && t.len==0);
    struct Bytes bytes=dg_slice_utf8();const uint8_t expected[]={0xe8,0x91,0xa3,0,0x41};
    CHECK(bytes.len==5 && !memcmp(bytes.ptr,expected,5));bytes=dg_slice_empty();CHECK(bytes.len==0);
    CHECK(dg_slice_index(s,2)==33 && dg_slice_array_range(1,3)==2);
    CHECK(dg_slice_effects()==123130 && dg_slice_alias()==3847);
    CHECK(dg_slice_snapshot()==10350 && dg_slice_arg_snapshot()==217);
    CHECK(dg_slice_nested()==205 && dg_slice_null_empty()==0);
    CHECK(dg_slice_snapshot_bounds(1)==20 && dg_slice_range_snapshot()==120);
    CHECK(dg_slice_external_asm()==408 && dg_slice_external_c()==1873126);
    CHECK(slices_abi_probe()==1 && dg_slice_scalars()==204);
    CHECK(dg_slice_positions()==POSITION_TOTAL);
    POSITION_CHECKS
    puts("native slices, SysV aggregate and external ABI probes passed");return 0;
}
