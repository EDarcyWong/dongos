/* Independent byte fixtures, PA reader oracle and fail-atomic inventory model. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"ACPI oracle line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
typedef struct { uint64_t address_space,bit_width,bit_offset,access_size,address; } Gas;
typedef struct { uint64_t kind,uid,apic_id,flags; } Cpu;
typedef struct { uint64_t id,address,gsi_base; } IoApic;
typedef struct { uint64_t bus,source,gsi,flags; } Iso;
typedef struct { uint64_t kind,processor,flags,lint,gsi; } Nmi;
typedef struct { uint64_t base,segment,start_bus,end_bus; } Mcfg;
typedef struct {
    uint64_t rsdp,xsdt,madt,fadt,hpet,mcfg,rsdp_revision,table_count,lapic_address,madt_flags;
    uint64_t cpu_count,ioapic_count,iso_count,nmi_count,mcfg_count;
    uint64_t fadt_revision,fadt_flags,sci_interrupt,boot_arch,dsdt,pm_timer_block,pm_timer_length,pm_timer_32bit;
    uint64_t reset_value,hpet_id,hpet_number,hpet_min_tick,hpet_page_protection;
    Gas pm_timer_gas,reset_gas,hpet_gas;
    Cpu cpus[16]; IoApic ioapics[8]; Iso isos[16]; Nmi nmis[16]; Mcfg mcfg_regions[8];
} Inventory;
extern ABI size_t acpi_inventory_size(void);
extern ABI size_t acpi_inventory_align(void);
extern ABI uint64_t acpi_parse(uint64_t,uint64_t,Inventory *);
ABI void __dong_panic(uint64_t code) { fprintf(stderr,"unexpected Dong panic %llu\n",(unsigned long long)code); exit(99); }
ABI void acpi_negative_hit(uint64_t kind) { fprintf(stderr,"ACPI_NEGATIVE_HIT kind=%llu\n",(unsigned long long)kind); }

enum { RSDP, XSDT, MADT, FADT, HPET, MCFG, UNKNOWN, EXTRA, REGION_COUNT };
static const uint64_t addresses[REGION_COUNT] = {0x123000,0x200000,0x300000,0x400000,0x500000,0x600000,0x700000,0x800000};
typedef struct { uint64_t physical; size_t length; uint8_t bytes[4096]; } Region;
static Region regions[REGION_COUNT], saved[REGION_COUNT];
static unsigned reader_calls, checks, successes, failures;
static uint64_t denied, context_tag = UINT64_C(0x12345678abc000);
static size_t last_length;
static uint64_t last_physical;
static uint8_t extra_tables[64][36], maximum_table[0x100000];
static int extra_tables_on, maximum_table_on;

static void put16(uint8_t *p,uint16_t x) { p[0]=(uint8_t)x; p[1]=(uint8_t)(x>>8); }
static void put32(uint8_t *p,uint32_t x) { for(unsigned i=0;i<4;i++) p[i]=(uint8_t)(x>>(i*8)); }
static void put64(uint8_t *p,uint64_t x) { for(unsigned i=0;i<8;i++) p[i]=(uint8_t)(x>>(i*8)); }
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static void sum_at(uint8_t *p,size_t n,size_t at) { uint8_t sum=0; p[at]=0; for(size_t i=0;i<n;i++) sum=(uint8_t)(sum+p[i]); p[at]=(uint8_t)(0-sum); }
static void finish(unsigned region) { uint8_t *p=regions[region].bytes; sum_at(p,get32(p+4),9); }
static void rsdp_finish(void) { uint8_t *p=regions[RSDP].bytes; sum_at(p,20,8); sum_at(p,get32(p+20),32); }
static void header(unsigned id,const char *signature,size_t length,unsigned revision) {
    Region *r=&regions[id]; r->physical=addresses[id]; r->length=sizeof r->bytes;
    memcpy(r->bytes,signature,4); put32(r->bytes+4,(uint32_t)length); r->bytes[8]=(uint8_t)revision;
    memcpy(r->bytes+10,"ORACLE",6); memcpy(r->bytes+16,"BYTES   ",8);
}
static void gas_bytes(uint8_t *p,unsigned space,unsigned width,unsigned offset,unsigned access,uint64_t address) {
    p[0]=(uint8_t)space; p[1]=(uint8_t)width; p[2]=(uint8_t)offset; p[3]=(uint8_t)access; put64(p+4,address);
}
static size_t entry(unsigned kind) {
    uint8_t *p=regions[MADT].bytes; size_t end=get32(p+4);
    for(size_t i=44;i+2<=end&&p[i+1]>=2;i+=p[i+1]) if(p[i]==kind) return i;
    CHECK(0); return 0;
}
static void root_entries(const unsigned *ids,size_t count) {
    put32(regions[XSDT].bytes+4,(uint32_t)(36+count*8));
    for(size_t i=0;i<count;i++) put64(regions[XSDT].bytes+36+i*8,addresses[ids[i]]);
    finish(XSDT);
}
static void fixture(void) {
    memset(regions,0,sizeof regions); denied=0; reader_calls=0;
    for(unsigned i=0;i<REGION_COUNT;i++) { regions[i].physical=addresses[i]; regions[i].length=4096; }
    uint8_t *p=regions[RSDP].bytes;
    memcpy(p,"RSD PTR ",8); memcpy(p+9,"ORACLE",6); p[15]=2; put32(p+20,36); put64(p+24,addresses[XSDT]); rsdp_finish();
    header(XSDT,"XSDT",76,1);
    const unsigned ids[]={MADT,FADT,HPET,MCFG,UNKNOWN}; root_entries(ids,5);
    header(MADT,"APIC",132,5); p=regions[MADT].bytes; put32(p+36,0xfee00000); put32(p+40,1);
    size_t at=44;
    p[at]=0; p[at+1]=8; p[at+2]=1; p[at+3]=2; put32(p+at+4,1); at+=8;
    p[at]=1; p[at+1]=12; p[at+2]=3; put32(p+at+4,0xfec00000); put32(p+at+8,0); at+=12;
    p[at]=2; p[at+1]=10; p[at+2]=0; p[at+3]=0; put32(p+at+4,2); put16(p+at+8,0); at+=10;
    p[at]=3; p[at+1]=8; put16(p+at+2,0); put32(p+at+4,31); at+=8;
    p[at]=4; p[at+1]=6; p[at+2]=255; put16(p+at+3,5); p[at+5]=1; at+=6;
    p[at]=5; p[at+1]=12; put64(p+at+4,0xfee01000); at+=12;
    p[at]=9; p[at+1]=16; put32(p+at+4,0x102); put32(p+at+8,2); put32(p+at+12,0x100); at+=16;
    p[at]=10; p[at+1]=12; put16(p+at+2,15); put32(p+at+4,0x100); p[at+8]=0; at+=12;
    p[at]=127; p[at+1]=4; p[at+2]=0xbb; p[at+3]=0xcc; at+=4; CHECK(at==132); finish(MADT);
    header(FADT,"FACP",276,6); p=regions[FADT].bytes;
    put32(p+40,0x900000); put16(p+46,9); put32(p+76,0x608); p[91]=4; put16(p+109,3); put32(p+112,0x500);
    gas_bytes(p+116,1,8,0,1,0xcf9); p[128]=6; put64(p+140,0x910000); gas_bytes(p+208,1,32,0,3,0x608); finish(FADT);
    header(HPET,"HPET",56,1); p=regions[HPET].bytes; put32(p+36,0x8086a201);
    gas_bytes(p+40,0,0,0,0,0xfed00000); p[52]=1; put16(p+53,0x80); p[55]=1; finish(HPET);
    header(MCFG,"MCFG",76,1); p=regions[MCFG].bytes;
    put64(p+44,0xb0000000); put16(p+52,0); p[54]=0; p[55]=63;
    put64(p+60,0xc0000000); put16(p+68,1); p[70]=64; p[71]=127; finish(MCFG);
    header(UNKNOWN,"TEST",40,1); regions[UNKNOWN].bytes[36]=0x5c; finish(UNKNOWN);
    memcpy(saved,regions,sizeof saved);
}
static void restore(void) { memcpy(regions,saved,sizeof regions); denied=0; reader_calls=0; extra_tables_on=maximum_table_on=0; }
ABI const uint8_t *acpi_reader(uint64_t context,uint64_t physical,size_t length) {
    CHECK(context==context_tag); CHECK(physical>0&&physical<UINT64_C(0x100000000));
    CHECK(length>0&&length<=0x100000&&length<=UINT64_C(0x100000000)-physical);
    reader_calls++; last_length=length; last_physical=physical;
    if(physical==denied) return NULL;
    if(maximum_table_on && physical==0x2000000 && length<=sizeof maximum_table) return maximum_table;
    if(extra_tables_on && physical>=0x1000000 && physical<0x1000000+64*4096 && (physical&4095)==0 && length<=36)
        return extra_tables[(physical-0x1000000)/4096];
    for(unsigned i=0;i<REGION_COUNT;i++) {
        Region *r=&regions[i];
        if(physical>=r->physical && physical-r->physical<=r->length && length<=r->length-(size_t)(physical-r->physical))
            return r->bytes+(size_t)(physical-r->physical);
    }
    return NULL;
}
static void expected_full(Inventory *e) {
    memset(e,0,sizeof *e); e->rsdp=addresses[RSDP]; e->xsdt=addresses[XSDT]; e->madt=addresses[MADT];
    e->fadt=addresses[FADT]; e->hpet=addresses[HPET]; e->mcfg=addresses[MCFG]; e->rsdp_revision=2; e->table_count=5;
    e->lapic_address=0xfee01000; e->madt_flags=1; e->cpu_count=2; e->ioapic_count=1; e->iso_count=1; e->nmi_count=3; e->mcfg_count=2;
    e->fadt_revision=6; e->fadt_flags=0x500; e->sci_interrupt=9; e->boot_arch=3; e->dsdt=0x910000;
    e->pm_timer_block=0x608; e->pm_timer_length=4; e->pm_timer_32bit=1; e->reset_value=6;
    e->hpet_id=0x8086a201; e->hpet_number=1; e->hpet_min_tick=0x80; e->hpet_page_protection=1;
    e->pm_timer_gas=(Gas){1,32,0,3,0x608}; e->reset_gas=(Gas){1,8,0,1,0xcf9}; e->hpet_gas=(Gas){0,0,0,0,0xfed00000};
    e->cpus[0]=(Cpu){0,1,2,1}; e->cpus[1]=(Cpu){9,0x100,0x102,2}; e->ioapics[0]=(IoApic){3,0xfec00000,0};
    e->isos[0]=(Iso){0,0,2,0}; e->nmis[0]=(Nmi){3,0,0,0,31}; e->nmis[1]=(Nmi){4,255,5,1,0}; e->nmis[2]=(Nmi){10,0x100,15,0,0};
    e->mcfg_regions[0]=(Mcfg){0xb0000000,0,0,63}; e->mcfg_regions[1]=(Mcfg){0xc0000000,1,64,127};
}
static uint64_t source_hash(void) {
    uint64_t hash=UINT64_C(1469598103934665603);
    for(unsigned r=0;r<REGION_COUNT;r++) for(size_t i=0;i<sizeof regions[r].bytes;i++) hash=(hash^regions[r].bytes[i])*UINT64_C(1099511628211);
    if(extra_tables_on) for(size_t i=0;i<sizeof extra_tables;i++) hash=(hash^((const uint8_t *)extra_tables)[i])*UINT64_C(1099511628211);
    if(maximum_table_on) for(size_t i=0;i<sizeof maximum_table;i++) hash=(hash^maximum_table[i])*UINT64_C(1099511628211);
    return hash;
}
static void success(Inventory *expected) {
    struct { uint64_t prefix[2]; Inventory out; uint64_t suffix[2]; } guarded;
    memset(&guarded,0xa7,sizeof guarded);
    uint64_t input_before=source_hash();
    uint64_t error=acpi_parse(context_tag,addresses[RSDP],&guarded.out);
    if(error) fprintf(stderr,"unexpected error 0x%llx\n",(unsigned long long)error);
    CHECK(error==0); CHECK(memcmp(&guarded.out,expected,sizeof guarded.out)==0); CHECK(reader_calls>0); CHECK(input_before==source_hash());
    CHECK(guarded.prefix[0]==UINT64_C(0xa7a7a7a7a7a7a7a7)&&guarded.prefix[1]==guarded.prefix[0]);
    CHECK(guarded.suffix[0]==guarded.prefix[0]&&guarded.suffix[1]==guarded.prefix[0]); successes++; checks++;
}
static void reject(uint64_t rsdp,uint64_t expected_error) {
    struct { uint64_t prefix[2]; Inventory out; uint64_t suffix[2]; } guarded;
    Inventory before; memset(&guarded,0xa7,sizeof guarded); before=guarded.out;
    Inventory *out=&guarded.out;
    uint64_t input_before=source_hash();
    uint64_t error=acpi_parse(context_tag,rsdp,out);
    if(error!=expected_error) fprintf(stderr,"reject %u got 0x%llx expected 0x%llx\n",checks,(unsigned long long)error,(unsigned long long)expected_error);
    CHECK(error==expected_error); CHECK(memcmp(out,&before,sizeof *out)==0); CHECK(input_before==source_hash());
    CHECK(guarded.prefix[0]==UINT64_C(0xa7a7a7a7a7a7a7a7)&&guarded.prefix[1]==guarded.prefix[0]);
    CHECK(guarded.suffix[0]==guarded.prefix[0]&&guarded.suffix[1]==guarded.prefix[0]); failures++; checks++;
}
#define ERROR(x) (UINT64_C(0x03010000)+(x))
static void append_entry(const uint8_t *entry_bytes,size_t n) {
    uint8_t *p=regions[MADT].bytes; size_t len=get32(p+4); CHECK(len+n<4096); memcpy(p+len,entry_bytes,n); put32(p+4,(uint32_t)(len+n)); finish(MADT);
}
int main(void) {
    CHECK(sizeof(Inventory)==2456); CHECK(acpi_inventory_size()==sizeof(Inventory)); CHECK(acpi_inventory_align()==8);
    fixture(); Inventory expected; expected_full(&expected); success(&expected);
    /* Legacy-sized FADT remains usable; absent optional tables are zero. */
    restore(); const unsigned minimal[]={MADT,FADT}; root_entries(minimal,2); put32(regions[FADT].bytes+4,116); regions[FADT].bytes[8]=1; put32(regions[FADT].bytes+112,0x100); finish(FADT);
    expected_full(&expected); expected.hpet=expected.mcfg=0; expected.table_count=2; expected.mcfg_count=0;
    expected.fadt_revision=1; expected.fadt_flags=0x100; expected.dsdt=0x900000; expected.reset_value=0;
    expected.hpet_id=expected.hpet_number=expected.hpet_min_tick=expected.hpet_page_protection=0;
    expected.pm_timer_gas=(Gas){0}; expected.reset_gas=(Gas){0}; expected.hpet_gas=(Gas){0};
    memset(expected.mcfg_regions,0,sizeof expected.mcfg_regions); success(&expected);
    /* Forward-compatible RSDP tail and declared MADT tail/reserved bytes. */
    restore(); put32(regions[RSDP].bytes+20,48); regions[RSDP].bytes[40]=0x99; rsdp_finish(); expected_full(&expected); success(&expected);
    restore(); regions[MADT].bytes[entry(9)+2]=0x99; put32(regions[MADT].bytes+40,0x80000001); finish(MADT); expected_full(&expected); expected.madt_flags=0x80000001; success(&expected);
    /* Distinct ISA sources may share one GSI and local wildcard NMI may coexist. */
    restore(); const uint8_t shared[]={2,10,0,9,2,0,0,0,15,0}; append_entry(shared,sizeof shared); expected_full(&expected); expected.iso_count=2; expected.isos[1]=(Iso){0,9,2,15}; success(&expected);
    restore(); const uint8_t specific[]={4,6,1,0,0,1}; append_entry(specific,sizeof specific); expected_full(&expected); expected.nmi_count=4; expected.nmis[3]=(Nmi){4,1,0,1,0}; success(&expected);
    /* Positive hard bounds: all 64 XSDT addresses distinct and one full 1MiB table. */
    restore(); extra_tables_on=1;
    for(unsigned i=0;i<60;i++) { memset(extra_tables[i],0,36); memcpy(extra_tables[i],"TEST",4); put32(extra_tables[i]+4,36); extra_tables[i][8]=1; sum_at(extra_tables[i],36,9); put64(regions[XSDT].bytes+36+(i+4)*8,0x1000000+(uint64_t)i*4096); }
    put32(regions[XSDT].bytes+4,36+64*8); finish(XSDT); expected_full(&expected); expected.table_count=64; success(&expected);
    restore(); maximum_table_on=1; memset(maximum_table,0,sizeof maximum_table); memcpy(maximum_table,"TEST",4); put32(maximum_table+4,sizeof maximum_table); maximum_table[8]=1; maximum_table[sizeof maximum_table-1]=0x87; sum_at(maximum_table,sizeof maximum_table,9);
    put64(regions[XSDT].bytes+36+4*8,0x2000000); finish(XSDT); expected_full(&expected); success(&expected);
    restore(); regions[RSDP].bytes[15]=3; rsdp_finish(); expected_full(&expected); expected.rsdp_revision=3; success(&expected);
    restore(); memmove(regions[MADT].bytes+53,regions[MADT].bytes+52,80); regions[MADT].bytes[52]=0x77; regions[MADT].bytes[45]=9; put32(regions[MADT].bytes+4,133); finish(MADT); expected_full(&expected); success(&expected);
    /* Every fixed array's final usable slot is part of an independent model. */
    restore(); expected_full(&expected);
    for(unsigned i=0;i<14;i++) { uint8_t c[]={0,8,(uint8_t)(i+20),(uint8_t)(i+30),1,0,0,0}; append_entry(c,8); expected.cpus[i+2]=(Cpu){0,i+20,i+30,1}; }
    expected.cpu_count=16; success(&expected);
    restore(); expected_full(&expected);
    for(unsigned i=0;i<7;i++) { uint8_t io[12]={1,12,(uint8_t)(i+20),0}; put32(io+4,0xfec01000+i*4096); put32(io+8,100+i*24); append_entry(io,12); expected.ioapics[i+1]=(IoApic){i+20,0xfec01000+i*4096,100+i*24}; }
    expected.ioapic_count=8; success(&expected);
    restore(); expected_full(&expected);
    for(unsigned i=1;i<16;i++) { uint8_t iso[10]={2,10,0,(uint8_t)i}; put32(iso+4,100+i); append_entry(iso,10); expected.isos[i]=(Iso){0,i,100+i,0}; }
    expected.iso_count=16; success(&expected);
    restore(); expected_full(&expected);
    for(unsigned i=0;i<13;i++) { uint8_t n[8]={3,8,0,0}; put32(n+4,100+i); append_entry(n,8); expected.nmis[i+3]=(Nmi){3,0,0,0,100+i}; }
    expected.nmi_count=16; success(&expected);
    restore(); expected_full(&expected); expected.mcfg_count=8;
    for(unsigned i=2;i<8;i++) { size_t at=44+i*16; uint64_t base=UINT64_C(0xd0000000)+(i-2)*0x100000; put64(regions[MCFG].bytes+at,base); put16(regions[MCFG].bytes+at+8,(uint16_t)i); regions[MCFG].bytes[at+10]=regions[MCFG].bytes[at+11]=0; expected.mcfg_regions[i]=(Mcfg){base,i,0,0}; }
    put32(regions[MCFG].bytes+4,44+8*16); finish(MCFG); success(&expected);
    /* GAS exact extents: last I/O byte/dword and last low-4GiB memory byte. */
    restore(); gas_bytes(regions[FADT].bytes+116,1,8,0,1,0xffff); finish(FADT);
    expected_full(&expected); expected.reset_gas.address=0xffff; success(&expected);
    restore(); gas_bytes(regions[FADT].bytes+208,1,32,0,3,0xfffc); put32(regions[FADT].bytes+76,0xfffc); finish(FADT);
    expected_full(&expected); expected.pm_timer_gas.address=0xfffc; expected.pm_timer_block=0xfffc; success(&expected);
    restore(); gas_bytes(regions[FADT].bytes+116,0,8,0,1,UINT64_C(0xffffffff)); finish(FADT);
    expected_full(&expected); expected.reset_gas.address_space=0; expected.reset_gas.address=UINT64_C(0xffffffff); success(&expected);
    /* An empty optional MCFG describes no ECAM allocation, not a bad header. */
    restore(); put32(regions[MCFG].bytes+4,44); finish(MCFG); expected_full(&expected);
    expected.mcfg_count=0; memset(expected.mcfg_regions,0,sizeof expected.mcfg_regions); success(&expected);
    /* Range and transport: malformed PA never reaches Reader. */
    restore(); reject(0,ERROR(1)); CHECK(reader_calls==0);
    restore(); reject(UINT64_C(0x100000000),ERROR(1)); CHECK(reader_calls==0);
    restore(); reject(UINT64_MAX-16,ERROR(1)); CHECK(reader_calls==0);
    restore(); reject(UINT64_C(0xfffffff0),ERROR(1)); CHECK(reader_calls==0);
    restore(); denied=addresses[RSDP]; reject(addresses[RSDP],ERROR(2)); CHECK(reader_calls==1);
    restore(); regions[RSDP].length=20; reject(addresses[RSDP],ERROR(2)); CHECK(last_length==36);
    restore(); regions[RSDP].length=36; put32(regions[RSDP].bytes+20,48); rsdp_finish(); reject(addresses[RSDP],ERROR(2)); CHECK(last_length==48);
    restore(); regions[RSDP].bytes[0]^=1; reject(addresses[RSDP],ERROR(3));
    restore(); regions[RSDP].bytes[9]^=1; reject(addresses[RSDP],ERROR(5));
    restore(); regions[RSDP].bytes[15]=1; rsdp_finish(); reject(addresses[RSDP],ERROR(6));
    restore(); regions[RSDP].bytes[33]^=1; reject(addresses[RSDP],ERROR(5));
    restore(); put32(regions[RSDP].bytes+20,35); reject(addresses[RSDP],ERROR(4));
    restore(); put32(regions[RSDP].bytes+20,0x100001); reject(addresses[RSDP],ERROR(4));
    restore(); put64(regions[RSDP].bytes+24,UINT64_C(0x100000000)); rsdp_finish(); reject(addresses[RSDP],ERROR(1)); CHECK(last_physical==addresses[RSDP]);
    /* XSDT/header/full checksum checks, including unknown signature tables. */
    restore(); denied=addresses[XSDT]; reject(addresses[RSDP],ERROR(2));
    restore(); regions[XSDT].length=35; reject(addresses[RSDP],ERROR(2));
    restore(); memcpy(regions[XSDT].bytes,"RSDT",4); finish(XSDT); reject(addresses[RSDP],ERROR(3));
    restore(); put32(regions[XSDT].bytes+4,35); reject(addresses[RSDP],ERROR(4));
    restore(); put32(regions[XSDT].bytes+4,0x100001); reject(addresses[RSDP],ERROR(4));
    restore(); put32(regions[XSDT].bytes+4,37); finish(XSDT); reject(addresses[RSDP],ERROR(4));
    restore(); put32(regions[XSDT].bytes+4,36+65*8); finish(XSDT); reject(addresses[RSDP],ERROR(8));
    restore(); regions[XSDT].bytes[10]^=1; reject(addresses[RSDP],ERROR(5));
    restore(); regions[UNKNOWN].bytes[36]^=1; reject(addresses[RSDP],ERROR(5));
    restore(); put32(regions[UNKNOWN].bytes+4,5000); reject(addresses[RSDP],ERROR(2)); CHECK(last_length==5000);
    restore(); put64(regions[XSDT].bytes+36,addresses[XSDT]); finish(XSDT); reject(addresses[RSDP],ERROR(7));
    restore(); put64(regions[XSDT].bytes+36+4*8,addresses[MADT]); finish(XSDT); reject(addresses[RSDP],ERROR(7));
    restore(); const unsigned no_madt[]={FADT}; root_entries(no_madt,1); reject(addresses[RSDP],ERROR(10));
    restore(); const unsigned no_fadt[]={MADT}; root_entries(no_fadt,1); reject(addresses[RSDP],ERROR(10));
    restore(); regions[EXTRA]=regions[FADT]; regions[EXTRA].physical=addresses[EXTRA]; const unsigned duplicate[]={MADT,FADT,EXTRA}; root_entries(duplicate,3); reject(addresses[RSDP],ERROR(7));
    restore(); regions[EXTRA]=regions[HPET]; regions[EXTRA].physical=addresses[EXTRA]; const unsigned two_hpet[]={MADT,FADT,HPET,EXTRA}; root_entries(two_hpet,4); reject(addresses[RSDP],ERROR(8));
    restore(); regions[EXTRA]=regions[MCFG]; regions[EXTRA].physical=addresses[EXTRA]; const unsigned two_mcfg[]={MADT,FADT,MCFG,EXTRA}; root_entries(two_mcfg,4); reject(addresses[RSDP],ERROR(7));
    /* MADT record bounds and architectural meanings. */
    restore(); put32(regions[MADT].bytes+4,43); finish(MADT); reject(addresses[RSDP],ERROR(4));
    restore(); regions[MADT].bytes[45]=0; finish(MADT); reject(addresses[RSDP],ERROR(4));
    restore(); regions[MADT].bytes[45]=1; finish(MADT); reject(addresses[RSDP],ERROR(4));
    restore(); regions[MADT].bytes[45]=255; finish(MADT); reject(addresses[RSDP],ERROR(4));
    const unsigned kinds[]={0,1,2,3,4,5,9,10};
    for(unsigned k=0;k<sizeof kinds/sizeof *kinds;k++) { restore(); regions[MADT].bytes[entry(kinds[k])+1]=2; finish(MADT); reject(addresses[RSDP],ERROR(4)); }
    restore(); put32(regions[MADT].bytes+entry(9)+4,2); finish(MADT); reject(addresses[RSDP],ERROR(7));
    restore(); put32(regions[MADT].bytes+entry(9)+12,1); finish(MADT); reject(addresses[RSDP],ERROR(7));
    restore(); put32(regions[MADT].bytes+entry(9)+4,UINT32_MAX); finish(MADT); reject(addresses[RSDP],ERROR(9));
    restore(); put32(regions[MADT].bytes+entry(1)+4,0xfec00001); finish(MADT); reject(addresses[RSDP],ERROR(9));
    restore(); put64(regions[MADT].bytes+entry(5)+4,UINT64_C(0x100000000)); finish(MADT); reject(addresses[RSDP],ERROR(1));
    restore(); regions[MADT].bytes[entry(2)+2]=1; finish(MADT); reject(addresses[RSDP],ERROR(6));
    restore(); regions[MADT].bytes[entry(2)+3]=16; finish(MADT); reject(addresses[RSDP],ERROR(6));
    for(unsigned bits=0;bits<2;bits++) { restore(); put16(regions[MADT].bytes+entry(2)+8,(uint16_t)(2u<<(bits*2))); finish(MADT); reject(addresses[RSDP],ERROR(9)); }
    restore(); regions[MADT].bytes[entry(4)+5]=2; finish(MADT); reject(addresses[RSDP],ERROR(9));
    restore(); regions[MADT].bytes[entry(10)+8]=2; finish(MADT); reject(addresses[RSDP],ERROR(9));
    restore(); uint8_t again[16]; memcpy(again,regions[MADT].bytes+entry(5),12); append_entry(again,12); reject(addresses[RSDP],ERROR(7));
    restore(); for(unsigned i=0;i<15;i++) { uint8_t c[]={0,8,(uint8_t)(i+20),(uint8_t)(i+30),1,0,0,0}; append_entry(c,8); } reject(addresses[RSDP],ERROR(8));
    restore(); for(unsigned i=0;i<8;i++) { uint8_t io[12]={1,12,(uint8_t)(i+20),0}; put32(io+4,0xfec01000+i*4096); put32(io+8,100+i*24); append_entry(io,12); } reject(addresses[RSDP],ERROR(8));
    restore(); for(unsigned i=1;i<=16;i++) { uint8_t iso[10]={2,10,0,(uint8_t)(i&15)}; put32(iso+4,100+i); append_entry(iso,10); } reject(addresses[RSDP],ERROR(8));
    restore(); for(unsigned i=0;i<14;i++) { uint8_t n[8]={3,8,0,0}; put32(n+4,100+i); append_entry(n,8); } reject(addresses[RSDP],ERROR(8));
    restore(); uint8_t duplicate_iso[10]; memcpy(duplicate_iso,regions[MADT].bytes+entry(2),10); append_entry(duplicate_iso,10); reject(addresses[RSDP],ERROR(7));
    restore(); uint8_t duplicate_nmi[12]; memcpy(duplicate_nmi,regions[MADT].bytes+entry(10),12); append_entry(duplicate_nmi,12); reject(addresses[RSDP],ERROR(7));
    restore(); uint8_t duplicate_io[12]; memcpy(duplicate_io,regions[MADT].bytes+entry(1),12); append_entry(duplicate_io,12); reject(addresses[RSDP],ERROR(7));
    /* FADT optional-prefix reads, real GAS semantics and 64-bit address bound. */
    restore(); put32(regions[FADT].bytes+4,115); finish(FADT); reject(addresses[RSDP],ERROR(4));
    restore(); put64(regions[FADT].bytes+140,UINT64_C(0x100000000)); finish(FADT); reject(addresses[RSDP],ERROR(1));
    restore(); regions[FADT].bytes[119]=5; finish(FADT); reject(addresses[RSDP],ERROR(9));
    restore(); regions[FADT].bytes[117]=16; finish(FADT); reject(addresses[RSDP],ERROR(9));
    restore(); regions[FADT].bytes[208]=2; finish(FADT); reject(addresses[RSDP],ERROR(6));
    restore(); regions[FADT].bytes[209]=16; finish(FADT); reject(addresses[RSDP],ERROR(9));
    restore(); regions[FADT].bytes[91]=3; finish(FADT); reject(addresses[RSDP],ERROR(9));
    restore(); gas_bytes(regions[FADT].bytes+116,1,8,0,1,0x10000); finish(FADT); reject(addresses[RSDP],ERROR(1));
    restore(); gas_bytes(regions[FADT].bytes+208,1,32,0,3,0xfffd); finish(FADT); reject(addresses[RSDP],ERROR(1));
    restore(); gas_bytes(regions[FADT].bytes+116,0,8,0,1,UINT64_C(0x100000000)); finish(FADT); reject(addresses[RSDP],ERROR(1));
    restore(); put32(regions[FADT].bytes+76,0xfffd); finish(FADT); reject(addresses[RSDP],ERROR(9));
    /* HPET does not confuse reserved width zero with an invalid scalar GAS. */
    restore(); put32(regions[HPET].bytes+4,55); finish(HPET); reject(addresses[RSDP],ERROR(4));
    restore(); regions[HPET].bytes[40]=1; finish(HPET); reject(addresses[RSDP],ERROR(6));
    restore(); put64(regions[HPET].bytes+44,0xfed00001); finish(HPET); reject(addresses[RSDP],ERROR(9));
    restore(); regions[HPET].bytes[55]=3; finish(HPET); reject(addresses[RSDP],ERROR(9));
    /* MCFG range overlap, bus-zero base meaning, and capacity. */
    restore(); regions[MCFG].bytes[55]=0; regions[MCFG].bytes[54]=1; finish(MCFG); reject(addresses[RSDP],ERROR(9));
    restore(); put64(regions[MCFG].bytes+44,0xb0000001); finish(MCFG); reject(addresses[RSDP],ERROR(9));
    restore(); put64(regions[MCFG].bytes+44,0xf8000000); regions[MCFG].bytes[55]=255; finish(MCFG); reject(addresses[RSDP],ERROR(9));
    restore(); put16(regions[MCFG].bytes+68,0); regions[MCFG].bytes[70]=63; finish(MCFG); reject(addresses[RSDP],ERROR(7));
    restore(); put64(regions[MCFG].bytes+60,0xb0000000); regions[MCFG].bytes[70]=0; finish(MCFG); reject(addresses[RSDP],ERROR(7));
    restore(); put32(regions[MCFG].bytes+4,44+9*16); finish(MCFG); reject(addresses[RSDP],ERROR(8));
    printf("acpi independent fixture passed: checks=%u success=%u rejected=%u full-output-unchanged=%u\n",checks,successes,failures,failures);
    return 0;
}
