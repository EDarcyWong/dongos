#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"preflight check at %d: %s\n",__LINE__,#x);exit(1); } } while(0)
struct State { uint64_t cr0,cr3,cr4,efer,rflags,pat; };
struct Plan { uint64_t cr0,efer,actions; };
extern uint64_t DG preflight_plan(const struct State*,uint64_t,struct Plan*);
extern uint64_t DG preflight_unchanged(const struct State*,const struct State*);
__attribute__((noreturn)) void DG __dong_panic(void) { fputs("unexpected Dong panic\n",stderr);exit(2); }
static void checked(struct State s,uint64_t root,int good) {
    struct { uint64_t lo; struct State s; uint64_t hi; } input={0x1234,s,0x5678};
    struct { uint64_t lo; struct Plan p; uint64_t hi; } output;
    memset(&output,0xA9,sizeof(output));
    unsigned char snap[sizeof(output)]; memcpy(snap,&output,sizeof(output));
    uint64_t result=preflight_plan(&input.s,root,&output.p);
    CHECK(input.lo==0x1234&&input.hi==0x5678&&!memcmp(&input.s,&s,sizeof(s)));
    if(good) {
        CHECK(result==0);CHECK(output.p.cr0==(s.cr0|0x10000));CHECK(output.p.efer==(s.efer|0x800));
        uint64_t expected=4+(!(s.efer&0x800))+2*(!(s.cr0&0x10000));CHECK(output.p.actions==expected);
        CHECK(!memcmp(&output.lo,snap,sizeof(output.lo)));CHECK(!memcmp(&output.hi,snap+sizeof(output)-8,8));
    } else { CHECK(result==0x02080001);CHECK(!memcmp(&output,snap,sizeof(output))); }
}
int main(void) {
    const struct State base={0x80000011,0x400000,0x620,0x500,2,UINT64_C(0x0007040600070406)};
    for(unsigned nxe=0;nxe<2;nxe++)for(unsigned wp=0;wp<2;wp++) {
        struct State s=base;s.efer|=(uint64_t)nxe<<11;s.cr0|=(uint64_t)wp<<16;checked(s,s.cr3,1);
    }
    checked(base,0,0);checked(base,0x400001,0);checked(base,0x500000,0);checked(base,UINT64_C(0x100000000),0);
    const unsigned cr0_bad[]={0,31,29,30};
    for(unsigned i=0;i<4;i++){struct State s=base;s.cr0^=UINT64_C(1)<<cr0_bad[i];checked(s,s.cr3,0);}
    const unsigned cr4_bad[]={5,7,12,17,23};
    for(unsigned i=0;i<5;i++){struct State s=base;s.cr4^=UINT64_C(1)<<cr4_bad[i];checked(s,s.cr3,0);}
    const unsigned flag_bad[]={1,9,10,17,18};
    for(unsigned i=0;i<5;i++){struct State s=base;s.rflags^=UINT64_C(1)<<flag_bad[i];checked(s,s.cr3,0);}
    for(unsigned bit=8;bit<=10;bit+=2){struct State s=base;s.efer^=UINT64_C(1)<<bit;checked(s,s.cr3,0);}
    for(unsigned byte=0;byte<256;byte++){struct State s=base;s.pat=(s.pat&~UINT64_C(255))|byte;checked(s,s.cr3,byte==6);}
    for(unsigned byte=0;byte<256;byte++){struct State s=base;s.pat=(s.pat&~(UINT64_C(255)<<24))|((uint64_t)byte<<24);checked(s,s.cr3,byte==0);}
    struct State other=base;other.rflags^=0x8D5;CHECK(preflight_unchanged(&base,&other)==0);
    other=base;other.rflags|=UINT64_C(1)<<18;CHECK(preflight_unchanged(&base,&other)==0x02080002);
    for(unsigned field=0;field<6;field++) {
        struct State a=base,b=base;uint64_t words[6];memcpy(words,&b,sizeof(b));
        words[field]^=field==4?0x200:1;memcpy(&b,words,sizeof(b));
        CHECK(preflight_unchanged(&a,&b)==0x02080002);CHECK(!memcmp(&a,&base,sizeof(a)));
    }
    puts("preflight native checks passed");return 0;
}
