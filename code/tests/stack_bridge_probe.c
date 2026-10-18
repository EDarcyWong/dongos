/* Genuine stack switches through the same SysV entry used by the kernel. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"stack bridge failed at %d: %s\n",__LINE__,#x); exit(1); } } while (0)
typedef uint64_t (DG *Callback)(void *);
extern uint64_t DG dong_call_on_stack(uint64_t,uint64_t,Callback,void*,uint64_t*);
extern uint64_t DG stack_bridge_test_callback(void*);
extern uint64_t DG stack_bridge_test_probe(uint64_t,uint64_t,Callback,void*,uint64_t*,uint64_t);
extern uint64_t DG stack_bridge_test_current_overlap(uint64_t,uint64_t,Callback,void*,uint64_t*);
extern uint64_t DG stack_bridge_test_out_overlap(uint64_t,uint64_t,Callback,void*,uint64_t*,uint64_t);
struct Stack { uint8_t *raw,*bottom,*top; size_t size; };
struct Context {
    uint64_t entry_rsp,entry_flags; /* assembly callback's exact entry view */
    struct Stack *stack;
    struct Context *child;
    uint64_t cookie,seen,local_address,child_value;
};
static struct Stack make_stack(size_t size) {
    struct Stack s;
    s.raw=malloc(size+512);CHECK(s.raw);
    s.bottom=(uint8_t*)(((uintptr_t)(s.raw+128)+15)&~(uintptr_t)15);
    s.top=s.bottom+size;s.size=size;
    memset(s.bottom-64,0xD5,64);memset(s.bottom,0xA7,size);memset(s.top,0x5D,64);
    return s;
}
static void check_guards(const struct Stack *s) {
    for (unsigned i=0;i<64;i++) { CHECK(s->bottom[-(ptrdiff_t)64+(ptrdiff_t)i]==0xD5);CHECK(s->top[i]==0x5D); }
}
static uint64_t expected(const struct Context *c) { return UINT64_C(0xfedcba9876543210)^c->cookie; }
uint64_t DG stack_bridge_c_callback(void *arg) {
    struct Context *c=arg;volatile uint64_t local=c->cookie;
    c->seen++;c->local_address=(uint64_t)(uintptr_t)&local;
    CHECK(c->entry_rsp>=(uint64_t)(uintptr_t)c->stack->bottom);
    CHECK(c->entry_rsp<(uint64_t)(uintptr_t)c->stack->top);
    CHECK((c->entry_rsp&15)==8);CHECK(!(c->entry_flags&0x400));
    CHECK(c->local_address>=(uint64_t)(uintptr_t)c->stack->bottom);
    CHECK(c->local_address<(uint64_t)(uintptr_t)c->stack->top);
    if (c->child) {
        uint64_t value=0;
        CHECK(dong_call_on_stack((uint64_t)(uintptr_t)c->child->stack->bottom,
            (uint64_t)(uintptr_t)c->child->stack->top,stack_bridge_test_callback,c->child,&value)==0);
        CHECK(value==expected(c->child));c->child_value=value;
    }
    return expected(c);
}
static void invalid(struct Stack *s,struct Context *c,uint64_t bottom,uint64_t top,Callback fn,uint64_t *out) {
    uint8_t *snapshot=malloc(s->size);CHECK(snapshot);memcpy(snapshot,s->bottom,s->size);
    uint64_t seen=c->seen,old=out?*out:0;
    CHECK(dong_call_on_stack(bottom,top,fn,c,out)==1);
    CHECK(c->seen==seen);CHECK(!memcmp(snapshot,s->bottom,s->size));
    if (out) CHECK(*out==old);
    check_guards(s);free(snapshot);
}
static void invalid_unmapped_out(struct Stack *s,struct Context *c,uint64_t *out) {
    uint8_t *snapshot=malloc(s->size);CHECK(snapshot);memcpy(snapshot,s->bottom,s->size);
    uint64_t seen=c->seen;
    CHECK(dong_call_on_stack((uintptr_t)s->bottom,(uintptr_t)s->top,stack_bridge_test_callback,c,out)==1);
    CHECK(c->seen==seen);CHECK(!memcmp(snapshot,s->bottom,s->size));
    check_guards(s);free(snapshot);
}
int main(void) {
    struct Stack a=make_stack(65536),b=make_stack(8192),minimum=make_stack(4096);
    struct Context child={0,0,&b,NULL,0x22334455,0,0,0};
    struct Context outer={0,0,&a,&child,0x11223344,0,0,0};
    struct Context tiny={0,0,&minimum,NULL,0x33445566,0,0,0};
    uint64_t value=0;
    CHECK(dong_call_on_stack((uintptr_t)a.bottom,(uintptr_t)a.top,stack_bridge_test_callback,&outer,&value)==0);
    CHECK(value==expected(&outer)&&outer.child_value==expected(&child));
    CHECK(outer.seen==1&&child.seen==1);
    CHECK(stack_bridge_test_probe((uintptr_t)a.bottom,(uintptr_t)a.top,stack_bridge_test_callback,&outer,&value,0)==0);
    CHECK(stack_bridge_test_probe((uintptr_t)a.bottom,(uintptr_t)a.top,stack_bridge_test_callback,&outer,&value,1)==0);
    CHECK(outer.seen==3&&child.seen==3&&value==expected(&outer));
    CHECK(dong_call_on_stack((uintptr_t)minimum.bottom,(uintptr_t)minimum.top,stack_bridge_test_callback,&tiny,&value)==0);
    CHECK(tiny.seen==1&&value==expected(&tiny));
    for (unsigned i=0;i<32;i++) CHECK(a.top[-1-(ptrdiff_t)i]==0xA7);
    check_guards(&a);check_guards(&b);check_guards(&minimum);
    uint64_t *output=malloc(8);CHECK(output);*output=UINT64_C(0x12345678abcdef01);
    uint64_t sentinel=*output;
    invalid(&a,&outer,(uintptr_t)a.bottom+1,(uintptr_t)a.top,stack_bridge_test_callback,output);
    invalid(&a,&outer,(uintptr_t)a.bottom,(uintptr_t)a.top+1,stack_bridge_test_callback,output);
    invalid(&a,&outer,(uintptr_t)a.top,(uintptr_t)a.bottom,stack_bridge_test_callback,output);
    invalid(&a,&outer,(uintptr_t)a.bottom,(uintptr_t)a.bottom,stack_bridge_test_callback,output);
    invalid(&a,&outer,(uintptr_t)a.top-4080,(uintptr_t)a.top,stack_bridge_test_callback,output);
    invalid(&a,&outer,(uintptr_t)a.bottom,(uintptr_t)a.top,NULL,output);
    invalid(&a,&outer,(uintptr_t)a.bottom,(uintptr_t)a.top,stack_bridge_test_callback,NULL);
    invalid(&a,&outer,(uintptr_t)a.bottom,(uintptr_t)a.top,stack_bridge_test_callback,(uint64_t*)(a.bottom+128));
    invalid(&a,&outer,(uintptr_t)a.bottom,(uintptr_t)a.top,stack_bridge_test_callback,(uint64_t*)(a.top-8));
    invalid(&a,&outer,(uintptr_t)a.bottom,(uintptr_t)a.top,(Callback)(uintptr_t)(a.bottom+64),output);
    invalid(&a,&outer,0,4096,stack_bridge_test_callback,output);
    invalid(&a,&outer,UINT64_MAX-4095,0,stack_bridge_test_callback,output);
    invalid(&a,&outer,UINT64_C(0x0000800000000000),UINT64_C(0x0000800000001000),stack_bridge_test_callback,output);
    invalid(&a,&outer,UINT64_C(0x00007ffffffff000),UINT64_C(0xffff800000001000),stack_bridge_test_callback,output);
    invalid(&a,&outer,(uintptr_t)a.bottom,(uintptr_t)a.top,(Callback)(uintptr_t)UINT64_C(0x0000800000000000),output);
    /* Invalid out values are never dereferenced by either bridge or fixture. */
    invalid_unmapped_out(&a,&outer,(uint64_t*)(uintptr_t)(UINT64_MAX-7));
    invalid_unmapped_out(&a,&outer,(uint64_t*)((uint8_t*)output+1));
    uint64_t seen=outer.seen;
    CHECK(stack_bridge_test_current_overlap(0,0,stack_bridge_test_callback,&outer,output)==1);
    CHECK(stack_bridge_test_out_overlap((uintptr_t)a.bottom,(uintptr_t)a.top,stack_bridge_test_callback,&outer,output,0)==1);
    CHECK(stack_bridge_test_out_overlap((uintptr_t)a.bottom,(uintptr_t)a.top,stack_bridge_test_callback,&outer,output,1)==1);
    CHECK(outer.seen==seen&&*output==sentinel);
    check_guards(&a);check_guards(&b);check_guards(&minimum);
    free(output);free(a.raw);free(b.raw);free(minimum.raw);
    puts("stack bridge probe ok: actual stacks, nested callback, flags, NV, rejection");
    return 0;
}
