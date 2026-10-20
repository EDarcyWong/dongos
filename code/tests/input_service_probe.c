// Execute production CPL3 input service: i8042 ACK/RESEND, IRQ authority,
// Set2 decoding, F12 routing, character publication, drain-before-ACK.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#define ABI __attribute__((sysv_abi))
#else
#include <sys/mman.h>
#define ABI
#endif
typedef uint64_t U;
typedef struct {U version,token,irq,gsi,vector,generation,sequence,flags;} Irq;
typedef struct {U head,tail,dropped;unsigned char bytes[256];} Console;
typedef struct {U kind,code;int64_t a,b;} Event;
typedef struct {U head,count;Event items[64];} Events;
extern ABI U service_main(void),input_errors(void),input_interrupts(void),input_console_pop(Console*,unsigned char*,U*);
static U checks;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"input service check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static U boot[16],rx[256],rxhead,rxtail,config_pending,mouse_prefix,key_resends,mouse_resends,binds,waits,acks,yields,ready,logs,irq_on;
static unsigned scenario,configured,started,delivered_key,delivered_mouse;
static void append(U value){CK(rxtail<256);rx[rxtail++]=value;}
static void inject(void){U bytes[]={0x20012,0x07,0x12,0x1c,0xf0,0x1c,0xf0,0x12,0x12,0x16,0xf0,0x16,0xf0,0x12,0x5a,0x07,0x108,0x101,0x102};for(unsigned i=0;i<sizeof bytes/sizeof bytes[0];i++)append(bytes[i]);}
ABI U svc_call(U number,U a,U b,U c,U d,U e,U f){
 /* This PS/2-only model has no admitted USB session or pending HID RPC. */
 if(number==0x2e){CK(a==0x101&&!b&&!c&&!d&&!e&&!f);return 0;}
 if(number==0x2f){CK(a==0x101&&!b&&!c&&!d&&!e&&!f);return 0x050b0002;}
 if(number==0x25){CK(a==0x101&&b&&c&&!d&&!e&&!f);return 0x05110005;}
 if(number==0x97){CK(a==0x444&&b==0&&c&&!d&&!e&&!f);U *entry=(U*)(uintptr_t)c;memset(entry,0,16*sizeof(U));entry[0]=1;return 0;}
 if(number==2){CK(!a&&!b&&!c&&!d&&!e&&!f);return (U)(uintptr_t)boot;}
 if(number==0x60){CK(a==0x444&&b>=0xe0000000&&b<0xe0100000&&c&&!d&&!e&&!f);*(uint32_t*)(uintptr_t)c=0xffff;return 0;}
 if(number==0x76){CK(a==0x333&&(b==0x60||b==0x64)&&c<=255&&!d&&!e&&!f);if(b==0x64){if(c==0x20)append(0x43);else if(c==0x60)config_pending=1;else if(c==0xd4)mouse_prefix=1;else CK(c==0xad||c==0xa7||c==0xae||c==0xa8);}else if(config_pending){config_pending=0;CK(c==0||c==3);configured++;if(c==3){CK(binds==2);irq_on=1;}}else{if(mouse_prefix){mouse_prefix=0;if(c==0xf6&&!mouse_resends){mouse_resends++;append(0x1fe);}else append(0x1fa);}else if(c==0xf5&&(scenario==5||!key_resends)){key_resends++;append(0xfe);}else append(0xfa);}return 0;}
 if(number==0x75){CK(a==0x333&&!b&&!c&&!d&&!e&&!f);if(rxhead<rxtail)return rx[rxhead++];return 0x10000;}
 if(number==0x86){CK(a==0x101&&!b&&!c&&!d&&!e&&!f);return 1;}
 if(number==0x92){CK(a==0x333&&(b==1||b==12)&&c==1&&d&&!e&&!f);binds++;if(scenario==1)return 0x0512000a;if(scenario==2)return 0x05120004;Irq q={1,b==1?0x501:0x502,b,b,0x50+b,1,0,0};*(Irq*)(uintptr_t)d=q;return 0;}
 if(number==0x93){CK((a==0x501||a==0x502)&&c&&!d&&!e&&!f);waits++;if(!started)return 0x05120006;if(scenario==3)return 0x05120004;unsigned*delivered=a==0x501?&delivered_key:&delivered_mouse;if(*delivered)return 0x05120006;CK(b==0);*delivered=1;U irq=a==0x501?1:12;Irq q={1,a,irq,irq,0x50+irq,1,1,3};*(Irq*)(uintptr_t)c=q;return 0;}
 if(number==0x94){CK((a==0x501||a==0x502)&&b==1&&!c&&!d&&!e&&!f);CK(rxhead==rxtail);acks++;if(scenario==4)return 0x05120004;return 0;}
 if(number==0x84){CK(a==0x101&&b==1&&!c&&!d&&!e&&!f);ready++;CK(key_resends==1&&mouse_resends==1);return 0;}
 if(number==0x70){CK(a&&b&&b<=4096&&!c&&!d&&!e&&!f);logs++;return 0;}
 if(number==3){CK(!a&&!b&&!c&&!d&&!e&&!f);yields++;if(!started){started=1;inject();return 0;}return 0x073100ff;}
 fprintf(stderr,"unexpected syscall: %#lx\n",(unsigned long)number);CK(0);return 1;
}
ABI void svc_fence(void){}
ABI void svc_vector_clobber(void){}
ABI void __dong_panic(void){fprintf(stderr,"unexpected input service Dong panic\n");exit(2);}
int main(int argc,char**argv){CK(argc==2);scenario=(unsigned)atoi(argv[1]);CK(scenario<=5);
#ifdef _WIN32
 void*mapped=VirtualAlloc((void*)(uintptr_t)0x54000000,0x200000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);CK(mapped==(void*)(uintptr_t)0x54000000);
#else
 void*mapped=mmap((void*)(uintptr_t)0x54000000,0x200000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);CK(mapped==(void*)(uintptr_t)0x54000000);
#endif
 boot[0]=1;boot[1]=5;boot[2]=0x101;boot[6]=0x54000000;boot[8]=0x444;boot[10]=0x333;boot[11]=7;boot[12]=0xe0000000;
 CK(service_main()==0x07310001);Console*q=(Console*)(uintptr_t)0x54100000;
 if(scenario==5){CK(ready==0&&input_interrupts()==0&&q->tail==0&&binds==0&&acks==0&&key_resends==3&&yields==0);}
 else if(scenario==2){CK(ready==0&&input_interrupts()==0&&q->tail==0&&binds==1&&acks==0&&yields==0);}
 else if(scenario==3){CK(ready==1&&input_interrupts()==1&&q->tail==0&&binds==2&&acks==0&&yields==1);}
 else{
  CK(ready==1&&input_errors()==1&&q->tail==3&&q->head==0&&q->dropped==0);
  CK(input_interrupts()==(scenario==1?0:1));CK(configured==(scenario==1?1:2)&&irq_on==(scenario!=1));
  CK(acks==(scenario==1?0:scenario==4?1:2));CK(binds==(scenario==1?1:2));
  unsigned char byte=0;U present;const unsigned char expected[]={'A','!',13};for(unsigned i=0;i<3;i++){CK(input_console_pop(q,&byte,&present)==0&&present&&byte==expected[i]);}byte=0xa5;CK(input_console_pop(q,&byte,&present)==0&&!present&&byte==0xa5);
  Events*gui=(Events*)(uintptr_t)0x54000000;int mouse=0;for(U i=0;i<gui->count;i++){Event v=gui->items[(gui->head+i)%64];if(v.kind==2&&v.a==1&&v.b==-2)mouse=1;CK(v.kind!=1);}CK(mouse);
 }
#ifdef _WIN32
 CK(VirtualFree(mapped,0,MEM_RELEASE)!=0);
#else
 CK(munmap(mapped,0x200000)==0);
#endif
 printf("input service native scenario=%u passed; checks=%lu; ready=%lu; ACK=%lu; bind=%lu; errors=%lu\n",scenario,(unsigned long)checks,(unsigned long)ready,(unsigned long)acks,(unsigned long)binds,(unsigned long)input_errors());return 0;
}
