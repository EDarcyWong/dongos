#define svc_call legacy_svc_call
#define main legacy_main
#include "input_service_probe.c"
#undef svc_call
#undef main
typedef struct{U w[8];}Message;
extern U ABI usb_test_last(U);
static unsigned usb_only,mode;
static U queries,pre_ready_yields,port_calls,accepted,pump_calls,replies,usb_ready_logs,ps2_logs,departures,post_ready_yields;
static U usb_ready_inc(void){
 const U tag=0x55485244ULL<<32;
 if(mode==1||mode==5)return 0;
 if(mode==2)return tag|0x10000000;
 if(mode==3)return 0x050b0002;
 if(mode==4)return queries==1024?tag|3:0;
 if(mode==6)return 3;
 if(mode==7)return UINT64_MAX;
 if(mode==8)return (0x55485245ULL<<32)|3;
 if(mode==9)return tag;
 return queries>=3?tag|3:0;
}
ABI U svc_call(U number,U a,U b,U c,U d,U e,U f){
 if(!usb_only){if(number==0x2f)return 0x050b0002;if(number==0x2e)return 0;if(number==0x25)return 0x05110005;return legacy_svc_call(number,a,b,c,d,e,f);}
 if(number==2){CK(!a&&!b&&!c&&!d&&!e&&!f);return (U)(uintptr_t)boot;}
 if(number==0x86){CK(a==0x101&&!b&&!c&&!d&&!e&&!f);return 1;}
 if(number==0x76||number==0x75){CK(a==0x333&&queries==0&&ready==0);port_calls++;return number==0x76?2:0x10000;}
 if(number==0x2f){CK(a==0x101&&!b&&!c&&!d&&!e&&!f&&ready==0);queries++;return usb_ready_inc();}
 if(number==3){CK(!a&&!b&&!c&&!d&&!e&&!f);if(!ready){pre_ready_yields++;return mode==5?0x073100ff:0;}post_ready_yields++;return (mode>=10&&mode<=15)&&post_ready_yields==1?0:0x073100ff;}
 if(number==0x60){CK(a==0x444&&c&&!d&&!e&&!f&&queries>=3);*(uint32_t*)(uintptr_t)c=0xffff;return 0;}
 if(number==0x70){CK(a&&b&&!c&&!d&&!e&&!f);const char*text=(const char*)(uintptr_t)a;if(b==24&&!memcmp(text,"DONGOS_INPUT_USB_READY\r\n",24))usb_ready_logs++;if(b==24&&!memcmp(text,"DONGOS_INPUT_PS2_READY\r\n",24))ps2_logs++;return 0;}
 if(number==0x84){CK(a==0x101&&b==1&&!c&&!d&&!e&&!f&&queries>=3);ready++;return 0;}
 if(number==0x2e){CK(a==0x101&&!b&&!c&&!d&&!e&&!f&&ready==1);departures++;if(mode>=10&&departures==2){
  if(mode==10)return (0x55484450ULL<<32)|3;
  if(mode==11)return 0x050b0002;
  if(mode==12)return 3;
  if(mode==13)return (0x55484451ULL<<32)|3;
  if(mode==14)return 0x55484450ULL<<32;
  if(mode==15)return (0x55484450ULL<<32)|0x10000000;
 }return 0;}
 if(number==0x25){CK(a==0x101&&b&&c&&!d&&!e&&!f&&ready==1);pump_calls++;if(accepted)return 0x05110005;Message m={{0x4447554849440001ULL,1,1,8,1,4ULL<<16,3,0}};*(Message*)(uintptr_t)b=m;*(U*)(uintptr_t)c=0x1234;accepted++;return 0;}
 if(number==0x29){CK(a==0x101&&b==0x1234&&!c&&!d&&!e&&!f);return 14;}
 if(number==0x2a){CK(a==0x101&&b==0x1234&&!c&&!d&&!e&&!f);return (1ULL<<32)|3;}
 if(number==0x24){CK(a==0x101&&b==0x1234&&c&&!d&&!e&&!f);Message*m=(Message*)(uintptr_t)c;CK(m->w[0]==0&&m->w[1]==1&&m->w[2]==1);for(unsigned i=3;i<8;i++)CK(!m->w[i]);replies++;return 0;}
 CK(0);return 1;
}
int main(int argc,char**argv){CK(argc==2);if(strncmp(argv[1],"usb",3))return legacy_main(argc,argv);usb_only=1;mode=(unsigned)atoi(argv[1]+3);CK(mode<=15);
#ifdef _WIN32
 void*mapped=VirtualAlloc((void*)(uintptr_t)0x54000000,0x200000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);CK(mapped==(void*)(uintptr_t)0x54000000);
#else
 void*mapped=mmap((void*)(uintptr_t)0x54000000,0x200000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);CK(mapped==(void*)(uintptr_t)0x54000000);
#endif
 boot[0]=1;boot[1]=5;boot[2]=0x101;boot[6]=0x54000000;boot[8]=0x444;boot[10]=0x333;boot[11]=7;boot[12]=0xe0000000;
 CK(service_main()==0x07310001&&input_interrupts()==0&&port_calls==1&&binds==0&&acks==0);
 if(mode==0||mode==4||mode>=10){CK(ready==1&&accepted==1&&replies==1&&pump_calls==(mode==10?3:2));CK(queries==(mode==4?1024:3)&&pre_ready_yields==queries-1);Events*q=(Events*)(uintptr_t)0x54000000;CK(q->count==(mode==10?2:1));Event event=q->items[q->head];CK(event.kind==1&&event.code==30&&event.a==1&&event.b==0);if(mode==10){event=q->items[(q->head+1)%64];CK(event.kind==1&&event.code==30&&event.a==0&&event.b==0);}if(mode>=10){CK(departures==2&&post_ready_yields==(mode==10?2:1));CK(usb_test_last(1)==(mode==10?0:1));}CK(usb_ready_logs==1&&ps2_logs==0);}
 else{CK(ready==0&&!accepted&&!pump_calls&&!replies&&!usb_ready_logs&&!ps2_logs);CK(queries==(mode==1?1024:1)&&pre_ready_yields==(mode==1?1023:mode==5?1:0));Events*q=(Events*)(uintptr_t)0x54000000;CK(!q->count);}
#ifdef _WIN32
 CK(VirtualFree(mapped,0,MEM_RELEASE)!=0);
#else
 CK(munmap(mapped,0x200000)==0);
#endif
 printf("USB_ONLY_INPUT_NATIVE_PASS checks=%lu mode=%u queries=%lu yields=%lu ready=%lu\n",(unsigned long)checks,mode,(unsigned long)queries,(unsigned long)pre_ready_yields,(unsigned long)ready);return 0;
}
