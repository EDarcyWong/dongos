#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
extern void ABI broker_reset(void);
extern U ABI broker_grant(U,U);
extern void ABI broker_snapshot(U*);
extern U ABI broker_caps(U,U,U*);
enum {INVALID=0x050a0001,DENIED=0x050a0002};
typedef struct {U selected,input_selected,kind,block_attempted,input_attempted,reserved,bars[6][4],input_bars[6][4];} Snapshot;
static uint32_t cfg[1024],bar_value[2],bar_mask[2];
static unsigned probing[2],commands,bar_writes,maps,installs,control_writes,cap_reads,reads,ignored_clear,ignored_control,negative_seen;
static U cases,checks,events;
static FILE *trace;
static const U ECAM=UINT64_C(0xe0000000);
static void record(const char *event,U a,U b,U c) {
    events++;if(trace)fprintf(trace,"{\"case\":%" PRIu64 ",\"event\":\"%s\",\"a\":%" PRIu64 ",\"b\":%" PRIu64 ",\"c\":%" PRIu64 "}\n",cases,event,a,b,c);
}
static void failure(const char *expression,int line) {if(trace)fflush(trace);fprintf(stderr,"NVME_BROKER_ASSERT line %d: %s\n",line,expression);exit(1);}
#define CHECK(x) do {checks++;if(!(x))failure(#x,__LINE__);}while(0)
void ABI __dong_panic(U reason) {fprintf(stderr,"unexpected panic %" PRIu64 "\n",reason);exit(99);}
void ABI broker_negative_hit(U kind) {if(!negative_seen){negative_seen=1;fprintf(stderr,"NVME_BROKER_NEGATIVE_HIT %" PRIu64 "\n",kind);}}
static int at(U address,U bytes) {return address>=ECAM && address-ECAM<=4096 && bytes<=4096-(address-ECAM);}
U ABI broker_read32(U address,uint32_t *out) {
    if(!at(address,4) || (address&3))return 1;U off=address-ECAM;reads++;
    if(off>=0x34)cap_reads++;
    if(off==16 || off==20){unsigned i=(unsigned)((off-16)/4);*out=probing[i]?bar_mask[i]:bar_value[i];}
    else *out=cfg[off/4];record("READ32",off,*out,0);return 0;
}
static int interrupt_disabled(void) {
    /* Independently scan actual backing config slots, rather than trusting
       traversal return flags or the driver's apparent write success. */
    for(unsigned offset=0x40;offset<=0xfc;offset+=4) {
        uint32_t value=cfg[offset/4];unsigned kind=value&255,control=value>>16;
        if(kind==5 && (control&1))return 0;if(kind==0x11 && (control&0x8000))return 0;
    }return 1;
}
U ABI broker_control16(U address,uint16_t value) {
    CHECK(at(address,2) && (address&3)==2);U off=address-ECAM;
    CHECK(off>=0x42 && off<=0xfe);
    control_writes++;uint32_t before=cfg[off/4];record("CONTROL16",off,value,before);CHECK((cfg[1]&7)==0);
    if(!ignored_control)cfg[off/4]=(before&65535)|((uint32_t)value<<16);
    CHECK((cfg[off/4]&65535)==(before&65535));return 0;
}
U ABI broker_write32(U address,uint32_t value) {
    CHECK(at(address,4));U off=address-ECAM;
    CHECK(off==16 || off==20);CHECK((cfg[1]&7)==0);CHECK(interrupt_disabled());
    bar_writes++;unsigned index=(unsigned)((off-16)/4);record("BAR32",off,value,0);
    if(value==UINT32_MAX)probing[index]=1;else{probing[index]=0;bar_value[index]=value;}return 0;
}
U ABI broker_command(U ecam,uint16_t value) {
    CHECK(ecam==ECAM);commands++;record("COMMAND16",value,cfg[1],commands);
    CHECK((value&4)==0);uint32_t status=cfg[1]&UINT32_C(0xffff0000);
    if(!(ignored_clear && commands==1))cfg[1]=status|value;
    CHECK((cfg[1]&UINT32_C(0xffff0000))==status);return 0;
}
U ABI broker_mmio_range(U pa,U bytes,U ecam) {
    CHECK(!ecam && bytes==16384 && (cfg[1]&7)==0 && interrupt_disabled());
    U expected=bar_value[0]&~UINT64_C(15);if((bar_value[0]&6)==4)expected|=(U)bar_value[1]<<32;
    CHECK(pa==expected);record("RANGE",pa,bytes,0);return 0;
}
U ABI broker_map(U id,U virtual,U pa,U bytes) {
    maps++;CHECK(id==2 && virtual==0x60000000 && bytes==16384 && (cfg[1]&7)==0 && interrupt_disabled());
    U expected=bar_value[0]&~UINT64_C(15);if((bar_value[0]&6)==4)expected|=(U)bar_value[1]<<32;
    CHECK(pa==expected);record("MAP",id,pa,bytes);return 0;
}
U ABI broker_install(U kind,U object,U rights) {
    installs++;CHECK(kind==5 && object==100 && rights==131 && maps==1);record("INSTALL",kind,object,rights);return 0x1064;
}
static void reset(void) {
    cases++;memset(cfg,0,sizeof cfg);memset(probing,0,sizeof probing);
    commands=bar_writes=maps=installs=control_writes=cap_reads=reads=ignored_clear=ignored_control=0;
    cfg[0]=0x00101b36;cfg[1]=0xa5100407;cfg[2]=0x01080201;
    cfg[0x34/4]=0x40;cfg[0x40/4]=0x01816005;cfg[0x60/4]=0x80038011;
    cfg[0x80/4]=0x12340009;bar_value[0]=0xf0000000;bar_value[1]=0;
    bar_mask[0]=0xffffc000;bar_mask[1]=UINT32_MAX;broker_reset();
}
static Snapshot snapshot(void) {Snapshot s;memset(&s,0,sizeof s);broker_snapshot((U*)&s);return s;}
static void success(void) {
    uint32_t before[1024];memcpy(before,cfg,sizeof cfg);CHECK(broker_grant(2,ECAM)==0);Snapshot s=snapshot();
    CHECK(s.selected==ECAM && s.kind==3 && s.block_attempted==1 && !s.input_selected && !s.input_attempted);
    CHECK(commands==2 && maps==1 && installs==1 && interrupt_disabled() && ((cfg[1]&0x407)==0x402));
    CHECK((cfg[1]>>16)==(before[1]>>16));CHECK((cfg[0x40/4]&65535)==(before[0x40/4]&65535));
    CHECK((cfg[0x60/4]&65535)==(before[0x60/4]&65535));
    CHECK(s.bars[0][1]==16384 && s.bars[0][2]==0x1064 && s.bars[0][3]==0x60000000);
    for(unsigned i=1;i<6;i++)for(unsigned j=0;j<4;j++)CHECK(s.bars[i][j]==0);
    unsigned oldreads=reads;CHECK(broker_grant(2,ECAM)==DENIED && reads==oldreads);
}
static void denied(void) {
    CHECK(broker_grant(2,ECAM)!=0);Snapshot s=snapshot();
    CHECK(!s.selected && !s.kind && s.block_attempted==1 && !bar_writes && !maps && !installs);
    unsigned old_commands=commands,old_caps=cap_reads;CHECK(broker_grant(2,ECAM)==DENIED && commands==old_commands && cap_reads==old_caps);
}
static void initial_readback(void) {
    reset();ignored_clear=1;denied();CHECK(commands==1 && !control_writes && !cap_reads && !bar_writes && !maps);
}
int main(int argc,char **argv) {
    if(argc>1){trace=fopen(argv[1],"wb");if(!trace)return 3;}
    /* First scenario proves no capability/BAR transaction after initial
       command readback failure, including for a malicious negative adapter. */
    initial_readback();
    reset();ignored_control=1;denied();CHECK(control_writes==1);
    reset();cfg[0x34/4]=0x60;cfg[0x40/4]=0;ignored_control=1;denied();CHECK(control_writes==1);
    reset();success();CHECK(control_writes==2);
    for(unsigned value=0;value<256;value++) {
        reset();cfg[1]=(cfg[1]&UINT32_C(0xffff0000))|(value*257);success();
    }
    reset();bar_value[0]=4;bar_value[1]=1;bar_mask[0]=0xffffc004;success();CHECK(bar_writes==4);
    reset();cfg[1]&=~UINT32_C(0x100000);cfg[0x40/4]=cfg[0x60/4]=0;success();CHECK(!control_writes);
    reset();cfg[0x34/4]=0;cfg[0x40/4]=cfg[0x60/4]=0;success();CHECK(!control_writes);
    reset();cfg[0x40/4]=0x01810005;cfg[0x60/4]=0;success();CHECK(control_writes==1);
    reset();cfg[0x34/4]=0x60;cfg[0x40/4]=0;cfg[0x60/4]=0x80030011;success();CHECK(control_writes==1);
    reset();for(unsigned offset=0x40;offset<=0xfc;offset+=4)cfg[offset/4]=((offset+4)<<8)|9;
    cfg[0xf8/4]=0x8001fc11;cfg[0xfc/4]=0x00010005;success();CHECK(control_writes==2);
    reset();for(unsigned offset=0x40;offset<=0xfc;offset+=4)cfg[offset/4]=((offset+4)<<8)|9;
    cfg[0xfc/4]=0x4009;denied();CHECK(!control_writes);
    reset();CHECK(broker_grant(4,ECAM)==DENIED && !commands && !bar_writes && !control_writes);
    /* Every 16-bit MSI and MSI-X control value is preserved except the
       explicit enable/mask bits, using only actual 16-bit writes/readbacks. */
    for(U control=0;control<=65535;control++) {
        reset();cfg[1]&=~UINT32_C(7);cfg[0x34/4]=0x40;cfg[0x40/4]=(uint32_t)(control<<16)|5;cfg[0x60/4]=0;
        U output=99;CHECK(broker_caps(ECAM,1,&output)==0 && output==3);
        CHECK((cfg[0x40/4]>>16)==(control&~UINT64_C(1)) && control_writes==1 && !commands);
        reset();cfg[1]&=~UINT32_C(7);cfg[0x34/4]=0x40;cfg[0x40/4]=(uint32_t)(control<<16)|0x11;cfg[0x60/4]=0;
        output=99;CHECK(broker_caps(ECAM,1,&output)==0 && output==3);
        CHECK((cfg[0x40/4]>>16)==((control|0x4000)&~UINT64_C(0x8000)) && control_writes==1 && !commands);
    }
    for(unsigned offset=1;offset<=255;offset++)if(offset<0x40 || (offset&3)) {
        reset();cfg[0x34/4]=offset;denied();CHECK(!control_writes);
    }
    for(unsigned offset=0x40;offset<=0xfc;offset+=4) {
        reset();memset(cfg+0x40/4,0,48*4);cfg[0x34/4]=offset;cfg[offset/4]=(offset<<8)|9;denied();
    }
    for(unsigned kind=5;kind<=0x11;kind+=12) {
        reset();cfg[0x40/4]=(0x60<<8)|kind;cfg[0x60/4]=kind;cfg[0x80/4]=0;denied();
    }
    /* Read-only recheck sees re-enabled MSI/MSI-X and never writes them. */
    for(unsigned msi=0;msi<2;msi++)for(unsigned msix=0;msix<2;msix++) {
        reset();cfg[0x40/4]=(msi<<16)|0x6005;cfg[0x60/4]=(msix<<31)|0x11;
        U output=99;CHECK(broker_caps(ECAM,0,&output)==0 && output==((msi?0:1)|(msix?0:2)) && !control_writes);
    }
    if(trace)fclose(trace);
    printf("NVME_BROKER_MODEL_OK cases=%" PRIu64 " assertions=%" PRIu64 " events=%" PRIu64 " full-capwalk-and-grant=true hardware=false\n",cases,checks,events);return 0;
}
