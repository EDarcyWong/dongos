#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct {U selected,input_selected,kind,block_attempted,input_attempted,reserved,bars[6][4],input_bars[6][4];} Snapshot;
extern void ABI broker_reset(void);
extern U ABI broker_grant(U,U);
extern void ABI broker_snapshot(U*);
enum {INVALID=0x050a0001,DENIED=0x050a0002};
enum {AHCI=1,VBLK,VINPUT};
typedef struct {
    U ecam;unsigned kind;uint32_t identity,class_rev,header;
    uint16_t command,status;
    uint32_t bars[6],masks[6];unsigned probing[6];
    unsigned command_count,bar_writes,bar_mask,reads,map_attempts,handle_attempts,handles,range_count,bme_requests;
} Device;
static Device dev[2];
static FILE *trace;
static U checks,cases,events,all_bar_writes,all_maps,all_handles,all_bme_requests;
static unsigned ignore_clear,corrupt_clear,ignore_final,fail_map,fail_handle,fail_range,fail_bar_write,negative_seen;
static unsigned map_dev,map_index;
static U last_map_pa,last_map_bytes;
static void record(const char *event,unsigned which,U a,U b,U c,U d) {
    events++;
    if(trace) fprintf(trace,"{\"case\":%" PRIu64 ",\"event\":\"%s\",\"device\":%u,\"a\":%" PRIu64 ",\"b\":%" PRIu64 ",\"c\":%" PRIu64 ",\"d\":%" PRIu64 "}\n",cases,event,which,a,b,c,d);
}
static void fail(const char *expression,int line) {if(trace)fflush(trace);fprintf(stderr,"BROKER_MODEL_ASSERT line %d: %s\n",line,expression);exit(1);}
#define CHECK(x) do {checks++;if(!(x))fail(#x,__LINE__);} while(0)
void ABI __dong_panic(U code) {fprintf(stderr,"unexpected broker panic %" PRIu64 "\n",code);if(trace)fflush(trace);exit(99);}
void ABI broker_negative_hit(U n) {if(!negative_seen) {negative_seen=1;fprintf(stderr,"BROKER_NEGATIVE_HIT %" PRIu64 "\n",n);}}
static Device *locate(U address,unsigned *index,U *offset) {
    for(unsigned i=0;i<2;i++) if(address>=dev[i].ecam && address-dev[i].ecam<4096) {*index=i;*offset=address-dev[i].ecam;return &dev[i];}
    return NULL;
}
U ABI broker_read32(U address,uint32_t *out) {
    unsigned i=0;U offset=0;Device *p=locate(address,&i,&offset);if(!p || (offset&3))return 1;
    p->reads++;uint32_t value=0;
    if(offset==0)value=p->identity;
    else if(offset==4)value=((uint32_t)p->status<<16)|p->command;
    else if(offset==8)value=p->class_rev;
    else if(offset==12)value=p->header;
    else if(offset>=16 && offset<40) {unsigned bar=(unsigned)((offset-16)/4);value=p->probing[bar]?p->masks[bar]:p->bars[bar];}
    else return 1;
    *out=value;record("read32",i,offset,value,0,0);return 0;
}
U ABI broker_write32(U address,uint32_t value) {
    unsigned i=0;U offset=0;Device *p=locate(address,&i,&offset);if(!p || offset<16 || offset>=40 || (offset&3))return 1;
    unsigned bar=(unsigned)((offset-16)/4);p->bar_writes++;p->bar_mask|=1u<<bar;all_bar_writes++;
    record("BAR_WRITE",i,bar,value,p->command,0);
    /* This is deliberately independent of the extracted implementation: no
       destructive BAR probe/restoration may occur before all decode/BME bits
       are observed clear in the model's actual configuration register. */
    CHECK((p->command&7)==0);
    if(fail_bar_write)return 1;
    if(value==UINT32_MAX)p->probing[bar]=1;
    else {p->probing[bar]=0;p->bars[bar]=value;}
    return 0;
}
U ABI broker_command(U ecam,uint16_t value) {
    unsigned i=0;U offset=0;Device *p=locate(ecam,&i,&offset);if(!p || offset)return 1;
    p->command_count++;if(value&4){p->bme_requests++;all_bme_requests++;record("BME_ENABLE_REQUEST",i,value,p->command,0,0);}
    record("PCI_COMMAND",i,value,p->command,p->command_count,0);
    if(!(ignore_clear && p->command_count==1) && !(ignore_final && p->command_count==2))p->command=value;
    if(corrupt_clear && p->command_count==1)p->command^=0x8000;
    return 0;
}
U ABI broker_mmio_range(U physical,U bytes,U ecam) {
    CHECK(ecam==0);CHECK(physical && bytes>=4096 && !(physical&4095) && !(bytes&4095));
    record("RANGE_CHECK",0,physical,bytes,ecam,0);if(fail_range)return 1;
    for(unsigned d=0;d<2;d++) for(unsigned b=0;b<6;b++) {
        U pa=dev[d].bars[b]&~UINT64_C(15);if((dev[d].bars[b]&6)==4 && b<5)pa|=(U)dev[d].bars[b+1]<<32;
        if(pa==physical)dev[d].range_count++;
    }
    return 0;
}
U ABI broker_map(U id,U virtual,U physical,U bytes) {
    unsigned d=id==4?1:0;CHECK(id==2 || id==4);Device *p=&dev[d];p->map_attempts++;all_maps++;
    CHECK((p->command&7)==0);CHECK(virtual>=0x60000000 && virtual<0x66000000 && ((virtual-0x60000000)%0x1000000)==0);
    unsigned bar=(unsigned)((virtual-0x60000000)/0x1000000);CHECK(bar<6);if(p->kind==AHCI)CHECK(bar==5);
    U pa=p->bars[bar]&~UINT64_C(15);if((p->bars[bar]&6)==4 && bar<5)pa|=(U)p->bars[bar+1]<<32;
    CHECK(physical==pa);CHECK(bytes==((p->kind==AHCI || bar==2)?8192:4096));
    map_dev=d;map_index=bar;last_map_pa=physical;last_map_bytes=bytes;
    record("MAP_ATTEMPT",d,id,virtual,physical,bytes);return fail_map?1:0;
}
U ABI broker_install(U kind,U object,U rights) {
    Device *p=&dev[map_dev];p->handle_attempts++;CHECK(kind==5 && rights==131 && object==100+map_index);CHECK((p->command&7)==0);
    record("HANDLE_ATTEMPT",map_dev,kind,object,rights,0);if(fail_handle)return 0;
    p->handles++;all_handles++;return 0x1000+map_dev*0x100+object;
}
static Snapshot snapshot(void) {
    struct {U before[2];Snapshot value;U after[2];} result={{0x1234,0x5678},{0},{0x9abc,0xdef0}};
    broker_snapshot((U*)&result.value);CHECK(result.before[0]==0x1234 && result.before[1]==0x5678 && result.after[0]==0x9abc && result.after[1]==0xdef0);
    return result.value;
}
static void setup_device(unsigned d,unsigned kind,uint16_t command) {
    Device *p=&dev[d];p->ecam=UINT64_C(0xe0000000)+d*4096;p->kind=kind;p->command=command;p->status=0xbeef;
    p->identity=kind==AHCI?0x29228086:kind==VBLK?0x10421af4:0x10521af4;
    p->class_rev=kind==AHCI?0x01060101:0x02000001;
    if(kind==AHCI) {p->bars[5]=0xf0000000+d*0x100000;p->masks[5]=0xffffe000;}
    else {
        p->bars[0]=0xd0000000+d*0x100000;p->masks[0]=0xfffff000;
        p->bars[1]=1; /* I/O BAR is skipped. */
        p->bars[2]=4+d*0x100000;p->bars[3]=1;p->masks[2]=0xffffe004;p->masks[3]=UINT32_MAX;
        p->bars[4]=2; /* unsupported 20-bit memory BAR is skipped. */
        p->bars[5]=0xd0006000+d*0x100000;p->masks[5]=0xfffff000;
    }
}
static void reset(unsigned kind,uint16_t command) {
    ++cases;memset(dev,0,sizeof dev);ignore_clear=corrupt_clear=ignore_final=fail_map=fail_handle=fail_range=fail_bar_write=0;map_dev=map_index=0;last_map_pa=last_map_bytes=0;
    setup_device(0,kind,command);setup_device(1,VINPUT,command);broker_reset();Snapshot s=snapshot();Snapshot zero={0};CHECK(memcmp(&s,&zero,sizeof s)==0);
}
static void no_publication(const Snapshot *s,unsigned role) {
    CHECK(s->selected==0 && s->input_selected==0 && s->kind==0);
    for(unsigned b=0;b<6;b++)for(unsigned k=0;k<4;k++)CHECK(s->bars[b][k]==0 && s->input_bars[b][k]==0);
    CHECK(s->block_attempted==(role==2));CHECK(s->input_attempted==(role==4));
}
static void check_ahci_success(uint16_t original) {
    CHECK(broker_grant(2,dev[0].ecam)==0);Snapshot s=snapshot();Device *p=&dev[0];
    CHECK(s.selected==p->ecam && s.input_selected==0 && s.kind==2 && s.block_attempted==1 && !s.input_attempted);
    CHECK(p->command_count==2 && p->command==(uint16_t)((original|0x402)&~5));CHECK(p->status==0xbeef);
    CHECK(p->bar_writes==2 && p->bar_mask==(1u<<5));CHECK(p->map_attempts==1 && p->handles==1 && p->bme_requests==0);
    for(unsigned b=0;b<6;b++) {
        if(b==5)CHECK(s.bars[b][0]==p->bars[5] && s.bars[b][1]==8192 && s.bars[b][2]==0x1000+105 && s.bars[b][3]==0x65000000);
        else for(unsigned k=0;k<4;k++)CHECK(s.bars[b][k]==0);
    }
    unsigned prior=p->bar_writes,commands=p->command_count,maps=p->map_attempts,handles=p->handle_attempts,reads=p->reads;
    CHECK(broker_grant(2,p->ecam)==DENIED);CHECK(p->bar_writes==prior && p->command_count==commands && p->map_attempts==maps && p->handle_attempts==handles && p->reads==reads);
}
static void test_ignored_clear(void) {
    reset(AHCI,0x407);ignore_clear=1;CHECK(broker_grant(2,dev[0].ecam)==INVALID);Snapshot s=snapshot();no_publication(&s,2);
    CHECK(dev[0].command==0x407 && dev[0].command_count==1 && dev[0].bar_writes==0 && dev[0].map_attempts==0 && dev[0].handles==0 && dev[0].bme_requests==0);
    CHECK(broker_grant(2,dev[0].ecam)==DENIED);CHECK(dev[0].command_count==1 && dev[0].bar_writes==0);
    /* One stuck reserved bit is also caught by the exact 16-bit comparison,
       even though low-three bits alone might look clear. */
    reset(AHCI,0x407);corrupt_clear=1;CHECK(broker_grant(2,dev[0].ecam)==INVALID);s=snapshot();no_publication(&s,2);
    CHECK((dev[0].command&7)==0 && dev[0].bar_writes==0);
}
static void test_success_and_compatibility(void) {
    for(unsigned c=0;c<256;c++) {reset(AHCI,(uint16_t)((c*257u)^0xa55a));check_ahci_success(dev[0].command);}
    reset(VBLK,7);CHECK(broker_grant(2,dev[0].ecam)==0);Snapshot s=snapshot();
    CHECK(s.selected==dev[0].ecam && s.kind==1 && s.block_attempted==1);CHECK(dev[0].handles==3 && dev[0].map_attempts==3 && dev[0].bme_requests==1 && dev[0].command==0x407);
    CHECK(dev[0].bar_mask==((1u<<0)|(1u<<2)|(1u<<3)|(1u<<5)));CHECK(s.bars[2][0]==UINT64_C(0x100000000) && s.bars[2][1]==8192);
    CHECK(broker_grant(4,dev[1].ecam)==0);s=snapshot();CHECK(s.input_selected==dev[1].ecam && s.input_attempted==1 && dev[1].handles==3 && dev[1].bme_requests==1);
    CHECK(s.bars[0][0]!=s.input_bars[0][0]);
}
static void test_rejections_and_sticky_failures(void) {
    for(U role=0;role<7;role++)for(unsigned kind=AHCI;kind<=VINPUT;kind++) {
        reset(kind,7);U ecam=role==4?dev[1].ecam:dev[0].ecam;
        if(role==4)setup_device(1,kind,7);
        int valid=(role==2 && kind!=VINPUT)||(role==4 && kind==VINPUT);
        U status=broker_grant(role,ecam);CHECK((status==0)==valid);
        if(!valid) {Snapshot s=snapshot();no_publication(&s,0);CHECK(dev[0].bar_writes==0 && dev[1].bar_writes==0 && dev[0].command_count==0 && dev[1].command_count==0);}
    }
    reset(AHCI,7);CHECK(broker_grant(2,dev[0].ecam+1)==DENIED);CHECK(dev[0].reads==0);
    reset(AHCI,7);dev[0].identity=0xffff;CHECK(broker_grant(2,dev[0].ecam)==DENIED);Snapshot s=snapshot();no_publication(&s,0);
    reset(AHCI,7);dev[0].identity=0;CHECK(broker_grant(2,dev[0].ecam)==DENIED);s=snapshot();no_publication(&s,0);
    reset(AHCI,7);dev[0].header=0x10000;CHECK(broker_grant(2,dev[0].ecam)==DENIED);s=snapshot();no_publication(&s,0);
    for(unsigned fault=0;fault<4;fault++) {
        reset(AHCI,7);if(fault==0)fail_range=1;if(fault==1)fail_map=1;if(fault==2)fail_handle=1;if(fault==3)fail_bar_write=1;
        CHECK(broker_grant(2,dev[0].ecam)!=0);s=snapshot();no_publication(&s,2);CHECK((dev[0].command&7)==0 && dev[0].bme_requests==0);
        unsigned writes=dev[0].bar_writes,commands=dev[0].command_count,maps=dev[0].map_attempts,handles=dev[0].handle_attempts;
        CHECK(broker_grant(2,dev[0].ecam)==DENIED);CHECK(dev[0].bar_writes==writes && dev[0].command_count==commands && dev[0].map_attempts==maps && dev[0].handle_attempts==handles);
    }
    /* A late failure retains published BAR/handle state, but SELECTED stays 0,
       attempt is sticky, and no BME-enable write or DMA lease is manufactured. */
    reset(AHCI,7);ignore_final=1;CHECK(broker_grant(2,dev[0].ecam)==INVALID);s=snapshot();CHECK(s.selected==0 && s.kind==0 && s.block_attempted==1 && s.bars[5][2]!=0);
    CHECK(dev[0].command==0 && dev[0].handles==1 && dev[0].bme_requests==0);CHECK(broker_grant(2,dev[0].ecam)==DENIED);
    /* Second-role BAR collision is checked against the first role's grant. */
    reset(VBLK,7);CHECK(broker_grant(2,dev[0].ecam)==0);dev[1].bars[0]=dev[0].bars[0];CHECK(broker_grant(4,dev[1].ecam)==DENIED);
    s=snapshot();CHECK(s.input_attempted==1 && s.input_selected==0 && dev[1].handles==0 && dev[1].map_attempts==0 && dev[1].bme_requests==0);
}
int main(int argc,char **argv) {
    if(argc>1){trace=fopen(argv[1],"wb");if(!trace){perror("trace");return 3;}}
    CHECK(sizeof(Snapshot)==432);test_ignored_clear();test_success_and_compatibility();test_rejections_and_sticky_failures();
    if(trace)fclose(trace);
    printf("AHCI_BROKER_MODEL_OK cases=%" PRIu64 " assertions=%" PRIu64 " events=%" PRIu64 " BAR-writes=%" PRIu64 " map-attempts=%" PRIu64 " installed-handles=%" PRIu64 " BME-on-requests=%" PRIu64 " extracted-body=true hardware-executed=false\n",cases,checks,events,all_bar_writes,all_maps,all_handles,all_bme_requests);return 0;
}
