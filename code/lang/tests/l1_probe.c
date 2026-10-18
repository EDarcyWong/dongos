#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(x) do { if (!(x)) {fprintf(stderr,"L1 check failed at %d: %s\n",__LINE__,#x);return 1;} } while (0)
typedef struct {uint64_t tag,slot;} Pair;
extern uint64_t DG l1_trace(void),l1_defer(_Bool),l1_shadow_defer(void),l1_while_defer(void);
extern uint64_t DG l1_late_defer(void),l1_defer_registration(_Bool),l1_panic_defer(uint64_t);
extern uint64_t DG l1_for_range(void),l1_for_array(void),l1_for_slice(void),l1_loop_defer(void),l1_local_const(void),l1_methods(void);
extern Pair DG l1_event(uint64_t,int16_t),l1_optional(_Bool,int16_t),l1_result(uint64_t),l1_try(uint64_t),l1_try_pair_return(uint64_t),l1_void_result(_Bool);
extern int64_t DG l1_event_score(Pair),l1_optional_score(Pair);
extern uint64_t DG l1_flag(uint64_t),l1_bool_match(_Bool),l1_result_score(Pair),l1_void_match(Pair),l1_static_values(void);
extern int16_t DG l1_orelse(Pair);
extern uint64_t DG l1_orelse_return(Pair),l1_orelse_continue(void),l1_orelse_break(void),l1_asm_check(void);
extern Pair DG l1_optional_indirect(Pair),l1_optional_stack(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,Pair,uint64_t);
extern Pair DG l1_result_stack(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,Pair,uint64_t),l1_event_stack(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,Pair,uint64_t);
extern void DG __attribute__((noreturn)) l1_never(void);
void DG __attribute__((noreturn)) l1_terminate(uint64_t code) {exit((int)code);}
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length) {
    fprintf(stderr,"L1 panic kind=%u trace=%" PRIu64 " at %.*s:%u\n",kind,l1_trace(),(int)length,(const char *)file,line);exit(90+(int)kind);
}
static int pair_equal(Pair value,uint64_t tag,uint64_t slot) {return value.tag==tag && value.slot==slot;}
int main(int argc,char **argv) {
    if (argc>1 && !strcmp(argv[1],"noreturn")) l1_never();
    if (argc>1 && !strcmp(argv[1],"panic")) return (int)l1_panic_defer(7);
    CHECK(l1_defer(0)==9 && l1_trace()==537);
    CHECK(l1_defer(1)==42 && l1_trace()==432);
    CHECK(l1_shadow_defer()==9 && l1_trace()==89);
    CHECK(l1_late_defer()==3 && l1_trace()==219);
    CHECK(l1_defer_registration(1)==4 && l1_trace()==1);
    CHECK(l1_defer_registration(0)==5 && l1_trace()==21);
    CHECK(l1_while_defer()==1 && l1_trace()==1239);
    CHECK(l1_for_range()==9 && l1_trace()==12);
    CHECK(l1_for_array()==11);
    CHECK(l1_for_slice()==11 && l1_trace()==1);
    CHECK(l1_loop_defer()==5 && l1_trace()==2123);
    CHECK(l1_local_const()==29);
    CHECK(l1_methods()==82);
    CHECK(pair_equal(l1_event(0,-7),0,0));
    CHECK(pair_equal(l1_event(1,203),1,203));
    CHECK(pair_equal(l1_event(2,-7),2,UINT64_C(0xfff9)));
    CHECK(pair_equal(l1_event(3,99),3,0));
    CHECK(l1_event_score((Pair){0,0})==10);
    CHECK(l1_event_score((Pair){1,203})==303);
    CHECK(l1_event_score((Pair){2,0xfff9})==-107);
    CHECK(l1_event_score((Pair){3,0})==20);
    CHECK(l1_flag(0)==11 && l1_flag(1)==22 && l1_flag(2)==33);
    CHECK(l1_bool_match(0)==27 && l1_bool_match(1)==81);
    CHECK(pair_equal(l1_optional(0,-123),0,0));
    CHECK(pair_equal(l1_optional(1,-123),1,0xff85));
    CHECK(l1_optional_score((Pair){0,0})==-999 && l1_optional_score((Pair){1,0xff85})==-123);
    CHECK(l1_orelse((Pair){1,0xff85})==-123 && l1_trace()==0);
    CHECK(l1_orelse((Pair){0,0})==-12 && l1_trace()==6);
    CHECK(l1_orelse_return((Pair){0,0})==7 && l1_trace()==9);
    CHECK(l1_orelse_return((Pair){1,123})==123 && l1_trace()==19);
    CHECK(l1_orelse_continue()==2 && l1_trace()==1239);
    CHECK(l1_orelse_break()==0 && l1_trace()==129);
    CHECK(pair_equal(l1_result(0),17,0));
    CHECK(pair_equal(l1_result(1),18,0));
    CHECK(pair_equal(l1_result(123456),0,123456));
    CHECK(l1_result_score((Pair){17,0})==1017 && l1_result_score((Pair){0,777})==777);
    CHECK(pair_equal(l1_try(0),17,0) && l1_trace()==39);
    CHECK(pair_equal(l1_try(1),18,0) && l1_trace()==39);
    CHECK(pair_equal(l1_try(5),0,9) && l1_trace()==139);
    CHECK(pair_equal(l1_try_pair_return(255),0,255));
    CHECK(pair_equal(l1_try_pair_return(0),17,0));
    CHECK(pair_equal(l1_void_result(0),0,0) && l1_trace()==17);
    CHECK(pair_equal(l1_void_result(1),17,0) && l1_trace()==7);
    CHECK(l1_void_match((Pair){0,0})==5 && l1_void_match((Pair){18,0})==118);
    CHECK(l1_static_values()==358);
    CHECK(pair_equal(l1_optional_indirect((Pair){1,0xff85}),1,0xff85));
    CHECK(pair_equal(l1_optional_stack(1,2,3,4,5,(Pair){1,0xff85},6),1,0xff85));
    CHECK(pair_equal(l1_result_stack(1,2,3,4,5,(Pair){17,0},6),17,0));
    CHECK(pair_equal(l1_event_stack(1,2,3,4,5,(Pair){2,0xfff9},6),2,0xfff9));
    CHECK(l1_asm_check()==313);
    puts("remaining L1 flow, cleanup, tagged values, methods and pair ABI passed");
    return 0;
}
