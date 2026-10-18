#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr,"device policy failure line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
typedef struct { uint64_t kind,base,length; } Resource;
typedef struct { uint64_t views[11],physical[11],count; } Plan;
typedef struct { uint64_t low[4]; Plan value; uint64_t high[4]; } Guard;
extern ABI uint64_t device_plan(const uint64_t*,const uint8_t*,size_t,size_t,const Resource*,size_t,Plan*);
extern ABI size_t device_plan_size(void);
ABI void __dong_panic(uint64_t code) { fprintf(stderr,"unexpected panic %llu\n",(unsigned long long)code); exit(99); }
static uint64_t inventory[307];
static uint8_t raw[120];
static Resource resource;
static unsigned checks;
static void put64(uint8_t *p,uint64_t value) { memcpy(p,&value,8); }
static void descriptor(unsigned index,unsigned kind,uint64_t base,uint64_t pages,uint64_t attr) {
    uint8_t *p=raw+40*index; memset(p,0,40); memcpy(p,&kind,4); put64(p+8,base); put64(p+24,pages); put64(p+32,attr);
}
static void fixture(void) {
    memset(inventory,0,sizeof inventory); memset(raw,0,sizeof raw);
    inventory[8]=0xfee00000; inventory[11]=1; inventory[108]=0xfec00000;
    inventory[4]=0xabc000; inventory[42]=0xfed00000;
    resource=(Resource){8,0x100000,0x30000};
    descriptor(0,7,0x100000,16,0);
}
static uint64_t call(size_t length,size_t stride,size_t count,Guard *g) {
    return device_plan(inventory,raw,length,stride,&resource,count,&g->value);
}
static void failure(size_t length,size_t stride,size_t count,uint64_t code) {
    Guard g,before; uint64_t input[307]; uint8_t map[sizeof raw]; Resource kept=resource;
    memset(&g,0xa5,sizeof g); before=g; memcpy(input,inventory,sizeof input); memcpy(map,raw,sizeof map);
    REQUIRE(call(length,stride,count,&g)==code); REQUIRE(!memcmp(&g,&before,sizeof g));
    REQUIRE(!memcmp(input,inventory,sizeof input)); REQUIRE(!memcmp(map,raw,sizeof map)); REQUIRE(!memcmp(&kept,&resource,sizeof kept));
    checks++;
}
int main(void) {
    const uint64_t base=UINT64_C(0xffffc00000000000);
    Guard g,before; fixture(); REQUIRE(device_plan_size()==sizeof(Plan));
    memset(&g,0x7c,sizeof g); before=g; REQUIRE(call(40,40,1,&g)==0);
    Plan expected={0}; expected.views[0]=base; expected.views[1]=base+4096; expected.views[9]=base+9*4096;
    expected.physical[0]=0xfee00000; expected.physical[1]=0xfec00000; expected.physical[9]=0xfed00000; expected.count=3;
    REQUIRE(!memcmp(&g.value,&expected,sizeof expected)); REQUIRE(!memcmp(g.low,before.low,sizeof g.low)); REQUIRE(!memcmp(g.high,before.high,sizeof g.high)); checks++;
    fixture(); inventory[4]=0; REQUIRE(call(40,40,1,&g)==0); REQUIRE(g.value.count==2 && !g.value.views[9]); checks++;
    fixture(); inventory[28]=0; inventory[32]=0xfed01010; REQUIRE(call(40,40,1,&g)==0); REQUIRE(g.value.count==4 && g.value.views[10]==base+10*4096+16); checks++;
    fixture(); descriptor(1,11,0xfec00000,1,0); REQUIRE(call(80,40,1,&g)==0); checks++;
    for(unsigned kind=0;kind<16;kind++) {
        fixture(); descriptor(1,kind,0xfee00000,1,0);
        if(kind==11) { REQUIRE(call(80,40,1,&g)==0); checks++; } else failure(80,40,1,0x03030002);
    }
    fixture(); descriptor(1,11,0xfee00000,1,UINT64_C(1)<<63); failure(80,40,1,0x03030002);
    fixture(); resource.base=0xfec00800; resource.length=128; failure(40,40,1,0x03030003);
    fixture(); inventory[108]=0xfee00000; failure(40,40,1,0x03030004);
    fixture(); inventory[11]=0; failure(40,40,1,0x03030001);
    fixture(); inventory[11]=9; failure(40,40,1,0x03030001);
    fixture(); inventory[8]++; failure(40,40,1,0x03030005);
    fixture(); inventory[8]=0; failure(40,40,1,0x03030005);
    fixture(); inventory[8]=UINT64_C(1)<<32; failure(40,40,1,0x03030005);
    fixture(); inventory[38]=1; failure(40,40,1,0x03030005);
    fixture(); inventory[42]=0xfed00f00; failure(40,40,1,0x03030005);
    fixture(); inventory[28]=0; inventory[32]=0xfed01ffe; failure(40,40,1,0x03030005);
    fixture(); failure(0,40,1,0x03030001);
    fixture(); failure(40,32,1,0x03030001);
    fixture(); failure(39,40,1,0x03030001);
    fixture(); failure(65537,40,1,0x03030001);
    fixture(); failure(40,40,0,0x03030001);
    fixture(); put64(raw+24,0); failure(40,40,1,0x03030001);
    fixture(); put64(raw+24,UINT64_MAX); failure(40,40,1,0x03030001);
    fixture(); put64(raw+8,0x100001); failure(40,40,1,0x03030001);
    fixture(); descriptor(1,11,0x108000,1,0); failure(80,40,1,0x03030001);
    fixture(); resource.base=UINT64_MAX-10; resource.length=20; failure(40,40,1,0x03030001);
    // Independent randomized exclusions: one page overlapping one discovered
    // register page is permitted only for actual non-runtime MMIO. Other
    // nonoverlapping pages never affect the expected original full Plan.
    uint32_t rng=0x4b1d4e39;
    for(unsigned i=0;i<1000;i++) {
        rng=rng*1664525u+1013904223u; unsigned kind=(rng>>16)&15, selected=(rng>>8)&3;
        uint64_t page=selected==0?0xfee00000:selected==1?0xfec00000:selected==2?0xfed00000:0xfd000000;
        fixture(); descriptor(1,kind,page,1,0);
        if(selected<3 && kind!=11) failure(80,40,1,0x03030002);
        else { REQUIRE(call(80,40,1,&g)==0); REQUIRE(!memcmp(&g.value,&expected,sizeof expected)); checks++; }
    }
    printf("device policy native checks=%u complete Plan and input guards verified\n",checks);
    return 0;
}
