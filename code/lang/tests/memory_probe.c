/* Independently defined C layouts and arithmetic expectations. No generated
   layout header is consumed here, so offsets are checked across compilers. */
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DG __attribute__((sysv_abi))
struct Natural { uint8_t a; uint32_t b; int16_t c; uint8_t d[3]; };
struct __attribute__((packed)) Packed { uint8_t a; int32_t b; uint16_t c; };
struct __attribute__((aligned(16))) Aligned { uint8_t a; uint64_t b; };

#define DECL(T,N) \
extern T DG dg_##N##_add(T,T); extern T DG dg_##N##_sub(T,T); \
extern T DG dg_##N##_mul(T,T); extern T DG dg_##N##_div(T,T); \
extern T DG dg_##N##_mod(T,T); extern T DG dg_##N##_neg(T); \
extern T DG dg_##N##_shl(T,uint64_t); extern T DG dg_##N##_shr(T,uint64_t); \
extern uint8_t DG dg_##N##_lt(T,T); extern T DG dg_##N##_cast(uint64_t)
DECL(uint8_t,u8); DECL(int8_t,i8); DECL(uint16_t,u16); DECL(int16_t,i16);
DECL(uint32_t,u32); DECL(int32_t,i32); DECL(uint64_t,u64); DECL(int64_t,i64);
extern uint64_t DG dg_layout(uint64_t);
extern uint64_t DG dg_local_memory(void), dg_repeat(void), dg_struct_order(void), dg_aggregate(void);
extern uint64_t DG dg_temporary_index(void), dg_len_effect(void);
extern int64_t DG dg_call_narrow(int8_t,int16_t,uint32_t);
extern int64_t DG dg_alias(void), dg_packed(struct Packed *), dg_pointer_index(int32_t *,uint64_t);
extern void DG dg_overlap(uint8_t *), dg_overlap_reverse(uint8_t *);
extern uint8_t DG dg_null(uint8_t *);
extern uint64_t DG dg_bounds(uint64_t), dg_address_order(uint64_t,uint64_t);
extern uint64_t DG dg_nested_bounds(uint64_t);
extern uint64_t DG memory_df_probe(void), memory_narrow_probe(void);

int panic_entry_alignment;
static uint32_t expected_kind;
void DG __attribute__((noreturn)) panic_record(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length)
{
    if(kind!=expected_kind || !line || length!=15 || memcmp(file,"memory_probe.dg",15) || panic_entry_alignment!=8) {
        fprintf(stderr,"invalid memory panic ABI: kind=%u line=%u length=%" PRIu64 " alignment=%d\n",kind,line,length,panic_entry_alignment);
        exit(100);
    }
    printf("observed panic %u\n",kind);
    exit((int)(64+kind));
}
#define CHECK(X) do {if(!(X)){fprintf(stderr,"check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
#define PANIC(NAME,KIND,EXPR) if(!strcmp(argv[1],NAME)){expected_kind=KIND;(void)(EXPR);fprintf(stderr,"missing panic %s\n",NAME);return 1;}
#define PANICS_U(N,MAX,W) \
PANIC(#N "_zero",3,dg_##N##_div(1,0)); \
PANIC(#N "_modzero",3,dg_##N##_mod(1,0)); \
PANIC(#N "_shift",4,dg_##N##_shl(1,W)); \
PANIC(#N "_shiftmax",4,dg_##N##_shr(1,UINT64_MAX))
#define PANICS_I(N,MIN,W) \
PANICS_U(N,0,W); \
PANIC(#N "_divoverflow",5,dg_##N##_div(MIN,-1)); \
PANIC(#N "_modoverflow",5,dg_##N##_mod(MIN,-1))
#define OVERFLOW_U(N,MAX) \
PANIC(#N "_add",2,dg_##N##_add(MAX,1)); \
PANIC(#N "_sub",2,dg_##N##_sub(0,1)); \
PANIC(#N "_mul",2,dg_##N##_mul(MAX,2)); \
PANIC(#N "_neg",2,dg_##N##_neg(1))
#define OVERFLOW_I(N,MIN,MAX) \
PANIC(#N "_add",2,dg_##N##_add(MAX,1)); \
PANIC(#N "_sub",2,dg_##N##_sub(MIN,1)); \
PANIC(#N "_mul",2,dg_##N##_mul(MAX,2)); \
PANIC(#N "_neg",2,dg_##N##_neg(MIN))
#define NORMAL_U(T,N,MAX,W) \
CHECK(dg_##N##_add(20,22)==42 && dg_##N##_sub(42,20)==22); \
CHECK(dg_##N##_mul(9,8)==72 && dg_##N##_div(100,7)==14 && dg_##N##_mod(100,7)==2); \
CHECK(dg_##N##_shr(MAX,W-1)==1 && dg_##N##_shl(1,W-1)==(T)((uint64_t)1<<(W-1))); \
CHECK(dg_##N##_lt(MAX,0)==0 && dg_##N##_lt(0,MAX)==1); \
CHECK(dg_##N##_cast(UINT64_MAX)==MAX)
#define NORMAL_I(T,N,MIN,MAX,W) \
CHECK(dg_##N##_add(-20,22)==2 && dg_##N##_sub(-20,22)==-42 && dg_##N##_mul(-9,8)==-72); \
CHECK(dg_##N##_div(-100,7)==-14 && dg_##N##_mod(-100,7)==-2); \
CHECK(dg_##N##_shr(-2,1)==-1 && dg_##N##_shl(1,W-1)==MIN); \
CHECK(dg_##N##_lt(-1,0)==1 && dg_##N##_lt(MAX,MIN)==0); \
CHECK(dg_##N##_cast(UINT64_MAX)==-1)
#define WRAP_U(N,MAX) \
CHECK(dg_##N##_add(MAX,1)==0 && dg_##N##_sub(0,1)==MAX); \
CHECK(dg_##N##_mul(MAX,2)==MAX-1 && dg_##N##_neg(1)==MAX)
#define WRAP_I(N,MIN,MAX) \
CHECK(dg_##N##_add(MAX,1)==MIN && dg_##N##_sub(MIN,1)==MAX); \
CHECK(dg_##N##_mul(MAX,2)==-2 && dg_##N##_neg(MIN)==MIN)

int main(int argc,char **argv)
{
    if(argc>1) {
        PANICS_U(u8,UINT8_MAX,8); PANICS_I(i8,INT8_MIN,8);
        PANICS_U(u16,UINT16_MAX,16); PANICS_I(i16,INT16_MIN,16);
        PANICS_U(u32,UINT32_MAX,32); PANICS_I(i32,INT32_MIN,32);
        PANICS_U(u64,UINT64_MAX,64); PANICS_I(i64,INT64_MIN,64);
        PANIC("bounds",1,dg_bounds(3)); PANIC("boundsmax",1,dg_bounds(UINT64_MAX));
        PANIC("address_order",1,dg_address_order(2,0));
        PANIC("nested_bounds",1,dg_nested_bounds(2));
#if DEBUG_MODE
        OVERFLOW_U(u8,UINT8_MAX); OVERFLOW_I(i8,INT8_MIN,INT8_MAX);
        OVERFLOW_U(u16,UINT16_MAX); OVERFLOW_I(i16,INT16_MIN,INT16_MAX);
        OVERFLOW_U(u32,UINT32_MAX); OVERFLOW_I(i32,INT32_MIN,INT32_MAX);
        OVERFLOW_U(u64,UINT64_MAX); OVERFLOW_I(i64,INT64_MIN,INT64_MAX);
#endif
        fprintf(stderr,"unknown panic %s\n",argv[1]);return 1;
    }
    NORMAL_U(uint8_t,u8,UINT8_MAX,8); NORMAL_I(int8_t,i8,INT8_MIN,INT8_MAX,8);
    NORMAL_U(uint16_t,u16,UINT16_MAX,16); NORMAL_I(int16_t,i16,INT16_MIN,INT16_MAX,16);
    NORMAL_U(uint32_t,u32,UINT32_MAX,32); NORMAL_I(int32_t,i32,INT32_MIN,INT32_MAX,32);
    NORMAL_U(uint64_t,u64,UINT64_MAX,64); NORMAL_I(int64_t,i64,INT64_MIN,INT64_MAX,64);
#if !DEBUG_MODE
    WRAP_U(u8,UINT8_MAX); WRAP_I(i8,INT8_MIN,INT8_MAX);
    WRAP_U(u16,UINT16_MAX); WRAP_I(i16,INT16_MIN,INT16_MAX);
    WRAP_U(u32,UINT32_MAX); WRAP_I(i32,INT32_MIN,INT32_MAX);
    WRAP_U(u64,UINT64_MAX); WRAP_I(i64,INT64_MIN,INT64_MAX);
#endif
    uint64_t layouts[]={sizeof(struct Natural),_Alignof(struct Natural),offsetof(struct Natural,b),offsetof(struct Natural,c),
                        offsetof(struct Natural,d),sizeof(struct Packed),_Alignof(struct Packed),offsetof(struct Packed,b),
                        offsetof(struct Packed,c),sizeof(struct Aligned),_Alignof(struct Aligned)};
    for(uint64_t i=0;i<sizeof(layouts)/sizeof(layouts[0]);i++)CHECK(dg_layout(i)==layouts[i]);
    CHECK(dg_local_memory()==2190 && dg_repeat()==103 && dg_struct_order()==213123);
    CHECK(dg_temporary_index()==123 && dg_len_effect()==103);
    CHECK(dg_call_narrow(-120,-30000,4000000000U)==INT64_C(3999969880));
    CHECK(dg_aggregate()==2842 && dg_alias()==-1241);
    struct Packed packed={1,-100,60000};
    CHECK(dg_packed(&packed)==59901 && packed.a==1 && packed.b==-99 && packed.c==60000);
    int32_t integers[]={-1,20,-100};CHECK(dg_pointer_index(integers,2)==-98 && integers[1]==20);
    uint8_t bytes[]={1,2,3,4,5};dg_overlap(bytes);CHECK(!memcmp(bytes,"\1\1\2\3\4",5));
    dg_overlap_reverse(bytes);CHECK(!memcmp(bytes,"\1\2\3\4\4",5));
    CHECK(dg_null(NULL)==1 && dg_null(bytes)==0 && memory_df_probe()==1 && memory_narrow_probe()==1);
    CHECK(dg_bounds(2)==3);
    CHECK(dg_nested_bounds(1)==2);
    puts("native memory, narrow integer and layout probes passed");return 0;
}
