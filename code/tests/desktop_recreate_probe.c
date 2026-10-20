#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#endif
#define SYSV __attribute__((sysv_abi))
typedef struct{uint64_t version,width,height,stride,format,framebuffer,bytes,back,font,font_bytes,hz,queue,background,windows,scale,pixels;} Display;
typedef struct{uint64_t width,height,stride,format,framebuffer;} Screen;
typedef struct{uint64_t physical;} Plan;
typedef struct{uint64_t ready;} Process;
typedef struct{uint8_t*pointer;uint64_t length;} Contents;
typedef struct{uint64_t id,va,pa,rw,live;} Mapping;
extern uint64_t SYSV dtr_prepare(void),dtr_recreate(uint64_t),dtr_font(uint64_t);
static Screen screen={1920,1080,1920,1,0xffff8000e0000080ULL};static Plan plan={0x80000000};static Process processes[16];
static Mapping maps[20000];static unsigned used;static Display descriptor,saved;static uint64_t generations[16],scale=320,checks,bad,next_pa=0x10000000,anonymous_calls,shares,readonly_calls,device_calls,apertures,call_count,fail_call,queue_pa,descriptor_pa,old_back,new_back;
static uint8_t*fontbase=(uint8_t*)(uintptr_t)0x30000000;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"DESKTOP_RECREATE_ASSERT line %u checks=%llu bad=%llu\n",__LINE__,(unsigned long long)checks,(unsigned long long)bad);return 1;}}while(0)
void SYSV __dong_panic(uint64_t code,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"unexpected panic %llu\n",(unsigned long long)code);exit(9);}
void SYSV dt_unexpected_gui(void){fprintf(stderr,"unexpected GUI client path in compositor fixture\n");exit(9);}
void SYSV dt_negative_hit(uint64_t kind){fprintf(stderr,"DESKTOP_RECREATE_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}
static int fail(void){call_count++;return fail_call&&call_count==fail_call;}
static Mapping*find(uint64_t id,uint64_t va){for(unsigned i=0;i<used;i++)if(maps[i].live&&maps[i].id==id&&maps[i].va==va)return &maps[i];return NULL;}
static uint64_t add(uint64_t id,uint64_t va,uint64_t pa,uint64_t rw){if(find(id,va)||used>=20000){bad++;return 1;}maps[used++]=(Mapping){id,va,pa,rw,1};return 0;}
void*SYSV dt_runtime(void){return &screen;}void*SYSV dt_plan(void){return &plan;}void*SYSV dt_processes(void){return processes;}
uint64_t SYSV dt_generation(uint64_t id){return id<16?generations[id]:0;}
uint64_t SYSV dt_find(const uint8_t*p,uint64_t n,Contents*out){if(n==14&&!memcmp(p,"desktop-config",14)){out->pointer=(uint8_t*)&scale;out->length=8;return 0;}if(n!=6||memcmp(p,"font",4)){bad++;return 1;}unsigned pixels=(p[4]-'0')*10+p[5]-'0';if(pixels<16||pixels>32||(pixels-16)%4){bad++;return 1;}out->pointer=fontbase+((pixels-16)/4+1)*4096;out->length=81;return 0;}
uint64_t SYSV dt_clock(uint64_t*out){*out=1000000000;return 0;}
uint64_t SYSV dt_device(uint64_t id,uint64_t va,uint64_t pa,uint64_t bytes){device_calls++;if(fail())return 1;if(id!=3||va!=0x60000000||pa!=0xe0000000||bytes!=(1920ULL*1080*4+128+4095)/4096*4096){bad++;return 1;}return add(id,va,pa,1);}
uint64_t SYSV dt_anonymous(uint64_t id,uint64_t va){anonymous_calls++;if(fail())return 0;uint64_t pa=next_pa;next_pa+=4096;if(add(id,va,pa,1))return 0;if(id==4&&va==0x54000000)queue_pa=pa;if(id==3&&va==0x70001000)descriptor_pa=pa;if(id==3&&va==0x58000000){if(!old_back)old_back=pa;else new_back=pa;}return pa;}
uint64_t SYSV dt_share(uint64_t from,uint64_t to,uint64_t sva,uint64_t tva,uint64_t rw){shares++;if(fail())return 1;Mapping*m=find(from,sva);if(!m||(rw&&!m->rw)||from==to){bad++;return 1;}return add(to,tva,m->pa,rw);}
uint64_t SYSV dt_copy(uint64_t id,uint64_t va,const uint8_t*p,uint64_t n){if(id!=3||va!=0x70001000||n!=sizeof(Display)||!find(id,va)){bad++;return 1;}memcpy(&descriptor,p,sizeof descriptor);return 0;}
uint64_t SYSV dt_readonly(uint64_t id,uint64_t va){readonly_calls++;Mapping*m=find(id,va);if(!m||id!=3||va!=0x70001000){bad++;return 1;}m->rw=0;return 0;}
uint64_t SYSV dt_alias(uint64_t id,uint64_t va,uint64_t write){if(fail())return 0;Mapping*m=find(id,va);if(!m||va!=0x70001000||(write&&!m->rw)){bad++;return 0;}return (uint64_t)(uintptr_t)&descriptor;}
uint64_t SYSV dt_range(uint64_t id,uint64_t va,uint64_t n,uint64_t write){Mapping*m=find(id,va);if(id!=4||va!=0x54000000||n!=4096||!m||(write&&!m->rw)){bad++;return 1;}return 0;}
uint64_t SYSV dt_aperture(uint64_t id,uint64_t va,uint64_t pa,uint64_t bytes){apertures++;if(fail())return 1;if(id!=3||va!=0x72000000||bytes!=81||pa<0x80001000||pa>0x80005000||(pa&4095)){bad++;return 1;}return add(id,va,pa,0);}
uint64_t SYSV dt_replace(uint64_t id,uint64_t va,uint64_t old_pa,uint64_t old_bytes,uint64_t pa,uint64_t bytes){Mapping*m=find(id,va);if(!m||m->pa!=old_pa||old_bytes!=81||bytes!=81){bad++;return 1;}m->pa=pa;return 0;}
static void put32(void *p,uint32_t value){memcpy(p,&value,4);}
static void retire_compositor(void){for(unsigned i=0;i<used;i++)if(maps[i].id==3)maps[i].live=0;generations[3]++;}
int main(void){
#ifdef _WIN32
 CHECK(VirtualAlloc(fontbase,65536,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)==fontbase);
#else
 CHECK(mmap(fontbase,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==fontbase);
#endif
 /* One real bounded DGFONT01 glyph, not a header-only pseudo-font. */
 for(unsigned i=0;i<5;i++){uint8_t*p=fontbase+(i+1)*4096;memcpy(p,"DGFONT01",8);
  put32(p+8,1);put32(p+12,48);put32(p+16,1);put32(p+20,16+i*4);
  put32(p+24,48);put32(p+28,80);put32(p+32,1);put32(p+36,16);put32(p+40,4);
  uint8_t*r=p+48;put32(r,65);r[4]=r[6]=r[20]=1;put32(r+12,64);p[80]=255;
 }
 processes[3].ready=processes[4].ready=1;generations[3]=generations[4]=1;
 CHECK(dtr_recreate(3)!=0&&call_count==0);CHECK(!dtr_prepare());CHECK(!bad);CHECK(descriptor.version==3&&descriptor.scale==320&&descriptor.pixels==20&&descriptor.font_bytes==81);saved=descriptor;
 uint64_t anon_before=anonymous_calls,calls_before=call_count;CHECK(dtr_recreate(3)!=0&&call_count==calls_before);CHECK(dtr_recreate(4)!=0&&call_count==calls_before);
 CHECK(find(4,0x70001000)&&!find(4,0x70001000)->rw&&find(4,0x70001000)->pa==descriptor_pa);CHECK(find(4,0x54000000)->pa==queue_pa);
 retire_compositor();CHECK(!dtr_recreate(3));CHECK(new_back&&new_back!=old_back);CHECK(anonymous_calls-anon_before==2*((1920ULL*1080*4+4095)/4096)+2048);
 CHECK(find(3,0x54000000)->pa==queue_pa&&find(3,0x54000000)->rw&&find(3,0x70001000)->pa==descriptor_pa&&!find(3,0x70001000)->rw);CHECK(!memcmp(&saved,&descriptor,sizeof saved)&&readonly_calls==1);CHECK(!dtr_font(512)&&descriptor.scale==512&&descriptor.pixels==32&&find(3,0x72000000)->pa==0x80005000);saved=descriptor;
 retire_compositor();generations[4]++;calls_before=call_count;CHECK(dtr_recreate(3)!=0&&call_count==calls_before);generations[4]--;descriptor.back=0xdeadbeef;CHECK(dtr_recreate(3)!=0);descriptor=saved;
 // Inject a private-page publication failure. No queue/descriptor is rebuilt;
 // the incomplete candidate is retired before a later successful retry.
 fail_call=call_count+3;CHECK(dtr_recreate(3)!=0);fail_call=0;CHECK(!memcmp(&saved,&descriptor,sizeof saved));retire_compositor();CHECK(!dtr_recreate(3));CHECK(!memcmp(&saved,&descriptor,sizeof saved)&&find(3,0x72000000)->pa==0x80005000);CHECK(!bad);
 printf("Desktop production recreate passed checks=%llu fresh_private_calls=%llu preserved_queue=%llx descriptor=%llx\n",(unsigned long long)checks,(unsigned long long)anonymous_calls,(unsigned long long)queue_pa,(unsigned long long)descriptor_pa);return 0;
}
