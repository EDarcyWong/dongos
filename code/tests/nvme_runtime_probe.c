/* Independent PCIe NVMe register/queue/PRP model; no actual hardware. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#define ABI __attribute__((sysv_abi))
#define PA UINT64_C(0x04000000)
#define HANDLE UINT64_C(0xabcd)
#define GUARD UINT64_C(0x5a6170e5deadbeef)
#define SIZE 131072
#define INVALID UINT64_C(0x05210001)
#define ALREADY UINT64_C(0x05210002)
#define BUSY UINT64_C(0x05210003)
#define NOTREADY UINT64_C(0x05210004)
#define IO UINT64_C(0x05210005)
#define UNSUP UINT64_C(0x05210006)
#define CLOCK UINT64_C(0x05210007)
#define TIMEOUT UINT64_C(0x05210008)
#define CLEANUP UINT64_C(0x0521000a)
#define DEVICE UINT64_C(0x0521000b)
#define CORE_UNSUP UINT64_C(0x05200002)
#define CORE_EXHAUST UINT64_C(0x05200004)
#define CORE_TIMEOUT UINT64_C(0x05200007)
#define CORE_BAD UINT64_C(0x05200008)
typedef struct {uint64_t token,physical;uint8_t *pointer;size_t length;} Lease;
typedef struct {uint64_t physical,length,handle;} Bar;
typedef struct {uint64_t capacity_sectors,max_transfer_sectors,readonly,ready,faulted,held,completed;} Info;
typedef struct {uint64_t cap,version,physical_bits;} Caps;
typedef struct {uint64_t timeout,stride,max_entries;} Limits;
typedef struct {uint64_t ready,version,max_sectors,cache;} Controller;
typedef struct {uint64_t ready,sectors,max_sectors,readonly;} Namespace;
typedef struct {uint64_t ready,held,fault,epoch,qid,depth,pa,length,sq_tail,cq_head,phase,next_cid,generation,pending,pending_cid,pending_kind,pending_bytes,pending_generation,started_ms,last_ms,timeout_ms;} Queue;
typedef ABI uint64_t (*Read)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t *);
typedef ABI uint64_t (*Write)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
typedef ABI uint64_t (*Fence)(uint64_t,uint64_t);
typedef ABI uint64_t (*Acquire)(uint64_t,size_t,size_t,Lease *);
typedef ABI uint64_t (*Release)(uint64_t,const Lease *);
typedef ABI uint64_t (*Enable)(uint64_t);
typedef ABI uint64_t (*Now)(uint64_t,uint64_t *);
typedef struct {Read read;Write write;Fence fence;Acquire acquire;Release release;Enable enable;Now now;} Ops;
typedef struct {Info info;Lease lease;Bar bar;const Ops *ops;uint64_t context;Caps caps;Limits limits;Controller ctrl;Namespace ns;Queue admin,io;
    uint64_t busy,enabled,clock_seen,last_ms,phase,published,last_csts;uint8_t cqe[16];uint64_t last_kind;} State;
extern ABI void nr_reset(State *);
extern ABI void nr_sizes(uint64_t *);
extern ABI uint64_t nr_init(State *,const Bar *,const Ops *,uint64_t);
extern ABI uint64_t nr_read(State *,uint64_t,size_t,uint8_t *);
extern ABI uint64_t nr_write(State *,uint64_t,size_t,const uint8_t *);
extern ABI uint64_t nr_flush(State *);
extern ABI uint64_t nr_mutant_hits(void);
static uint64_t assertions,scenarios,commands,enables,acquires,releases,reads,writes,wraps,barriers[4];
static void check(int yes,const char *what,int line){assertions++;if(!yes){uint64_t hit=nr_mutant_hits();if(hit)fprintf(stderr,"NVME_RUNTIME_MUTANT_PATH_HIT=%" PRIu64 "\n",hit);
    fprintf(stderr,"NVMe runtime oracle line %d: %s\n",line,what);exit(1);}}
#define C(x) check(!!(x),#x,__LINE__)
ABI void __dong_panic(uint64_t a,uint64_t b,uint64_t c,uint64_t d){fprintf(stderr,"panic %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",a,b,c,d);exit(99);}
static uint64_t get(const uint8_t *p,size_t n){uint64_t v=0;for(size_t i=0;i<n;i++)v|=(uint64_t)p[i]<<(8*i);return v;}
static void put(uint8_t *p,uint64_t v,size_t n){for(size_t i=0;i<n;i++)p[i]=(uint8_t)(v>>(8*i));}
static uint8_t arena[SIZE+8192] __attribute__((aligned(4096)));
static uint8_t *const dma=arena+4096;
static uint8_t disk[512*512],durable[512*512];
enum {NORMAL,STRIDE8,TO2,TOZERO,VS2,CRMS,BAD_LEASE,ACQUIRE_FAIL,ENABLE_DENY,DISABLE_STUCK,ENABLE_STUCK,
    BAD_CONTROLLER,BAD_NAMESPACE,READONLY,MDTS1,HANG,OLD_PHASE,BAD_CID,BAD_SQID,BAD_SQHD,BAD_STATUS,BAD_RESERVED,
    BAD_RESULT,FATAL,SQ_UNCERTAIN,CQ_UNCERTAIN,CLOCK_BACK,DISABLE_TO2,SHUTDOWN_COMPLETE,SHUTDOWN_IN_PROGRESS};
typedef struct {unsigned sq_tail,cq_tail,cq_head,phase,last_cid,posted;} HwQueue;
static struct {uint64_t mode,cap,time,clock_calls,disable_start,enable_start,command_start;
    uint32_t cc,csts,intms,aqa,asq[2],acq[2];int bme,pending;unsigned pending_q,progress,init_step,cq_created,sq_created,features;
    uint8_t command[64];HwQueue q[2];} h;
static void guards(void){for(size_t i=0;i<4096;i++){C(arena[i]==0xa5);C(arena[SIZE+4096+i]==0x5a);}}
static void reset_model(uint64_t mode){memset(&h,0,sizeof h);h.mode=mode;h.cc=0x460001;h.csts=1;
    h.cap=UINT64_C(1)|(UINT64_C(1)<<16)|(UINT64_C(1)<<24)|(UINT64_C(1)<<37);
    if(mode==STRIDE8){h.cap|=UINT64_C(1)<<32;}if(mode==TO2||mode==DISABLE_TO2){h.cap+=(UINT64_C(1)<<24);}
    if(mode==TOZERO){h.cap&=~(UINT64_C(255)<<24);}if(mode==CRMS){h.cap|=UINT64_C(1)<<59;}
    if(mode==SHUTDOWN_COMPLETE||mode==SHUTDOWN_IN_PROGRESS){h.cc=0x464001;h.csts=mode==SHUTDOWN_COMPLETE?9:5;}
    h.q[0].phase=h.q[1].phase=1;memset(arena,0xa5,4096);memset(dma,0x9c,SIZE);memset(arena+SIZE+4096,0x5a,4096);
    for(size_t i=0;i<sizeof disk;i++){disk[i]=durable[i]=(uint8_t)(i*31+7);}scenarios++;
}
static uint64_t stride(void){return UINT64_C(1)<<(2+((h.cap>>32)&15));}
static uint8_t *bus(uint64_t pa,size_t n){C(pa>=PA&&n<=SIZE&&pa-PA<=SIZE-n);return dma+(size_t)(pa-PA);}
static void controller_data(void){uint8_t *p=dma+0x5000;memset(p,0,4096);p[77]=h.mode==MDTS1?1:0;put(p+80,0x10400,4);p[111]=1;p[512]=0x66;p[513]=0x44;
    put(p+516,h.mode==BAD_CONTROLLER?0:256,4);p[525]=1;}
static void namespace_data(void){uint8_t *p=dma+0x5000;memset(p,0,4096);put(p,65536,8);put(p+8,65536,8);put(p+16,17,8);
    p[24]=0x34;put(p+128,(h.mode==BAD_NAMESPACE?12:9)<<16,4);p[99]=h.mode==READONLY?1:0;}
static void transfer(uint64_t op,uint64_t lba,size_t bytes,const uint8_t *sqe){
    C(lba+bytes/512<=512);uint64_t first=get(sqe+24,8),second=get(sqe+32,8);size_t pages=(bytes+4095)/4096;
    C(first==PA+0x6000);if(pages==1)C(second==0);if(pages==2)C(second==PA+0x7000);if(pages>2)C(second==PA+0x4000);
    for(size_t i=0;i<16;i++){uint64_t expected=pages>2&&i<pages-1?PA+0x7000+i*4096:0;C(get(dma+0x4000+i*8,8)==expected);}
    size_t offset=0;
    for(size_t i=0;i<pages;i++){uint64_t pa=i==0?first:(pages==2?second:get(bus(second,128)+(i-1)*8,8));size_t n=bytes-offset;if(n>4096)n=4096;
        C(pa==PA+0x6000+i*4096);if(op==2)memcpy(bus(pa,n),disk+lba*512+offset,n);else memcpy(disk+lba*512+offset,bus(pa,n),n);offset+=n;}
    C(offset==bytes);
}
static void finish(void){C(h.pending&&!h.q[h.pending_q].posted);unsigned q=h.pending_q;uint8_t *s=h.command;uint64_t op=s[0],result=0;
    if(q==0){
        if(h.init_step==0){controller_data();h.init_step++;}
        else if(h.init_step==1){namespace_data();h.init_step++;}
        else if(h.init_step==2){h.features=1;h.init_step++;}
        else if(h.init_step==3){C(h.features);h.cq_created=1;h.init_step++;}
        else{C(h.init_step==4&&h.cq_created);h.sq_created=1;h.init_step++;}
    }else{
        if(op==0)memcpy(durable,disk,sizeof disk);else{uint64_t lba=get(s+40,8);size_t bytes=((size_t)get(s+48,2)+1)*512;transfer(op,lba,bytes,s);}
    }
    HwQueue *v=&h.q[q];uint8_t *c=dma+(q?0x3000:0x1000)+v->cq_tail*16;memset(c,0,16);
    put(c,h.mode==BAD_RESULT?1:result,4);put(c+4,h.mode==BAD_RESERVED?1:0,4);
    put(c+8,h.mode==BAD_SQHD?(v->sq_tail^1):v->sq_tail,2);put(c+10,h.mode==BAD_SQID?(q^1):q,2);
    put(c+12,h.mode==BAD_CID?v->last_cid+1:v->last_cid,2);
    put(c+14,(h.mode==OLD_PHASE?(v->phase^1):v->phase)|(h.mode==BAD_STATUS?2:0),2);
    v->cq_tail^=1;if(!v->cq_tail){v->phase^=1;wraps++;}v->posted=1;h.pending=0;
}
static void issue(unsigned q,uint64_t tail){
    C(h.bme&&h.cc==0x460001&&h.csts==1&&tail==(h.q[q].sq_tail^1)&&!h.pending&&!h.q[q].posted);
    C(q==0||h.sq_created);uint8_t *s=dma+(q?0x2000:0)+h.q[q].sq_tail*64;uint8_t expected[64]={0};
    uint64_t cid=get(s+2,2);C(cid==h.q[q].last_cid+1&&cid>0&&cid<65535);put(expected+2,cid,2);
    if(q==0){
        if(h.init_step<2){expected[0]=6;put(expected+4,h.init_step?1:0,4);put(expected+24,PA+0x5000,8);put(expected+40,h.init_step?0:1,4);}
        else if(h.init_step==2){expected[0]=9;put(expected+40,7,4);}
        else if(h.init_step==3){expected[0]=5;put(expected+24,PA+0x3000,8);put(expected+40,0x10001,4);put(expected+44,1,4);}
        else{C(h.init_step==4);expected[0]=1;put(expected+24,PA+0x2000,8);put(expected+40,0x10001,4);put(expected+44,0x10001,4);}
    }else{
        uint64_t op=s[0];C(op==0||op==1||op==2);expected[0]=(uint8_t)op;put(expected+4,1,4);
        if(op){size_t bytes=((size_t)get(s+48,2)+1)*512;C(bytes&&bytes<=65536);put(expected+24,PA+0x6000,8);
            if(bytes>4096){put(expected+32,bytes<=8192?PA+0x7000:PA+0x4000,8);}put(expected+40,get(s+40,8),8);put(expected+48,get(s+48,2),4);}
    }
    C(!memcmp(expected,s,64));C(barriers[1]&&barriers[3]);h.q[q].sq_tail=(unsigned)tail;h.q[q].last_cid=(unsigned)cid;
    memcpy(h.command,s,64);h.pending=1;h.pending_q=q;h.progress=0;h.command_start=h.time;commands++;
}
static ABI uint64_t model_read(uint64_t ctx,uint64_t handle,uint64_t off,uint64_t width,uint64_t *out){
    C(ctx==91&&handle==HANDLE&&width==4&&!(off&3)&&off<8192);reads++;
    switch(off){case 0:*out=h.cap&UINT32_MAX;break;case 4:*out=h.cap>>32;break;case 8:*out=h.mode==VS2?0x20000:0x10400;break;
    case 0xc:*out=h.intms;break;case 0x14:*out=h.cc;break;case 0x1c:
        if(h.pending&&h.mode==FATAL)h.csts|=2;
        if(h.pending&&h.mode!=HANG&&h.mode!=FATAL&&++h.progress>=2){finish();}*out=h.csts;break;
    case 0x24:*out=h.aqa;break;case 0x28:*out=h.asq[0];break;case 0x2c:*out=h.asq[1];break;case 0x30:*out=h.acq[0];break;case 0x34:*out=h.acq[1];break;default:C(0);}
    return 0;
}
static ABI uint64_t model_write(uint64_t ctx,uint64_t handle,uint64_t off,uint64_t width,uint64_t value){
    C(ctx==91&&handle==HANDLE&&width==4&&!(off&3)&&value<=UINT32_MAX&&off<8192);writes++;
    if(off>=0x1000){uint64_t delta=off-0x1000;C(delta%stride()==0&&delta/stride()<4);unsigned index=(unsigned)(delta/stride()),q=index/2;
        if(index&1){C(h.q[q].posted&&value==h.q[q].cq_tail);h.q[q].cq_head=(unsigned)value;h.q[q].posted=0;
            if(h.mode==CQ_UNCERTAIN)return 1;
        }else{issue(q,value);if(h.mode==SQ_UNCERTAIN)return 1;}return 0;}
    switch(off){case 0xc:C(value==UINT32_MAX&&!h.bme);h.intms|=(uint32_t)value;break;
    case 0x14:
        if(!(value&1)){if(h.cc&1){C(value==(h.cc&~1u)&&!h.bme);h.disable_start=h.time;h.csts=(h.mode==DISABLE_STUCK||h.mode==DISABLE_TO2)?1:0;}else{C(value==0x460000);}C(!h.bme);h.cc=(uint32_t)value;}
        else{C(value==0x460001&&h.bme&&h.cc==0x460000);h.cc=(uint32_t)value;h.enable_start=h.time;h.csts=h.mode==ENABLE_STUCK?0:1;}break;
    case 0x24:C(!h.bme&&h.cc==0x460000&&h.csts==0&&value==0x10001);h.aqa=(uint32_t)value;break;
    case 0x28:case 0x2c:C(!h.bme&&h.cc==0x460000&&h.csts==0);h.asq[(off-0x28)/4]=(uint32_t)value;break;
    case 0x30:case 0x34:C(!h.bme&&h.cc==0x460000&&h.csts==0);h.acq[(off-0x30)/4]=(uint32_t)value;break;default:C(0);}
    return 0;
}
static ABI uint64_t model_fence(uint64_t ctx,uint64_t kind){C(ctx==91&&kind>=1&&kind<=3);barriers[kind]++;return 0;}
static ABI uint64_t model_acquire(uint64_t ctx,size_t n,size_t align,Lease *out){C(ctx==91&&n==SIZE&&align==4096&&!h.bme);acquires++;
    if(h.mode==ACQUIRE_FAIL){return 1;}*out=(Lease){1,PA,dma,h.mode==BAD_LEASE?SIZE-4096:SIZE};return 0;}
static ABI uint64_t model_release(uint64_t ctx,const Lease *l){(void)ctx;(void)l;releases++;C(0);return 1;}
static ABI uint64_t model_enable(uint64_t ctx){C(ctx==91&&!h.bme&&h.cc==0x460000&&h.csts==0&&h.aqa==0x10001&&h.intms==UINT32_MAX);
    C(h.asq[0]==PA&&!h.asq[1]&&h.acq[0]==PA+0x1000&&!h.acq[1]);for(size_t i=0;i<SIZE;i++)C(dma[i]==0);
    if(h.mode==ENABLE_DENY){return 1;}h.bme=1;enables++;return 0;}
static ABI uint64_t model_now(uint64_t ctx,uint64_t *out){C(ctx==91);h.clock_calls++;if(h.mode==CLOCK_BACK){*out=0;return 0;}*out=++h.time;return 0;}
static const Ops ops={model_read,model_write,model_fence,model_acquire,model_release,model_enable,model_now};
static const Bar bar={0xfebf0000,8192,HANDLE};
typedef struct {uint64_t pre;State s;uint64_t post;} GuardState;
static uint64_t init(GuardState *g,uint64_t mode){reset_model(mode);g->pre=g->post=GUARD;nr_reset(&g->s);uint64_t e=nr_init(&g->s,&bar,&ops,91);
    C(g->pre==GUARD&&g->post==GUARD);guards();return e;}
static void held(GuardState *g){State *s=&g->s;C(s->info.held&&s->info.faulted&&!s->info.ready&&!s->busy&&s->lease.pointer==dma&&s->lease.token==1);
    if(s->admin.ready)C(s->admin.held&&s->admin.fault);if(s->io.ready)C(s->io.held&&s->io.fault);
    State before=*s;uint64_t cmd=commands,rd=reads,wr=writes;uint8_t out[512];memset(out,0x87,512);
    C(nr_read(s,0,1,out)==CLEANUP&&nr_write(s,0,1,out)==CLEANUP&&nr_flush(s)==CLEANUP&&nr_init(s,&bar,&ops,91)==ALREADY);
    C(!memcmp(s,&before,sizeof before)&&cmd==commands&&rd==reads&&wr==writes);for(size_t i=0;i<512;i++)C(out[i]==0x87);
    C(g->pre==GUARD&&g->post==GUARD&&releases==0);guards();}
static void good(uint64_t mode){GuardState g;C(init(&g,mode)==0);State *s=&g.s;
    C(s->info.ready&&s->info.held&&!s->info.faulted&&s->info.capacity_sectors==65536&&s->phase==11&&s->enabled&&h.features&&h.cq_created&&h.sq_created);
    C(s->limits.timeout==(mode==TO2?1000:500)&&s->limits.stride==(mode==STRIDE8?8:4));
    C(s->admin.generation==5&&s->admin.cq_head==1&&s->admin.phase==1&&s->admin.next_cid==5&&!s->admin.pending);
    struct {uint64_t pre;uint8_t data[65536];uint64_t post;} data;data.pre=data.post=GUARD;
    size_t n=s->info.max_transfer_sectors;for(size_t i=0;i<sizeof data.data;i++)data.data[i]=(uint8_t)(i*17+33);
    C(nr_write(s,16,n,data.data)==0&&s->info.completed==1);C(memcmp(durable+8192,data.data,n*512)!=0);
    C(nr_flush(s)==0&&s->info.completed==2);C(!memcmp(durable+8192,data.data,n*512));memset(data.data,0,sizeof data.data);
    C(nr_read(s,16,n,data.data)==0&&s->info.completed==3);C(!memcmp(durable+8192,data.data,n*512));
    for(unsigned i=0;i<12;i++)C(nr_read(s,i,i%2?1:8,data.data)==0);
    C(data.pre==GUARD&&data.post==GUARD&&g.pre==GUARD&&g.post==GUARD&&s->io.next_cid==15&&barriers[2]>0);
    State before=*s;uint64_t cmd=commands,rd=reads,wr=writes;
    C(nr_read(s,0,0,data.data)==INVALID&&nr_read(s,0,129,data.data)==INVALID&&nr_read(s,65535,2,data.data)==INVALID);
    C(nr_read(s,0,1,NULL)==INVALID&&nr_read(s,0,1,dma)==INVALID&&nr_write(s,0,1,(const uint8_t*)s)==INVALID);
    C(nr_read(s,0,1,(uint8_t*)&ops)==INVALID&&nr_read(s,0,1,(uint8_t*)(uintptr_t)(UINT64_MAX-31))==INVALID);
    C(!memcmp(s,&before,sizeof before)&&cmd==commands&&rd==reads&&wr==writes);guards();}
int main(void){uint64_t size[3]={0};nr_sizes(size);C(size[0]==sizeof(State)&&size[1]==sizeof(Ops)&&size[2]==sizeof(Info));C(sizeof(State)==656&&sizeof(Queue)==168);
    good(NORMAL);good(STRIDE8);good(TO2);good(MDTS1);good(SHUTDOWN_COMPLETE);
    GuardState g;const uint64_t modes[]={TOZERO,VS2,CRMS,BAD_LEASE,ACQUIRE_FAIL,ENABLE_DENY,DISABLE_STUCK,ENABLE_STUCK,DISABLE_TO2,BAD_CONTROLLER,BAD_NAMESPACE,SHUTDOWN_IN_PROGRESS};
    const uint64_t errors[]={CORE_UNSUP,CORE_UNSUP,CORE_UNSUP,INVALID,IO,IO,TIMEOUT,TIMEOUT,TIMEOUT,CORE_UNSUP,CORE_UNSUP,UNSUP};
    for(size_t i=0;i<sizeof modes/sizeof *modes;i++){C(init(&g,modes[i])==errors[i]);if(g.s.info.held)held(&g);else C(!h.bme&&g.s.info.faulted);
        if(modes[i]==DISABLE_STUCK)C(h.time-h.disable_start>=500);if(modes[i]==ENABLE_STUCK)C(h.time-h.enable_start>=500);if(modes[i]==DISABLE_TO2)C(h.time-h.disable_start>=1000);}
    const uint64_t fails[]={HANG,OLD_PHASE,BAD_CID,BAD_SQID,BAD_SQHD,BAD_STATUS,BAD_RESERVED,BAD_RESULT,FATAL,SQ_UNCERTAIN,CQ_UNCERTAIN,CLOCK_BACK};
    for(size_t i=0;i<sizeof fails/sizeof *fails;i++){C(init(&g,NORMAL)==0);h.mode=fails[i];uint8_t out[512];memset(out,0x5b,512);
        uint64_t expected=CORE_BAD;if(fails[i]==HANG||fails[i]==OLD_PHASE)expected=CORE_TIMEOUT;if(fails[i]==FATAL)expected=DEVICE;
        if(fails[i]==SQ_UNCERTAIN||fails[i]==CQ_UNCERTAIN){expected=UINT64_C(0x05020005);}if(fails[i]==CLOCK_BACK){expected=CLOCK;}
        C(nr_read(&g.s,0,1,out)==expected);for(size_t j=0;j<512;j++)C(out[j]==0x5b);if(fails[i]==HANG||fails[i]==OLD_PHASE)C(h.time-h.command_start>=5000);held(&g);}
    C(init(&g,READONLY)==0);State before=g.s;uint8_t out[512];uint64_t cmd=commands;C(nr_write(&g.s,0,1,out)==UNSUP&&!memcmp(&before,&g.s,sizeof before)&&cmd==commands);
    C(init(&g,NORMAL)==0);g.s.io.next_cid=65534;C(nr_flush(&g.s)==CORE_EXHAUST);held(&g);
    nr_reset(&g.s);before=g.s;C(nr_read(&g.s,0,1,out)==NOTREADY&&!memcmp(&before,&g.s,sizeof before));
    C(nr_init(NULL,&bar,&ops,91)==INVALID&&nr_init(&g.s,NULL,&ops,91)==INVALID&&nr_init(&g.s,&bar,NULL,91)==INVALID);
    g.s.busy=1;C(nr_flush(&g.s)==BUSY);C(releases==0&&nr_mutant_hits()==0&&wraps>20);
    printf("NVME_RUNTIME_MODEL_PASS assertions=%" PRIu64 " scenarios=%" PRIu64 " commands=%" PRIu64 " enables=%" PRIu64 " acquire=%" PRIu64 " release=%" PRIu64 " reads=%" PRIu64 " writes=%" PRIu64 " wraps=%" PRIu64 " CAP-TO-CSTS queue-order actual-SQE-PRPs CID-phase doorbells durable-flush retained-all-guards=ok\n",assertions,scenarios,commands,enables,acquires,releases,reads,writes,wraps);return 0;
}
