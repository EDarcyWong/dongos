#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DG __attribute__((sysv_abi))
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"ACPI startup failure line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
#define LIMIT UINT64_C(0x100000000)
#define BASE UINT64_C(0x100000)
#define INVALID_INFO UINT64_C(0x03020001)
#define NOT_READY UINT64_C(0x03020003)
#define BUSY UINT64_C(0x03020004)
#define ALREADY UINT64_C(0x03020005)

struct Gas { uint64_t space, width, offset, access, address; };
struct Cpu { uint64_t kind, uid, apic_id, flags; };
struct IoApic { uint64_t id, address, gsi_base; };
struct Iso { uint64_t bus, source, gsi, flags; };
struct Nmi { uint64_t kind, processor, flags, lint, gsi; };
struct Mcfg { uint64_t base, segment, first, last; };
struct Inventory {
    uint64_t rsdp,xsdt,madt,fadt,hpet,mcfg,rsdp_revision,table_count,lapic_address,madt_flags;
    uint64_t cpu_count,ioapic_count,iso_count,nmi_count,mcfg_count;
    uint64_t fadt_revision,fadt_flags,sci_interrupt,boot_arch,dsdt,pm_timer_block,pm_timer_length,pm_timer_32bit;
    uint64_t reset_value,hpet_id,hpet_number,hpet_min_tick,hpet_page_protection;
    struct Gas pm_timer_gas,reset_gas,hpet_gas;
    struct Cpu cpus[16]; struct IoApic ioapics[8]; struct Iso isos[16]; struct Nmi nmis[16]; struct Mcfg mcfg_regions[8];
};
struct Report { uint64_t value[24]; };
struct GuardReport { uint8_t before[16]; struct Report report; uint8_t after[16]; };
struct GuardInventory { uint8_t before[16]; struct Inventory inventory; uint8_t after[16]; };
typedef const uint8_t *(DG *Reader)(uint64_t,uint64_t,size_t);
extern uint64_t DG as_report_size(void),as_report_align(void),as_inventory_size(void),as_inventory_align(void);
extern uint64_t DG as_readable(const uint8_t *,size_t,size_t,uint64_t,size_t);
extern uint64_t DG as_prepare(const void *),as_prepare_with(Reader,uint64_t,uint64_t),as_report(struct Report *);
extern const struct Inventory *DG as_inventory_pointer(void);
extern uint64_t DG as_inventory_copy(struct Inventory *);

void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length) {
    fprintf(stderr,"unexpected ACPI startup panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,file); exit(99);
}
static uint32_t u32(const uint8_t *p) { uint32_t v; memcpy(&v,p,4); return v; }
static uint64_t u64(const uint8_t *p) { uint64_t v; memcpy(&v,p,8); return v; }
static void w16(uint8_t *p,uint16_t v) { memcpy(p,&v,2); }
static void w32(uint8_t *p,uint32_t v) { memcpy(p,&v,4); }
static void w64(uint8_t *p,uint64_t v) { memcpy(p,&v,8); }
static void descriptor(uint8_t *p,uint32_t type,uint64_t start,uint64_t pages,uint64_t attr) {
    w32(p,type); w64(p+8,start); w64(p+16,UINT64_C(0xdeadbeef)); w64(p+24,pages); w64(p+32,attr);
}
struct Segment { uint64_t start,end,attr; uint32_t type; };
static int compare(const void *a,const void *b) {
    const struct Segment *x=a,*y=b; return (x->start>y->start)-(x->start<y->start);
}
// Independent sort-and-advance interval oracle, with 128-bit endpoint math.
static int readable_model(const uint8_t *raw,size_t length,size_t stride,uint64_t pa,size_t bytes) {
    if (!raw || !length || length>65536 || stride<40 || stride%8 || length%stride || !pa || pa>=LIMIT || !bytes || bytes>LIMIT-pa) return 0;
    struct Segment segments[1639]; size_t n=length/stride;
    for (size_t i=0;i<n;i++) {
        const uint8_t *p=raw+i*stride; uint64_t start=u64(p+8),pages=u64(p+24);
        __uint128_t end=(__uint128_t)start+(__uint128_t)pages*4096;
        if (start%4096 || !pages || end>UINT64_MAX) return 0;
        segments[i]=(struct Segment){start,(uint64_t)end,u64(p+32),u32(p)};
    }
    qsort(segments,n,sizeof(segments[0]),compare);
    for (size_t i=1;i<n;i++) if (segments[i-1].end>segments[i].start) return 0;
    uint64_t cursor=pa,end=pa+bytes;
    for (size_t i=0;i<n && cursor<end;i++) {
        if (segments[i].end<=cursor) continue;
        if (segments[i].start>cursor || (segments[i].type!=9 && segments[i].type!=10) || segments[i].attr>>63) return 0;
        cursor=segments[i].end;
    }
    return cursor>=end;
}
static uint64_t rng=UINT64_C(0xf7bd42953a197e61);
static uint64_t next(void) { rng^=rng<<13; rng^=rng>>7; rng^=rng<<17; return rng; }
static void range_case(uint8_t *raw,size_t length,size_t stride,uint64_t pa,size_t bytes) {
    uint8_t before[512]; CHECK(length<=sizeof(before)); memcpy(before,raw,length);
    CHECK(as_readable(raw,length,stride,pa,bytes)==(uint64_t)readable_model(raw,length,stride,pa,bytes));
    CHECK(!memcmp(raw,before,length));
}
static void ranges(void) {
    uint8_t storage[16+512+16],before[sizeof(storage)]; memset(storage,0xa5,sizeof(storage));
    uint8_t *raw=storage+17; // Deliberately unaligned raw map, opaque tails intact.
    descriptor(raw,9,0x1000,1,0); descriptor(raw+48,10,0x2000,1,0);
    CHECK(as_readable(raw,96,48,0x1ff0,32)==1); range_case(raw,96,48,0x1ff0,32);
    descriptor(raw,10,0x2000,1,0); descriptor(raw+48,9,0x1000,1,0);
    range_case(raw,96,48,0x1ff0,32);
    descriptor(raw+48,9,0x1000,1,UINT64_C(1)<<63); range_case(raw,96,48,0x1ff0,32);
    descriptor(raw+48,11,0x1000,1,0); range_case(raw,96,48,0x1000,1);
    descriptor(raw+48,9,0x4000,1,0); range_case(raw,96,48,0x2ff0,32);
    descriptor(raw+48,9,0x2000,1,0); range_case(raw,96,48,0x2000,1);
    descriptor(raw,9,LIMIT-4096,1,0); range_case(raw,48,48,LIMIT-1,1);
    CHECK(as_readable(raw,48,48,LIMIT-1,1)==1);
    const uint64_t addresses[]={0,1,LIMIT-1,LIMIT,UINT64_MAX};
    const size_t lengths[]={0,1,4096,SIZE_MAX};
    for (size_t a=0;a<sizeof(addresses)/sizeof(addresses[0]);a++) for (size_t b=0;b<sizeof(lengths)/sizeof(lengths[0]);b++) range_case(raw,48,48,addresses[a],lengths[b]);
    memcpy(before,storage,sizeof(storage));
    CHECK(!as_readable(NULL,48,48,0x1000,1)); CHECK(!as_readable(raw,0,48,0x1000,1));
    CHECK(!as_readable(raw,65537,48,0x1000,1));
    for (size_t s=0;s<48;s++) if (s<40 || s%8) CHECK(!as_readable(raw,48,s,0x1000,1));
    CHECK(!memcmp(before,storage,sizeof(storage)));
    for (size_t round=0;round<512;round++) {
        size_t count=1+next()%6,stride=(next()&1)?40:48;
        memset(raw,0xa5,512);
        for (size_t i=0;i<count;i++) {
            uint32_t type=(uint32_t[]){7,9,10,11}[next()%4];
            descriptor(raw+i*stride,type,UINT64_C(0x1000000)+(next()%24)*4096,1+next()%4,(next()%8==0)?UINT64_C(1)<<63:0);
        }
        if (round%13==0) w64(raw+24,0);
        if (round%17==0) w64(raw+8,UINT64_MAX-4095);
        if (round%19==0) w64(raw+24,UINT64_MAX);
        for (size_t q=0;q<12;q++) range_case(raw,count*stride,stride,UINT64_C(0x1000000)+(next()%28)*4096+(next()%64),1+next()%8192);
    }
    for (size_t i=0;i<17;i++) CHECK(storage[i]==0xa5);
    for (size_t i=17+512;i<sizeof(storage);i++) CHECK(storage[i]==0xa5);
    puts("ACPI UEFI independent coverage model passed");
}

struct Context { uint8_t image[0x7000]; size_t calls; int unreadable,reenter,reentered; };
static void checksum(uint8_t *p,size_t n,size_t offset) { p[offset]=0; unsigned sum=0; for(size_t i=0;i<n;i++) sum+=p[i]; p[offset]=(uint8_t)(0-sum); }
static void header(uint8_t *p,const char *signature,uint32_t n,uint8_t revision) {
    memset(p,0,n); memcpy(p,signature,4); w32(p+4,n); p[8]=revision; memcpy(p+10,"DONGOS",6); memcpy(p+16,"STARTUP ",8);
}
static void gas(uint8_t *p,uint8_t space,uint8_t width,uint8_t access,uint64_t address) {
    p[0]=space;p[1]=width;p[2]=0;p[3]=access;w64(p+4,address);
}
static void tables(struct Context *c) {
    memset(c,0,sizeof(*c)); uint8_t *p=c->image;
    memcpy(p,"RSD PTR ",8);memcpy(p+9,"DONGOS",6);p[15]=2;w32(p+20,36);w64(p+24,BASE+0x1000);
    checksum(p,20,8); checksum(p,36,32);
    p=c->image+0x1000;header(p,"XSDT",68,1);for(size_t i=0;i<4;i++)w64(p+36+i*8,BASE+0x2000+i*0x1000);checksum(p,68,9);
    p=c->image+0x2000;header(p,"APIC",96,5);w32(p+36,0xfee00000);w32(p+40,1);
    p[44]=0;p[45]=8;p[46]=1;p[47]=2;w32(p+48,1);
    p[52]=9;p[53]=16;w32(p+56,0x102);w32(p+60,3);w32(p+64,9);
    p[68]=1;p[69]=12;p[70]=7;w32(p+72,0xfec00000);w32(p+76,0);
    p[80]=2;p[81]=10;p[82]=0;p[83]=9;w32(p+84,9);w16(p+88,0);
    p[90]=4;p[91]=6;p[92]=255;w16(p+93,0);p[95]=1;checksum(p,96,9);
    p=c->image+0x3000;header(p,"FACP",244,6);w32(p+40,(uint32_t)(BASE+0x6000));w16(p+46,9);
    w32(p+76,0x408);p[91]=4;w16(p+109,3);w32(p+112,0x100);w64(p+140,BASE+0x6000);
    gas(p+208,1,32,3,0x408);checksum(p,244,9);
    p=c->image+0x4000;header(p,"HPET",56,1);w32(p+36,0x8086a201);gas(p+40,0,64,4,0xfed00000);p[52]=0;w16(p+53,128);p[55]=0;checksum(p,56,9);
    p=c->image+0x5000;header(p,"MCFG",60,1);w64(p+44,0xe0000000);w16(p+52,0);p[54]=0;p[55]=255;checksum(p,60,9);
    p=c->image+0x6000;header(p,"DSDT",36,2);checksum(p,36,9);
}
static const uint8_t *DG reader(uint64_t context,uint64_t pa,size_t bytes) {
    struct Context *c=(struct Context *)(uintptr_t)context;c->calls++;
    if(c->reenter && !c->reentered) {
        c->reentered=1;struct GuardReport out,old;memset(&out,0xa5,sizeof(out));old=out;
        CHECK(as_prepare_with(reader,context,BASE)==BUSY);CHECK(as_report(&out.report)==BUSY);
        CHECK(!memcmp(&out,&old,sizeof(out)));CHECK(as_inventory_pointer()==NULL);
    }
    if(c->unreadable || pa<BASE || !bytes || pa-BASE>sizeof(c->image) || bytes>sizeof(c->image)-(size_t)(pa-BASE)) return NULL;
    return c->image+(size_t)(pa-BASE);
}
static void DG persistent(void) {
    CHECK(sizeof(struct Inventory)==2456);CHECK(as_inventory_size()==2456 && as_inventory_align()==8);
    CHECK(as_report_size()==192 && as_report_align()==8);
    struct GuardReport out,old;memset(&out,0xa5,sizeof(out));old=out;
    static struct GuardInventory copy,copy_before;memset(&copy,0xa5,sizeof(copy));copy_before=copy;
    CHECK(as_inventory_pointer()==NULL);CHECK(as_report(&out.report)==NOT_READY);CHECK(!memcmp(&out,&old,sizeof(out)));
    CHECK(as_inventory_copy(&copy.inventory)==NOT_READY);CHECK(!memcmp(&copy,&copy_before,sizeof(copy)));
    CHECK(as_prepare(NULL)==INVALID_INFO);uint64_t info[20]={0};CHECK(as_prepare(info)==INVALID_INFO);
    info[0]=UINT64_C(0x544f4f42474e4f44);info[1]=1;info[2]=160;info[3]=1;info[4]=1;info[5]=40;info[6]=40;info[7]=2;info[14]=BASE;
    CHECK(as_prepare(info)==INVALID_INFO);CHECK(as_inventory_pointer()==NULL);
    static struct Context c;tables(&c);c.unreadable=1;
    CHECK(as_prepare_with(reader,(uintptr_t)&c,BASE)==UINT64_C(0x03010002));CHECK(c.calls>0);CHECK(as_inventory_pointer()==NULL);
    CHECK(as_report(&out.report)==NOT_READY);CHECK(!memcmp(&out,&old,sizeof(out)));
    tables(&c);c.image[8]^=1;
    CHECK(as_prepare_with(reader,(uintptr_t)&c,BASE)==UINT64_C(0x03010005));CHECK(c.calls>0);CHECK(as_inventory_pointer()==NULL);
    CHECK(as_report(&out.report)==NOT_READY);CHECK(!memcmp(&out,&old,sizeof(out)));
    tables(&c);c.reenter=1;CHECK(as_prepare_with(reader,(uintptr_t)&c,BASE)==0);CHECK(c.reentered);
    CHECK(as_report(&out.report)==0);CHECK(as_inventory_copy(&copy.inventory)==0);
    const uint64_t expected[24]={BASE,BASE+0x1000,BASE+0x2000,BASE+0x3000,BASE+0x4000,BASE+0x5000,
        4,2,1,1,1,1,UINT64_C(0xfee00000),1,0x100,3,0x408,4,1,0x04004000,UINT64_C(0xfed00000),0x03002001,0x408,7};
    CHECK(!memcmp(out.report.value,expected,sizeof(expected)));
    for(size_t i=0;i<16;i++)CHECK(out.before[i]==0xa5 && out.after[i]==0xa5 && copy.before[i]==0xa5 && copy.after[i]==0xa5);
    static struct Inventory expect;memset(&expect,0,sizeof(expect));
    expect.rsdp=BASE;expect.xsdt=BASE+0x1000;expect.madt=BASE+0x2000;expect.fadt=BASE+0x3000;expect.hpet=BASE+0x4000;expect.mcfg=BASE+0x5000;
    expect.rsdp_revision=2;expect.table_count=4;expect.lapic_address=0xfee00000;expect.madt_flags=1;
    expect.cpu_count=2;expect.ioapic_count=expect.iso_count=expect.nmi_count=expect.mcfg_count=1;
    expect.fadt_revision=6;expect.fadt_flags=0x100;expect.sci_interrupt=9;expect.boot_arch=3;expect.dsdt=BASE+0x6000;
    expect.pm_timer_block=0x408;expect.pm_timer_length=4;expect.pm_timer_32bit=1;
    expect.hpet_id=0x8086a201;expect.hpet_min_tick=128;
    expect.pm_timer_gas=(struct Gas){1,32,0,3,0x408};expect.hpet_gas=(struct Gas){0,64,0,4,0xfed00000};
    expect.cpus[0]=(struct Cpu){0,1,2,1};expect.cpus[1]=(struct Cpu){9,9,0x102,3};
    expect.ioapics[0]=(struct IoApic){7,0xfec00000,0};expect.isos[0]=(struct Iso){0,9,9,0};
    expect.nmis[0]=(struct Nmi){4,255,0,1,0};expect.mcfg_regions[0]=(struct Mcfg){0xe0000000,0,0,255};
    CHECK(!memcmp(&copy.inventory,&expect,sizeof(expect)));
    const struct Inventory *stable=as_inventory_pointer();CHECK(stable!=NULL && (uintptr_t)stable%8==0);
    CHECK((uintptr_t)stable<(uintptr_t)c.image || (uintptr_t)stable>=(uintptr_t)(c.image+sizeof(c.image)));
    size_t calls=c.calls;memset(c.image,0xcc,sizeof(c.image));old=out;copy_before=copy;
    CHECK(as_report(&out.report)==0);CHECK(as_inventory_copy(&copy.inventory)==0);
    CHECK(!memcmp(&out,&old,sizeof(out)) && !memcmp(&copy,&copy_before,sizeof(copy)));
    CHECK(as_inventory_pointer()==stable && c.calls==calls);
    CHECK(as_prepare_with(reader,(uintptr_t)&c,BASE)==ALREADY && c.calls==calls);
    CHECK(as_prepare(NULL)==ALREADY);CHECK(!memcmp(stable,&expect,sizeof(expect)));
    puts("ACPI startup persistent-copy/failure/reentry model passed");
}
int main(void) { ranges();persistent();return 0; }
