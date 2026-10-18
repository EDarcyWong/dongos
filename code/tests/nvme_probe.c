#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct {U cap,version,physical_bits;} Caps;
typedef struct {U ready_timeout_ms,doorbell_stride,max_queue_entries;} Limits;
typedef struct {U ready,version,max_sectors,volatile_cache;} Controller;
typedef struct {U ready,capacity_sectors,max_sectors,readonly;} Namespace;
typedef struct {U qid,depth,epoch,lease_physical,lease_bytes;} Setup;
typedef struct {U kind,lba,sectors,data_offset;} Request;
typedef struct {uint8_t command[64];U prps[16],bytes,data_physical,list_entries,sq_slot,sq_tail,cq_slot,cid,generation;} Plan;
typedef struct {
 U ready,held,fault,epoch,qid,depth,lease_physical,lease_bytes,sq_tail,cq_head,phase,next_cid,generation,pending,pending_cid,pending_kind,pending_bytes,pending_generation,started_ms,last_ms,timeout_ms;
} Queue;
typedef struct {U cid,generation,result,bytes,cq_head,phase;} Completion;
typedef struct {U pre[2];Plan p;U post[2];} GuardedPlan;
extern void ABI nvme_sizes(U*);
extern U ABI nvme_limits(const Caps*,U,Limits*);
extern U ABI nvme_controller(const Caps*,const uint8_t*,U,Controller*);
extern U ABI nvme_namespace(const Controller*,const uint8_t*,U,Namespace*);
extern U ABI nvme_initialize(Queue*,const Caps*,const Setup*);
extern U ABI nvme_encode(const Queue*,const Namespace*,const Request*,U,Plan*);
extern U ABI nvme_submit(Queue*,const Namespace*,const Request*,U,U,Plan*);
extern U ABI nvme_poll(Queue*,U,U,const uint8_t*,U,U,Completion*,U*);
extern U ABI nvme_poison(Queue*,U);
enum {INVALID=0x05200001,UNSUPPORTED,BUSY,EXHAUSTED,STALE,CLOCK,TIMEOUT,BAD,FAULTED};
enum {ID_CTRL=1,ID_NS,RD,WR,FLUSH,CREATE_CQ,CREATE_SQ,SET_QUEUES};
static U assertions,plans,controller_cases,namespace_cases,queue_completions,atomic_rejections;
static unsigned negative_seen;
static Caps caps;
static Namespace ns;
static uint8_t controller_data[4096],namespace_data[4096];
#define CHECK(x) do {assertions++;if(!(x)){fprintf(stderr,"NVME_MODEL_ASSERT line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
void ABI __dong_panic(U code) {fprintf(stderr,"unexpected NVMe panic %" PRIu64 "\n",code);exit(99);}
void ABI nvme_negative_hit(U n) {if(n<32 && !(negative_seen&(1u<<n))){negative_seen|=1u<<n;fprintf(stderr,"NVME_NEGATIVE_HIT %" PRIu64 "\n",n);}}
static void put(uint8_t *p,U value,unsigned bytes) {for(unsigned i=0;i<bytes;i++){p[i]=(uint8_t)value;value>>=8;}}
static U get(const uint8_t *p,unsigned bytes) {U v=0;for(unsigned i=bytes;i>0;i--)v=v*256+p[i-1];return v;}
static void defaults(void) {
 caps=(Caps){(UINT64_C(1)<<37)|(UINT64_C(1)<<24)|0x10000|63,0x10400,48};ns=(Namespace){1,UINT64_C(0xf123456789abcdef),128,0};
 memset(controller_data,0,sizeof controller_data);controller_data[77]=0;put(controller_data+80,caps.version,4);controller_data[111]=1;controller_data[512]=0x66;controller_data[513]=0x44;put(controller_data+516,1,4);controller_data[525]=7;
 memset(namespace_data,0,sizeof namespace_data);put(namespace_data,ns.capacity_sectors,8);put(namespace_data+8,ns.capacity_sectors,8);put(namespace_data+16,0,8);put(namespace_data+128,0x00090000,4);
}
static Queue initialized(U qid,U depth,U physical) {
 Queue q={0};Setup setup={qid,depth,0x34125678,physical,131072};CHECK(nvme_initialize(&q,&caps,&setup)==0);
 CHECK(q.ready==1 && q.held==1 && q.fault==0 && q.phase==1 && q.depth==depth && q.qid==qid && q.lease_physical==physical && q.lease_bytes==131072);return q;
}
static GuardedPlan output(void) {GuardedPlan g;memset(&g,0xa5,sizeof g);g.pre[0]=0x1234;g.pre[1]=0x5678;g.post[0]=0x9abc;g.post[1]=0xdef0;return g;}
static void guards(const GuardedPlan *g) {CHECK(g->pre[0]==0x1234 && g->pre[1]==0x5678 && g->post[0]==0x9abc && g->post[1]==0xdef0);}
/* Build the complete SQE independently, then walk the byte span page by page
   rather than using the implementation's ceil formula for PRP cardinality. */
static Plan reference(const Queue *q,const Request *r,U cid) {
 Plan p={0};U opcode=0;uint8_t *c=p.command;
 if(r->kind==ID_CTRL || r->kind==ID_NS){opcode=6;p.bytes=4096;p.data_physical=q->lease_physical+0x5000;put(c+24,p.data_physical,8);put(c+4,r->kind==ID_NS?1:0,4);put(c+40,r->kind==ID_CTRL?1:0,4);}
 else if(r->kind==CREATE_CQ || r->kind==CREATE_SQ){opcode=r->kind==CREATE_CQ?5:1;p.data_physical=q->lease_physical+(r->kind==CREATE_CQ?0x3000:0x2000);put(c+24,p.data_physical,8);put(c+40,((q->depth-1)<<16)|1,4);put(c+44,r->kind==CREATE_CQ?1:0x10001,4);}
 else if(r->kind==SET_QUEUES){opcode=9;put(c+40,7,4);}
 else {
  put(c+4,1,4);
  if(r->kind!=FLUSH){
   opcode=r->kind==RD?2:1;p.bytes=r->sectors*512;p.data_physical=q->lease_physical+0x6000+r->data_offset;put(c+24,p.data_physical,8);
   U left=p.bytes,address=p.data_physical,rest[16],count=0;
   U first=4096-(address%4096);if(left>first){left-=first;address+=first;}else left=0;
   while(left){CHECK(count<16);rest[count++]=address;U part=left<4096?left:4096;left-=part;address+=part;}
   if(count==1)put(c+32,rest[0],8);else if(count>1){put(c+32,q->lease_physical+0x4000,8);p.list_entries=count;memcpy(p.prps,rest,(size_t)count*sizeof(U));}
   put(c+40,r->lba,8);put(c+48,r->sectors-1,4);
  }
 }
 c[0]=(uint8_t)opcode;put(c+2,cid,2);p.cid=cid;p.sq_slot=q->sq_tail;p.sq_tail=(q->sq_tail+1)%q->depth;p.cq_slot=q->cq_head;return p;
}
static void compare_plan(const Plan *a,const Plan *b) {
 const uint8_t *x=(const uint8_t*)a,*y=(const uint8_t*)b;
 for(unsigned i=0;i<sizeof *a;i++) {if(x[i]!=y[i]){fprintf(stderr,"plan byte %u actual=%02x expected=%02x\n",i,x[i],y[i]);CHECK(x[i]==y[i]);}}
 CHECK(get(a->command+2,2)==a->cid);CHECK(get(a->command+24,8)==a->data_physical);
 ++plans;
}
#define REJECT_ENCODE(expected,q,request,cid) do {Queue saved=(q);GuardedPlan before=output(),actual=before;CHECK(nvme_encode(&(q),&ns,&(request),(cid),&actual.p)==(expected));CHECK(memcmp(&saved,&(q),sizeof saved)==0);CHECK(memcmp(&before,&actual,sizeof actual)==0);atomic_rejections++;}while(0)
static void test_limits_and_identify(void) {
 defaults();Limits lim;
 for(U to=1;to<=255;to++)for(U stride=0;stride<16;stride++){
  Caps c=caps;c.cap=(c.cap&~((UINT64_C(255)<<24)|(UINT64_C(15)<<32)))|(to<<24)|(stride<<32);
  CHECK(nvme_limits(&c,64,&lim)==0);CHECK(lim.ready_timeout_ms==to*500 && lim.doorbell_stride==(UINT64_C(4)<<stride) && lim.max_queue_entries==64);
 }
 for(unsigned bad=0;bad<9;bad++){
  Caps c=caps;U code=UNSUPPORTED;switch(bad){case 0:c.version=0x20000;break;case 1:c.version=0x10500;break;case 2:c.version=0x10401;break;case 3:c.cap&=~(UINT64_C(1)<<37);break;case 4:c.cap|=UINT64_C(1)<<48;break;case 5:c.cap&=~(UINT64_C(255)<<24);break;case 6:c.cap|=UINT64_C(1)<<59;break;case 7:c.physical_bits=35;code=INVALID;break;case 8:c.cap|=UINT64_C(1)<<19;break;}
  Limits before={77,88,99};lim=before;CHECK(nvme_limits(&c,2,&lim)==code);CHECK(memcmp(&lim,&before,sizeof lim)==0);atomic_rejections++;
 }
 for(U mdts=0;mdts<256;mdts++)for(U v=0;v<=4;v++) {
  defaults();Caps c=caps;c.version=0x10000+(v<<8);put(controller_data+80,v<2?0:c.version,4);controller_data[111]=(uint8_t)(v<4?0:1);controller_data[77]=(uint8_t)mdts;
  Controller out;CHECK(nvme_controller(&c,controller_data,4096,&out)==0);U maximum=128;if(mdts && mdts<4)maximum=8*(UINT64_C(1)<<mdts);
  CHECK(out.ready==1 && out.version==c.version && out.max_sectors==maximum && out.volatile_cache==1);controller_cases++;
 }
 for(unsigned mutation=0;mutation<12;mutation++) {
  defaults();switch(mutation){case 0:controller_data[512]=0x65;break;case 1:controller_data[512]=0x56;break;case 2:controller_data[513]=0x43;break;case 3:controller_data[513]=0x34;break;case 4:put(controller_data+516,0,4);break;case 5:put(controller_data+516,UINT64_C(0xffffffff),4);break;case 6:controller_data[111]=0;break;case 7:controller_data[111]=2;break;case 8:controller_data[525]=0x80;break;case 9:controller_data[525]=2;break;case 10:put(controller_data+80,0,4);break;case 11:put(controller_data+80,0x10300,4);break;}
  Controller before={11,22,33,44},out=before;CHECK(nvme_controller(&caps,controller_data,4096,&out)==UNSUPPORTED);CHECK(memcmp(&out,&before,sizeof out)==0);atomic_rejections++;
 }
 /* NN is the maximum legal NSID, not an active namespace count. We only
  * select NSID1, so other supported IDs do not change encoded requests. */
 const U maximum_ids[]={1,2,256,65535,UINT64_C(0x80000000),UINT64_C(0xfffffffe)};
 for(unsigned n=0;n<sizeof maximum_ids/sizeof *maximum_ids;n++) {
  defaults();put(controller_data+516,maximum_ids[n],4);Controller got;
  CHECK(nvme_controller(&caps,controller_data,4096,&got)==0);
  CHECK(got.ready==1&&got.version==caps.version&&got.max_sectors==128&&got.volatile_cache==1);controller_cases++;
 }
 defaults();Controller ctrl;CHECK(nvme_controller(&caps,controller_data,4096,&ctrl)==0);
 for(unsigned count=0;count<16;count++)for(unsigned format=0;format<=count;format++)for(unsigned rp=0;rp<4;rp++) {
  defaults();namespace_data[25]=(uint8_t)count;namespace_data[26]=(uint8_t)format;put(namespace_data+128+format*4,0x90000|((U)rp<<24),4);Namespace out;
  CHECK(nvme_namespace(&ctrl,namespace_data,4096,&out)==0);CHECK(out.ready==1 && out.capacity_sectors==ns.capacity_sectors && out.max_sectors==128 && out.readonly==0);namespace_cases++;
 }
 for(unsigned mutation=0;mutation<17;mutation++) {
  defaults();switch(mutation){case 0:put(namespace_data,0,8);break;case 1:put(namespace_data+8,ns.capacity_sectors-1,8);break;case 2:put(namespace_data+16,ns.capacity_sectors+1,8);break;case 3:namespace_data[24]=1;break;case 4:namespace_data[25]=16;break;case 5:namespace_data[26]=1;break;case 6:namespace_data[26]=0x10;break;case 7:namespace_data[26]=0x20;break;case 8:namespace_data[29]=1;break;case 9:namespace_data[30]=1;break;case 10:namespace_data[99]=2;break;case 11:put(namespace_data+128,0xc0000,4);break;case 12:put(namespace_data+128,0x90008,4);break;case 13:put(namespace_data+128,0x4090000,4);break;case 14:put(namespace_data+128,0x80000,4);break;case 15:put(namespace_data+128,0,4);break;case 16:namespace_data[26]=0x80;break;}
  Namespace before={11,22,33,44},out=before;CHECK(nvme_namespace(&ctrl,namespace_data,4096,&out)==UNSUPPORTED);CHECK(memcmp(&out,&before,sizeof out)==0);atomic_rejections++;
 }
 /* Every feature byte and write protection combination. NSFEAT DAE
  * capability and all four OPTPERF advisory values may be ignored without
  * changing Read/Write command bytes. Other feature bits remain unsupported. */
 for(unsigned feature=0;feature<256;feature++)for(unsigned readonly=0;readonly<2;readonly++) {
  defaults();namespace_data[24]=(uint8_t)feature;namespace_data[99]=(uint8_t)readonly;
  Namespace before={11,22,33,44},got=before;
  U code=nvme_namespace(&ctrl,namespace_data,4096,&got);
  if(feature&0xcb) {CHECK(code==UNSUPPORTED);CHECK(!memcmp(&got,&before,sizeof got));atomic_rejections++;}
  else {
   CHECK(code==0&&got.ready==1&&got.capacity_sectors==ns.capacity_sectors&&got.max_sectors==128&&got.readonly==readonly);
   Queue q=initialized(1,2,0x100000);Request request={RD,7,2,0};Plan actual,expected=reference(&q,&request,9);
   CHECK(nvme_encode(&q,&got,&request,9,&actual)==0);compare_plan(&actual,&expected);
   request.kind=WR;memset(&actual,0xa5,sizeof actual);Plan saved=actual;
   if(readonly) {CHECK(nvme_encode(&q,&got,&request,9,&actual)==UNSUPPORTED);CHECK(!memcmp(&actual,&saved,sizeof actual));}
   else {expected=reference(&q,&request,9);CHECK(nvme_encode(&q,&got,&request,9,&actual)==0);compare_plan(&actual,&expected);}
   namespace_cases++;
  }
 }
 defaults();namespace_data[99]=1;Namespace out;CHECK(nvme_namespace(&ctrl,namespace_data,4096,&out)==0 && out.readonly==1);
}
static void test_commands_prps_and_bounds(void) {
 defaults();Queue admin=initialized(0,64,0x100000),io=initialized(1,64,0x100000);U kinds[]={ID_CTRL,ID_NS,CREATE_CQ,CREATE_SQ,SET_QUEUES,FLUSH};
 for(unsigned i=0;i<sizeof kinds/sizeof kinds[0];i++)for(U cid=1;cid<65535;cid+=65533){Request r={kinds[i],0,0,0};Queue *q=r.kind==FLUSH?&io:&admin;GuardedPlan actual=output();Queue before=*q;CHECK(nvme_encode(q,&ns,&r,cid,&actual.p)==0);Plan expected=reference(q,&r,cid);compare_plan(&actual.p,&expected);guards(&actual);CHECK(memcmp(q,&before,sizeof *q)==0);}
 for(U sectors=1;sectors<=128;sectors++)for(U offset=0;offset<=4092;offset+=4)for(U kind=RD;kind<=WR;kind++) {
  Request r={kind,UINT64_C(0xe123456700000001)+sectors,sectors,offset};GuardedPlan actual=output();CHECK(nvme_encode(&io,&ns,&r,65534,&actual.p)==0);Plan expected=reference(&io,&r,65534);compare_plan(&actual.p,&expected);guards(&actual);
  CHECK(actual.p.data_physical>=io.lease_physical+0x6000 && actual.p.data_physical+actual.p.bytes<=io.lease_physical+131072);
  if(actual.p.list_entries)for(U n=0;n<actual.p.list_entries;n++)CHECK((actual.p.prps[n]&4095)==0 && actual.p.prps[n]>=io.lease_physical+0x6000 && actual.p.prps[n]<io.lease_physical+131072);
 }
 for(U bits=36;bits<=52;bits++) {
  Caps c=caps;c.physical_bits=bits;Setup s={1,2,1,(UINT64_C(1)<<bits)-131072,131072};Queue q={0};CHECK(nvme_initialize(&q,&c,&s)==0);Request r={RD,0,128,4092};GuardedPlan g=output();CHECK(nvme_encode(&q,&ns,&r,1,&g.p)==0);Plan e=reference(&q,&r,1);compare_plan(&g.p,&e);guards(&g);
  q=(Queue){0};s.lease_physical+=4096;Queue saved=q;CHECK(nvme_initialize(&q,&c,&s)==INVALID);CHECK(memcmp(&q,&saved,sizeof q)==0);atomic_rejections++;
 }
 Request r={RD,0,1,0};REJECT_ENCODE(INVALID,io,r,0);REJECT_ENCODE(INVALID,io,r,65535);r.sectors=0;REJECT_ENCODE(INVALID,io,r,1);r.sectors=129;REJECT_ENCODE(INVALID,io,r,1);
 r=(Request){RD,ns.capacity_sectors-1,2,0};REJECT_ENCODE(INVALID,io,r,1);r.lba=ns.capacity_sectors;REJECT_ENCODE(INVALID,io,r,1);
 r=(Request){RD,0,1,4096};REJECT_ENCODE(INVALID,io,r,1);r.data_offset=3;REJECT_ENCODE(INVALID,io,r,1);
 r=(Request){WR,0,1,0};ns.readonly=1;REJECT_ENCODE(UNSUPPORTED,io,r,1);ns.readonly=0;ns.max_sectors=16;r.sectors=17;REJECT_ENCODE(INVALID,io,r,1);ns.max_sectors=128;
 r=(Request){FLUSH,1,0,0};REJECT_ENCODE(INVALID,io,r,1);r=(Request){ID_CTRL,0,0,0};REJECT_ENCODE(UNSUPPORTED,io,r,1);r=(Request){RD,0,1,0};REJECT_ENCODE(UNSUPPORTED,admin,r,1);
 for(unsigned mutation=0;mutation<7;mutation++){Queue q={0},saved=q;Setup s={1,2,1,0x100000,131072};switch(mutation){case 0:s.qid=2;break;case 1:s.depth=1;break;case 2:s.depth=65;break;case 3:s.epoch=0;break;case 4:s.lease_physical=0;break;case 5:s.lease_physical=1;break;case 6:s.lease_bytes=69632;break;}CHECK(nvme_initialize(&q,&caps,&s)!=0);CHECK(memcmp(&q,&saved,sizeof q)==0);atomic_rejections++;}
}
static void cq_entry(uint8_t cqe[16],U cid,U qid,U head,U phase,U result) {memset(cqe,0,16);put(cqe,result,4);put(cqe+8,head,2);put(cqe+10,qid,2);put(cqe+12,cid,2);put(cqe+14,phase,2);}
static void test_queue_wrap_and_cid_lifetime(void) {
 defaults();
 for(U depth=2;depth<=64;depth++) {
  Queue q=initialized(depth%2,depth,0x100000);U total=depth==2?65534:depth*5;
  for(U index=0;index<total;index++) {
   U before_tail=index%depth,before_head=index%depth,phase=1^((index/depth)&1);Request r={q.qid==0?ID_CTRL:RD,0,q.qid==0?0:1,0};
   GuardedPlan actual=output();Plan expected=reference(&q,&r,index+1);expected.generation=index+1;
   CHECK(q.sq_tail==before_tail && q.cq_head==before_head && q.phase==phase && q.next_cid==index);
   CHECK(nvme_submit(&q,&ns,&r,index*3+100,5000,&actual.p)==0);compare_plan(&actual.p,&expected);guards(&actual);
   CHECK(q.pending==1 && q.held==1 && q.pending_cid==index+1 && q.pending_generation==index+1 && q.sq_tail==(index+1)%depth);
   uint8_t cqe[16];Completion receipt;memset(&receipt,0xa5,sizeof receipt);Completion untouched=receipt;U done=19;
   cq_entry(cqe,index+1,q.qid,(index+1)%depth,phase^1,0);
   CHECK(nvme_poll(&q,q.epoch,index+1,cqe,16,index*3+101,&receipt,&done)==0);CHECK(done==0);CHECK(memcmp(&receipt,&untouched,sizeof receipt)==0);
   cq_entry(cqe,index+1,q.qid,(index+1)%depth,phase,0);done=19;
   CHECK(nvme_poll(&q,q.epoch,index+1,cqe,16,index*3+102,&receipt,&done)==0);CHECK(done==1);
   CHECK(receipt.cid==index+1 && receipt.generation==index+1 && receipt.bytes==(q.qid==0?4096:512) && receipt.cq_head==(index+1)%depth && receipt.phase==(1^(((index+1)/depth)&1)));
   CHECK(q.pending==0 && q.pending_cid==0 && q.pending_generation==0 && q.cq_head==(index+1)%depth && q.phase==receipt.phase && q.held==1 && q.fault==0);queue_completions++;
  }
  if(depth==2){GuardedPlan out=output(),before=out;Queue saved=q;Request r={ID_CTRL,0,0,0};CHECK(nvme_submit(&q,&ns,&r,UINT64_C(1000000),1000,&out.p)==EXHAUSTED);CHECK(memcmp(&q,&saved,sizeof q)==0 && memcmp(&out,&before,sizeof out)==0);atomic_rejections++;}
 }
}
static void test_faults_stale_and_atomic_outputs(void) {
 defaults();Request r={RD,0,128,4092};
 for(unsigned mutation=0;mutation<21;mutation++) {
  Queue q=initialized(1,8,0x100000);Plan plan;CHECK(nvme_submit(&q,&ns,&r,100,5000,&plan)==0);
  uint8_t cqe[16];cq_entry(cqe,plan.cid,1,q.sq_tail,q.phase,0);U now=101,epoch=q.epoch,generation=plan.generation,len=16;U expected=BAD;
  if(mutation<16)cqe[mutation]^=mutation==14?2:1;
  else if(mutation==16){now=5100;expected=TIMEOUT;}else if(mutation==17){now=99;expected=CLOCK;}else if(mutation==18){epoch++;expected=STALE;}else if(mutation==19){generation++;expected=STALE;}else {len=15;expected=INVALID;}
  Completion out;memset(&out,0xa5,sizeof out);Completion before=out;U done=55;Queue saved=q;
  CHECK(nvme_poll(&q,epoch,generation,cqe,len,now,&out,&done)==expected);CHECK(done==55 && memcmp(&out,&before,sizeof out)==0);
  if(expected==BAD || expected==TIMEOUT || expected==CLOCK){saved.fault=expected;CHECK(memcmp(&q,&saved,sizeof q)==0 && q.pending==1 && q.held==1);CHECK(nvme_submit(&q,&ns,&r,6000,5000,&plan)==FAULTED);CHECK(nvme_poll(&q,q.epoch,q.pending_generation,cqe,16,6001,&out,&done)==FAULTED);}
  else {CHECK(memcmp(&q,&saved,sizeof q)==0);atomic_rejections++;}
 }
 Queue q=initialized(0,2,0x100000);Request sq={SET_QUEUES,0,0,0};Plan plan;CHECK(nvme_submit(&q,&ns,&sq,0,5000,&plan)==0);uint8_t cqe[16];cq_entry(cqe,1,0,1,1,0x12345678);Completion out;U done=55;
 CHECK(nvme_poll(&q,q.epoch,1,cqe,16,1,&out,&done)==0 && done==1 && out.result==0x12345678);
 q=initialized(1,2,0x100000);Request read={RD,0,1,0};CHECK(nvme_submit(&q,&ns,&read,0,5000,&plan)==0);Queue saved=q;GuardedPlan p=output(),before=p;
 CHECK(nvme_submit(&q,&ns,&read,1,5000,&p.p)==BUSY && memcmp(&q,&saved,sizeof q)==0 && memcmp(&p,&before,sizeof p)==0);atomic_rejections++;
 CHECK(nvme_poison(&q,0x12345678)==0 && q.fault==0x12345678 && q.held==1 && q.pending==1);CHECK(nvme_poison(&q,1)==FAULTED);
 q=initialized(1,2,0x100000);saved=q;CHECK(nvme_poison(&q,0)==INVALID && memcmp(&q,&saved,sizeof q)==0);atomic_rejections++;
}
int main(void) {
 U sizes[9]={0},expected[9]={sizeof(Caps),sizeof(Limits),sizeof(Controller),sizeof(Namespace),sizeof(Setup),sizeof(Request),sizeof(Plan),sizeof(Queue),sizeof(Completion)};nvme_sizes(sizes);CHECK(memcmp(sizes,expected,sizeof sizes)==0);
 test_limits_and_identify();test_commands_prps_and_bounds();test_queue_wrap_and_cid_lifetime();test_faults_stale_and_atomic_outputs();
 printf("NVME_MODEL_OK assertions=%" PRIu64 " full-byte-plans=%" PRIu64 " controllers=%" PRIu64 " namespaces=%" PRIu64 " queue-completions=%" PRIu64 " atomic-rejections=%" PRIu64 " data-offsets=1024 counts=128 held=permanent hardware-executed=false\n",assertions,plans,controller_cases,namespace_cases,queue_completions,atomic_rejections);return 0;
}
