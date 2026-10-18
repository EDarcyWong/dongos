/* Independent split-ring device. CPU VA is deliberately unrelated to bus PA. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { checks++;if(!(x)){fprintf(stderr,"TABLET_MODEL_ASSERT line %d: %s\n",__LINE__,#x);exit(1);} }while(0)
#define BYTES 16384u
#define BUS UINT64_C(0x123450000)
#define TOKEN UINT64_C(0xfeed010203040506)
#define ERR_INVALID UINT64_C(0x07330001)
#define ERR_UNSUPPORTED UINT64_C(0x07330002)
#define ERR_COMPLETION UINT64_C(0x07330003)
#define ERR_IO UINT64_C(0x07330004)
typedef struct { uint64_t handle,offset,length,bar; } Area;
typedef struct { Area common,notify,isr,device;uint64_t multiplier; } Transport;
typedef struct { uint64_t token,physical;uint8_t *pointer;size_t length; } Lease;
typedef uint64_t (ABI *Read)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t *);
typedef uint64_t (ABI *Write)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
typedef uint64_t (ABI *Fence)(uint64_t,uint64_t);
typedef uint64_t (ABI *Acquire)(uint64_t,size_t,size_t,Lease *);
typedef uint64_t (ABI *Release)(uint64_t,const Lease *);
typedef struct { Read read;Write write;Fence fence;Acquire acquire;Release release; } Ops;
typedef struct { uint64_t kind,code;int64_t a,b; } Event;
typedef struct { size_t head,count;Event items[64]; } Queue;
typedef struct { uint64_t ready,fault,used,available,notify,completed,token,physical,pointer,length; } Info;
extern ABI void tablet_sizes(uint64_t *),tablet_empty(void *,Queue *),tablet_info(const void *,Info *);
extern ABI uint64_t tablet_initialize(void *,const Transport *,const Ops *,int64_t,int64_t);
extern ABI uint64_t tablet_poll(void *,Queue *),tablet_pop(Queue *,Event *,uint64_t *);
static uint64_t checks;
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected tablet panic %llu\n",(unsigned long long)code);exit(99);}
ABI void tablet_negative_hit(uint64_t kind){static unsigned seen;if(!seen++){fprintf(stderr,"TABLET_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}}
static uint16_t u16(const uint8_t *p){uint16_t v;memcpy(&v,p,2);return v;}
static uint32_t u32(const uint8_t *p){uint32_t v;memcpy(&v,p,4);return v;}
static uint64_t u64(const uint8_t *p){uint64_t v;memcpy(&v,p,8);return v;}
static void w16(uint8_t *p,uint16_t v){memcpy(p,&v,2);}
static void w32(uint8_t *p,uint32_t v){memcpy(p,&v,4);}
static void w64(uint8_t *p,uint64_t v){memcpy(p,&v,8);}
static uint8_t *allocation,*dma,*state_allocation,*state,*before_state,*expected_state;
static size_t state_bytes;
static uint8_t expected_dma[BYTES],saved_dma[BYTES];
static struct { uint64_t pre;Queue queue;uint64_t post; } output;
static Transport transport={ {0x11,128,56,0},{0x22,64,32,1},{0x44,16,1,2},{0x33,32,28,3},4 };
static unsigned scenario,status,feature_select,driver_select,selected,config_select,config_axis,generation;
static unsigned acquired,released,notifications,mmio_calls,fences[4],release_fence_at_enable[2];
static uint64_t accepted[2],desc[2],avail[2],used[2];
static unsigned qsize[2],qenable[2],qvector[2],status_log[16],status_count;
static uint16_t device_avail,device_used,expected_old_avail,expected_new_avail;
static unsigned in_poll,phase,batch;
static unsigned wire_events,polls,frames;
static ABI void guards(void){
 for(unsigned i=0;i<16;i++){CHECK(dma[-16+(int)i]==0xa7&&dma[BYTES+i]==0xa7);CHECK(state[-16+(int)i]==0xb9&&state[state_bytes+i]==0xb9);}
 CHECK(output.pre==UINT64_C(0x1020304050607080)&&output.post==UINT64_C(0x8070605040302010));
 CHECK(released==0);
}
static ABI void queue_image(unsigned q){
 size_t base=(size_t)q*8192;
 CHECK(desc[q]==BUS+base&&avail[q]==BUS+base+1024&&used[q]==BUS+base+2048);
 CHECK(qsize[q]==64&&qvector[q]==65535&&u16(dma+base+1024)==1);
 CHECK(u16(dma+base+2048)==0&&u16(dma+base+2050)==0);
 if(q==0){
  CHECK(u16(dma+1026)==64);
  for(unsigned i=0;i<64;i++){const uint8_t *d=dma+i*16;CHECK(u64(d)==BUS+4096+i*8&&u32(d+8)==8&&u16(d+12)==2&&u16(d+14)==0);CHECK(u16(dma+1028+i*2)==i);}
 }else{for(unsigned i=0;i<1024;i++)CHECK(dma[base+i]==0);CHECK(u16(dma+base+1026)==0);}
}
static ABI uint64_t read_register(uint64_t context,uint64_t handle,uint64_t offset,uint64_t width,uint64_t *out){
 CHECK(context==0);mmio_calls++;*out=0;
 if(handle==0x11){CHECK(offset>=128&&offset+width<=184);unsigned off=(unsigned)(offset-128);
  if(off==4&&width==4){*out=feature_select==1?(scenario==5?0:scenario==6?3:1):0;return 0;}
  if(off==18&&width==2){*out=scenario==7?1:2;return 0;}
  if(off==20&&width==1){*out=status;if(scenario==8&&status==11)*out=3;return 0;}
  if(off==21&&width==1){*out=generation;if(scenario==9&&config_axis==1)(*out)++;return 0;}
  if(off==24&&width==2){*out=qsize[selected];return 0;}
  if(off==28&&width==2){*out=qenable[selected];return 0;}
  if(off==30&&width==2){*out=selected+2;return 0;}
 }else if(handle==0x33){CHECK(offset>=32&&offset+width<=60);unsigned off=(unsigned)(offset-32);
  if(off==2&&width==1){*out=scenario==10?19:20;return 0;}
  if(off==8&&width==4){CHECK(config_select==0x12&&config_axis<2);*out=config_axis==0?(uint32_t)-100:1000;return 0;}
  if(off==12&&width==4){CHECK(config_select==0x12&&config_axis<2);*out=config_axis==0?300:5000;return 0;}
 }
 CHECK(!"unexpected register read");return 1;
}
static ABI uint64_t write_register(uint64_t context,uint64_t handle,uint64_t offset,uint64_t width,uint64_t value){
 CHECK(context==0);mmio_calls++;
 if(handle==0x11){CHECK(offset>=128&&offset+width<=184);unsigned off=(unsigned)(offset-128);
  if(off==0&&width==4){feature_select=(unsigned)value;CHECK(value<=1);return 0;}
  if(off==8&&width==4){driver_select=(unsigned)value;CHECK(value<=1);return 0;}
  if(off==12&&width==4){accepted[driver_select]=value;return 0;}
  if(off==16&&width==2){CHECK(value==65535);return 0;}
  if(off==20&&width==1){CHECK(status_count<16);status_log[status_count++]=(unsigned)value;
   if(value==0){status=0;qenable[0]=qenable[1]=0;}
   else {CHECK((status==0&&value==1)||(status==1&&value==3)||(status==3&&value==11)||(status==11&&value==15));status=(unsigned)value;}
   return 0;
  }
  if(off==22&&width==2){CHECK(value<2);selected=(unsigned)value;return 0;}
  if(off==24&&width==2){CHECK(value==64);qsize[selected]=64;return 0;}
  if(off==26&&width==2){qvector[selected]=(unsigned)value;return 0;}
  if(off==28&&width==2){CHECK(value==1&&status==11&&fences[1]>release_fence_at_enable[selected]);queue_image(selected);qenable[selected]=1;release_fence_at_enable[selected]=fences[1];return 0;}
  if(width==4&&off>=32&&off<=52){unsigned which=(off-32)/8;uint64_t *target=which==0?&desc[selected]:which==1?&avail[selected]:&used[selected];
   if((off&4)==0)*target=(*target&UINT64_C(0xffffffff00000000))|value;else *target=(*target&UINT32_MAX)|(value<<32);return 0;
  }
 }else if(handle==0x33){
  if(offset==32&&width==1){config_select=(unsigned)value;return 0;}
  if(offset==33&&width==1){config_axis=(unsigned)value;return 0;}
 }else if(handle==0x22){
  CHECK(offset==72&&width==2&&value==0&&status==15&&qenable[0]==1&&qenable[1]==1);
  CHECK(accepted[0]==0&&accepted[1]==1);
  if(in_poll){CHECK(phase==3);CHECK(u16(dma+1026)==expected_new_avail);CHECK(memcmp(dma,expected_dma,BYTES)==0);phase=4;}
  else {CHECK(notifications==0);CHECK(memcmp(dma,expected_dma,BYTES)==0);}
  notifications++;guards();return 0;
 }
 CHECK(!"unexpected register write");return 1;
}
static ABI uint64_t barrier(uint64_t context,uint64_t kind){
 CHECK(context==0&&kind>=1&&kind<=3);fences[kind]++;
 if(in_poll){
  if(kind==2){CHECK(phase==0&&u16(dma+1026)==expected_old_avail);phase=1;}
  else if(kind==1){CHECK(phase==1&&u16(dma+1026)==expected_old_avail);w16(expected_dma+1026,expected_old_avail);CHECK(memcmp(dma,expected_dma,BYTES)==0);w16(expected_dma+1026,expected_new_avail);phase=2;}
  else {CHECK(phase==2&&u16(dma+1026)==expected_new_avail);phase=3;}
 }
 return 0;
}
static ABI uint64_t acquire(uint64_t context,size_t bytes,size_t alignment,Lease *out){
 CHECK(context==0&&bytes==BYTES&&alignment==4096&&acquired==0);acquired++;
 memset(dma-16,0xa7,BYTES+32);*out=(Lease){TOKEN,BUS,dma,BYTES};return 0;
}
static ABI uint64_t release(uint64_t context,const Lease *lease){(void)context;(void)lease;released++;CHECK(!"published DMA lease released");return 1;}
static const Ops ops={read_register,write_register,barrier,acquire,release};
static ABI Info info(void){Info v;tablet_info(state,&v);return v;}
static ABI void initial_dma(void){
 memset(expected_dma,0,sizeof expected_dma);
 for(unsigned i=0;i<64;i++){w64(expected_dma+i*16,BUS+4096+i*8);w32(expected_dma+i*16+8,8);w16(expected_dma+i*16+12,2);w16(expected_dma+1028+i*2,(uint16_t)i);}
 w16(expected_dma+1024,1);w16(expected_dma+1026,64);w16(expected_dma+8192+1024,1);
}
static ABI void setup(void){
 uint64_t sizes[5];tablet_sizes(sizes);CHECK(sizes[0]>=224&&sizes[0]<=4096&&sizes[1]==8&&sizes[2]==sizeof(Transport)&&sizes[3]==sizeof(Ops)&&sizes[4]==sizeof(Queue));
 state_bytes=(size_t)sizes[0];state_allocation=malloc(state_bytes+32);before_state=malloc(state_bytes);expected_state=malloc(state_bytes);allocation=malloc(BYTES+8192);CHECK(state_allocation&&before_state&&expected_state&&allocation);
 state=state_allocation+16;dma=(uint8_t *)(((uintptr_t)allocation+4096+15)&~(uintptr_t)4095);CHECK((uintptr_t)dma!=BUS);
 memset(state_allocation,0xb9,state_bytes+32);memset(dma-16,0xa7,BYTES+32);output.pre=UINT64_C(0x1020304050607080);output.post=UINT64_C(0x8070605040302010);
 tablet_empty(state,&output.queue);qsize[0]=qsize[1]=128;if(scenario==11)qsize[1]=32;generation=7;initial_dma();
}
static ABI void initialized(void){
 CHECK(tablet_initialize(state,&transport,&ops,640,480)==0);Info v=info();
 CHECK(v.ready==1&&v.fault==0&&v.used==0&&v.available==64&&v.notify==8&&v.completed==0);
 CHECK(v.token==TOKEN&&v.physical==BUS&&v.pointer==(uint64_t)(uintptr_t)dma&&v.length==BYTES&&acquired==1&&released==0);
 CHECK(status_count==5&&status_log[0]==0&&status_log[1]==1&&status_log[2]==3&&status_log[3]==11&&status_log[4]==15);
 CHECK(notifications==1&&memcmp(dma,expected_dma,BYTES)==0);queue_image(0);queue_image(1);guards();
}
static ABI void device_event(uint16_t kind,uint16_t code,int32_t value){
 uint16_t available=u16(dma+1026);CHECK((uint16_t)(available-device_avail)>0&&(uint16_t)(available-device_avail)<=64);
 uint16_t id=u16(dma+1028+(device_avail%64)*2);CHECK(id<64);const uint8_t *d=dma+id*16;
 CHECK(u64(d)==BUS+4096+id*8&&u32(d+8)==8&&u16(d+12)==2&&u16(d+14)==0);
 size_t payload=(size_t)(u64(d)-BUS);w16(dma+payload,kind);w16(dma+payload+2,code);w32(dma+payload+4,(uint32_t)value);
 size_t entry=2052+(device_used%64)*8;w32(dma+entry,id);w32(dma+entry+4,8);device_used++;device_avail++;w16(dma+2050,device_used);wire_events++;
}
static ABI void prepare_poll(void){
 memcpy(expected_dma,dma,BYTES);Info v=info();expected_old_avail=(uint16_t)v.available;
 batch=(uint16_t)(device_used-(uint16_t)v.used);CHECK(batch<=64);expected_new_avail=(uint16_t)(expected_old_avail+batch);
 for(unsigned i=0;i<batch;i++){uint32_t id=u32(dma+2052+(((uint16_t)v.used+i)%64)*8);CHECK(id<64);w16(expected_dma+1028+((expected_old_avail+i)%64)*2,(uint16_t)id);}
 w16(expected_dma+1026,expected_new_avail);in_poll=1;phase=0;
}
static ABI void good_poll(void){
 Info old=info();prepare_poll();unsigned prior=notifications;CHECK(tablet_poll(state,&output.queue)==0);polls++;
 CHECK(phase==(batch?4u:0u)&&notifications==prior+(batch!=0));in_poll=0;Info v=info();
 CHECK(v.ready==1&&v.fault==0&&v.used==device_used&&v.available==expected_new_avail&&v.completed==old.completed+batch);
 CHECK(memcmp(dma,expected_dma,BYTES)==0);guards();
}
static ABI Event pop(void){Event e={99,99,99,99};uint64_t present=0;CHECK(tablet_pop(&output.queue,&e,&present)==0&&present==1);return e;}
static ABI void empty_output(void){Event e={99,99,99,99},old=e;uint64_t present=99;CHECK(tablet_pop(&output.queue,&e,&present)==0&&present==0&&memcmp(&e,&old,sizeof e)==0);}
static ABI void normal(void){
 initialized();good_poll();device_event(3,0,100);device_event(3,1,3000);device_event(1,272,1);good_poll();empty_output();
 device_event(0,0,0);good_poll();Event e=pop();CHECK(e.kind==3&&e.code==0&&e.a==319&&e.b==239);e=pop();CHECK(e.kind==1&&e.code==272&&e.a==1&&e.b==0);empty_output();frames++;
 device_event(3,0,INT32_MAX);device_event(3,1,INT32_MIN);device_event(1,272,0);device_event(0,0,0);good_poll();
 e=pop();CHECK(e.kind==3&&e.a==639&&e.b==0);e=pop();CHECK(e.kind==1&&e.code==272&&e.a==0);empty_output();frames++;
 device_event(3,0,-100);device_event(3,1,5000);device_event(0,0,0);good_poll();e=pop();CHECK(e.kind==3&&e.a==0&&e.b==479);empty_output();frames++;
 device_event(3,0,300);device_event(0,0,0);good_poll();e=pop();CHECK(e.kind==3&&e.a==639&&e.b==479);empty_output();frames++;
 unsigned calls=mmio_calls;memcpy(before_state,state,state_bytes);memcpy(saved_dma,dma,BYTES);CHECK(tablet_initialize(state,&transport,&ops,640,480)==ERR_INVALID);CHECK(mmio_calls==calls&&memcmp(before_state,state,state_bytes)==0&&memcmp(saved_dma,dma,BYTES)==0);guards();
 printf("tablet model passed: wire=%u polls=%u frames=%u real DMA queues=2 full-byte-guards=ok checks=%llu\n",wire_events,polls,frames,(unsigned long long)checks);
}
static ABI void failed_poll(uint64_t expected){
 Info old=info();Queue q=output.queue;memcpy(before_state,state,state_bytes);memcpy(saved_dma,dma,BYTES);unsigned prior=notifications;
 CHECK(tablet_poll(state,&output.queue)==expected);Info v=info();
 CHECK(v.ready==0&&v.fault==1&&v.used==old.used&&v.available==old.available&&v.completed==old.completed);
 CHECK(v.token==TOKEN&&v.physical==BUS&&v.pointer==(uint64_t)(uintptr_t)dma&&v.length==BYTES&&acquired==1&&released==0);
 CHECK(memcmp(&output.queue,&q,sizeof q)==0&&memcmp(dma,saved_dma,BYTES)==0&&notifications==prior);
 /* Only the documented ready/fault words may change on rejected completion. */
 memcpy(expected_state,before_state,state_bytes);uint64_t zero=0,one=1;memcpy(expected_state+176,&zero,8);memcpy(expected_state+184,&one,8);CHECK(memcmp(state,expected_state,state_bytes)==0);
 unsigned calls=mmio_calls;CHECK(tablet_poll(state,&output.queue)==ERR_INVALID&&mmio_calls==calls);CHECK(tablet_initialize(state,&transport,&ops,640,480)==ERR_INVALID&&mmio_calls==calls);guards();
 printf("tablet malformed completion/reset safely retained DMA: scenario=%u checks=%llu\n",scenario,(unsigned long long)checks);
}
static ABI void malformed(void){
 initialized();
 if(scenario==1){device_event(1,272,1);device_event(0,0,0);w32(dma+2060,u32(dma+2052));}
 if(scenario==2){device_event(1,272,1);device_event(0,0,0);w32(dma+2060,64);}
 if(scenario==3){device_event(1,272,1);device_event(0,0,0);w32(dma+2064,7);}
 if(scenario==4){w16(dma+2050,65);device_used=65;}
 if(scenario==12){status=3;failed_poll(ERR_IO);return;}
 failed_poll(ERR_COMPLETION);
}
static ABI void init_failure(void){
 uint64_t expected=scenario==9?ERR_IO:ERR_UNSUPPORTED;
 CHECK(tablet_initialize(state,&transport,&ops,640,480)==expected);Info v=info();CHECK(v.ready==0&&v.fault==1&&released==0&&notifications==0);
 if(scenario==11){CHECK(acquired==1&&v.token==TOKEN&&v.physical==BUS&&v.pointer==(uint64_t)(uintptr_t)dma&&v.length==BYTES&&qenable[0]==1&&qenable[1]==0);}
 else CHECK(acquired==0&&v.token==0);
 memcpy(before_state,state,state_bytes);unsigned calls=mmio_calls;CHECK(tablet_initialize(state,&transport,&ops,640,480)==ERR_INVALID&&calls==mmio_calls&&memcmp(before_state,state,state_bytes)==0);guards();
 printf("tablet initialization failure retained ownership: scenario=%u acquired=%u checks=%llu\n",scenario,acquired,(unsigned long long)checks);
}
static ABI void wrap(void){
 initialized();unsigned remaining=65540;while(remaining){unsigned n=remaining>64?64:remaining;for(unsigned i=0;i<n;i++)device_event(0,0,0);good_poll();empty_output();remaining-=n;}
 Info v=info();CHECK(v.completed==65540&&v.used==4&&v.available==68&&device_used==4&&device_avail==4);guards();
 printf("tablet actual 16-bit wrap passed: wire=%u polls=%u completed=%llu used=%llu avail=%llu full-byte-guards=ok checks=%llu\n",wire_events,polls,(unsigned long long)v.completed,(unsigned long long)v.used,(unsigned long long)v.available,(unsigned long long)checks);
}
int main(int argc,char **argv){
 CHECK(argc==2);scenario=(unsigned)strtoul(argv[1],NULL,10);CHECK(scenario<=13);setup();
 if(scenario==0)normal();else if(scenario<=4||scenario==12)malformed();else if(scenario<=11)init_failure();else wrap();
 free(allocation);free(state_allocation);free(before_state);free(expected_state);return 0;
}
