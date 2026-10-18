#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef HARDENING_MOCK_CPUID
#include <cpuid.h>
#endif

#define DG __attribute__((sysv_abi))
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"hardening check %d: %s\n",__LINE__,#x); exit(1); } } while (0)
#define INVALID_CONTROLS UINT64_C(0x020c0001)
#define INVALID_READBACK UINT64_C(0x020c0002)
struct Features { uint64_t max_basic, leaf7_ebx, leaf7_ecx; };
struct State { uint64_t cr0, cr3, cr4, efer, rflags, pat; };
struct Plan { uint64_t supported, cr4; };
struct Report {
    uint64_t max_basic, leaf7_ebx, leaf7_ecx, supported, cr4_before, cr4_after;
    uint64_t rflags_before, rflags_after, cr0, cr3, efer, pat, steps;
};
#define GUARDED(name,type) struct name { uint64_t lo[2]; struct type value; uint64_t hi[2]; }
GUARDED(GFeatures,Features); GUARDED(GState,State); GUARDED(GPlan,Plan); GUARDED(GReport,Report);
extern uint64_t DG hardening_supported(uint64_t,uint64_t,uint64_t);
extern void DG hardening_detect(struct Features *);
extern uint64_t DG hardening_plan(const struct Features *,const struct State *,struct Plan *);
extern uint64_t DG hardening_verify(const struct Features *,const struct State *,const struct State *,const struct Plan *,const struct Report *);
extern void DG hardening_reset(struct Features *,struct Plan *,struct Report *);
extern uint64_t DG hardening_constant(uint64_t);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length) {
    fprintf(stderr,"unexpected hardening panic kind=%u line=%u %.*s\n",kind,line,(int)length,(const char *)file); exit(99);
}
static const struct State base={UINT64_C(0x80010011),UINT64_C(0x400000),UINT64_C(0x620),UINT64_C(0xd00),2,UINT64_C(0x0007040600070406)};
static const uint64_t cr4_masks[]={UINT64_C(1)<<20,UINT64_C(1)<<21,UINT64_C(1)<<11};
static uint64_t mask(unsigned combo) {
    uint64_t result=0; for(unsigned i=0;i<3;i++) if(combo&(1u<<i))result|=cr4_masks[i]; return result;
}
static struct Features features(unsigned combo) {
    /* Irrelevant raw bits are retained but cannot enable an optional control. */
    struct Features f={7,UINT64_C(0x401),UINT64_C(0x101)};
    if(combo&1)f.leaf7_ebx|=UINT64_C(1)<<7;
    if(combo&2)f.leaf7_ebx|=UINT64_C(1)<<20;
    if(combo&4)f.leaf7_ecx|=UINT64_C(1)<<2;
    return f;
}
static void plan_case(struct Features f,struct State b,uint64_t error,uint64_t expected) {
    struct GFeatures gf,fs; struct GState gb,bs; struct GPlan gp,ps;
    memset(&gf,0xa1,sizeof(gf)); memset(&gb,0xb2,sizeof(gb)); memset(&gp,0xc3,sizeof(gp));
    gf.value=f; gb.value=b; fs=gf;bs=gb;ps=gp;
    CHECK(hardening_plan(&gf.value,&gb.value,&gp.value)==error);
    CHECK(!memcmp(&gf,&fs,sizeof(gf))); CHECK(!memcmp(&gb,&bs,sizeof(gb)));
    if(error)CHECK(!memcmp(&gp,&ps,sizeof(gp)));
    else { ps.value=(struct Plan){expected,b.cr4|expected}; CHECK(!memcmp(&gp,&ps,sizeof(gp))); }
}
static struct Report report_for(struct Features f,struct State b,struct State a,uint64_t expected) {
    return (struct Report){f.max_basic,f.leaf7_ebx,f.leaf7_ecx,expected,b.cr4,a.cr4,b.rflags,a.rflags,a.cr0,a.cr3,a.efer,a.pat,7};
}
static void verify_case(struct Features f,struct State b,struct State a,struct Plan p,struct Report r,uint64_t error) {
    struct GFeatures gf,fs; struct GState gb,bs,ga,as; struct GPlan gp,ps; struct GReport gr,rs;
    memset(&gf,0xa1,sizeof(gf));memset(&gb,0xb2,sizeof(gb));memset(&ga,0xc3,sizeof(ga));
    memset(&gp,0xd4,sizeof(gp));memset(&gr,0xe5,sizeof(gr));
    gf.value=f;gb.value=b;ga.value=a;gp.value=p;gr.value=r;fs=gf;bs=gb;as=ga;ps=gp;rs=gr;
    CHECK(hardening_verify(&gf.value,&gb.value,&ga.value,&gp.value,&gr.value)==error);
    CHECK(!memcmp(&gf,&fs,sizeof(gf)));CHECK(!memcmp(&gb,&bs,sizeof(gb)));
    CHECK(!memcmp(&ga,&as,sizeof(ga)));CHECK(!memcmp(&gp,&ps,sizeof(gp)));CHECK(!memcmp(&gr,&rs,sizeof(gr)));
}
static void flip(void *object,unsigned field,uint64_t bits) {
    uint64_t word; unsigned char *at=(unsigned char *)object+8*field;
    memcpy(&word,at,8);word^=bits;memcpy(at,&word,8);
}
static void pure_policy(void) {
    CHECK(hardening_constant(0)==cr4_masks[0]);CHECK(hardening_constant(1)==cr4_masks[1]);
    CHECK(hardening_constant(2)==cr4_masks[2]);CHECK(hardening_constant(3)==mask(7));
    struct GFeatures gf,fs;struct GPlan gp,ps;struct GReport gr,rs;
    memset(&gf,0x91,sizeof(gf));memset(&gp,0xa2,sizeof(gp));memset(&gr,0xb3,sizeof(gr));
    fs=gf;ps=gp;rs=gr;memset(&fs.value,0,sizeof(fs.value));memset(&ps.value,0,sizeof(ps.value));memset(&rs.value,0,sizeof(rs.value));
    hardening_reset(&gf.value,&gp.value,&gr.value);
    CHECK(!memcmp(&gf,&fs,sizeof(gf)));CHECK(!memcmp(&gp,&ps,sizeof(gp)));CHECK(!memcmp(&gr,&rs,sizeof(gr)));
    for(unsigned combo=0;combo<8;combo++) {
        struct Features f=features(combo);
        CHECK(hardening_supported(7,f.leaf7_ebx,f.leaf7_ecx)==mask(combo));
        CHECK(hardening_supported(UINT32_MAX,f.leaf7_ebx,f.leaf7_ecx)==mask(combo));
        CHECK(hardening_supported(6,f.leaf7_ebx,f.leaf7_ecx)==0);
        for(unsigned preset=0;preset<8;preset++) {
            struct State b=base;b.cr4|=mask(preset);
            plan_case(f,b,(preset&~combo)?INVALID_CONTROLS:0,mask(combo));
        }
        struct State a=base;a.cr4|=mask(combo);a.rflags|=UINT64_C(0x8d5);
        struct Plan p={mask(combo),a.cr4};struct Report r=report_for(f,base,a,mask(combo));
        verify_case(f,base,a,p,r,0);
        for(unsigned field=0;field<13;field++) { struct Report bad=r;flip(&bad,field,1);verify_case(f,base,a,p,bad,INVALID_READBACK); }
        for(unsigned field=0;field<2;field++) { struct Plan bad=p;flip(&bad,field,1);verify_case(f,base,a,bad,r,INVALID_READBACK); }
        for(unsigned field=0;field<6;field++) {
            struct State bad=a;flip(&bad,field,field==4?UINT64_C(0x40000):1);
            /* Matching forged report cannot hide a changed control register. */
            struct Report forged=report_for(f,base,bad,mask(combo));verify_case(f,base,bad,p,forged,INVALID_READBACK);
        }
    }
    for(unsigned maximum=0;maximum<7;maximum++) {
        struct Features f={maximum,0,0};plan_case(f,base,0,0);
        struct Plan p={0,base.cr4};struct Report r=report_for(f,base,base,0);verify_case(f,base,base,p,r,0);
        f.leaf7_ebx=1;plan_case(f,base,INVALID_CONTROLS,0);
        f.leaf7_ebx=0;f.leaf7_ecx=1;plan_case(f,base,INVALID_CONTROLS,0);
    }
    struct Features f=features(7);
    for(unsigned field=0;field<3;field++) { struct Features bad=f;flip(&bad,field,UINT64_C(1)<<32);plan_case(bad,base,INVALID_CONTROLS,0); }
    const unsigned cr0_bits[]={0,16,31,29,30},cr4_bits[]={5,7,12,17,23},efer_bits[]={8,10,11},flag_bits[]={1,9,10,17,18};
    for(unsigned i=0;i<sizeof(cr0_bits)/sizeof(cr0_bits[0]);i++){struct State b=base;b.cr0^=UINT64_C(1)<<cr0_bits[i];plan_case(f,b,INVALID_CONTROLS,0);}
    for(unsigned i=0;i<sizeof(cr4_bits)/sizeof(cr4_bits[0]);i++){struct State b=base;b.cr4^=UINT64_C(1)<<cr4_bits[i];plan_case(f,b,INVALID_CONTROLS,0);}
    for(unsigned i=0;i<sizeof(efer_bits)/sizeof(efer_bits[0]);i++){struct State b=base;b.efer^=UINT64_C(1)<<efer_bits[i];plan_case(f,b,INVALID_CONTROLS,0);}
    for(unsigned i=0;i<sizeof(flag_bits)/sizeof(flag_bits[0]);i++) {
        struct State b=base;b.rflags^=UINT64_C(1)<<flag_bits[i];plan_case(f,b,INVALID_CONTROLS,0);
        struct State a=base;a.cr4|=mask(7);a.rflags^=UINT64_C(1)<<flag_bits[i];
        struct Plan p={mask(7),a.cr4};struct Report r=report_for(f,base,a,mask(7));verify_case(f,base,a,p,r,INVALID_READBACK);
    }
    for(unsigned byte=0;byte<256;byte++) {
        struct State b=base;b.pat=(b.pat&~UINT64_C(255))|byte;plan_case(f,b,byte==6?0:INVALID_CONTROLS,mask(7));
        b=base;b.pat=(b.pat&~(UINT64_C(255)<<24))|((uint64_t)byte<<24);plan_case(f,b,byte==0?0:INVALID_CONTROLS,mask(7));
    }
    struct State b=base;b.cr3=0;plan_case(f,b,INVALID_CONTROLS,0);b.cr3=base.cr3+1;plan_case(f,b,INVALID_CONTROLS,0);
    b.cr3=UINT64_C(0x100000000);plan_case(f,b,0,mask(7));
    struct State a=base;a.cr4|=mask(7);struct Plan p={mask(7),a.cr4};struct Report r=report_for(f,base,a,mask(7));
    struct Features invalid=f;invalid.max_basic|=UINT64_C(1)<<32;verify_case(invalid,base,a,p,r,INVALID_READBACK);
    b=base;b.rflags|=UINT64_C(1)<<18;verify_case(f,b,a,p,r,INVALID_READBACK);
    for(unsigned bit=0;bit<64;bit++) {
        uint64_t original=UINT64_C(1)<<bit;
        if(original&(UINT64_C(0x00821080)|mask(7)))continue;
        b=base;b.cr4|=original;plan_case(f,b,0,mask(7));
    }
}

#ifdef HARDENING_MOCK_CPUID
struct CpuId { uint32_t eax,ebx,ecx,edx; };
static uint32_t mock_max,mock_ebx,mock_ecx;static unsigned calls;
void DG dg_arch_cpuid(uint32_t leaf,uint32_t subleaf,struct CpuId *out) {
    CHECK(subleaf==0);CHECK(calls<(mock_max>=7?2u:1u));CHECK(leaf==(calls?7u:0u));calls++;
    *out=(struct CpuId){mock_max,UINT32_MAX,UINT32_MAX,UINT32_MAX};
    if(leaf==7){out->eax=0;out->ebx=mock_ebx;out->ecx=mock_ecx;}
}
static void detect_probe(void) {
    const uint32_t maxima[]={0,1,6,7,8,UINT32_MAX};
    for(unsigned n=0;n<sizeof(maxima)/sizeof(maxima[0]);n++)for(unsigned combo=0;combo<8;combo++) {
        struct Features expected=features(combo);mock_max=maxima[n];mock_ebx=(uint32_t)expected.leaf7_ebx;mock_ecx=(uint32_t)expected.leaf7_ecx;calls=0;
        expected.max_basic=mock_max;if(mock_max<7){expected.leaf7_ebx=0;expected.leaf7_ecx=0;}
        struct GFeatures gf,gs;memset(&gf,0xa8,sizeof(gf));gs=gf;gs.value=expected;
        hardening_detect(&gf.value);CHECK(!memcmp(&gf,&gs,sizeof(gf)));CHECK(calls==(mock_max>=7?2u:1u));
    }
    puts("hardening exact CPUID sequence passed");
}
#else
static void detect_probe(void) {
    unsigned eax,ebx,ecx,edx;__cpuid_count(0,0,eax,ebx,ecx,edx);
    struct Features expected={eax,0,0};
    if(eax>=7){__cpuid_count(7,0,eax,ebx,ecx,edx);expected.leaf7_ebx=ebx;expected.leaf7_ecx=ecx;}
    struct GFeatures gf,gs;memset(&gf,0xa8,sizeof(gf));gs=gf;gs.value=expected;
    hardening_detect(&gf.value);CHECK(!memcmp(&gf,&gs,sizeof(gf)));
    printf("hardening independent CPUID passed max=%" PRIu64 "\n",expected.max_basic);
}
#endif
int main(void) {pure_policy();detect_probe();puts("hardening native checks passed");return 0;}
