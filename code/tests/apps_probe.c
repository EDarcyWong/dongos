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
#define BAD 0x05120001ULL
#define DENIED 0x050c0003ULL
typedef struct{uint64_t words[16];}Boot;
typedef struct{uint64_t words[8];}Message;
extern uint64_t SYSV service_main(void),app_canary(void);
extern uint64_t SYSV app_probe(void);
extern void SYSV app_reset(void);
static Boot boot;static uint64_t checks,bad,ready,ud2,yields,receives,replies,operation=7,peer_status=0x05110008ULL,fs_reads,denials,flip_probe;
static char log_bytes[1024];static size_t logged;
static uint8_t*channel=(uint8_t*)(uintptr_t)0x53000000;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"APP_FIXTURE_ASSERT line %u checks=%llu bad=%llu\n",__LINE__,(unsigned long long)checks,(unsigned long long)bad);return 1;}}while(0)
void SYSV __dong_panic(uint64_t code,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"unexpected panic %llu\n",(unsigned long long)code);exit(9);}
void SYSV svc_user_ud2(void){ud2++;}
void SYSV svc_fence(void){}
uint64_t SYSV svc_receive(uint64_t endpoint,Message*message,uint64_t*ticket){if(endpoint!=55){bad++;return 99;}receives++;memset(message,0,sizeof *message);message->words[0]=operation;message->words[1]=0x12345678;*ticket=123;return 0;}
uint64_t SYSV svc_reply_wait(uint64_t endpoint,uint64_t ticket,const Message*reply,Message*next,uint64_t*next_ticket){(void)next;(void)next_ticket;if(endpoint!=55||ticket!=123||reply->words[0]!=operation||reply->words[1]!=0x12345678){bad++;return 99;}replies++;return 0xc0ffee;}
uint64_t SYSV svc_call(uint64_t number,uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e,uint64_t f){
 if(number==2){if(a||b||c||d||e||f){bad++;return 99;}return (uint64_t)(uintptr_t)&boot;}
 if(number==0x86){if(a!=55||b||c||d||e||f){bad++;return 99;}return 2;}
 if(number==0x84){if(a!=55||b!=2||c||d||e||f){bad++;return 99;}ready++;return 0;}
 if(number==3){yields++;if(flip_probe&&yields==flip_probe){*(uint64_t*)(uintptr_t)0x44000000=99;}return yields<3?0:0xc0ffee;}
 if(number==0x70){if(b>sizeof log_bytes-logged-1){bad++;return 99;}memcpy(log_bytes+logged,(const void*)(uintptr_t)a,(size_t)b);logged+=(size_t)b;log_bytes[logged]=0;return 0;}
 if(number==0x22&&a==66){const Message*r=(const Message*)(uintptr_t)b;if(r->words[0]!=999){bad++;return 99;}return peer_status;}
 if(number==0x22&&a==11){const Message*r=(const Message*)(uintptr_t)b;Message*out=(Message*)(uintptr_t)c;memset(out,0,sizeof *out);out->words[5]=3;
  if(r->words[0]==0x200){if(r->words[4]==395){out->words[1]=0x100000101ULL;out->words[2]=395;return 0;}if(r->words[4]==1023){out->words[0]=DENIED;denials++;return 0;}}
  if(r->words[0]==0x201){if(r->words[1]!=0x100000101ULL||r->words[4]!=3||r->words[5]!=11||memcmp(channel,"/README.TXT",11)){bad++;return 99;}out->words[1]=0x100000102ULL;out->words[2]=3;return 0;}
  if(r->words[0]==0x206){if(r->words[1]!=0x100000102ULL||r->words[2]||r->words[3]!=4096){bad++;return 99;}memcpy(channel+4096,"DongOS FAT32 persistence fixture.\n",34);out->words[1]=34;fs_reads++;return 0;}
  if(r->words[0]==0x207||r->words[0]==0x103||r->words[0]==3){out->words[0]=DENIED;denials++;return 0;}
  if(r->words[0]==0x203){if(r->words[1]!=0x100000102ULL){bad++;return 99;}return 0;}
 }
 bad++;return 99;
}
int main(void){
 boot.words[0]=1;boot.words[2]=55;boot.words[3]=11;boot.words[4]=66;boot.words[6]=0x53000000;boot.words[7]=65536;boot.words[12]=42;
#if APP_KIND==1
 const uint64_t args[]={0,42,UINT64_MAX};for(unsigned i=0;i<3;i++){app_reset();boot.words[12]=args[i];CHECK(service_main()==args[i]&&app_canary()==args[i]);}uint64_t was_ready=ready;CHECK(service_main()==BAD&&ready==was_ready);
 app_reset();boot.words[12]=999;CHECK(service_main()==0&&app_canary()==999&&strstr(log_bytes,"DONGOS_APP_PEER_GONE"));app_reset();peer_status=0;CHECK(service_main()==BAD);
#elif APP_KIND==2
 CHECK(service_main()==BAD&&ud2==1&&ready==1);
#elif APP_KIND==3
 {uint64_t*probe=(uint64_t*)(uintptr_t)0x44000000;
#ifdef _WIN32
 CHECK(VirtualAlloc(probe,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)==probe);
#else
 CHECK(mmap(probe,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==probe);
#endif
 *probe=42;CHECK(service_main()==0xc0ffee&&yields==3&&app_canary()==42&&app_probe()==42&&ready==1);
 app_reset();*probe=42;yields=0;flip_probe=2;CHECK(service_main()==BAD&&app_probe()==99&&ready==2&&yields==2);
 app_reset();flip_probe=0;*probe=99;CHECK(service_main()==BAD&&app_probe()==99&&ready==2&&yields==2);}
#elif APP_KIND==4
 CHECK(service_main()==0xc0ffee&&receives==1&&replies==1&&app_canary()==42&&ready==1);app_reset();operation=999;CHECK(service_main()==BAD&&ud2==1);
#elif APP_KIND==5
#ifdef _WIN32
 CHECK(VirtualAlloc(channel,65536,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)==channel);
#else
 CHECK(mmap(channel,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==channel);
#endif
 CHECK(service_main()==0&&app_canary()==42&&ready==1&&fs_reads==2&&denials==4&&strstr(log_bytes,"DONGOS_APP_FS_RIGHTS_PASS"));
#endif
 CHECK(!bad);printf("App production fixture kind=%d checks=%llu ready=%llu ud2_stub=%llu\n",APP_KIND,(unsigned long long)checks,(unsigned long long)ready,(unsigned long long)ud2);return 0;
}
