/* Independent serialized ELF fixtures and byte-level load/relocation oracle. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"ELF_MODEL_ASSERT line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
#define ERR(n) (UINT64_C(0x04030000)+(n))
#define LIMIT UINT64_C(0x8000000000)
typedef struct { uint64_t virtual_address,offset,filesz,memsz,start,size,flags,align; } Segment;
typedef struct { uint64_t entry,bias,count,pages,reloc_count,rela_offset; Segment segments[16]; } Plan;
typedef struct { uint64_t target,value; } Reloc;
extern ABI size_t elf_plan_size(void);
extern ABI uint64_t elf_exec_validate(const uint8_t *,size_t,uint64_t,Plan *);
extern ABI uint64_t elf_exec_relocation(const uint8_t *,size_t,const Plan *,uint64_t,Reloc *);
ABI void __dong_panic(uint64_t code) { fprintf(stderr,"unexpected Dong panic %llu\n",(unsigned long long)code); exit(99); }
ABI void elf_negative_hit(uint64_t kind) { fprintf(stderr,"ELF_NEGATIVE_HIT %llu\n",(unsigned long long)kind); }
static uint8_t image[0x5000],original[sizeof image];
static unsigned checks,success,rejected;
static void w16(size_t at,uint16_t value) { memcpy(image+at,&value,2); }
static void w32(size_t at,uint32_t value) { memcpy(image+at,&value,4); }
static void w64(size_t at,uint64_t value) { memcpy(image+at,&value,8); }
static void ph(unsigned i,uint32_t type,uint32_t flags,uint64_t off,uint64_t va,uint64_t fs,uint64_t ms,uint64_t align) {
    size_t at=64+i*56; w32(at,type);w32(at+4,flags);w64(at+8,off);w64(at+16,va);w64(at+24,0x12345678);
    w64(at+32,fs);w64(at+40,ms);w64(at+48,align);
}
static void dyn(unsigned i,uint64_t tag,uint64_t value) { w64(0x1100+i*16,tag);w64(0x1108+i*16,value); }
static void fixture(int pie) {
    memset(image,0,sizeof image); memcpy(image,"\177ELF\2\1\1",7);w16(16,pie?3:2);w16(18,62);w32(20,1);
    uint64_t text=pie?0:0x400000;w64(24,text+0x200);w64(32,64);w16(52,64);w16(54,56);w16(56,pie?4:3);
    ph(0,1,5,0,text,0x500,0x500,4096);ph(1,1,6,0x1000,text+0x2000,0x800,0x1000,4096);
    ph(2,0x6474e551,6,0,0,0,0,16);
    for(size_t i=0x200;i<0x500;i++) image[i]=(uint8_t)(i*37+3);
    for(size_t i=0x1000;i<0x1800;i++) image[i]=(uint8_t)(i*19+7);
    if(pie) {
        ph(3,2,6,0x1100,0x2100,96,96,8);memset(image+0x1100,0,96);
        dyn(0,7,0x2400);dyn(1,8,48);dyn(2,9,24);dyn(3,0x6ffffff9,2);dyn(4,0x6ffffffb,0x8000000);dyn(5,0,0);
        w64(0x1400,0x2a00);w64(0x1408,8);w64(0x1410,0x200);
        w64(0x1418,0x2a08);w64(0x1420,8);w64(0x1428,UINT64_MAX-0xffff);
    }
}
static Plan validate(uint64_t bias,uint64_t expected,size_t bytes) {
    struct { uint64_t a[2];Plan value;uint64_t z[2]; } guarded;
    memset(&guarded,0xa7,sizeof guarded);Plan before=guarded.value;memcpy(original,image,sizeof image);
    uint64_t error=elf_exec_validate(image,bytes,bias,&guarded.value);checks++;
    if(error!=expected) fprintf(stderr,"error got 0x%llx expected 0x%llx\n",(unsigned long long)error,(unsigned long long)expected);
    CHECK(error==expected);CHECK(memcmp(image,original,sizeof image)==0);
    CHECK(guarded.a[0]==UINT64_C(0xa7a7a7a7a7a7a7a7)&&guarded.a[1]==guarded.a[0]&&guarded.z[0]==guarded.a[0]&&guarded.z[1]==guarded.a[0]);
    if(expected) { CHECK(memcmp(&before,&guarded.value,sizeof before)==0);rejected++; } else success++;
    return guarded.value;
}
static void load_oracle(int pie) {
    const uint64_t bias=pie?0x1000000:0,text=pie?0x1000000:0x400000;
    fixture(pie);Plan got=validate(bias,0,sizeof image), expected={0};
    expected.entry=text+0x200;expected.bias=bias;expected.count=2;expected.pages=2;
    expected.segments[0]=(Segment){text,0,0x500,0x500,text,4096,5,4096};
    expected.segments[1]=(Segment){text+0x2000,0x1000,0x800,0x1000,text+0x2000,4096,6,4096};
    if(pie) { expected.reloc_count=2;expected.rela_offset=0x1400; }
    CHECK(memcmp(&got,&expected,sizeof got)==0);
    uint8_t memory[2][4096];memset(memory,0,sizeof memory);
    for(unsigned i=0;i<2;i++) {
        Segment *s=&got.segments[i];memcpy(memory[i]+s->virtual_address-s->start,image+s->offset,(size_t)s->filesz);
        CHECK(memcmp(memory[i],image+s->offset,(size_t)s->filesz)==0);
        for(size_t j=(size_t)s->filesz;j<4096;j++) CHECK(memory[i][j]==0);
    }
    if(pie) {
        for(unsigned i=0;i<2;i++) { Reloc relocation={0};CHECK(elf_exec_relocation(image,sizeof image,&got,i,&relocation)==0);
            CHECK(relocation.target==text+0x2a00+i*8);CHECK(relocation.value==(i==0?text+0x200:text-0x10000));
            memcpy(memory[1]+relocation.target-(text+0x2000),&relocation.value,8);
        }
        uint64_t first,second;memcpy(&first,memory[1]+0xa00,8);memcpy(&second,memory[1]+0xa08,8);
        CHECK(first==text+0x200&&second==text-0x10000);
        Reloc out={0x1234,0x5678},before=out;CHECK(elf_exec_relocation(image,sizeof image,&got,2,&out)==ERR(4));CHECK(memcmp(&out,&before,sizeof out)==0);
    }
}
int main(void) {
    CHECK(elf_plan_size()==sizeof(Plan)&&sizeof(Plan)==1072);load_oracle(0);load_oracle(1);
    fixture(0);ph(0,1,5,0,LIMIT-0x4000,0x500,0x500,4096);ph(1,1,6,0x1000,LIMIT-0x2000,0x800,0x2000,4096);w64(24,LIMIT-0x3e00);Plan top=validate(0,0,sizeof image);CHECK(top.pages==3);
    fixture(0);ph(0,1,5,0,0x10000,0x500,0x500,0);ph(1,1,6,0x1000,0x12000,0,0x2000,1);w64(24,0x10200);validate(0,0,sizeof image);
    fixture(1);w64(0x1410,0x10000);w64(0x1428,0x10008);validate(0x2000000,0,sizeof image);
    fixture(1);ph(1,1,6,0x1000,0x2000,0x2000,0x3000,4096);dyn(1,8,128*24);dyn(3,0x6ffffff9,128);
    for(unsigned i=0;i<128;i++) { w64(0x1400+i*24,0x4000+i*8);w64(0x1408+i*24,8);w64(0x1410+i*24,0x200+i*8); }
    Plan full=validate(0x1000000,0,sizeof image);CHECK(full.reloc_count==128&&full.pages==4);
    Reloc last={0};CHECK(elf_exec_relocation(image,sizeof image,&full,127,&last)==0);CHECK(last.target==0x10043f8&&last.value==0x10005f8);
    w64(0x1400+127*24,0x4000);validate(0x1000000,ERR(7),sizeof image);
    struct Mutation { unsigned offset,width;uint64_t value,error;int pie; } cases[]={
        {0,4,0,2,0},{4,2,1,2,0},{6,2,0,2,0},{8,2,1,2,0},{16,2,1,3,0},{18,2,3,3,0},{20,4,0,3,0},
        {48,4,1,3,0},{52,2,63,3,0},{54,2,55,3,0},{56,2,0,8,0},{56,2,33,8,0},
        {32,8,UINT64_MAX,2,0},{32,8,0x5000,4,0},{40,8,0x1000,3,0},{60,2,1,2,0},
        {68,4,7,6,0},{68,4,1,6,0},{68,4,0x105,6,0},{96,8,0x501,4,0},
        {112,8,3,5,0},{112,8,0x400000,5,0},{80,8,0x400001,5,0},
        {24,8,0x401000,9,0},{24,8,0x402000,9,0},{24,8,0xffff800000000000ULL,9,0},
        {128,8,0x4fff,4,0},{136,8,0x400000,7,0},{136,8,0x3ff000,2,0},
        {160,8,0x5000000,8,0},{64,4,3,3,0},{176,4,0x6474e552,3,0},{180,4,7,6,0},
        {0x1100,8,1,3,1},{0x1118,8,47,3,1},{0x1128,8,23,3,1},{0x1138,8,3,3,1},
        {0x1108,8,0x2a00,4,1},{0x1408,8,0x100000008ULL,3,1},{0x1408,8,1,3,1},
        {0x1400,8,0x200,6,1},{0x1400,8,0x2fff,5,1},{0x1400,8,0x3000,6,1},
        {0x1418,8,0x2a00,7,1},{0x1410,8,LIMIT,4,1},{0x1410,8,UINT64_C(0x8000000000000000),4,1},
        {0x1118,8,129*24,3,1},{64+3*56+32,8,0,3,1},{0x1150,8,7,2,1}
    };
    for(unsigned i=0;i<sizeof cases/sizeof cases[0];i++) { struct Mutation *m=&cases[i];fixture(m->pie);
        if(m->width==2) w16(m->offset,(uint16_t)m->value);else if(m->width==4) w32(m->offset,(uint32_t)m->value);else w64(m->offset,m->value);
        validate(m->pie?0x1000000:0,ERR(m->error),sizeof image);
    }
    fixture(0);validate(4096,ERR(5),sizeof image);fixture(1);validate(1,ERR(5),sizeof image);
    fixture(1);validate(UINT64_C(0xfffffffffffff000),ERR(4),sizeof image);
    fixture(0);validate(0,ERR(1),63);fixture(0);validate(0,ERR(1),0x1000001);
    fixture(1);w64(0x1118,0);w64(0x1138,0);validate(0x1000000,0,sizeof image);
    printf("elf independent fixture passed checks=%u success=%u rejected=%u full-output-unchanged=%u\n",checks,success,rejected,rejected);
    return 0;
}
