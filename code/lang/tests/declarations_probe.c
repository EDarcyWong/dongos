/* C layouts and constants are deliberate, independent target expectations. */
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
struct Packet {uint8_t tag;uint32_t count;int16_t values[3];};
struct __attribute__((aligned(16))) Cache {uint8_t first;uint8_t payload[6];};
struct View {int16_t *ptr;uint64_t len;};
extern uint8_t DG declarations_u8(void),declarations_bool(uint8_t);
extern int8_t DG declarations_i8(void);
extern uint16_t DG declarations_u16(void);
extern int16_t DG declarations_i16(void);
extern uint32_t DG declarations_u32(void);
extern int32_t DG declarations_i32(void);
extern uint64_t DG declarations_u64(void);
extern int64_t DG declarations_i64(void);
extern uint64_t DG declarations_layout(uint64_t),declarations_repeat(void),declarations_shadow(void),declarations_constants(void);
extern int64_t DG declarations_alias_memory(void);
extern int16_t DG declarations_alias_pointer(int16_t *,uint64_t);
extern struct View DG declarations_alias_slice(struct View);
extern uint64_t DG declarations_abi_probe(void);
int declarations_panic_alignment;
void DG __attribute__((noreturn)) declarations_panic_record(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t size){
    if(kind!=1 || !line || size!=21 || memcmp(file,"declarations_probe.dg",21) || declarations_panic_alignment!=8){
        fprintf(stderr,"invalid alias panic: kind=%u line=%u length=%" PRIu64 " alignment=%d\n",kind,line,size,declarations_panic_alignment);exit(99);
    }
    puts("observed alias slice bounds panic");exit(65);
}
#define CHECK(X) do{if(!(X)){fprintf(stderr,"declaration check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
int main(int argc,char **argv){
    (void)argv;int16_t values[]={-8,19,-30};struct View view={values,3};
    if(argc>1){view.len=0;(void)declarations_alias_slice(view);return 98;}
    CHECK(declarations_u8()==UINT8_MAX && declarations_i8()==INT8_MIN);
    CHECK(declarations_u16()==UINT16_MAX && declarations_i16()==INT16_MIN);
    CHECK(declarations_u32()==UINT32_MAX && declarations_i32()==INT32_MIN);
    CHECK(declarations_u64()==UINT64_MAX && declarations_i64()==INT64_MIN);
    CHECK(declarations_bool(0)==0 && declarations_bool(1)==1 && declarations_abi_probe()==1);
    const uint64_t layouts[]={sizeof(struct Packet),_Alignof(struct Packet),offsetof(struct Packet,count),offsetof(struct Packet,values),
                              sizeof(int16_t[3]),16,6,sizeof(struct Cache),_Alignof(struct Cache),offsetof(struct Cache,payload),14,56};
    for(uint64_t i=0;i<sizeof(layouts)/sizeof(layouts[0]);++i)CHECK(declarations_layout(i)==layouts[i]);
    CHECK(declarations_repeat()==1116 && declarations_alias_memory()==-187);
    CHECK(declarations_alias_pointer(values,1)==18 && values[1]==18 && values[0]==-8 && values[2]==-30);
    struct View tail=declarations_alias_slice(view);CHECK(tail.ptr==values+1 && tail.len==2);
    CHECK(declarations_shadow()==102028 && declarations_constants()==141);
    puts("native typed constants, transparent aliases and declaration layouts passed");return 0;
}
