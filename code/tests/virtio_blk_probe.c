/* Independent PCI/modern VirtIO register, DMA chain and durable disk model. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"VBLK_MODEL_ASSERT line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
#define ERROR(n) (UINT64_C(0x05030000)+(n))
#define ECAM UINT64_C(0xe0000000)
#define GPA UINT64_C(0x200000000)
#define DMA_BYTES 69632
typedef struct { uint64_t base,segment,first,last; } Region;
typedef struct { size_t region;uint64_t index; } Cursor;
typedef struct { uint64_t ecam,segment,bus,device,function,vendor,id,class_code,subclass,interface,header; } Function;
typedef struct { uint64_t physical,length,handle; } Bar;
typedef struct { uint64_t handle,offset,length,bar; } Area;
typedef struct { Area common,notify,isr,device;uint64_t multiplier; } Transport;
typedef struct { uint64_t token,physical;uint8_t *pointer;size_t length; } Lease;
typedef uint64_t (ABI *Read)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t *);
typedef uint64_t (ABI *Write)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
typedef uint64_t (ABI *Fence)(uint64_t,uint64_t);
typedef uint64_t (ABI *Acquire)(uint64_t,size_t,size_t,Lease *);
typedef uint64_t (ABI *Release)(uint64_t,const Lease *);
typedef struct { Read read;Write write;Fence fence;Acquire acquire;Release release; } Ops;
typedef struct { uint64_t capacity,maximum,readonly,ready,faulted,held,completed,avail,used; } Info;
typedef struct { Info info;uint64_t busy,published,generation,notify_offset;Transport transport;const Ops *ops;uint64_t context;Lease lease; } State;
typedef uint64_t (ABI *ConfigRead)(uint64_t,uint64_t,uint32_t *);
extern ABI size_t vb_state_size(void),vb_transport_size(void);
extern ABI void vb_state_reset(State *);
extern ABI uint64_t vb_scan(ConfigRead,uint64_t,const Region *,size_t,Cursor *,Function *);
extern ABI uint64_t vb_discover(ConfigRead,uint64_t,const Function *,const Bar *,Transport *);
extern ABI uint64_t vb_initialize(State *,const Transport *,const Ops *,uint64_t),vb_close(State *),vb_flush(State *),vb_info(const State *,Info *);
extern ABI uint64_t vb_read(State *,uint64_t,size_t,uint8_t *),vb_write(State *,uint64_t,size_t,const uint8_t *);
extern ABI uint64_t vb_callback_read(uint64_t,uint64_t,size_t,uint8_t *),vb_callback_write(uint64_t,uint64_t,size_t,const uint8_t *),vb_callback_flush(uint64_t);
ABI void __dong_panic(uint64_t code) { fprintf(stderr,"unexpected Dong panic %llu\n",(unsigned long long)code);exit(99); }
ABI void vb_negative_hit(uint64_t kind) { fprintf(stderr,"VBLK_NEGATIVE_HIT %llu\n",(unsigned long long)kind); }
static uint8_t cfg[256],disk[256*512],cache[256*512];
static unsigned scenario,config_fail,config_calls,acquired,released,release_fail,reset_fail,status,feature_select,driver_select,qsize,qenable,gen;
static uint64_t accepted[2],desc_address,avail_address,used_address;
static uint8_t *allocation,*dma;static unsigned fences[4],old_release,old_full,requests,flushes;
static uint16_t device_avail,device_used;static State state;
static uint16_t r16(const uint8_t *p) { uint16_t x;memcpy(&x,p,2);return x; }
static uint32_t r32(const uint8_t *p) { uint32_t x;memcpy(&x,p,4);return x; }
static uint64_t r64(const uint8_t *p) { uint64_t x;memcpy(&x,p,8);return x; }
static void w16(uint8_t *p,uint16_t x) { memcpy(p,&x,2); }
static void w32(uint8_t *p,uint32_t x) { memcpy(p,&x,4); }
static void cap(unsigned at,unsigned next,unsigned type,unsigned offset,unsigned length,unsigned size) {
    w32(cfg+at,9|(next<<8)|(size<<16)|(type<<24));w32(cfg+at+4,0);w32(cfg+at+8,offset);w32(cfg+at+12,length);
}
static void config_init(void) {
    memset(cfg,0,sizeof cfg);w32(cfg,0x10421af4);w32(cfg+4,0x100006);w32(cfg+8,0x01000000);w32(cfg+12,0x00800000);
    w32(cfg+16,0xfc000004);w32(cfg+20,1);w32(cfg+52,0x40);
    cap(0x40,0x50,1,0,56,16);cap(0x50,0x64,2,0x100,0x100,20);w32(cfg+0x60,4);
    cap(0x64,0x74,3,0x200,1,16);cap(0x74,0,4,0x300,8,16);
}
static ABI uint64_t config_read(uint64_t context,uint64_t address,uint32_t *out) {
    CHECK(context==37);CHECK((address&3)==0);config_calls++;
    if(config_fail)return 1;
    if(address>=ECAM+0x8000&&address<ECAM+0x8100) { *out=r32(cfg+(size_t)(address-ECAM-0x8000));return 0; }
    if(address>=ECAM&&address<ECAM+0x100) { unsigned off=(unsigned)(address-ECAM);*out=off==0?0x29c08086:off==8?0x06000000:0;return 0; }
    if(address>=ECAM+0x9000&&address<ECAM+0x9100) { unsigned off=(unsigned)(address-ECAM-0x9000);*out=off==0?0x56781234:off==8?0x02000000:0;return 0; }
    *out=UINT32_MAX;return 0;
}
static ABI uint64_t fence(uint64_t context,uint64_t kind) { CHECK(context==99&&kind>=1&&kind<=3);fences[kind]++;return 0; }
static ABI uint64_t acquire(uint64_t context,size_t bytes,size_t align,Lease *out) {
    CHECK(context==99&&bytes==DMA_BYTES&&align==4096);if(scenario==8)return 1;
    CHECK(acquired==released);acquired++;memset(dma-16,0xa7,DMA_BYTES+32);
    *out=(Lease){0x1234,GPA,dma,DMA_BYTES};return 0;
}
static ABI uint64_t release(uint64_t context,const Lease *lease) {
    CHECK(context==99&&lease->token==0x1234&&lease->physical==GPA&&lease->pointer==dma&&lease->length==DMA_BYTES);
    CHECK(status==0&&qenable==0);CHECK(acquired==released+1);
    for(unsigned i=0;i<16;i++)CHECK(dma[-16+(int)i]==0xa7&&dma[DMA_BYTES+i]==0xa7);
    if(release_fail)return 1;
    released++;return 0;
}
static void process_request(void) {
    CHECK(status==15&&qenable==1&&qsize==8&&accepted[1]==1&&accepted[0]==(scenario==10?544:512));
    CHECK(desc_address==GPA&&avail_address==GPA+128&&used_address==GPA+152);
    CHECK(fences[1]>old_release&&fences[3]>old_full);old_release=fences[1];old_full=fences[3];
    uint16_t available=r16(dma+130);CHECK(available==(uint16_t)(device_avail+1));
    CHECK(r16(dma+128)==1&&r16(dma+132+(device_avail%8)*2)==0);device_avail=available;
    CHECK(r64(dma)==GPA+256&&r32(dma+8)==16&&r16(dma+12)==1);
    CHECK(r64(dma+32)==GPA+272&&r32(dma+40)==1&&r16(dma+44)==2&&r16(dma+46)==0);
    unsigned kind=r32(dma+256);CHECK(r32(dma+260)==0);uint64_t lba=r64(dma+264);size_t bytes=0;
    if(kind==4) { CHECK(r16(dma+14)==2&&lba==0); }
    else {
        CHECK(kind<=1&&r16(dma+14)==1&&r64(dma+16)==GPA+4096&&r16(dma+30)==2);
        CHECK(r16(dma+28)==(kind==0?3:1));bytes=r32(dma+24);CHECK(bytes&&bytes<=65536&&bytes%512==0&&lba<=256-bytes/512);
    }
    // Reentry from a device/notification callback sees Busy and no new request.
    State before=state;uint8_t untouched[512];memset(untouched,0xa7,sizeof untouched);
    CHECK(vb_read(&state,0,1,untouched)==ERROR(4));CHECK(vb_write(&state,0,1,untouched)==ERROR(4));CHECK(vb_flush(&state)==ERROR(4));CHECK(vb_close(&state)==ERROR(4));CHECK(memcmp(&before,&state,sizeof state)==0);
    for(unsigned i=0;i<512;i++)CHECK(untouched[i]==0xa7);
    requests++;if(scenario==5)return;
    if(kind==0)memcpy(dma+4096,cache+lba*512,bytes);
    if(kind==1)memcpy(cache+lba*512,dma+4096,bytes);
    if(kind==4) { memcpy(disk,cache,sizeof disk);flushes++; }
    dma[272]=scenario==4?255:scenario==6?1:0;
    unsigned slot=156+(device_used%8)*8;w32(dma+slot,scenario==1||scenario==7?5:0);
    uint32_t written=(uint32_t)(kind==0?bytes+1:1);if(scenario==2)written++;
    w32(dma+slot+4,written);device_used=(uint16_t)(device_used+(scenario==3?2:1));w16(dma+154,device_used);
}
static ABI uint64_t mmio_read(uint64_t context,uint64_t handle,uint64_t offset,uint64_t width,uint64_t *out) {
    CHECK(context==99&&handle==11&&(offset&(width-1))==0);
    if(offset==0x300||offset==0x304) { CHECK(width==4);*out=offset==0x300?256:0;return 0; }
    if(offset==4) { CHECK(width==4);*out=feature_select?(scenario==11?3:1):(scenario==12?0:scenario==10?544:512);return 0; }
    if(offset==18) { CHECK(width==2);*out=1;return 0; }
    if(offset==20) { CHECK(width==1);*out=status;return 0; }
    if(offset==21) { CHECK(width==1);*out=gen;return 0; }
    if(offset==24) { CHECK(width==2);*out=qsize;return 0; }
    if(offset==28) { CHECK(width==2);*out=qenable;return 0; }
    if(offset==30) { CHECK(width==2);*out=2;return 0; }
    CHECK(0);return 1;
}
static ABI uint64_t mmio_write(uint64_t context,uint64_t handle,uint64_t offset,uint64_t width,uint64_t value) {
    CHECK(context==99&&handle==11&&(offset&(width-1))==0);
    if(offset==0x108) { CHECK(width==2&&value==0);process_request();return scenario==9?1:0; }
    if(offset==20) {
        CHECK(width==1);
        if(value==0) { if(reset_fail) { status=64;return 0; } status=0;qsize=16;qenable=0;device_avail=0;device_used=0;desc_address=avail_address=used_address=0;return 0; }
        CHECK((value==1&&status==0)||(value==3&&status==1)||(value==11&&status==3)||(value==15&&status==11));status=(unsigned)value;return 0;
    }
    CHECK(width==2||width==4);
    if(offset==0) { CHECK(width==4&&value<=1);feature_select=(unsigned)value;return 0; }
    if(offset==8) { CHECK(width==4&&value<=1);driver_select=(unsigned)value;return 0; }
    if(offset==12) { CHECK(width==4);accepted[driver_select]=value;return 0; }
    if(offset==16||offset==26) { CHECK(width==2&&value==65535);return 0; }
    if(offset==22) { CHECK(width==2&&value==0);return 0; }
    if(offset==24) { CHECK(width==2&&value==8);qsize=8;return 0; }
    if(offset==28) { CHECK(width==2&&value==1&&qenable==0);qenable=1;old_release=fences[1];old_full=fences[3];return 0; }
    uint64_t *address=NULL;unsigned half=0;
    if(offset>=32&&offset<=52&&offset%4==0) { unsigned which=(unsigned)(offset-32)/8;half=(unsigned)(offset-32)%8;address=which==0?&desc_address:which==1?&avail_address:&used_address; }
    CHECK(address&&width==4);if(half==0)*address=(*address&UINT64_C(0xffffffff00000000))|value;else*address=(*address&UINT64_C(0xffffffff))|(value<<32);return 0;
}
static const Ops ops={mmio_read,mmio_write,fence,acquire,release};
static void invalid_snapshot(uint64_t lba,size_t count,uint8_t *out,uint64_t expected) {
    State before=state;uint8_t *snapshot=malloc(DMA_BYTES);CHECK(snapshot);memcpy(snapshot,dma,DMA_BYTES);unsigned old=requests;
    CHECK(vb_read(&state,lba,count,out)==expected);CHECK(memcmp(&before,&state,sizeof state)==0&&memcmp(snapshot,dma,DMA_BYTES)==0&&old==requests);free(snapshot);
}
int main(int argc,char **argv) {
    CHECK(argc==2);scenario=(unsigned)strtoul(argv[1],NULL,0);CHECK(scenario<=12);
    CHECK(vb_state_size()==288&&sizeof state==288&&vb_transport_size()==136&&sizeof(Transport)==136);
    allocation=malloc(DMA_BYTES+8192);CHECK(allocation);dma=(uint8_t *)(((uintptr_t)allocation+4095+16)&~(uintptr_t)4095);
    CHECK((uintptr_t)dma!=GPA);config_init();Region region={ECAM,0,0,0};Cursor cursor={0};Function function={0};
    CHECK(vb_scan(config_read,37,&region,1,&cursor,&function)==0&&function.vendor==0x8086&&function.device==0);
    CHECK(vb_scan(config_read,37,&region,1,&cursor,&function)==0&&function.vendor==0x1af4&&function.id==0x1042&&function.device==1&&function.function==0);
    Function target=function;CHECK(vb_scan(config_read,37,&region,1,&cursor,&function)==0&&function.function==1);
    CHECK(vb_scan(config_read,37,&region,1,&cursor,&function)==1);CHECK(config_calls<200);
    Cursor before_cursor={0};cursor=before_cursor;memset(&function,0xa7,sizeof function);Function before_function=function;config_fail=1;
    CHECK(vb_scan(config_read,37,&region,1,&cursor,&function)==0x05010003);CHECK(memcmp(&cursor,&before_cursor,sizeof cursor)==0&&memcmp(&function,&before_function,sizeof function)==0);config_fail=0;
    Bar bars[6]={{UINT64_C(0x1fc000000),4096,11}};Transport transport={0};
    CHECK(vb_discover(config_read,37,&target,bars,&transport)==0);
    Transport expected={{11,0,56,0},{11,0x100,0x100,0},{11,0x200,1,0},{11,0x300,8,0},4};CHECK(memcmp(&transport,&expected,sizeof expected)==0);
    // A reserved vendor type and reserved BAR are ignored before interpreting
    // their unsupported payload. Larger supported cap_len is accepted.
    w32(cfg+52,0x88);w32(cfg+0x88,9|(0x40<<8)|(4<<16)|(99u<<24));
    CHECK(vb_discover(config_read,37,&target,bars,&transport)==0&&memcmp(&transport,&expected,sizeof expected)==0);
    w32(cfg+0x88,9|(0x40<<8)|(4<<16)|(1u<<24));w32(cfg+0x8c,7);
    CHECK(vb_discover(config_read,37,&target,bars,&transport)==0&&memcmp(&transport,&expected,sizeof expected)==0);config_init();
    Transport sentinel;memset(&sentinel,0xa7,sizeof sentinel);Transport saved=sentinel;cfg[0x75]=0x74;
    CHECK(vb_discover(config_read,37,&target,bars,&sentinel)==0x05020003);CHECK(memcmp(&sentinel,&saved,sizeof saved)==0);config_init();
    for(unsigned i=0;i<sizeof disk;i++) { disk[i]=(uint8_t)(i*13+7); }
    memcpy(cache,disk,sizeof disk);
    vb_state_reset(&state);uint64_t init=vb_initialize(&state,&transport,&ops,99);
    if(scenario==8||scenario==11||scenario==12) {
        CHECK(init==ERROR(scenario==8?6:5));CHECK(acquired==0&&released==0);State empty={0};CHECK(memcmp(&state,&empty,sizeof empty)==0);printf("virtio block init rejection passed scenario=%u\n",scenario);free(allocation);return 0;
    }
    CHECK(init==0&&state.info.capacity==256&&state.info.maximum==128&&state.info.ready==1&&state.info.held==1&&status==15);
    uint8_t *output=malloc(65536+32),*input=malloc(65536);CHECK(output&&input);memset(output,0xa7,65536+32);
    if(scenario==10) { CHECK(vb_write(&state,0,1,output+16)==ERROR(10));CHECK(requests==0); }
    uint64_t result=vb_callback_read((uint64_t)(uintptr_t)&state,7,2,output+16);
    if((scenario>=1&&scenario<=7)||scenario==9) {
        CHECK(result==(scenario==9?UINT64_C(0x05020005):ERROR(scenario==5?7:scenario==6?9:8)));for(unsigned i=0;i<65536+32;i++)CHECK(output[i]==0xa7);
        CHECK(released==0&&state.info.held==1);
        if(scenario!=6) { CHECK(state.info.ready==0&&state.info.faulted==1&&state.published==1);CHECK(vb_read(&state,0,1,output)==ERROR(3)); }
        else { CHECK(state.info.ready==1&&state.info.faulted==0&&state.published==0&&state.info.completed==1);scenario=0;CHECK(vb_read(&state,0,1,output)==0);scenario=6; }
        if(scenario==7) { reset_fail=1;CHECK(vb_close(&state)==ERROR(11));CHECK(released==0&&state.info.held==1);reset_fail=0; }
        CHECK(vb_close(&state)==0&&released==1&&state.info.held==0);
        printf("virtio block bad completion safely retained DMA scenario=%u\n",scenario);free(output);free(input);free(allocation);return 0;
    }
    CHECK(result==0&&memcmp(output+16,cache+7*512,1024)==0&&fences[2]==1);
    for(unsigned i=0;i<16;i++)CHECK(output[i]==0xa7&&output[16+1024+i]==0xa7);
    invalid_snapshot(256,1,output,ERROR(1));invalid_snapshot(UINT64_MAX,1,output,ERROR(1));invalid_snapshot(0,0,output,ERROR(1));invalid_snapshot(0,129,output,ERROR(1));
    invalid_snapshot(0,1,dma+4096,ERROR(1));invalid_snapshot(0,1,(uint8_t *)&state,ERROR(1));
    if(scenario==0) {
        for(unsigned i=0;i<65536;i++)input[i]=(uint8_t)(i*29+11);
        CHECK(vb_callback_write((uint64_t)(uintptr_t)&state,17,128,input)==0);CHECK(memcmp(cache+17*512,input,65536)==0&&memcmp(disk+17*512,input,65536)!=0);
        CHECK(vb_callback_flush((uint64_t)(uintptr_t)&state)==0&&flushes==1&&memcmp(disk+17*512,input,65536)==0);
        CHECK(vb_read(&state,17,128,output+16)==0&&memcmp(output+16,input,65536)==0);
        state.info.avail=state.info.used=65535;device_avail=device_used=65535;w16(dma+130,65535);w16(dma+154,65535);
        CHECK(vb_read(&state,0,1,output+16)==0&&state.info.avail==0&&state.info.used==0);
        release_fail=1;CHECK(vb_close(&state)==ERROR(11)&&released==0&&state.info.held==1&&state.info.ready==0);release_fail=0;
    }
    CHECK(vb_close(&state)==0&&acquired==released);State empty={0};CHECK(memcmp(&state,&empty,sizeof empty)==0);
    if(scenario==0) { memcpy(cache,disk,sizeof cache);CHECK(vb_initialize(&state,&transport,&ops,99)==0);CHECK(vb_read(&state,17,128,output+16)==0&&memcmp(output+16,input,65536)==0);CHECK(vb_close(&state)==0&&acquired==released); }
    printf("virtio modern independent DMA/durable-disk model passed scenario=%u requests=%u releases=%u\n",scenario,requests,released);
    free(output);free(input);free(allocation);return 0;
}
