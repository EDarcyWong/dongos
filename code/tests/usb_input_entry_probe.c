#define svc_call legacy_svc_call
#define main legacy_main
#include "input_service_probe.c"
#undef svc_call
#undef main
typedef struct{U w[8];}Message;
extern U ABI usb_test_pump(void),usb_test_ps2(U),usb_test_epoch(void),usb_test_last(U);
extern U ABI usb_test_departed(void);
static Message request,response;
static U pending,peer=14,identity=((U)1<<32)|1,received,replied;
static U departed,departure_queries;
ABI U svc_call(U number,U a,U b,U c,U d,U e,U f){
 if(number==0x25){CK(a==0x101&&b&&c&&!d&&!e&&!f);if(!pending)return 0x05110005;*(Message*)(uintptr_t)b=request;*(U*)(uintptr_t)c=0x1234;pending=0;received++;return 0;}
 if(number==0x29){CK(a==0x101&&b==0x1234&&!c&&!d&&!e&&!f);return peer;}
 if(number==0x2a){CK(a==0x101&&b==0x1234&&!c&&!d&&!e&&!f);return identity;}
 if(number==0x2e){CK(a==0x101&&!b&&!c&&!d&&!e&&!f);U value=departed;departed=0;departure_queries++;return value?((U)0x55484450<<32)|value:0;}
 if(number==0x24){CK(a==0x101&&b==0x1234&&c&&!d&&!e&&!f);response=*(Message*)(uintptr_t)c;replied++;return 0;}
 return legacy_svc_call(number,a,b,c,d,e,f);
}
static void gui_empty(void){Events*q=(Events*)(uintptr_t)0x54000000;CK(q->count==0);}
static Event gui_next(void){Events*q=(Events*)(uintptr_t)0x54000000;CK(q->count>0);Event e=q->items[q->head];q->head=(q->head+1)%64;q->count--;return e;}
static void send_report(U seq,U modifiers,U usage,U epoch,U status){request=(Message){{0x4447554849440001ULL,1,1,8,seq,(usage<<16)|modifiers,epoch,0}};pending=1;U before=replied;CK(!usb_test_pump());CK(replied==before+1&&received==replied&&response.w[0]==status);}
int main(int argc,char**argv){if(argc==2)return legacy_main(argc,argv);char*args[]={"native","0"};CK(legacy_main(2,args)==0);
 // legacy_main releases only its host mapping; install a fresh read/write
 // queue for the continuing same input process's real RPC/pipeline calls.
#ifdef _WIN32
 void*mapped=VirtualAlloc((void*)(uintptr_t)0x54000000,0x200000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);CK(mapped==(void*)(uintptr_t)0x54000000);
#else
 void*mapped=mmap((void*)(uintptr_t)0x54000000,0x200000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);CK(mapped==(void*)(uintptr_t)0x54000000);
#endif
 CK(usb_test_epoch()==1);CK(!usb_test_ps2(0xf0));CK(!usb_test_ps2(0x07));CK(!usb_test_ps2(0x07));Event event=gui_next();CK(event.kind==5);gui_empty();
 CK(!usb_test_ps2(0x1c));event=gui_next();CK(event.kind==1&&event.code==30&&event.a==1);gui_empty();
 send_report(1,2,4,1,0);event=gui_next();CK(event.kind==1&&event.code==42&&event.a==1&&event.b==1);gui_empty();
 send_report(2,0,0,1,0);event=gui_next();CK(event.code==42&&event.a==0&&event.b==0);gui_empty();
 peer=3;send_report(3,0,5,1,0x081e0005);CK(usb_test_last(1)==2);gui_empty();peer=14;
 identity=((U)2<<32)|1;send_report(3,0,5,1,0x081e0005);CK(usb_test_last(1)==2);gui_empty();identity=((U)1<<32)|1;
 send_report(2,0,5,1,0x081e0004);CK(usb_test_last(1)==2);gui_empty();
 send_report(3,0,5,1,0);event=gui_next();CK(event.code==48&&event.a==1);gui_empty();
 identity=((U)1<<32)|2;send_report(1,0,6,2,0);event=gui_next();CK(event.code==48&&event.a==0);event=gui_next();CK(event.code==46&&event.a==1);gui_empty();
 CK(!usb_test_ps2(0xf0));CK(!usb_test_ps2(0x1c));event=gui_next();CK(event.code==30&&event.a==0);gui_empty();
 send_report(2,0,1,2,0);event=gui_next();CK(event.code==46&&event.a==0);gui_empty();
 CK(!usb_test_ps2(0x1c));event=gui_next();CK(event.code==30&&event.a==1);send_report(3,0,6,2,0);event=gui_next();CK(event.code==46&&event.a==1);gui_empty();
 departed=1;CK(!usb_test_departed());gui_empty();CK(usb_test_last(1)==3);departed=2;CK(!usb_test_departed());event=gui_next();CK(event.code==46&&event.a==0);gui_empty();CK(!departed);
 U before=departure_queries;CK(!usb_test_departed());gui_empty();CK(departure_queries==before+1);send_report(4,0,6,2,0x081e0004);gui_empty();
 identity=((U)1<<32)|3;send_report(1,0,7,3,0);event=gui_next();CK(event.code==32&&event.a==1);departed=2;CK(!usb_test_departed());gui_empty();
 CK(!usb_test_ps2(0xf0));CK(!usb_test_ps2(0x1c));event=gui_next();CK(event.code==30&&event.a==0);gui_empty();
 printf("USB_INPUT_ENTRY_NATIVE_PASS checks=%lu received=%lu replied=%lu\n",(unsigned long)checks,(unsigned long)received,(unsigned long)replied);
 return 0;
}
