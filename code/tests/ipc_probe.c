#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
typedef struct{uint64_t generation,kind,object,rights,live;} Entry;
typedef struct{uint64_t ready,used;Entry e[32];} Table;
typedef struct{uint64_t kind,object,rights;} View;
typedef struct{uint64_t peer,length;uint8_t bytes[64];} Message;
typedef struct{uint64_t initialized,live,identity,owner,queued,sequence,state,caller,token;Message request,response,messages[4];} Endpoint;
typedef struct{uint64_t initialized,live,bits;} Notification;
typedef struct{uint64_t initialized,live,identity,base,size,rights;} Memory;
typedef struct{uint64_t address,length,rights;} Region;
extern uint64_t SYSV ip_table_size(void),ip_endpoint_size(void),ip_init(Table*),ip_close(Table*,uint64_t);
extern uint64_t SYSV ip_install(Table*,uint64_t,uint64_t,uint64_t,uint64_t*),ip_lookup(const Table*,uint64_t,uint64_t,uint64_t,View*);
extern uint64_t SYSV ip_duplicate(const Table*,Table*,uint64_t,uint64_t,uint64_t*),ip_transfer(Table*,Table*,uint64_t,uint64_t,uint64_t*);
extern uint64_t SYSV ip_endpoint_init(Endpoint*,uint64_t,uint64_t),ip_send(Endpoint*,uint64_t,const uint8_t*,uint64_t),ip_receive(Endpoint*,uint64_t,Message*);
extern uint64_t SYSV ip_call(Endpoint*,uint64_t,const uint8_t*,uint64_t,uint64_t*),ip_accept(Endpoint*,uint64_t,Message*,uint64_t*);
extern uint64_t SYSV ip_reply(Endpoint*,uint64_t,uint64_t,const uint8_t*,uint64_t),ip_take_reply(Endpoint*,uint64_t,uint64_t,Message*);
extern uint64_t SYSV ip_cancel(Endpoint*,uint64_t,uint64_t),ip_detach(Endpoint*,uint64_t);
extern uint64_t SYSV ip_notification_init(Notification*),ip_signal(Notification*,uint64_t),ip_take_bits(Notification*,uint64_t,uint64_t*),ip_notification_close(Notification*);
extern uint64_t SYSV ip_memory_init(Memory*,uint64_t,uint64_t,uint64_t,uint64_t),ip_shared_view(const Table*,uint64_t,const Memory*,uint64_t,uint64_t,uint64_t,Region*),ip_memory_close(Memory*);
void SYSV __dong_panic(uint64_t code,const char*s,uint64_t n){(void)s;(void)n;fprintf(stderr,"IPC unexpected panic %x\n",(unsigned)code);exit(9);}
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"IPC check failed line %u\n",__LINE__);return 1;}}while(0)
#define HARG 0x04010001ULL
#define HINVALID 0x04010002ULL
#define HDENIED 0x04010003ULL
#define FULL 0x04010004ULL
#define ARG 0x04020001ULL
#define CLOSED 0x04020002ULL
#define BLOCK 0x04020003ULL
#define DENIED 0x04020004ULL
#define TOKEN 0x04020005ULL
static uint64_t rng=0x6ba931902eb5d478ULL;
static uint64_t random64(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static int handles(void){
 struct{uint64_t lo;Table t;uint64_t hi;} a={0},b={0};Table saved,other;View view,before_view;uint64_t token=0,out=0,old;
 a.lo=b.lo=0x1122334455667788ULL;a.hi=b.hi=0x8877665544332211ULL;
 CHECK(ip_table_size()==sizeof(Table)&&ip_init(&a.t)==0&&ip_init(&b.t)==0);
 CHECK(ip_install(&a.t,3,42,1|2|4|128,&token)==0&&token==257&&a.t.used==1);
 memset(&view,0xa5,sizeof view);before_view=view;saved=a.t;
 CHECK(ip_lookup(&a.t,token,3,256,&view)==HDENIED&&!memcmp(&view,&before_view,sizeof view)&&!memcmp(&saved,&a.t,sizeof saved));
 CHECK(ip_lookup(&a.t,token,3,3,&view)==0&&view.object==42&&view.rights==135);
 CHECK(ip_duplicate(&a.t,&b.t,token,1|128,&out)==0&&b.t.used==1&&a.t.used==1);
 saved=a.t;other=b.t;old=out;
 CHECK(ip_duplicate(&b.t,&a.t,out,1,&out)==HDENIED&&out==old&&!memcmp(&saved,&a.t,sizeof saved)&&!memcmp(&other,&b.t,sizeof other));
 CHECK(ip_duplicate(&a.t,&b.t,token,1|16,&out)==HDENIED);
 CHECK(ip_transfer(&a.t,&b.t,token,1,&out)==0&&a.t.used==0&&b.t.used==2);
 CHECK(ip_lookup(&a.t,token,3,1,&view)==HINVALID);CHECK(ip_close(&a.t,token)==HINVALID);
 CHECK(ip_install(&a.t,3,43,1|4|128,&out)==0&&out==513);CHECK(ip_close(&a.t,out)==0);
 /* Independent reference is three flat arrays, not the production Table. */
 uint64_t generation[32],rights[32],object[32];unsigned live[32];
 CHECK(ip_init(&a.t)==0x04010005ULL);memset(&a.t,0,sizeof a.t);CHECK(ip_init(&a.t)==0);
 for(unsigned i=0;i<32;i++){generation[i]=1;rights[i]=object[i]=live[i]=0;}
 for(unsigned i=0;i<2048;i++){
   unsigned j=(unsigned)(random64()%32);
   if(live[j]){uint64_t h=(generation[j]<<8)|(j+1);CHECK(ip_close(&a.t,h)==0);live[j]=0;generation[j]++;rights[j]=object[j]=0;CHECK(ip_lookup(&a.t,h,3,0,&view)==HINVALID);}
   else{unsigned free_slot=0;while(free_slot<32&&live[free_slot])free_slot++;
     uint64_t r=1|(random64()&2)|4|128,o=1000+i;
     CHECK(ip_install(&a.t,3,o,r,&out)==0);CHECK(out==((generation[free_slot]<<8)|(free_slot+1)));
     live[free_slot]=1;rights[free_slot]=r;object[free_slot]=o;
   }
   unsigned count=0;
   for(unsigned k=0;k<32;k++){count+=live[k];CHECK(a.t.e[k].generation==generation[k]&&a.t.e[k].live==live[k]);if(live[k])CHECK(a.t.e[k].rights==rights[k]&&a.t.e[k].object==object[k]&&a.t.e[k].kind==3);}
   CHECK(a.t.used==count);
 }
 while(a.t.used<32)CHECK(ip_install(&a.t,3,99,1|4,&out)==0);
 saved=a.t;other=b.t;old=out;CHECK(ip_install(&a.t,3,99,1,&out)==FULL&&out==old&&!memcmp(&saved,&a.t,sizeof saved));
 uint64_t source=0;CHECK(ip_install(&b.t,3,88,5,&source)==0);other=b.t;
 CHECK(ip_transfer(&b.t,&a.t,source,1,&out)==FULL&&!memcmp(&saved,&a.t,sizeof saved)&&!memcmp(&other,&b.t,sizeof other));
 /* A nearly exhausted slot is retired rather than wrapping into an old token. */
 CHECK(ip_close(&a.t,(a.t.e[0].generation<<8)|1)==0);a.t.e[0].generation=0x00fffffffffffffeULL;
 CHECK(ip_install(&a.t,3,99,5,&out)==0);CHECK(ip_close(&a.t,out)==0);saved=a.t;
 CHECK(ip_install(&a.t,3,99,1,&out)==FULL&&!memcmp(&saved,&a.t,sizeof saved));
 CHECK(a.lo==0x1122334455667788ULL&&a.hi==0x8877665544332211ULL&&b.lo==a.lo&&b.hi==a.hi);
 return 0;
}
static int messages(void){
 struct{uint64_t lo;Endpoint e;uint64_t hi;} box={0};Endpoint saved;struct{uint64_t lo;Message m;uint64_t hi;} out;
 uint8_t payload[65],snapshot[65];uint64_t ticket=0,reply_token=0;
 for(unsigned i=0;i<65;i++){payload[i]=(uint8_t)(i*3+7);}
 memcpy(snapshot,payload,sizeof payload);
 box.lo=0x123456789abcdef0ULL;box.hi=~box.lo;out.lo=box.lo;out.hi=box.hi;
 CHECK(ip_endpoint_size()==sizeof(Endpoint)&&ip_endpoint_init(&box.e,7,100)==0);
 memset(&out.m,0xa5,sizeof out.m);Message previous=out.m;saved=box.e;
 CHECK(ip_receive(&box.e,100,&out.m)==BLOCK&&!memcmp(&previous,&out.m,sizeof previous)&&!memcmp(&saved,&box.e,sizeof saved));
 CHECK(ip_send(&box.e,1,payload,65)==ARG&&!memcmp(&saved,&box.e,sizeof saved));
 for(unsigned i=0;i<4;i++)CHECK(ip_send(&box.e,i+1,payload,i==3?64:i)==0);
 saved=box.e;CHECK(ip_send(&box.e,5,payload,1)==BLOCK&&!memcmp(&saved,&box.e,sizeof saved));
 CHECK(ip_receive(&box.e,99,&out.m)==DENIED&&!memcmp(&saved,&box.e,sizeof saved));
 for(unsigned i=0;i<4;i++){unsigned len=i==3?64:i;CHECK(ip_receive(&box.e,100,&out.m)==0&&out.m.peer==i+1&&out.m.length==len);for(unsigned j=0;j<64;j++)CHECK(out.m.bytes[j]==(j<len?payload[j]:0));}
 CHECK(ip_call(&box.e,1,payload,64,&ticket)==0&&ticket==0x700000001ULL);
 saved=box.e;CHECK(ip_call(&box.e,2,payload,1,&reply_token)==BLOCK&&reply_token==0&&!memcmp(&saved,&box.e,sizeof saved));
 previous=out.m;CHECK(ip_take_reply(&box.e,1,ticket,&out.m)==BLOCK&&!memcmp(&previous,&out.m,sizeof previous));
 CHECK(ip_accept(&box.e,99,&out.m,&reply_token)==DENIED);
 CHECK(ip_accept(&box.e,100,&out.m,&reply_token)==0&&reply_token==ticket&&out.m.peer==1&&out.m.length==64&&!memcmp(out.m.bytes,payload,64));
 saved=box.e;CHECK(ip_reply(&box.e,100,ticket+1,payload,3)==TOKEN&&!memcmp(&saved,&box.e,sizeof saved));
 CHECK(ip_reply(&box.e,101,ticket,payload,3)==DENIED&&!memcmp(&saved,&box.e,sizeof saved));
 CHECK(ip_reply(&box.e,100,ticket,payload,3)==0);
 CHECK(ip_take_reply(&box.e,2,ticket,&out.m)==DENIED);
 CHECK(ip_take_reply(&box.e,1,ticket,&out.m)==0&&out.m.peer==100&&out.m.length==3);
 for(unsigned i=0;i<64;i++)CHECK(out.m.bytes[i]==(i<3?payload[i]:0));
 CHECK(ip_reply(&box.e,100,ticket,payload,3)==TOKEN);
 for(unsigned state=0;state<3;state++){
   CHECK(ip_call(&box.e,1,payload,8,&ticket)==0);
   if(state)CHECK(ip_accept(&box.e,100,&out.m,&reply_token)==0);
   if(state==2)CHECK(ip_reply(&box.e,100,ticket,payload,2)==0);
   CHECK(ip_cancel(&box.e,1,ticket)==0);saved=box.e;
   CHECK(ip_reply(&box.e,100,ticket,payload,2)==TOKEN&&!memcmp(&saved,&box.e,sizeof saved));
 }
 CHECK(ip_send(&box.e,1,payload,4)==0&&ip_send(&box.e,2,payload,5)==0&&ip_send(&box.e,1,payload,6)==0);
 CHECK(ip_call(&box.e,1,payload,1,&ticket)==0&&ip_accept(&box.e,100,&out.m,&reply_token)==0);
 CHECK(ip_detach(&box.e,1)==0&&box.e.queued==1&&box.e.messages[0].peer==2&&box.e.state==0);
 CHECK(ip_reply(&box.e,100,ticket,payload,1)==TOKEN);
 CHECK(ip_call(&box.e,2,payload,1,&ticket)==0&&ip_detach(&box.e,100)==0&&box.e.live==0&&box.e.queued==0);
 saved=box.e;CHECK(ip_send(&box.e,1,payload,1)==CLOSED&&!memcmp(&saved,&box.e,sizeof saved));
 CHECK(ip_endpoint_init(&box.e,7,100)==0x04020006ULL&&!memcmp(&saved,&box.e,sizeof saved));
 CHECK(box.lo==0x123456789abcdef0ULL&&box.hi==~box.lo&&out.lo==box.lo&&out.hi==box.hi&&!memcmp(snapshot,payload,sizeof payload));
 return 0;
}
static int notifications_and_memory(void){
 Notification n={0},ns;uint64_t out=0xabcdef;
 CHECK(ip_notification_init(&n)==0&&ip_signal(&n,0x8000000000000005ULL)==0&&ip_signal(&n,2)==0);
 CHECK(ip_take_bits(&n,3,&out)==0&&out==3&&n.bits==0x8000000000000004ULL);
 ns=n;out=0xabcdef;CHECK(ip_take_bits(&n,2,&out)==BLOCK&&out==0xabcdef&&!memcmp(&ns,&n,sizeof n));
 CHECK(ip_take_bits(&n,UINT64_MAX,&out)==0&&out==0x8000000000000004ULL&&n.bits==0);
 CHECK(ip_notification_close(&n)==0&&ip_signal(&n,1)==CLOSED);
 Table t={0};Memory m={0},wrong={0},ms;struct{uint64_t lo;Region r;uint64_t hi;} region={0};uint64_t rw,ro;
 region.lo=0xa5a5a5a5a5a5a5a5ULL;region.hi=~region.lo;
 CHECK(ip_init(&t)==0&&ip_memory_init(&m,9,0x40000000,4096,3)==0&&ip_memory_init(&wrong,10,0x40000000,4096,3)==0);
 CHECK(ip_install(&t,3,9,1|2|4|128,&rw)==0&&ip_duplicate(&t,&t,rw,1|128,&ro)==0);
 CHECK(ip_shared_view(&t,rw,&m,0,4096,3,&region.r)==0&&region.r.address==0x40000000&&region.r.length==4096&&region.r.rights==3);
 Region prev=region.r;CHECK(ip_shared_view(&t,ro,&m,0,1,2,&region.r)==HDENIED&&!memcmp(&prev,&region.r,sizeof prev));
 CHECK(ip_shared_view(&t,rw,&wrong,0,1,1,&region.r)==DENIED&&!memcmp(&prev,&region.r,sizeof prev));
 const uint64_t off[]={4096,4097,UINT64_MAX,4095},len[]={1,1,2,2};
 for(unsigned i=0;i<4;i++)CHECK(ip_shared_view(&t,rw,&m,off[i],len[i],1,&region.r)==ARG&&!memcmp(&prev,&region.r,sizeof prev));
 CHECK(ip_shared_view(&t,ro,&m,4095,1,1,&region.r)==0&&region.r.address==0x40000fff);
 CHECK(ip_memory_close(&m)==0);prev=region.r;CHECK(ip_shared_view(&t,rw,&m,0,1,1,&region.r)==CLOSED&&!memcmp(&prev,&region.r,sizeof prev));
 memset(&m,0,sizeof m);ms=m;CHECK(ip_memory_init(&m,1,UINT64_MAX-8,16,1)==ARG&&!memcmp(&ms,&m,sizeof m));
 CHECK(ip_memory_init(&m,1,0x7ffffffff000ULL,8192,1)==ARG&&!memcmp(&ms,&m,sizeof m));
 CHECK(region.lo==0xa5a5a5a5a5a5a5a5ULL&&region.hi==~region.lo);
 return 0;
}
static int device_authority(void) {
 const uint64_t allowed[]={3,131,131,3,24}; /* config,MMIO,DMA,console,IRQ */
 for(unsigned kind=4;kind<=8;kind++)for(unsigned rights=1;rights<256;rights++) {
   Table table={0},before;View view={0};uint64_t token=0xabcdef;
   CHECK(ip_init(&table)==0);before=table;
   uint64_t status=ip_install(&table,kind,123,rights,&token);
   if((rights&~allowed[kind-4])!=0) {
     CHECK(status==UINT64_C(0x04010001)&&token==0xabcdef&&!memcmp(&before,&table,sizeof table));
   } else {
     CHECK(status==0&&table.used==1);
     CHECK(ip_lookup(&table,token,kind,rights,&view)==0&&view.kind==kind&&view.object==123&&view.rights==rights);
     for(unsigned other=1;other<=8;other++)if(other!=kind)CHECK(ip_lookup(&table,token,other,1,&view)==HDENIED);
     CHECK(ip_close(&table,token)==0&&ip_lookup(&table,token,kind,1,&view)==HINVALID);
   }
 }
 return 0;
}
int main(void){if(handles()||messages()||notifications_and_memory()||device_authority())return 1;printf("IPC native checks passed %u\n",checks);return 0;}
