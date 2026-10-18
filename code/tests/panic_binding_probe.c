#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define DG __attribute__((sysv_abi))
#define CHECK(x) do {if(!(x)){fprintf(stderr,"panic binding failed at %d\n",__LINE__);exit(1);}}while(0)
extern void DG panic_init(const void*,uint64_t,uint64_t);
extern uint64_t DG panic_binding_matches(const void*,uint64_t,uint64_t);
extern uint64_t DG panic_test_select_range(uint64_t);
void DG kernel_panic_screen(const void *context,const void *display) {(void)context;(void)display;abort();}
int main(void) {
    uint64_t display[6]={0};
    uint64_t low=UINT64_C(0xffff900000001000),high=low+65536;
    panic_init(display,0x700000,0x710000);
    CHECK(panic_test_select_range(0x700000)==1);
    panic_init(display,0,0); /* outgoing root: future STACK is not mapped yet */
    CHECK(panic_binding_matches(display,0,0)==1);
    CHECK(panic_test_select_range(0x700000)==0);
    CHECK(panic_test_select_range(low)==0);CHECK(panic_test_select_range(high-16)==0);
    CHECK(panic_test_select_range(UINT64_C(0xffffffff80020000))==1);
    /* Model the later registration, performed only after root activation. */
    panic_init(display,low,high);
    CHECK(panic_binding_matches(display,low,high)==1);
    CHECK(panic_binding_matches(display,0x700000,0x710000)==0);
    CHECK(panic_test_select_range(0x700000)==0); /* outgoing RBP is never read */
    CHECK(panic_test_select_range(low)==1);CHECK(panic_test_select_range(high-16)==1);
    CHECK(panic_test_select_range(low-8)==0);CHECK(panic_test_select_range(high-8)==0);
    CHECK(panic_test_select_range(low+1)==0);
    CHECK(panic_test_select_range(UINT64_C(0xffffffff80020000))==1);
    CHECK(panic_test_select_range(UINT64_C(0xffffffff80024000)-16)==1);
    CHECK(panic_test_select_range(UINT64_C(0xffffffff80024000))==0);
    CHECK(panic_test_select_range(UINT64_C(0xffffffff8001f000))==0);
    panic_init(display,low+1,high);CHECK(panic_test_select_range(low)==0);
    puts("panic binding probes passed");return 0;
}
