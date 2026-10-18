/* Target layouts, UTF-8 bytes and relocation contents checked independently. */
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
struct Natural { uint8_t tag; uint32_t count; int16_t values[3]; };
struct __attribute__((packed)) Packed { uint8_t tag; uint32_t word; int16_t delta; };
struct Nested { uint8_t prefix; struct Natural natural; struct Packed record; uint8_t tail[4]; };
struct Node { uint64_t value; struct Node *next; };
struct Bytes { const uint8_t *ptr; uint64_t len; };
struct MutableBytes { uint8_t *ptr; uint64_t len; };
extern uint8_t DG globals_u8(void),globals_bool(void);
extern int8_t DG globals_i8(void);
extern uint16_t DG globals_u16(void);
extern int16_t DG globals_i16(void);
extern uint32_t DG globals_u32(void);
extern int32_t DG globals_i32(void);
extern uint64_t DG globals_u64(void),globals_hidden(void),globals_copy_constant(void),globals_abi_probe(void);
extern int64_t DG globals_i64(void);
extern void DG globals_write_scalars(void),globals_mutate_view(void),globals_rebind_text(void),globals_page_mark(void);
extern struct Natural *DG globals_packet(void);
extern struct Packed *DG globals_packed(void);
extern struct Nested *DG globals_nested(void);
extern const struct Natural *DG globals_frozen_packet(void);
extern uint8_t *DG globals_bytes(void),*DG globals_zeros(void),*DG globals_element_address(void);
extern uint8_t *DG globals_nested_address(void),*DG globals_indirect(void),*DG globals_page(void);
extern const uint8_t *DG globals_frozen(void),*DG globals_frozen_address(void);
extern const uint16_t *DG globals_scalar_address(void);
extern uint32_t *DG globals_count_address(void);
extern struct Bytes DG globals_greeting(void),globals_empty(void),globals_text(void),globals_constant_view(void),globals_empty_view(void);
extern struct MutableBytes DG globals_mutable_view(void);
extern struct Node *DG globals_self_node(void),*DG globals_first(void),*DG globals_second(void);
extern struct Node *const *DG globals_node_table(void);

void DG __attribute__((noreturn)) globals_panic_record(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length) {
    fprintf(stderr,"unexpected global panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);
    exit(99);
}
#define CHECK(X) do{if(!(X)){fprintf(stderr,"global check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
int main(void) {
    CHECK(sizeof(struct Natural)==16 && _Alignof(struct Natural)==4);
    CHECK(offsetof(struct Natural,count)==4 && offsetof(struct Natural,values)==8);
    CHECK(sizeof(struct Packed)==7 && offsetof(struct Packed,word)==1 && offsetof(struct Packed,delta)==5);
    CHECK(sizeof(struct Nested)==32 && offsetof(struct Nested,natural)==4 && offsetof(struct Nested,record)==20 && offsetof(struct Nested,tail)==27);
    CHECK(sizeof(struct Node)==16 && offsetof(struct Node,next)==8);
    CHECK(globals_abi_probe()==1 && globals_bool()==1 && globals_hidden()==19);
    CHECK(globals_u8()==UINT8_MAX && globals_i8()==INT8_MIN);
    CHECK(globals_u16()==UINT16_MAX && globals_i16()==INT16_MIN);
    CHECK(globals_u32()==UINT32_MAX && globals_i32()==INT32_MIN);
    CHECK(globals_u64()==UINT64_MAX && globals_i64()==INT64_MIN);

    struct Natural *packet=globals_packet();
    const uint8_t natural_bytes[]={0xa5,0,0,0,0x44,0x33,0x22,0x11,0xfe,0xff,0x2c,0x01,0x60,0xf0,0,0};
    CHECK(!memcmp(packet,natural_bytes,sizeof(natural_bytes)));
    const uint8_t packed_bytes[]={0x7e,0x40,0x30,0x20,0x10,0x2e,0xfb};
    CHECK(!memcmp(globals_packed(),packed_bytes,sizeof(packed_bytes)));
    struct Nested *nested=globals_nested();
    CHECK(nested->prefix==0x99 && nested->natural.tag==3 && nested->natural.count==5);
    CHECK(nested->natural.values[0]==-1 && nested->natural.values[1]==2 && nested->natural.values[2]==-3);
    CHECK(nested->record.tag==4 && nested->record.word==UINT32_C(0xa0b0c0d0) && nested->record.delta==-5);
    CHECK(nested->tail[0]==9 && nested->tail[1]==0 && nested->tail[2]==8 && nested->tail[3]==7);
    CHECK(((uint8_t *)nested)[1]==0 && ((uint8_t *)nested)[2]==0 && ((uint8_t *)nested)[3]==0 && ((uint8_t *)nested)[31]==0);

    uint8_t *bytes=globals_bytes(),*zeros=globals_zeros();
    const uint8_t byte_values[]={0,1,2,255,4,5},frozen_values[]={9,8,7,6};
    CHECK(!memcmp(bytes,byte_values,6) && !memcmp(globals_frozen(),frozen_values,4));
    for(size_t i=0;i<64;++i)CHECK(zeros[i]==0);
    zeros[63]=0x7b;CHECK(globals_zeros()[63]==0x7b);
    CHECK(globals_count_address()==&packet->count && globals_element_address()==bytes+3);
    CHECK(globals_frozen_address()==globals_frozen()+2 && globals_nested_address()==nested->tail+2);
    CHECK(globals_indirect()==bytes+2 && *globals_scalar_address()==UINT16_C(0x7a9b));
    *globals_count_address()=UINT32_C(0x55667788);CHECK(globals_packet()->count==UINT32_C(0x55667788));
    *globals_element_address()=33;CHECK(globals_bytes()[3]==33);
    CHECK(globals_copy_constant()==1199 && globals_frozen_packet()->count==11 && globals_frozen_packet()->values[0]==-1);

    const uint8_t greeting[]={0xe8,0x91,0xa3,0,0x41},original_text[]={0xe4,0xb8,0x96,0xe7,0x95,0x8c,0,0x21};
    const uint8_t rebound_text[]={0xe6,0x9b,0xbf,0xe6,0x8d,0xa2,0};
    struct Bytes greeting_view=globals_greeting(),text=globals_text(),constant=globals_constant_view(),empty_view=globals_empty_view();
    CHECK(greeting_view.len==5 && !memcmp(greeting_view.ptr,greeting,5));
    CHECK(text.len==8 && !memcmp(text.ptr,original_text,8) && globals_empty().len==0);
    CHECK(constant.ptr==globals_frozen()+1 && constant.len==2 && constant.ptr[0]==8 && constant.ptr[1]==7);
    CHECK(empty_view.ptr==bytes+2 && empty_view.len==0);
    struct MutableBytes mutable=globals_mutable_view();CHECK(mutable.ptr==bytes+1 && mutable.len==4);
    globals_mutate_view();CHECK(bytes[1]==90 && globals_mutable_view().ptr==bytes+1);
    globals_rebind_text();text=globals_text();CHECK(text.len==7 && !memcmp(text.ptr,rebound_text,7));

    struct Node *self=globals_self_node(),*first=globals_first(),*second=globals_second();
    CHECK(self->value==123 && self->next==self);
    CHECK(first->value==101 && second->value==202 && first->next==second && second->next==first);
    struct Node *const *table=globals_node_table();CHECK(table[0]==first && table[1]==second && table[2]==self);
    uint8_t *page=globals_page();CHECK(((uintptr_t)page&4095)==0);
    for(size_t i=0;i<4096;++i)CHECK(page[i]==0);
    globals_page_mark();CHECK(page[4095]==0x5a && page[0]==0);

    globals_write_scalars();
    CHECK(globals_u8()==17 && globals_i8()==-17 && globals_u16()==2000 && globals_i16()==-2000);
    CHECK(globals_u32()==UINT32_C(3000000000) && globals_i32()==-INT32_C(2000000000));
    CHECK(globals_u64()==UINT64_C(0xfedcba9876543210) && globals_i64()==-INT64_C(1234567890123456) && globals_bool()==0);
    puts("native initialized globals, readonly aggregates and 64-bit static relocations passed");return 0;
}
