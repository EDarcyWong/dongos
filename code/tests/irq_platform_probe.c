/* Independent register/clock model; hardware accessors are substituted only here. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"IRQ_MODEL_ASSERT line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
#define BASE UINT64_C(0xffffc00000000000)
typedef struct { uint32_t eax,ebx,ecx,edx; } CpuId;
typedef struct { uint64_t lapic,ioapics[8],hpet,pm_timer; } Views;
typedef struct { uint64_t value[24]; } Report;
extern ABI size_t irq_report_size(void),irq_views_size(void);
extern ABI uint64_t irq_model_init(const uint64_t *,const Views *,Report *),irq_model_arm(uint64_t),irq_model_stop(void),irq_model_report(Report *);
extern ABI uint64_t irq_clock_accepted(void),irq_clock_rejected(void),irq_clock_count(void),irq_clock_ready(void);
extern ABI uint64_t platform_timer_rearm(void),platform_timer_stop(void),platform_diagnostic_word(uint64_t);
static int scenario;
static uint64_t ns,hpet_ticks,pm_ticks,deadline,lapic_started,seq,fence_seq,lvt_seq,lapic_base;
static uint64_t initial_pm=0;
static uint32_t lapic[1024],io[8][256],selector[8],initial_count,hpet_config;
static unsigned controllers=1;
static uint32_t initial_ids[8],wanted_ids[8];
static unsigned io_id_reads[8],io_version_reads[8],id_writes[8],id_readbacks[8],lapic_data_writes;
static uint8_t pic[2];
static unsigned data_writes,deadline_writes,calibration_round,calibration_reads;
static unsigned msr_reads,lapic_identity_reads,io_identity_reads,selector_writes;
static unsigned max_lvt(void) { return scenario==2?3:scenario==3?4:scenario==1?6:5; }
ABI void __dong_panic(uint64_t code) { fprintf(stderr,"unexpected Dong panic %llu\n",(unsigned long long)code); exit(99); }
ABI void irq_negative_hit(uint64_t kind) { fprintf(stderr,"IRQ_NEGATIVE_HIT %llu\n",(unsigned long long)kind); }
ABI uint64_t irq_hw_flags(void) { return scenario==5?0x202:2; }
ABI uint64_t irq_hw_cr4(void) { return 0x300820; }
ABI void irq_hw_set_lapic(uint64_t base) { lapic_base=base; }
ABI void dg_arch_cpuid(uint32_t leaf,uint32_t subleaf,CpuId *out) {
    CHECK(subleaf==0); *out=(CpuId){0};
    if(leaf==0) out->eax=scenario==0?0x15:1;
    else if(leaf==1) { out->edx=0x230; out->ecx=scenario==0?1u<<24:0; }
    else if(leaf==0x15) *out=(CpuId){3,250,24000000,0};
    else CHECK(0);
}
ABI uint64_t dg_arch_read_msr(uint32_t msr) { CHECK(msr==0x1b); msr_reads++; return scenario==6?0xfee00d00:scenario==29?0xfec00900:0xfee00900; }
ABI void dg_arch_write_msr(uint32_t msr,uint64_t value) {
    CHECK(scenario==0); CHECK(msr==0x6e0); CHECK(fence_seq>lvt_seq);
    deadline=value; deadline_writes++; seq++;
}
ABI uint64_t dg_arch_read_tsc(void) { return UINT64_C(100000000)+ns*2; }
ABI void dg_arch_lfence(void) { seq++; }
ABI void dg_arch_mfence(void) { fence_seq=++seq; }
ABI void dg_arch_sfence(void) { seq++; }
static void all_preflight(void){
    for(unsigned i=0;i<controllers;i++)CHECK(io_id_reads[i]>=1&&io_version_reads[i]>=1);
}
static void all_pins_masked(void){
    CHECK(pic[0]==255&&pic[1]==255);
    for(unsigned i=0;i<controllers;i++)for(unsigned pin=0;pin<24;pin++)CHECK((io[i][0x10+pin*2]&0x10000)!=0);
}
static void before_lapic_write(void){
    all_preflight();all_pins_masked();
    for(unsigned i=0;i<controllers;i++){
        if(id_writes[i])CHECK(id_readbacks[i]==1);
        CHECK(((io[i][0]>>24)&15)==wanted_ids[i]);
    }
}
ABI void dg_arch_out8(uint16_t port,uint8_t value) { CHECK(port==0x21||port==0xa1);all_preflight();pic[port==0xa1]=value;data_writes++; }
ABI uint8_t dg_arch_in8(uint16_t port) { CHECK(port==0x21||port==0xa1); return pic[port==0xa1]; }
static uint32_t pm_read(void) {
    pm_ticks+=36; ns=pm_ticks*UINT64_C(1000000000)/3579545;
    return (uint32_t)((initial_pm+pm_ticks)&(scenario==2?0xffffff:0xffffffff));
}
ABI uint32_t irq_hw_in32(uint16_t port) { CHECK(port==0x608); return pm_read(); }
ABI uint64_t irq_hw_read64(uint64_t address) {
    if(address==BASE+9*4096) return (UINT64_C(10000000)<<32)|0x2001;
    CHECK(address==BASE+9*4096+0xf0);
    if(scenario!=7) { hpet_ticks+=1000; ns=hpet_ticks*10; }
    return hpet_ticks;
}
ABI uint32_t irq_hw_read32(uint64_t address) {
    if(address>=BASE&&address<BASE+4096) {
        unsigned offset=(unsigned)(address-BASE); CHECK((offset&15)==0);
        if(offset==0x390) {
            if(initial_count==0xffffffffu && calibration_reads++==0 && (scenario==9 || (scenario==8 && calibration_round<=2))) { hpet_ticks+=200000;ns=hpet_ticks*10; }
            uint64_t ticks=(ns-lapic_started)*6250000/1000000000; return ticks>=initial_count?0:initial_count-(uint32_t)ticks; }
        if(offset==0x20||offset==0x30)lapic_identity_reads++;
        return lapic[offset/4];
    }
    if(address>=BASE+4096&&address<BASE+9*4096){
        unsigned index=(unsigned)((address-BASE)/4096)-1;CHECK(index<controllers&&(address&4095)==16);
        unsigned reg=selector[index];
        if(reg<2){io_identity_reads++;if(reg==0){io_id_reads[index]++;if(id_writes[index])id_readbacks[index]++;}else io_version_reads[index]++;}
        return io[index][reg];
    }
    if(address==BASE+9*4096+0x10) return hpet_config;
    if(address==BASE+10*4096) return pm_read();
    CHECK(0); return 0;
}
ABI void irq_hw_write32(uint64_t address,uint32_t value) {
    seq++;
    if(address>=BASE&&address<BASE+4096) {
        unsigned offset=(unsigned)(address-BASE); CHECK((offset&15)==0);before_lapic_write();lapic_data_writes++;lapic[offset/4]=value; data_writes++;
        if(offset==0x2f0||offset==0x330||offset==0x340||offset==0x350||offset==0x360||offset==0x370) CHECK(value==0x100ff);
        if(offset==0x340) CHECK(max_lvt()>=4);
        if(offset==0x330) CHECK(max_lvt()>=5);
        if(offset==0x2f0) CHECK(max_lvt()>=6);
        if(offset==0x320) lvt_seq=seq;
        if(offset==0x380) { initial_count=value; lapic_started=ns; if(value==0xffffffffu) { calibration_round++;calibration_reads=0; } }
        return;
    }
    if(address>=BASE+4096&&address<BASE+9*4096){
        unsigned index=(unsigned)((address-BASE)/4096)-1,offset=(unsigned)(address&4095);CHECK(index<controllers);
        if(offset==0){CHECK(value<256);selector_writes++;selector[index]=value;return;}
        CHECK(offset==16);unsigned reg=selector[index];all_preflight();
        if(reg==0){
            all_pins_masked();CHECK(id_writes[index]==0);CHECK(wanted_ids[index]<=15);
            CHECK(((value^initial_ids[index])&UINT32_C(0xf0ffffff))==0);
            CHECK(value==((initial_ids[index]&UINT32_C(0xf0ffffff))|(wanted_ids[index]<<24)));
            CHECK(value!=initial_ids[index]);id_writes[index]++;data_writes++;
            if(scenario!=17)io[index][0]=value^(scenario==18?UINT32_C(0x01000000):scenario==31?UINT32_C(0x80000000):0);
            return;
        }
        CHECK(reg>=0x10);CHECK(pic[0]==255&&pic[1]==255);CHECK(value==(io[index][reg]|0x10000));
        io[index][reg]=value;data_writes++;return;
    }
    if(address==BASE+9*4096+0x10) { hpet_config=value; data_writes++; return; }
    CHECK(0);
}
static uint64_t expected_error(void){
    if(scenario==5)return 0x03050001;
    if(scenario==7)return 0x03050005;
    if(scenario==9)return 0x03050004;
    switch(scenario){case 6:case 10:case 11:case 12:case 16:case 17:case 18:case 20:case 21:case 22:case 23:case 24:case 25:case 26:case 28:case 29:case 31:case 32:case 33:case 34:case 36:return 0x03050003;default:return 0;}
}
static unsigned static_bad(void){return scenario==16||scenario==22||scenario==23||scenario==24||scenario==25||scenario==26||scenario==32;}
static unsigned failed_index(void){return scenario==20||scenario==21||scenario==22||scenario==23||scenario==32?1:0;}
static void reject_checks(uint64_t expected){
    if(expected!=0x03050003)return;
    unsigned stage=(scenario==6||scenario==29)?1:(scenario==10||scenario==28)?2:(scenario==12||scenario==21||scenario==36)?4:3;
    unsigned valid=stage==1?1:stage==2||static_bad()?7:15;
    CHECK(platform_diagnostic_word(0)==1&&platform_diagnostic_word(1)==stage&&platform_diagnostic_word(2)==expected&&platform_diagnostic_word(3)==valid);
    CHECK(platform_diagnostic_word(4)==(scenario==6?0xfee00d00:scenario==29?0xfec00900:0xfee00900));
    CHECK(platform_diagnostic_word(5)==0xfee00000&&platform_diagnostic_word(8)==1&&platform_diagnostic_word(10)==controllers);
    CHECK(msr_reads==1&&lapic_identity_reads==(stage==1?0:2));
    if(stage==1||stage==2||static_bad())CHECK(io_identity_reads==0&&selector_writes==0);
    if((valid&8)!=0){
        unsigned index=failed_index();CHECK(platform_diagnostic_word(11)==index);
        CHECK(platform_diagnostic_word(12)==wanted_ids[index]&&platform_diagnostic_word(13)==UINT64_C(0xfec00000)+index*4096);
        CHECK(platform_diagnostic_word(15)==io[index][0]&&platform_diagnostic_word(16)==io[index][1]);
        CHECK(platform_diagnostic_word(17)==((io[index][1]>>16)&255)+1);
    }
    unsigned before_reads=msr_reads+lapic_identity_reads+io_identity_reads;
    for(unsigned i=0;i<56;i++){(void)platform_diagnostic_word(i);}
    CHECK(platform_diagnostic_word(56)==0&&platform_diagnostic_word(UINT64_MAX)==0);
    CHECK(before_reads==msr_reads+lapic_identity_reads+io_identity_reads);
}
int main(int argc,char **argv) {
    CHECK(argc==2);scenario=atoi(argv[1]);CHECK(scenario>=0&&scenario<=36);
    CHECK(irq_report_size()==192&&irq_views_size()==88);
    uint64_t topology[307]={0};Views views={0};Report out,before;
    if((scenario>=19&&scenario<=23)||scenario==32)controllers=2;
    if(scenario==30)controllers=8;
    topology[8]=0xfee00000;topology[10]=1;topology[11]=controllers;
    topology[43]=0;topology[44]=0;topology[45]=0;topology[46]=1;
    topology[20]=0x608;topology[21]=4;topology[22]=scenario==2?0:1;
    views.lapic=BASE;
    for(unsigned i=0;i<controllers;i++){
        unsigned id=controllers==2?i+4:i;topology[107+3*i]=id;topology[108+3*i]=0xfec00000+i*4096;topology[109+3*i]=i*24;
        views.ioapics[i]=BASE+(i+1)*4096;io[i][0]=id<<24;io[i][1]=23u<<16|0x11;
        for(unsigned pin=0;pin<24;pin++)io[i][0x10+pin*2]=0x20+pin;
    }
    if(scenario==1||scenario==7||scenario==8||scenario==9){topology[4]=0x123000;topology[42]=0xfed00000;views.hpet=BASE+9*4096;}
    if(scenario==4){topology[28]=0;topology[29]=32;topology[32]=0xfed01000;views.pm_timer=BASE+10*4096;}
    if(scenario==2)initial_pm=0xffffff-10000;
    if(scenario==3)initial_pm=0xffffffff-10000;
    lapic[0x20/4]=0;lapic[0x30/4]=max_lvt()<<16|0x14;
    if(scenario==10)lapic[0x20/4]=1u<<24;
    if(scenario==11){io[0][0]=1u<<24;io[0][1]=23u<<16;}
    if(scenario==12)topology[109]=UINT32_MAX;
    if(scenario==13){topology[107]=4;io[0][0]=0;io[0][1]=0x170020;}
    if(scenario==14){topology[107]=4;io[0][0]=0xa40055aa;}
    if(scenario==15||scenario==31){topology[107]=4;io[0][0]=0xb100abcd;}
    if(scenario==16)topology[107]=16;
    if(scenario==17||scenario==18){topology[107]=4;io[0][0]=0;}
    if(scenario>=19&&scenario<=23){io[0][0]=0;io[1][0]=1u<<24;}
    if(scenario==20)io[1][1]=23u<<16;
    if(scenario==21)topology[112]=23;
    if(scenario==22)topology[110]=topology[107];
    if(scenario==23)topology[111]=topology[108];
    if(scenario==24)topology[108]++;
    if(scenario==25)topology[108]=0;
    if(scenario==26)topology[108]=UINT64_C(0x100000000);
    if(scenario==27){topology[107]=15;io[0][0]=0;}
    if(scenario==28)topology[46]=0;
    if(scenario==30){for(unsigned i=1;i<controllers;i++)io[i][0]=0xb0001234;}
    if(scenario==32){topology[110]=16;io[0][0]=0;}
    if(scenario==33)io[0][1]=120u<<16|0x11;
    if(scenario==34)io[0][1]=23u<<16|0xff;
    if(scenario==35)topology[109]=UINT32_MAX-23;
    if(scenario==36)topology[109]=UINT32_MAX-22;
    for(unsigned i=0;i<controllers;i++){initial_ids[i]=io[i][0];wanted_ids[i]=(uint32_t)topology[107+3*i];}
    memset(&out,0xa7,sizeof out);before=out;
    CHECK(irq_model_arm(1000000)==(scenario==5?0x03050001:0x03050006));
    CHECK(irq_model_report(&out)==0x03050006);CHECK(memcmp(&out,&before,sizeof out)==0);
    uint64_t error=irq_model_init(topology,&views,&out),expected=expected_error();
    if(expected){
        CHECK(error==expected);CHECK(memcmp(&out,&before,sizeof out)==0);reject_checks(expected);
        if(scenario==17||scenario==18||scenario==31){all_pins_masked();CHECK(id_writes[0]==1&&id_readbacks[0]==1&&lapic_data_writes==0&&data_writes==27);}
        else if(scenario!=7&&scenario!=9){CHECK(data_writes==0);for(unsigned i=0;i<controllers;i++)CHECK(id_writes[i]==0);}
        if(scenario==9)CHECK(irq_clock_count()==7&&irq_clock_ready()==0&&irq_clock_accepted()==0);
        printf("irq platform reject model passed scenario=%d no-unsafe-ID-bypass=ok\n",scenario);return 0;
    }
    if(error)fprintf(stderr,"init error 0x%llx\n",(unsigned long long)error);
    CHECK(error==0);CHECK(lapic_base==BASE);CHECK(out.value[0]==0xfee00000&&out.value[1]==BASE);
    CHECK(out.value[2]==0&&out.value[4]==controllers&&out.value[5]==controllers*24);CHECK(out.value[6]==255&&out.value[7]==255);
    CHECK(out.value[8]==(scenario==0?1:(scenario==1||scenario==8)?2:scenario==4?4:3));
    CHECK(out.value[9]>=1999995000&&out.value[9]<=2000005000);
    if(scenario!=0){CHECK(irq_clock_count()==7&&irq_clock_ready()==1);CHECK(irq_clock_accepted()==(scenario==8?5:7));CHECK(irq_clock_rejected()==(scenario==8?2:0));}
    CHECK(out.value[11]==(scenario==0?1:2));CHECK(out.value[23]==31);
    if(scenario!=0)CHECK(out.value[10]>=6249000&&out.value[10]<=6251000);
    all_pins_masked();unsigned identity_writes=0;
    for(unsigned i=0;i<controllers;i++){
        unsigned mismatch=((initial_ids[i]>>24)&15)!=wanted_ids[i];CHECK(id_writes[i]==mismatch&&id_readbacks[i]==mismatch);identity_writes+=id_writes[i];
        CHECK(io[i][0]==((initial_ids[i]&UINT32_C(0xf0ffffff))|(wanted_ids[i]<<24)));
    }
    CHECK((lapic[0xf0/4]&0x11ff)==0x1ff);CHECK((lapic[0x350/4]&0x10000)!=0&&(lapic[0x360/4]&0x10000)!=0);
    CHECK((lapic[0x340/4]&0x10000)==(max_lvt()>=4?0x10000:0));CHECK((lapic[0x330/4]&0x10000)==(max_lvt()>=5?0x10000:0));CHECK((lapic[0x2f0/4]&0x10000)==(max_lvt()>=6?0x10000:0));
    CHECK(irq_model_arm(1000000)==0);
    if(scenario==0)CHECK(deadline==100000000+ns*2+2000000);else CHECK(initial_count>=6249&&initial_count<=6251);
    CHECK(platform_timer_rearm()==0);CHECK(irq_model_report(&out)==0);CHECK(out.value[15]==2);
    CHECK(platform_timer_stop()==0);CHECK(initial_count==0);CHECK((lapic[0x320/4]&0x10000)!=0);
    if(scenario==0)CHECK(deadline==0&&deadline_writes==4);else CHECK(deadline_writes==0);
    CHECK(irq_model_report(&out)==0);CHECK(out.value[16]==1&&out.value[23]==127);
    CHECK(irq_model_arm(0)==0x03050008);CHECK(irq_model_arm(UINT64_MAX)==0x03050008);CHECK(irq_model_init(topology,&views,&out)==0x03050007);
    printf("irq platform clock/register model passed scenario=%d controllers=%u IDwrites=%u reserved+all-pins-before-ID+readback=ok\n",scenario,controllers,identity_writes);return 0;
}
