#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{U version,pid,endpoint,fs,block,shared,address,bytes,configuration,dma,console,count,r[4];}Boot;
typedef struct{U generation,kind,object,rights,live;}Entry;
typedef struct{U w[8];}Message;
typedef struct{U version,token,next,kind,ecam,segment,bus,device,function,vendor,id,class_code,header,flags,generation,reserved;}Device;
typedef struct{U version,device,role,config,generation,irqmask,flags,reserved;}Binding;
typedef struct{U ecam,segment,bus,device,function,vendor,id,class_code,subclass,interface,header;}Pci;
extern void SYSV ur_reset(U),ur_entry(U,U,Entry*);
extern U SYSV ur_install(U,U,U),ur_endpoint(U,U,U),ur_channels(U),ur_manager(void),ur_select(void),ur_backend(void),ur_selected(void);
extern const Boot *SYSV ur_boot(U);
static U checks,mem_count,mem_fail,binds,device_count,pci_count,usb_calls,usb_status,logs;
static Device hardware[8];static Pci pci[8];static Boot boot;
static struct{U source,target,address,write;}maps[32];
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"USB_ROOT_ASSERT %d %s\n",__LINE__,#x);exit(1);}}while(0)
void SYSV __dong_panic(U c,const char*p,U n){(void)c;(void)p;(void)n;fprintf(stderr,"USB_ROOT_PANIC\n");exit(9);}
U SYSV ur_memory(U source,U target,U address,U write){
 CHECK(mem_count<32);maps[mem_count].source=source;maps[mem_count].target=target;maps[mem_count].address=address;maps[mem_count].write=write;
 mem_count++;return mem_fail==mem_count?0x09000001:0;
}
U SYSV ur_pci(U index,Pci*out){if(index>=pci_count)return 0;*out=pci[index];return 1;}
U SYSV svc_call(U number,U a,U b,U c,U d,U e,U f){
 if(number==2){CHECK(!a&&!b&&!c&&!d&&!e&&!f);return (U)(uintptr_t)&boot;}
 if(number==0x70){CHECK(a&&b&&!c&&!d&&!e&&!f);logs++;return 0;}
 if(number==0x22){CHECK(a==0x1234&&b&&c&&!d&&!e&&!f);const Message*r=(const Message*)(uintptr_t)b;Message*out=(Message*)(uintptr_t)c;CHECK(r->w[0]==1);usb_calls++;out->w[0]=usb_status;out->w[2]=4096;return 0;}
 if(number==0x90){CHECK(a==0x999&&b<=device_count&&c&&!d&&!e&&!f);Device v={0};v.version=1;if(b<device_count){v=hardware[b];v.next=b+1;}*(Device*)(uintptr_t)c=v;return 0;}
 if(number==0x91){CHECK(a==0x999&&b>=257&&b<257+device_count&&c>=1&&c<=4&&d&&!e&&!f);Device v=hardware[b-257];
   CHECK((c==1&&(v.class_code==0x010601||v.class_code==0x010802))||(c==3&&v.kind==2)||(c==4&&v.class_code==0x0c0330));
   Binding out={1,b,c,c==1?2:c==4?13:4,1,0,2,0};*(Binding*)(uintptr_t)d=out;binds++;return 0;}
 CHECK(0);return 1;
}
void SYSV svc_fence(void){}
U SYSV svc_receive(U a,Message*b,U*c){(void)a;(void)b;(void)c;return 1;}
U SYSV svc_reply_wait(U a,U b,const Message*c,Message*d,U*e){(void)a;(void)b;(void)c;(void)d;(void)e;return 1;}
static void grants(void){
 ur_reset(1);for(U id=0;id<16;id++){U cfg=id<7?id:id==13?13:7;CHECK(ur_install(id,cfg,1)==0);}
 for(U id=0;id<16;id++){const Boot*b=ur_boot(id);U calls=0;
  for(U slot=0;slot<32;slot++){Entry e;ur_entry(id,slot,&e);if(e.live&&e.kind==1&&e.object==14&&(e.rights&32)){CHECK(id==2&&e.rights==32);calls++;}}
  CHECK(calls==(id==2?1:0));if(id==2)CHECK(ur_endpoint(id,b->block,32)==13);
  if(id==13){CHECK(b->address==0x51000000&&b->fs==0&&b->console!=0);CHECK(ur_endpoint(13,b->console,32)==4);CHECK(ur_endpoint(13,b->endpoint,8|64)==13);CHECK(ur_endpoint(13,b->endpoint,32)!=13);}
 }
 U stolen=ur_boot(2)->block;for(U id=0;id<16;id++)if(id!=2)CHECK(ur_endpoint(id,stolen,32)!=13);
 ur_reset(0);CHECK(ur_install(2,2,1)==0&&ur_boot(2)->block==0);
 for(U failure=0;failure<=16;failure++){mem_count=0;mem_fail=failure;U status=ur_channels(13);CHECK(status==(failure?0x09000001:0));CHECK(mem_count==(failure?failure:16));for(U i=0;i<mem_count;i++)CHECK(maps[i].source==2&&maps[i].target==13&&maps[i].address==0x51000000+i*4096&&maps[i].write==1);}
}
static Device device(U kind,U cls,U index){Device d={0};d.version=1;d.kind=kind;d.class_code=cls;d.token=257+index;d.generation=1;d.vendor=0x8086;d.id=1;d.ecam=0xe0000000+index*4096;return d;}
static void manager(void){
 for(unsigned scenario=0;scenario<6;scenario++){memset(hardware,0,sizeof hardware);binds=0;device_count=0;
  if(scenario==1)hardware[device_count++]=device(1,0x0c0330,0);
  if(scenario==2)hardware[device_count++]=device(2,0,0);
  if(scenario==3)hardware[device_count++]=device(1,0x010802,0);
  if(scenario==4){hardware[device_count++]=device(1,0x0c0330,0);hardware[device_count++]=device(2,0,1);}
  if(scenario==5){hardware[device_count++]=device(1,0x010802,0);hardware[device_count++]=device(1,0x0c0330,1);}
  U status=ur_manager();CHECK(status==((scenario==0||scenario==2)?0x05120008:0));CHECK(binds==((scenario==0||scenario==2)?0:scenario>=4?2:1));
 }
}
static Pci function(U index,U kind){Pci v={0};v.ecam=0xe0000000+index*4096;v.vendor=0x8086;v.id=1;if(kind==1){v.vendor=0x1af4;v.id=0x1042;}if(kind==2){v.class_code=1;v.subclass=8;v.interface=2;}if(kind==3){v.class_code=1;v.subclass=6;v.interface=1;}return v;}
static void selection(void){
 memset(&boot,0,sizeof boot);boot.version=1;boot.bytes=65536;boot.block=0x1234;boot.configuration=0x999;
 for(U scenario=0;scenario<7;scenario++){pci_count=usb_calls=usb_status=logs=0;memset(pci,0,sizeof pci);
  if(scenario==1)pci[pci_count++]=function(0,3);
  if(scenario==2){pci[pci_count++]=function(0,3);pci[pci_count++]=function(1,2);}
  if(scenario==3){pci[pci_count++]=function(0,3);pci[pci_count++]=function(1,2);pci[pci_count++]=function(2,1);}
  if(scenario==4){pci[pci_count]=function(0,3);pci[pci_count++].header=1;pci[pci_count]=function(1,2);pci[pci_count++].header=1;}
  boot.block=scenario==5?0:0x1234;if(scenario==6)usb_status=0x05040004;
  U status=ur_select();CHECK(status==(scenario>=5?0x05060001:0));
  if(scenario<5){U expected=scenario==1?2:scenario==2?3:scenario==3?1:4;CHECK(ur_backend()==expected);CHECK(usb_calls==(expected==4));CHECK(logs==(expected==4));if(expected!=4)CHECK(ur_selected()==0xe0000000+(scenario-1)*4096);}
  else CHECK(usb_calls==(scenario==6));
 }
}
int main(void){grants();manager();selection();printf("USB_ROOT_NATIVE_PASS checks=%llu\n",(unsigned long long)checks);return 0;}
