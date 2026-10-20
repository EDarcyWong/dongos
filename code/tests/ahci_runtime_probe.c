/* A separate HBA model interprets actual descriptor bytes at CI issue. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#define ABI __attribute__((sysv_abi))
#define GUARD UINT64_C(0xbadc0fee98765432)
#define PA UINT64_C(0x02000000)
#define SIZE 131072
#define HANDLE UINT64_C(0x12345)
#define INVALID UINT64_C(0x09020001)
#define ALREADY UINT64_C(0x09020002)
#define BUSY UINT64_C(0x09020003)
#define NOTREADY UINT64_C(0x09020004)
#define IO UINT64_C(0x09020005)
#define UNSUP UINT64_C(0x09020006)
#define CLOCK UINT64_C(0x09020007)
#define CLEANUP UINT64_C(0x0902000a)
#define CORE_TIMEOUT UINT64_C(0x09010008)
#define CORE_BADCOMP UINT64_C(0x09010009)
#define CORE_DEVICE UINT64_C(0x0901000a)
typedef struct {uint64_t token,physical;uint8_t *pointer;size_t length;} Lease;
typedef struct {uint64_t physical,length,handle;} Bar;
typedef struct {uint64_t capacity_sectors,max_transfer_sectors,readonly,ready,faulted,held,completed;} Info;
typedef struct {uint64_t generation,pending,faulted,held,opcode,expected,start_ms,timeout_ms,last_ms,completed;} CoreState;
typedef struct {uint64_t sectors,sector_bytes,flush_ext,write_cache,valid;} Drive;
typedef struct {uint64_t physical_bits,s64a;} Caps;
typedef struct {uint64_t generation,ci,sact,interrupts,tfd,serr,prdbc,now_ms;uint8_t fis[256];} Sample;
typedef ABI uint64_t (*Read)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t *);
typedef ABI uint64_t (*Write)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
typedef ABI uint64_t (*Fence)(uint64_t,uint64_t);
typedef ABI uint64_t (*Acquire)(uint64_t,size_t,size_t,Lease *);
typedef ABI uint64_t (*Release)(uint64_t,const Lease *);
typedef ABI uint64_t (*Enable)(uint64_t,uint64_t);
typedef ABI uint64_t (*Now)(uint64_t,uint64_t *);
typedef struct {Read read;Write write;Fence fence;Acquire acquire;Release release;Enable enable;Now now;} Ops;
typedef struct {Info info;Lease lease;Bar bar;const Ops *ops;uint64_t context,port,cap,pi;CoreState transfer;Drive drive;Caps caps;
    uint64_t busy,enabled,last_ms,clock_seen,published;Sample last_sample;uint64_t completion_policy;} State;
extern ABI void ar_reset(State *);
extern ABI void ar_sizes(uint64_t *);
extern ABI uint64_t ar_init(State *,const Bar *,const Ops *,uint64_t);
extern ABI uint64_t ar_init_policy(State *,const Bar *,const Ops *,uint64_t,uint64_t);
extern ABI uint64_t ar_read(State *,uint64_t,size_t,uint8_t *);
extern ABI uint64_t ar_write(State *,uint64_t,size_t,const uint8_t *);
extern ABI uint64_t ar_flush(State *);
extern ABI uint64_t ar_mutant_hits(void);
static uint64_t assertions,commands,enabled_count,barriers[4],mmio_reads,mmio_writes,acquires,releases,scenarios;
static void check(int yes,const char *what,int line){assertions++;if(!yes){uint64_t hits=ar_mutant_hits();
    if(hits)fprintf(stderr,"AHCI_RUNTIME_MUTANT_PATH_HIT=%" PRIu64 "\n",hits);
    fprintf(stderr,"AHCI runtime oracle line %d: %s\n",line,what);exit(1);}}
#define C(x) check(!!(x),#x,__LINE__)
ABI void __dong_panic(uint64_t code,uint64_t a,uint64_t b,uint64_t c){
    fprintf(stderr,"DG panic %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",code,a,b,c);exit(99);}
static uint64_t get(const uint8_t *p,size_t n){uint64_t v=0;for(size_t i=0;i<n;i++)v|=(uint64_t)p[i]<<(i*8);return v;}
static void put(uint8_t *p,uint64_t v,size_t n){for(size_t i=0;i<n;i++)p[i]=(uint8_t)(v>>(i*8));}
static uint8_t arena[SIZE+8192] __attribute__((aligned(4096)));
static uint8_t *const dma=arena+4096;
/* Includes the captured VMware READ at LBA 0x7e4. */
static uint8_t cache[4096*512],durable[4096*512];
typedef struct {uint32_t cmd,ie,is,serr,ci,tfd,sact,ssts,sig,clb,clbu,fb,fbu;} Port;
static struct {uint32_t ghc,bohc;Port p[3];uint64_t time,ownership_reads,pending_reads,mode,bme,phase,issued_opcode,clock_calls;} hba;
enum {NORMAL,STUCK_CR,STUCK_FR,STUCK_BIOS,ENABLE_DENIED,ACQUIRE_FAIL,BAD_LEASE,CLOCK_BACK,
    HANG,SHORT_DMA,BAD_FIS,DEVICE_ERROR,NO_FLUSH,BAD_IDENTIFY,PIO_D2H,MMIO_FAIL,FRE_FAIL,
    VMWARE_PIO,VMWARE_TFD_ERR,VMWARE_TFD_DF,VMWARE_TFD_BSY,VMWARE_TFD_DRQ,VMWARE_SHORT,
    VMWARE_TYPE,VMWARE_DIRECTION,VMWARE_COUNT,VMWARE_STATUS_BSY,VMWARE_STATUS_DF,VMWARE_STATUS_ERR,
    VMWARE_END_BSY,VMWARE_END_DRQ,VMWARE_END_ERR,VMWARE_END_DF,VMWARE_SACT,VMWARE_NON_IDENTIFY};
static int vmware_pio(uint64_t mode){return mode>=VMWARE_PIO&&mode<=VMWARE_SACT;}
static void guards(void){for(size_t i=0;i<4096;i++){C(arena[i]==0xa5);C(arena[SIZE+4096+i]==0x5a);}}
static void fixture(uint8_t *p){memset(p,0,512);put(p,0x40,2);put(p+49*2,0x300,2);
    put(p+83*2,hba.mode==NO_FLUSH?0x4400:0x6400,2);put(p+85*2,0x20,2);
    put(p+86*2,hba.mode==NO_FLUSH?0x400:0x2400,2);put(p+87*2,0x4000,2);
    put(p+100*2,65536,8);put(p+106*2,hba.mode==BAD_IDENTIFY?0x5000:0x6003,2);}
static void reset_model(uint64_t mode){
    memset(&hba,0,sizeof hba);hba.mode=mode;hba.ghc=0x80000002;hba.bohc=0x1d;
    for(unsigned i=0;i<3;i++){hba.p[i].cmd=0x17;hba.p[i].ie=0xffffffff;hba.p[i].tfd=0x50;hba.p[i].serr=0x10000;hba.p[i].is=0x40;}
    hba.p[1].ssts=0x123;hba.p[1].sig=0xeb140101;hba.p[2].ssts=0x123;hba.p[2].sig=0x101;
    memset(arena,0xa5,4096);memset(dma,0xc3,SIZE);memset(arena+4096+SIZE,0x5a,4096);
    for(size_t i=0;i<sizeof cache;i++){cache[i]=durable[i]=(uint8_t)(i*17+11);}scenarios++;
}
static uint32_t cmd_value(unsigned p){uint32_t x=hba.p[p].cmd;
    if((x&1)||(hba.mode==STUCK_CR&&p==0))x|=0x8000;
    if((x&0x10)||(hba.mode==STUCK_FR&&p==0))x|=0x4000;
    if(hba.mode==FRE_FAIL&&hba.bme&&p==2)x&=~0x4000u;
    return x;
}
static void complete(void){
    C(hba.bme&&hba.p[2].ci==1);uint8_t *f=dma+0x800;uint64_t op=f[2];
    const unsigned positions[]={4,5,6,8,9,10};uint64_t lba=0;
    for(size_t i=0;i<6;i++)lba|=(uint64_t)f[positions[i]]<<(8*i);
    size_t n=(size_t)get(f+12,2),bytes=op==0xec?512:(op==0xea?0:n*512);
    if(op==0xec)fixture(dma+0x1000);
    if(op==0x25||op==0x35){C(lba+n<=4096);if(op==0x25)memcpy(dma+0x1000,cache+lba*512,bytes);else memcpy(cache+lba*512,dma+0x1000,bytes);}
    if(op==0xea)memcpy(durable,cache,sizeof durable);
    put(dma+4,hba.mode==SHORT_DMA?bytes-1:bytes,4);
    if(op==0xec&&hba.mode!=PIO_D2H){dma[0x420]=0x5f;dma[0x421]=0x60;dma[0x422]=0x58;dma[0x42f]=0x50;dma[0x431]=2;hba.p[2].is=2;}
    else{dma[0x440]=hba.mode==BAD_FIS?0x5f:0x34;dma[0x441]=0x40;dma[0x442]=0x50;hba.p[2].is=1;}
    hba.p[2].tfd=hba.mode==DEVICE_ERROR?0x51:0x50;hba.p[2].ci=0;
    if((op==0xec&&vmware_pio(hba.mode))||hba.mode==VMWARE_NON_IDENTIFY){
        /* Exact received VMware sample: saved Status40, E_Status00. This is
           an explicit interop fixture, not a wire-conformance assertion. */
        memset(dma+0x400,0,256);dma[0x420]=0x5f;dma[0x421]=0x60;dma[0x422]=0x40;dma[0x431]=2;
        hba.p[2].is=2;hba.p[2].tfd=0x40;
        switch(hba.mode){
        case VMWARE_TFD_ERR:hba.p[2].tfd=0x41;break;case VMWARE_TFD_DF:hba.p[2].tfd=0x60;break;
        case VMWARE_TFD_BSY:hba.p[2].tfd=0xc0;break;case VMWARE_TFD_DRQ:hba.p[2].tfd=0x48;break;
        case VMWARE_SHORT:put(dma+4,511,4);break;case VMWARE_TYPE:dma[0x420]=0x34;break;
        case VMWARE_DIRECTION:dma[0x421]=0x40;break;case VMWARE_COUNT:dma[0x430]=1;break;
        case VMWARE_STATUS_BSY:dma[0x422]=0xc0;break;case VMWARE_STATUS_DF:dma[0x422]=0x60;break;
        case VMWARE_STATUS_ERR:dma[0x422]=0x41;break;case VMWARE_END_BSY:dma[0x42f]=0x80;break;
        case VMWARE_END_DRQ:dma[0x42f]=8;break;case VMWARE_END_ERR:dma[0x42f]=1;break;
        case VMWARE_END_DF:dma[0x42f]=0x20;break;case VMWARE_SACT:hba.p[2].sact=1;break;default:break;
        }
    }
}
static ABI uint64_t model_read(uint64_t context,uint64_t handle,uint64_t offset,uint64_t width,uint64_t *out){
    C(context==77&&handle==HANDLE&&width==4&&!(offset&3)&&offset<0x280);mmio_reads++;
    if(hba.mode==MMIO_FAIL)return 1;
    if(offset==0){*out=0x80000002;return 0;}if(offset==4){*out=hba.ghc;return 0;}
    if(offset==8){*out=0;return 0;}if(offset==0xc){*out=7;return 0;}if(offset==0x10){*out=0x10301;return 0;}
    if(offset==0x24){*out=1;return 0;}
    if(offset==0x28){hba.ownership_reads++;if((hba.bohc&2)&&hba.ownership_reads>3&&hba.mode!=STUCK_BIOS)hba.bohc&=~0x11u;*out=hba.bohc;return 0;}
    C(offset>=0x100);unsigned p=(unsigned)((offset-0x100)/0x80),r=(unsigned)((offset-0x100)%0x80);C(p<3);
    Port *v=&hba.p[p];
    if(r==0x38&&p==2&&v->ci&&hba.mode!=HANG){if(++hba.pending_reads>=2)complete();}
    switch(r){case 0:*out=v->clb;break;case 4:*out=v->clbu;break;case 8:*out=v->fb;break;case 12:*out=v->fbu;break;
    case 0x10:*out=v->is;break;case 0x14:*out=v->ie;break;case 0x18:*out=cmd_value(p);break;
    case 0x20:*out=v->tfd;break;case 0x24:*out=v->sig;break;case 0x28:*out=v->ssts;break;
    case 0x30:*out=v->serr;break;case 0x34:*out=v->sact;break;case 0x38:*out=v->ci;break;case 0x40:*out=0;break;
    default:C(0);}
    return 0;
}
static void issue(uint64_t value){
    C(value==1&&hba.bme&&hba.p[2].ci==0&&hba.p[2].ie==0&&(cmd_value(2)&0xc011)==0xc011);
    uint8_t expected[32]={0},*f=dma+0x800;uint64_t op=f[2];C(op==0xec||op==0x25||op==0x35||op==0xea);
    size_t count=(size_t)get(f+12,2);uint64_t bytes=op==0xec?512:(op==0xea?0:count*512);
    put(expected,5+(op==0x35?64:0)+(bytes?65536:0),4);put(expected+8,PA+0x800,8);
    C(!memcmp(dma,expected,32));for(size_t i=32;i<1024;i++)C(dma[i]==0);
    C(f[0]==0x27&&f[1]==0x80&&f[3]==0&&f[11]==0&&f[14]==0&&f[15]==0);
    for(size_t i=16;i<128;i++)C(f[i]==0);
    if(bytes){C(get(f+128,8)==PA+0x1000&&get(f+136,4)==0&&get(f+140,4)==bytes-1);}
    else for(size_t i=128;i<144;i++)C(f[i]==0);
    for(size_t i=0;i<256;i++)C(dma[0x400+i]==0);
    if(op==0x25||op==0x35){C(f[7]==0x40&&count>=1&&count<=128);}
    else{C(f[7]==0&&count==0);for(size_t i=4;i<11;i++)C(f[i]==0);}
    C(barriers[1]>0&&barriers[3]>0);hba.p[2].ci=1;hba.pending_reads=0;hba.issued_opcode=op;commands++;
}
static ABI uint64_t model_write(uint64_t context,uint64_t handle,uint64_t offset,uint64_t width,uint64_t value){
    C(context==77&&handle==HANDLE&&width==4&&!(offset&3)&&value<=UINT32_MAX&&offset<0x280);mmio_writes++;
    if(offset==4){C(value==0x80000000);hba.ghc=(uint32_t)value;return 0;}
    if(offset==0x28){C(!hba.bme&&(value&~6u)==0&&(value&2));hba.bohc=(hba.bohc&0x19)|((uint32_t)value&6);return 0;}
    C(offset>=0x100);unsigned p=(unsigned)((offset-0x100)/0x80),r=(unsigned)((offset-0x100)%0x80);C(p<3);Port *v=&hba.p[p];
    switch(r){case 0:C(!hba.bme);v->clb=(uint32_t)value;break;case 4:C(!hba.bme);v->clbu=(uint32_t)value;break;
    case 8:C(!hba.bme);v->fb=(uint32_t)value;break;case 12:C(!hba.bme);v->fbu=(uint32_t)value;break;
    case 0x14:C(value==0);v->ie=0;break;case 0x10:C(!(value&~UINT64_C(0xfdc000ff)));v->is&=~(uint32_t)value;break;
    case 0x30:C(!(value&~UINT64_C(0x07ff0f03)));v->serr&=~(uint32_t)value;break;
    case 0x18:C(!(value&~UINT64_C(0x17)));if((value&0x10)&&!(v->cmd&0x10))C(hba.bme&&p==2);
        if((value&1)&&!(v->cmd&1)){C(hba.bme&&p==2&&(v->cmd&0x10));}v->cmd=(uint32_t)value;break;
    case 0x38:C(p==2);issue(value);break;default:C(0);}
    return 0;
}
static ABI uint64_t model_fence(uint64_t context,uint64_t kind){C(context==77&&kind>=1&&kind<=3);barriers[kind]++;return 0;}
static ABI uint64_t model_acquire(uint64_t context,size_t size,size_t alignment,Lease *out){
    C(context==77&&size==SIZE&&alignment==4096&&!hba.bme);acquires++;
    if(hba.mode==ACQUIRE_FAIL)return 1;
    *out=(Lease){0xabcdef,PA,dma,hba.mode==BAD_LEASE?SIZE-1:SIZE};return 0;
}
static ABI uint64_t model_release(uint64_t context,const Lease *l){(void)context;(void)l;releases++;C(0);return 1;}
static ABI uint64_t model_enable(uint64_t context,uint64_t port){
    C(context==77&&port==2&&!hba.bme&&(hba.ghc&0x80000003)==0x80000000);C((hba.bohc&0x13)==2);
    for(unsigned p=0;p<3;p++)C((cmd_value(p)&0xc011)==0&&hba.p[p].ci==0&&hba.p[p].sact==0&&hba.p[p].ie==0);
    C(hba.p[2].clb==PA&&hba.p[2].clbu==0&&hba.p[2].fb==PA+0x400&&hba.p[2].fbu==0);
    for(size_t i=0;i<SIZE;i++)C(dma[i]==0);
    if(hba.mode==ENABLE_DENIED)return 1;
    hba.bme=1;enabled_count++;return 0;
}
static ABI uint64_t model_now(uint64_t context,uint64_t *out){C(context==77);hba.clock_calls++;C(hba.clock_calls<=20000);
    if(hba.mode==CLOCK_BACK&&hba.clock_calls==5){*out=0;return 0;}*out=++hba.time;return 0;}
static const Ops ops={model_read,model_write,model_fence,model_acquire,model_release,model_enable,model_now};
static const Bar bar={0xfebd5000,4096,HANDLE};
typedef struct {uint64_t pre;State state;uint64_t post;} GuardState;
static void exact_sample(const State *s){
    Sample expected={0};
    if(s->transfer.generation){
        expected.generation=s->transfer.generation;expected.ci=hba.p[2].ci;expected.sact=hba.p[2].sact;
        expected.interrupts=hba.p[2].is;expected.tfd=hba.p[2].tfd;expected.serr=hba.p[2].serr;expected.now_ms=hba.time;
        if(!expected.ci){expected.prdbc=get(dma+4,4);memcpy(expected.fis,dma+0x400,256);}
    }
    C(!memcmp(&s->last_sample,&expected,sizeof expected));
}
static uint64_t init(GuardState *s,uint64_t mode){reset_model(mode);s->pre=s->post=GUARD;ar_reset(&s->state);
    uint64_t rc=ar_init(&s->state,&bar,&ops,77);C(s->pre==GUARD&&s->post==GUARD);guards();return rc;}
static uint64_t init_policy(GuardState *s,uint64_t mode,uint64_t policy){reset_model(mode);s->pre=s->post=GUARD;ar_reset(&s->state);
    uint64_t rc=ar_init_policy(&s->state,&bar,&ops,77,policy);C(s->pre==GUARD&&s->post==GUARD);guards();return rc;}
static void held_fault(GuardState *g){State *s=&g->state;C(!s->busy&&!s->info.ready&&s->info.faulted&&s->info.held);
    exact_sample(s);
    C(s->lease.token==0xabcdef&&s->lease.pointer==dma&&s->transfer.held&&s->transfer.faulted&&s->transfer.pending);
    State old=*s;uint8_t out[512];memset(out,0xa7,sizeof out);uint64_t issued=commands;
    C(ar_read(s,0,1,out)==CLEANUP&&ar_write(s,0,1,out)==CLEANUP&&ar_flush(s)==CLEANUP);
    C(!memcmp(&old,s,sizeof old)&&commands==issued);for(size_t i=0;i<sizeof out;i++)C(out[i]==0xa7);
    C(ar_init(s,&bar,&ops,77)==ALREADY);C(g->pre==GUARD&&g->post==GUARD&&releases==0);guards();}
static void good_path(uint64_t mode){GuardState s;C(init(&s,mode)==0);State *v=&s.state;
    exact_sample(v);
    C(v->info.ready==1&&!v->info.faulted&&v->info.held==1&&v->info.capacity_sectors==65536&&v->info.max_transfer_sectors==128);
    C(v->enabled==1&&v->port==2&&v->info.completed==0&&v->transfer.completed==1&&!v->transfer.pending);
    struct {uint64_t pre;uint8_t data[65536];uint64_t post;} out;out.pre=out.post=GUARD;
    for(size_t i=0;i<sizeof out.data;i++)out.data[i]=(uint8_t)(i*29+7);
    C(ar_write(v,16,128,out.data)==0&&v->info.completed==1);C(!memcmp(cache+16*512,out.data,sizeof out.data));
    C(memcmp(durable+16*512,out.data,sizeof out.data)!=0);C(ar_flush(v)==0&&v->info.completed==2);
    C(!memcmp(durable+16*512,out.data,sizeof out.data));memset(out.data,0,sizeof out.data);
    C(ar_read(v,16,128,out.data)==0&&v->info.completed==3);C(!memcmp(durable+16*512,out.data,sizeof out.data));
    exact_sample(v);
    C(out.pre==GUARD&&out.post==GUARD&&s.pre==GUARD&&s.post==GUARD);C(barriers[2]>0);
    State before=*v;uint64_t issued=commands;C(ar_read(v,0,0,out.data)==INVALID);C(ar_read(v,65535,2,out.data)==INVALID);
    C(ar_read(v,0,129,out.data)==INVALID);C(ar_read(v,0,1,NULL)==INVALID);C(ar_write(v,0,1,dma)==INVALID);
    C(ar_read(v,0,1,(uint8_t*)v)==INVALID);C(ar_read(v,0,1,(uint8_t*)&ops)==INVALID);
    C(ar_read(v,0,1,(uint8_t*)(uintptr_t)(UINT64_MAX-31))==INVALID);
    C(!memcmp(v,&before,sizeof before)&&commands==issued);C(ar_init(v,&bar,&ops,77)==ALREADY);guards();
}
static void policy_cases(void){
    GuardState s;C(init(&s,VMWARE_PIO)==CORE_BADCOMP);C(s.state.completion_policy==0);held_fault(&s);
    C(init_policy(&s,VMWARE_PIO,0)==CORE_BADCOMP);C(s.state.completion_policy==0);held_fault(&s);
    C(init_policy(&s,VMWARE_PIO,1)==0);C(s.state.completion_policy==1&&s.state.info.ready==1);exact_sample(&s.state);
    const uint8_t captured[20]={0x5f,0x60,0x40,[17]=2};
    C(!memcmp(s.state.last_sample.fis+0x20,captured,sizeof captured));
    C(s.state.last_sample.ci==0&&s.state.last_sample.sact==0&&s.state.last_sample.interrupts==2&&s.state.last_sample.tfd==0x40&&s.state.last_sample.prdbc==512);
    State old=s.state;uint64_t reads=mmio_reads,writes=mmio_writes,acquired=acquires;
    C(ar_init_policy(&s.state,&bar,&ops,77,1)==ALREADY);C(ar_init(&s.state,&bar,&ops,77)==ALREADY);
    C(ar_init_policy(&s.state,&bar,&ops,77,2)==INVALID);C(ar_init_policy(&s.state,&bar,&ops,77,UINT64_MAX)==INVALID);
    C(!memcmp(&old,&s.state,sizeof old)&&reads==mmio_reads&&writes==mmio_writes&&acquired==acquires);
    ar_reset(&s.state);old=s.state;C(ar_init_policy(&s.state,&bar,&ops,77,2)==INVALID);C(!memcmp(&old,&s.state,sizeof old));
    C(reads==mmio_reads&&writes==mmio_writes&&acquired==acquires);
    for(uint64_t mode=VMWARE_TFD_ERR;mode<=VMWARE_SACT;mode++){
        /* Adapter TFD BSY/DRQ is pending until the original deadline. Pure
           core completion controls still reject a completed busy snapshot. */
        uint64_t error=(mode==VMWARE_TFD_ERR||mode==VMWARE_TFD_DF)?CORE_DEVICE:
          (mode==VMWARE_TFD_BSY||mode==VMWARE_TFD_DRQ)?CORE_TIMEOUT:CORE_BADCOMP;
        C(init_policy(&s,mode,1)==error);C(s.state.completion_policy==1);held_fault(&s);
    }
    C(init_policy(&s,NORMAL,1)==0);hba.mode=VMWARE_NON_IDENTIFY;uint8_t out[512];memset(out,0x7e,sizeof out);
    C(ar_read(&s.state,0,1,out)==CORE_BADCOMP);for(size_t i=0;i<sizeof out;i++)C(out[i]==0x7e);held_fault(&s);
}
int main(void){uint64_t sizes[3]={0};ar_sizes(sizes);C(sizes[0]==sizeof(State)&&sizes[1]==sizeof(Ops)&&sizes[2]==sizeof(Info));C(sizeof(State)==656&&sizeof(Sample)==320&&offsetof(State,last_sample)==328&&offsetof(State,completion_policy)==648);
    good_path(NORMAL);good_path(PIO_D2H);
    const uint64_t modes[]={STUCK_CR,STUCK_FR,STUCK_BIOS,ENABLE_DENIED,BAD_LEASE,CLOCK_BACK,NO_FLUSH,BAD_IDENTIFY,FRE_FAIL};
    const uint64_t errors[]={CORE_TIMEOUT,CORE_TIMEOUT,CORE_TIMEOUT,IO,UINT64_C(0x09010002),CLOCK,UNSUP,UINT64_C(0x09010003),UINT64_C(0x09020008)};
    GuardState s;
    for(size_t i=0;i<sizeof modes/sizeof *modes;i++){uint64_t old=commands;C(init(&s,modes[i])==errors[i]);held_fault(&s);
        if(modes[i]!=NO_FLUSH&&modes[i]!=BAD_IDENTIFY)C(commands==old);}
    C(init(&s,ACQUIRE_FAIL)==IO&&!s.state.info.held&&s.state.info.faulted);C(!hba.bme);
    C(init(&s,MMIO_FAIL)!=0&&!s.state.info.held&&s.state.info.faulted);C(!hba.bme);
    const uint64_t fails[]={HANG,SHORT_DMA,BAD_FIS,DEVICE_ERROR};
    const uint64_t failerr[]={CORE_TIMEOUT,CORE_BADCOMP,CORE_BADCOMP,CORE_DEVICE};
    for(size_t i=0;i<sizeof fails/sizeof *fails;i++){
        C(init(&s,NORMAL)==0);hba.mode=fails[i];uint8_t out[512];memset(out,0x8f,sizeof out);uint64_t old=s.state.info.completed;
        C(ar_read(&s.state,0,1,out)==failerr[i]);for(size_t j=0;j<sizeof out;j++)C(out[j]==0x8f);
        C(s.state.info.completed==old);held_fault(&s);
    }
    ar_reset(&s.state);State before=s.state;uint8_t out[512];C(ar_read(&s.state,0,1,out)==NOTREADY&&!memcmp(&before,&s.state,sizeof before));
    C(ar_init(NULL,&bar,&ops,77)==INVALID);C(ar_init(&s.state,NULL,&ops,77)==INVALID);C(ar_init(&s.state,&bar,NULL,77)==INVALID);
    s.state.busy=1;C(ar_flush(&s.state)==BUSY);policy_cases();C(releases==0&&ar_mutant_hits()==0);
    printf("AHCI_RUNTIME_MODEL_PASS assertions=%" PRIu64 " scenarios=%" PRIu64 " commands=%" PRIu64 " enables=%" PRIu64 " acquire=%" PRIu64 " release=%" PRIu64 " reads=%" PRIu64 " writes=%" PRIu64 " all-port-stop-before-BME exact-dma-bytes real-ms-policy durable-flush all-guards=ok strict-default bounded-VMware-PIO-policy\n",assertions,scenarios,commands,enabled_count,acquires,releases,mmio_reads,mmio_writes);return 0;
}
