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
#define BAD 0x05080003ULL
#define STALE 0x05080004ULL
#define CHANNEL_BYTES 65536
#define DATA 4096
typedef struct{uint64_t words[8];} Message;
typedef struct{uint64_t words[16];} Boot;
typedef struct{uint8_t name[11],attributes;uint64_t cluster,size,sector,offset;} Dir;
typedef struct{Dir entry;uint64_t name_length,has_lfn,raw_index,first_index,group_count;uint8_t name[1020];} PathEntry;
extern uint64_t SYSV fsr_setup(void),fsr_operate(const Message*,Message*),fsr_generation(void);
extern void SYSV fsr_set_generation(uint64_t),fsr_record(const PathEntry*,uint64_t,uint64_t,Message*);
static Boot boot;
static FILE*disk;
static uint64_t sectors,reads,writes,flushes,peer=1,peer_calls,bad_syscall,checks,fs_epoch=1,caller_epoch[9],departures[9],grant=1023;
static uint8_t*shell=(uint8_t*)(uintptr_t)0x50000000,*block=(uint8_t*)(uintptr_t)0x51000000,*desktop=(uint8_t*)(uintptr_t)0x52000000;
static uint8_t*app=(uint8_t*)(uintptr_t)0x53000000;
static uint8_t before_shell[65536],before_desktop[65536];
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"FS service check failed line %u\n",__LINE__);return 1;}}while(0)
void SYSV __dong_panic(uint64_t code,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"FS service unexpected panic %x\n",(unsigned)code);exit(9);}
uint64_t SYSV svc_call(uint64_t number,uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e,uint64_t f){
 (void)d;(void)e;(void)f;if(number==2){return (uint64_t)(uintptr_t)&boot;}
 if(number==0x29){peer_calls++;if(a!=boot.words[2]||b!=123){bad_syscall++;return 0;}return peer;}
 if(number==0x2a){if(a!=boot.words[2]||b!=123||peer>8){bad_syscall++;return 0;}return (fs_epoch<<32)|(caller_epoch[peer]?caller_epoch[peer]:1);}
 if(number==0x2b){if(a!=boot.words[2]||b!=123){bad_syscall++;return 0;}return grant;}
 /* Existing role-policy query: default unscoped client, no new authority. */
 if(number==0x2d){if(a!=boot.words[2]||b!=123||c||d||e||f){bad_syscall++;return 99;}return 0;}
 if(number==0x2c){if(a!=boot.words[2]||b||c||d||e||f){bad_syscall++;return 0;}for(unsigned i=1;i<9;i++){if(departures[i]){uint64_t key=((uint64_t)i<<32)|departures[i];departures[i]=0;return key;}}return 0;}
 if(number==0x22&&a==boot.words[4]){const Message*r=(const Message*)(uintptr_t)b;Message*out=(Message*)(uintptr_t)c;memset(out,0,sizeof *out);uint64_t op=r->words[0],lba=r->words[1],count=r->words[2];
  if(op==1){out->words[2]=sectors;return 0;}if(op==4){flushes++;return fflush(disk)?1:0;}
  if(count==0||count>128||lba>=sectors||count>sectors-lba){bad_syscall++;return 1;}
  if(fseek(disk,(long)(lba*512),SEEK_SET)){return 1;}
  if(op==2){reads++;return fread(block,512,(size_t)count,disk)==count?0:1;}
  if(op==3){writes++;return fwrite(block,512,(size_t)count,disk)==count?0:1;}
 }
 bad_syscall++;return 99;
}
uint64_t SYSV svc_receive(uint64_t a,Message*b,uint64_t*c){(void)a;(void)b;(void)c;bad_syscall++;return 99;}
uint64_t SYSV svc_reply_wait(uint64_t a,uint64_t b,const Message*c,Message*d,uint64_t*e){(void)a;(void)b;(void)c;(void)d;(void)e;bad_syscall++;return 99;}
void SYSV svc_fence(void){}
static uint64_t u64(const uint8_t*p){uint64_t n=0;for(unsigned i=0;i<8;i++)n|=(uint64_t)p[i]<<(8*i);return n;}
static Message request(uint64_t op,const char*path){Message r={{0}};r.words[0]=op;r.words[3]=strlen(path);r.words[4]=DATA;r.words[5]=2;memcpy(shell,path,strlen(path));memcpy(desktop,path,strlen(path));return r;}
static int reject(Message r,uint64_t error){
 Message reply;memset(&reply,0xa5,sizeof reply);memcpy(before_shell,shell,65536);memcpy(before_desktop,desktop,65536);uint64_t rr=reads,ww=writes,ff=flushes,gg=fsr_generation(),pp=peer_calls;
 CHECK(fsr_operate(&r,&reply)==error&&reply.words[0]==error&&reads==rr&&writes==ww&&flushes==ff&&peer_calls==pp+1&&fsr_generation()==gg);
 CHECK(!memcmp(shell,before_shell,65536)&&!memcmp(desktop,before_desktop,65536));
 for(unsigned i=1;i<8;i++){if(i!=5&&i!=6){CHECK(reply.words[i]==0);}}
 if(peer==1||peer==4){CHECK(reply.words[5]==2&&reply.words[6]==gg);}else{CHECK(reply.words[5]==0&&reply.words[6]==0);}return 0;
}
static int guards(void){
 Message base=request(0x100,"/README.TXT"),bad;
 for(unsigned bit=0;bit<64;bit++){bad=base;bad.words[7]=1ULL<<bit;CHECK(!reject(bad,BAD));}
 const uint64_t versions[]={0,1,3,UINT64_MAX},lengths[]={0,4097,UINT64_MAX},offsets[]={0,4095,4097,65536,UINT64_MAX};
 for(unsigned i=0;i<sizeof versions/sizeof *versions;i++){bad=base;bad.words[5]=versions[i];CHECK(!reject(bad,BAD));}
 for(unsigned i=0;i<sizeof lengths/sizeof *lengths;i++){bad=base;bad.words[3]=lengths[i];CHECK(!reject(bad,BAD));}
 for(unsigned i=0;i<sizeof offsets/sizeof *offsets;i++){bad=base;bad.words[4]=offsets[i];CHECK(!reject(bad,BAD));}
 for(uint64_t op=0x100;op<=0x108;op++){bad=base;bad.words[0]=op;bad.words[2]=61441;CHECK(!reject(bad,BAD));bad=base;bad.words[0]=op;bad.words[6]=1;CHECK(!reject(bad,op==0x101?STALE:BAD));}
 const uint64_t operations[]={0x109,0x10000,UINT64_MAX};for(unsigned i=0;i<3;i++){bad=base;bad.words[0]=operations[i];CHECK(!reject(bad,BAD));}
 bad=base;bad.words[1]=1;CHECK(!reject(bad,BAD));bad=base;bad.words[2]=1;CHECK(!reject(bad,BAD));bad=base;bad.words[0]=0x101;bad.words[1]=4096;bad.words[6]=fsr_generation();CHECK(!reject(bad,BAD));
 bad=base;bad.words[0]=0x101;bad.words[1]=1;CHECK(!reject(bad,STALE));
 shell[0]='x';CHECK(!reject(base,BAD));shell[0]='/';peer=4;desktop[0]='x';CHECK(!reject(base,BAD));desktop[0]='/';peer=1;
 const uint64_t peers[]={0,2,3,5,UINT64_MAX};for(unsigned i=0;i<5;i++){peer=peers[i];CHECK(!reject(base,BAD));}peer=1;
 fsr_set_generation(UINT64_MAX);for(uint64_t op=0x103;op<=0x108;op++){bad=base;bad.words[0]=op;CHECK(!reject(bad,STALE));}fsr_set_generation(1);return 0;
}
static int routes_and_append(void){
 Message r,reply;memset(shell,0xa5,65536);memset(desktop,0x5a,65536);r=request(0x102,"/README.TXT");r.words[2]=100;memcpy(before_desktop,desktop,65536);uint64_t before=reads;peer=1;CHECK(fsr_operate(&r,&reply)==0&&reply.words[1]==34&&reads>before&&!memcmp(shell+DATA,"DongOS FAT32 persistence fixture.\n",34)&&!memcmp(desktop,before_desktop,65536));
 memcpy(before_shell,shell,65536);peer=4;r=request(0x102,"/README.TXT");memcpy(before_shell,shell,65536);r.words[2]=100;CHECK(fsr_operate(&r,&reply)==0&&reply.words[1]==34&&!memcmp(desktop+DATA,"DongOS FAT32 persistence fixture.\n",34)&&!memcmp(shell,before_shell,65536));
 peer=1;r=request(0x104,"/append 测试.txt");CHECK(fsr_operate(&r,&reply)==0&&fsr_generation()==2);r=request(0x108,"/append 测试.txt");r.words[2]=5;memcpy(shell+DATA,"first",5);uint64_t calls=peer_calls;CHECK(fsr_operate(&r,&reply)==0&&reply.words[1]==5&&peer_calls==calls+1&&fsr_generation()==3);
 r=request(0x108,"/append 测试.txt");r.words[2]=7;memcpy(shell+DATA," second",7);calls=peer_calls;CHECK(fsr_operate(&r,&reply)==0&&reply.words[1]==7&&peer_calls==calls+1&&fsr_generation()==4);
 r=request(0x102,"/append 测试.txt");r.words[2]=32;CHECK(fsr_operate(&r,&reply)==0&&reply.words[1]==12&&!memcmp(shell+DATA,"first second",12));
 r=request(0x101,"/");CHECK(fsr_operate(&r,&reply)==0&&reply.words[1]==1&&reply.words[7]==1&&u64(shell+DATA+48)==1&&u64(shell+DATA+56)==4);
 r.words[1]=1;r.words[6]=3;CHECK(!reject(r,STALE));r.words[6]=4;CHECK(fsr_operate(&r,&reply)==0&&reply.words[1]==1&&reply.words[7]==2);
 r=request(4,"");r.words[4]=0;r.words[5]=0;CHECK(fsr_operate(&r,&reply)==0);return 0;
}
static int records(void){
 PathEntry entry;Message reply;memset(&entry,0,sizeof entry);memcpy(entry.entry.name,"ALIAS~1 TXT",11);entry.entry.attributes=0x21;entry.entry.size=0xfedcba98;entry.name_length=1020;entry.has_lfn=1;for(unsigned i=0;i<1020;i++)entry.name[i]=(uint8_t)(0x41+i%26);
 memset(shell,0xa5,65536);fsr_set_generation(1234);fsr_record(&entry,4096,0x50000000,&reply);CHECK(u64(shell+DATA)==1100&&u64(shell+DATA+8)==1020&&u64(shell+DATA+16)==0x21&&u64(shell+DATA+24)==0xfedcba98&&u64(shell+DATA+32)==1&&u64(shell+DATA+40)==1&&u64(shell+DATA+48)==4096&&u64(shell+DATA+56)==1234);CHECK(!memcmp(shell+DATA+64,entry.entry.name,11)&&!memcmp(shell+DATA+80,entry.name,1020));for(unsigned i=75;i<80;i++){CHECK(shell[DATA+i]==0);}CHECK(shell[DATA-1]==0xa5&&shell[DATA+1100]==0xa5&&reply.words[4]==1100&&reply.words[7]==4096);
 memset(&entry,0,sizeof entry);entry.entry.name[0]=0x82;memcpy(entry.entry.name+1,"AWOEM  TXT",10);memset(desktop,0x5a,65536);fsr_record(&entry,0,0x52000000,&reply);CHECK(u64(desktop+DATA)==80&&u64(desktop+DATA+8)==0&&u64(desktop+DATA+32)==0&&u64(desktop+DATA+40)==2&&!memcmp(desktop+DATA+64,entry.entry.name,11)&&desktop[DATA+80]==0x5a);return 0;
}
static uint8_t*client(void){return peer==1?shell:peer==4?desktop:app;}
static Message hrequest(uint64_t op,uint64_t token,uint64_t offset,uint64_t count,uint64_t rights,const char*path){
 Message r={{op,token,offset,count,rights,0,3,0}};if(path){r.words[5]=strlen(path);memcpy(client(),path,strlen(path));}return r;
}
static int hrejected(Message r,uint64_t error){
 Message reply;uint64_t rr=reads,ww=writes,ff=flushes,gg=fsr_generation();CHECK(fsr_operate(&r,&reply)==error&&reply.words[0]==error);CHECK(reads==rr&&writes==ww&&flushes==ff&&fsr_generation()==gg);CHECK(reply.words[5]==3&&reply.words[6]==gg);for(unsigned i=1;i<8;i++){if(i!=5&&i!=6){CHECK(reply.words[i]==0);}}return 0;
}
static int handle_grants(void){
 const uint64_t denied=0x050c0003ULL,invalid=0x050c0002ULL;Message r,reply;peer=1;grant=1023;
 r=hrequest(0x200,0,0,0,1023,NULL);CHECK(!fsr_operate(&r,&reply));uint64_t root=reply.words[1];CHECK(root>>32==1&&reply.words[2]==1023&&reply.words[5]==3);
 for(unsigned bit=0;bit<64;bit++){r=hrequest(0x204,root,0,0,0,NULL);r.words[7]=1ULL<<bit;CHECK(!hrejected(r,BAD));}
 r=hrequest(0x201,root,0,0,255,"/README.TXT");CHECK(!fsr_operate(&r,&reply));uint64_t readme=reply.words[1];
 r=hrequest(0x202,readme,0,0,3,NULL);CHECK(!fsr_operate(&r,&reply));uint64_t reduced=reply.words[1];r=hrequest(0x207,reduced,0,1,0,NULL);CHECK(!hrejected(r,denied));
 r=hrequest(0x202,reduced,0,0,7,NULL);CHECK(!hrejected(r,denied));
 peer=4;r=hrequest(0x206,readme,0,34,0,NULL);CHECK(!hrejected(r,denied));peer=1;
 r=hrequest(0x206,reduced,0,100,0,NULL);CHECK(!fsr_operate(&r,&reply)&&reply.words[1]==34&&!memcmp(shell+DATA,"DongOS FAT32 persistence fixture.\n",34));
 r=hrequest(0x203,reduced,0,0,0,NULL);CHECK(!fsr_operate(&r,&reply));r=hrequest(0x204,reduced,0,0,0,NULL);CHECK(!hrejected(r,invalid));
 // Directory-scoped authority cannot escape using absolute or dotdot paths.
 r=hrequest(0x20c,root,0,0,0,"/Granted Directory");CHECK(!fsr_operate(&r,&reply));r=hrequest(0x204,readme,0,0,0,NULL);CHECK(!hrejected(r,invalid));
 r=hrequest(0x201,root,0,0,1023,"/Granted Directory");CHECK(!fsr_operate(&r,&reply));uint64_t directory=reply.words[1];
 r=hrequest(0x201,directory,0,0,3,"../README.TXT");CHECK(!hrejected(r,denied));r=hrequest(0x201,directory,0,0,3,"/README.TXT");CHECK(!hrejected(r,denied));
 r=hrequest(0x20b,directory,0,0,0,"actual handle.txt");CHECK(!fsr_operate(&r,&reply));r=hrequest(0x205,directory,0,0,0,NULL);CHECK(!hrejected(r,invalid));
 r=hrequest(0x201,root,0,0,255,"/Granted Directory/actual handle.txt");CHECK(!fsr_operate(&r,&reply));uint64_t file=reply.words[1];
 memcpy(shell+DATA,"first",5);r=hrequest(0x207,file,0,5,0,NULL);CHECK(!fsr_operate(&r,&reply)&&reply.words[1]==5);
 memcpy(shell+DATA," second",7);r=hrequest(0x208,file,0,7,0,NULL);CHECK(!fsr_operate(&r,&reply)&&reply.words[1]==7);
 r=hrequest(0x206,file,0,100,0,NULL);CHECK(!fsr_operate(&r,&reply)&&reply.words[1]==12&&!memcmp(shell+DATA,"first second",12));
 r=hrequest(0x209,file,5,0,0,NULL);CHECK(!fsr_operate(&r,&reply));r=hrequest(0x204,file,0,0,0,NULL);CHECK(!fsr_operate(&r,&reply)&&reply.words[2]==5&&u64(shell+DATA+24)==5);
 r=hrequest(0x20a,file,0,0,0,NULL);CHECK(!fsr_operate(&r,&reply));r=hrequest(0x20b,root,0,0,0,"/Granted Directory/actual handle.txt");CHECK(!fsr_operate(&r,&reply));r=hrequest(0x206,file,0,12,0,NULL);CHECK(!hrejected(r,invalid));
 // A regular application has only a kernel grant of 395. All legacy/path
 // bypasses, root-rights escalation and writes using somebody else's token fail.
 peer=8;grant=395;r=hrequest(0x200,0,0,0,1023,NULL);CHECK(!hrejected(r,denied));r=hrequest(0x200,0,0,0,395,NULL);CHECK(!fsr_operate(&r,&reply));uint64_t ro_root=reply.words[1];
 r=hrequest(0x201,ro_root,0,0,3,"/README.TXT");CHECK(!fsr_operate(&r,&reply));uint64_t ro_file=reply.words[1];
 r=hrequest(0x206,ro_file,0,34,0,NULL);CHECK(!fsr_operate(&r,&reply)&&reply.words[1]==34&&!memcmp(app+DATA,"DongOS FAT32 persistence fixture.\n",34));
 r=hrequest(0x207,ro_file,0,1,0,NULL);CHECK(!hrejected(r,denied));r=hrequest(0x201,ro_root,0,0,7,"/README.TXT");CHECK(!hrejected(r,denied));
 r=request(0x103,"/README.TXT");uint64_t rr=reads,ww=writes;CHECK(fsr_operate(&r,&reply)==denied&&reads==rr&&writes==ww);r=request(3,"README.TXT");r.words[5]=0;r.words[4]=16;CHECK(fsr_operate(&r,&reply)==denied&&reads==rr&&writes==ww);
 // PID reuse revokes old grants; service-epoch change rejects every old token.
 caller_epoch[8]=2;r=hrequest(0x206,ro_file,0,34,0,NULL);CHECK(!hrejected(r,invalid));r=hrequest(0x200,0,0,0,395,NULL);CHECK(!fsr_operate(&r,&reply));uint64_t new_root=reply.words[1];CHECK(new_root!=ro_root);
 departures[8]=1;r=hrequest(0x204,new_root,0,0,0,NULL);CHECK(!fsr_operate(&r,&reply));departures[8]=2;r=hrequest(0x204,new_root,0,0,0,NULL);CHECK(!hrejected(r,invalid));caller_epoch[8]=3;
 fs_epoch=2;r=hrequest(0x204,new_root,0,0,0,NULL);CHECK(!hrejected(r,invalid));r=hrequest(0x200,0,0,0,395,NULL);CHECK(!fsr_operate(&r,&reply)&&reply.words[1]>>32==2);
 peer=1;grant=1023;r=hrequest(0x200,0,0,0,1023,NULL);CHECK(!fsr_operate(&r,&reply));root=reply.words[1];r=hrequest(0x201,root,0,0,7,"/README.TXT");CHECK(!fsr_operate(&r,&reply));file=reply.words[1];
 grant=395;r=hrequest(0x207,file,0,1,0,NULL);CHECK(!hrejected(r,denied));grant=1023;r=request(4,"");r.words[4]=0;r.words[5]=0;CHECK(!fsr_operate(&r,&reply));return 0;
}
static void*map_channel(uint8_t*address){
#ifdef _WIN32
 return VirtualAlloc(address,65536,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
#else
 return mmap(address,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);
#endif
}
int main(int argc,char**argv){
 if(argc!=2){return 2;}if(map_channel(shell)!=shell||map_channel(block)!=block||map_channel(desktop)!=desktop||map_channel(app)!=app){return 3;}disk=fopen(argv[1],"r+b");if(!disk){return 4;}fseek(disk,0,SEEK_END);sectors=(uint64_t)ftell(disk)/512;
 boot.words[0]=1;boot.words[2]=11;boot.words[4]=22;boot.words[6]=0x50000000;boot.words[7]=65536;CHECK(fsr_setup()==0);memset(shell,0xa5,65536);memset(desktop,0x5a,65536);CHECK(!guards()&&!routes_and_append()&&!handle_grants()&&!records()&&!bad_syscall);fclose(disk);printf("FS service native checks passed %llu reads=%llu writes=%llu flushes=%llu peers=%llu\n",(unsigned long long)checks,(unsigned long long)reads,(unsigned long long)writes,(unsigned long long)flushes,(unsigned long long)peer_calls);return 0;
}
