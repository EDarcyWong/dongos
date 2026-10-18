#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"SERVICE_RESOURCE_ASSERT line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
#define ERROR(n) (UINT64_C(0x05050000)+(n))
typedef struct { uint64_t words[12]; } Handoff;
typedef struct { uint64_t physical,length; } Span;
typedef struct { Span handoff,bundle,arena; } Plan;
extern ABI size_t sr_handoff_size(void),sr_plan_size(void);
extern ABI uint64_t sr_readable(const uint8_t *,size_t,size_t,uint64_t);
extern ABI uint64_t sr_validate(const Handoff *,uint64_t,const uint8_t *,size_t,size_t,const Span *,size_t,Plan *);
ABI void __dong_panic(uint64_t code) { fprintf(stderr,"unexpected Dong panic %llu\n",(unsigned long long)code);exit(99); }
ABI void sr_negative_hit(uint64_t kind) { fprintf(stderr,"SERVICE_RESOURCE_NEGATIVE_HIT %llu\n",(unsigned long long)kind); }
static uint8_t map[16*48];static Handoff handoff;static unsigned count,checks,good,bad;
static void w32(size_t at,uint32_t x) { memcpy(map+at,&x,4); }
static void w64(size_t at,uint64_t x) { memcpy(map+at,&x,8); }
static void desc(unsigned i,uint32_t type,uint64_t pa,uint64_t pages,uint64_t attr) {
    memset(map+i*48,0,48);w32(i*48,type);w64(i*48+8,pa);w64(i*48+24,pages);w64(i*48+32,attr);memset(map+i*48+40,0xa7,8);
}
static void sum(void) { uint64_t total=0;handoff.words[11]=0;for(unsigned i=0;i<12;i++)total+=handoff.words[i];handoff.words[11]=0-total; }
static void fixture(void) {
    memset(map,0,sizeof map);handoff=(Handoff){{UINT64_C(0x31444e4148565344),1,96,1,0x10000000,8192,2,0x20000000,128*1024*1024,32768,0x30000000,0}};sum();
    // Unsorted contiguous resource coverage plus coalesced LoaderData objects.
    desc(0,2,0x22000000,8192,0);desc(1,2,0x0ffff000,4,0);desc(2,2,0x20000000,8192,0);
    desc(3,2,0x26000000,8192,0);desc(4,2,0x24000000,8192,0);desc(5,2,0x30000000,2,0);
    desc(6,7,UINT64_C(0x10000000000),16,0);count=7;
}
static void validate(uint64_t expected,size_t bytes,size_t stride,const Span *forbidden,size_t n) {
    struct { uint64_t a[2];Plan value;uint64_t z[2]; } out;memset(&out,0xa7,sizeof out);Plan before=out.value;
    uint8_t map_before[sizeof map];memcpy(map_before,map,sizeof map);Handoff h_before=handoff;
    uint64_t error=sr_validate(&handoff,0x30000000,map,bytes,stride,forbidden,n,&out.value);checks++;
    if(error!=expected)fprintf(stderr,"got 0x%llx expected 0x%llx\n",(unsigned long long)error,(unsigned long long)expected);
    CHECK(error==expected);CHECK(memcmp(map,map_before,sizeof map)==0&&memcmp(&handoff,&h_before,sizeof handoff)==0);
    CHECK(out.a[0]==UINT64_C(0xa7a7a7a7a7a7a7a7)&&out.a[1]==out.a[0]&&out.z[0]==out.a[0]&&out.z[1]==out.a[0]);
    if(error) { CHECK(memcmp(&out.value,&before,sizeof before)==0);bad++; }
    else { Plan wanted={{0x30000000,4096},{handoff.words[4],handoff.words[5]},{handoff.words[7],handoff.words[8]}};CHECK(memcmp(&wanted,&out.value,sizeof wanted)==0);good++; }
}
int main(void) {
    CHECK(sr_handoff_size()==96&&sr_plan_size()==48);fixture();Span allowed[]={{0x0ffff100,160},{0x30001010,96}};
    CHECK(sr_readable(map,count*48,48,0x30000000)==1);CHECK(sr_readable(map,count*48,48,0x10000000)==1);
    CHECK(sr_readable(map,count*48,48,0x30001000)==1);CHECK(sr_readable(map,count*48,48,0x30002000)==0);
    validate(0,count*48,48,allowed,2);fixture();validate(0,count*48,48,NULL,0);
    fixture();desc(6,5,UINT64_C(0x10000000000),16,UINT64_C(1)<<63);validate(0,count*48,48,allowed,2);
    for(unsigned i=0;i<12;i++) { fixture();handoff.words[i]^=1;if(i!=11)sum();validate(ERROR(i<=3||i==10||i==11?3:4),count*48,48,NULL,0); }
    fixture();handoff.words[4]=0x30000000;sum();validate(ERROR(6),count*48,48,NULL,0);
    fixture();handoff.words[7]=handoff.words[4];sum();validate(ERROR(6),count*48,48,NULL,0);
    fixture();Span overlap={handoff.words[4]-1,2};validate(ERROR(6),count*48,48,&overlap,1);
    fixture();Span adjacent={handoff.words[4]+8192,17};validate(0,count*48,48,&adjacent,1);
    fixture();Span malformed={UINT64_MAX-1,4};validate(ERROR(1),count*48,48,&malformed,1);
    fixture();desc(0,7,0x22000000,8192,0);validate(ERROR(5),count*48,48,NULL,0);
    fixture();desc(0,2,0x22000000,8192,UINT64_C(1)<<63);validate(ERROR(5),count*48,48,NULL,0);
    fixture();desc(0,2,0x22000000,8191,0);validate(ERROR(5),count*48,48,NULL,0);
    fixture();desc(5,7,0x30000000,2,0);CHECK(sr_readable(map,count*48,48,0x30000000)==0);validate(ERROR(5),count*48,48,NULL,0);
    fixture();desc(6,7,0x10000000,1,0);CHECK(sr_readable(map,count*48,48,0x30000000)==0);validate(ERROR(2),count*48,48,NULL,0);
    fixture();desc(6,16,UINT64_C(0x10000000000),16,0);validate(ERROR(2),count*48,48,NULL,0);
    fixture();desc(6,7,UINT64_C(0xfffffffffffff000),2,0);validate(ERROR(2),count*48,48,NULL,0);
    fixture();desc(6,7,0x50000001,16,0);validate(ERROR(2),count*48,48,NULL,0);
    fixture();desc(6,7,0x50000000,0,0);validate(ERROR(2),count*48,48,NULL,0);
    fixture();validate(ERROR(2),count*48-1,48,NULL,0);validate(ERROR(2),count*48,39,NULL,0);validate(ERROR(2),0,48,NULL,0);
    printf("service resource independent model passed checks=%u success=%u unchanged-rejections=%u\n",checks,good,bad);return 0;
}
