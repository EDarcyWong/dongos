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
typedef struct {uint64_t words[8];} Message;
typedef struct {uint64_t words[16];} Boot;
typedef struct {uint64_t version,id,dependencies,restarts,timeout,flags,image,length;uint8_t name[32];uint64_t reserved[4];} Config;
typedef struct {uint64_t version,configuration,process,generation,state,status,sequence,argument;} Snapshot;
typedef struct {uint64_t version,sequence,configuration,generation,process,state,status,flags;} Event;
extern uint64_t SYSV shc_setup(const Boot*),shc_command(const uint8_t*,uint64_t);
static uint8_t*channel=(uint8_t*)(uintptr_t)0x50000000;
static char output[100000];static uint64_t output_size,checks,bad,sequence=20,events_read,fs_generation=1,fs_epoch=1,spawns,executions,opens,closes,read_bytes,root_requests,append_failures,restarts;
static Boot boot;
static Config configs[32];static Snapshot states[32];static Event events[64];static unsigned events_count;
static uint64_t catalog_count=18,incarnation=1;
enum { MAX_EXEC_IMAGE=2*1024*1024 };
typedef struct {char path[1024];uint8_t content[MAX_EXEC_IMAGE+1];uint64_t size,live,directory;} File;
typedef struct {uint64_t live,generation,rights,target,root;} Handle;
static File files[16];static Handle handles[32];
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"SHELL_COMMAND_ASSERT line %u checks=%llu bad=%llu output=%s\n",__LINE__,(unsigned long long)checks,(unsigned long long)bad,output);return 1;}}while(0)
void SYSV __dong_panic(uint64_t code,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"unexpected panic %llu\n",(unsigned long long)code);exit(9);}
void SYSV shc_negative_hit(uint64_t kind){fprintf(stderr,"SHELL_COMMAND_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}
uint64_t SYSV svc_receive(uint64_t a,Message*b,uint64_t*c){(void)a;(void)b;(void)c;bad++;return 99;}
uint64_t SYSV svc_reply_wait(uint64_t a,uint64_t b,const Message*c,Message*d,uint64_t*e){(void)a;(void)b;(void)c;(void)d;(void)e;bad++;return 99;}
void SYSV svc_fence(void){}
static uint64_t htoken(unsigned slot){return (fs_epoch<<32)|(handles[slot].generation<<8)|(slot+1);}
static uint64_t issue(uint64_t target,uint64_t rights,uint64_t root){for(unsigned i=0;i<32;i++){if(!handles[i].live){if(!handles[i].generation)handles[i].generation=1;handles[i].live=1;handles[i].target=target;handles[i].rights=rights;handles[i].root=root;return htoken(i);}}bad++;return 0;}
static void invalidate(void){fs_generation++;for(unsigned i=0;i<32;i++){if(handles[i].live&&!handles[i].root){handles[i].live=0;handles[i].generation++;}}}
static uint64_t record(Message*out,unsigned file,uint64_t next){
 uint64_t*words=(uint64_t*)(void*)(channel+4096);const char*base=strrchr(files[file].path,'/');base=base&&base[1]?base+1:"/";size_t n=strlen(base);memset(words,0,80);words[0]=80+n;words[1]=n;words[2]=files[file].directory?16:0;words[3]=files[file].size;words[5]=1;words[6]=next;words[7]=fs_generation;memcpy((uint8_t*)words+64,"FIXTURE TXT",11);memcpy((uint8_t*)words+80,base,n);out->words[1]=1;out->words[2]=files[file].size;out->words[3]=words[2];out->words[4]=80+n;out->words[7]=next;return 0;
}
static uint64_t fs_call(const Message*r,Message*out){
 memset(out,0,sizeof *out);uint64_t op=r->words[0];if(op==1||op==4){out->words[5]=2;return 0;}
 out->words[5]=3;out->words[6]=fs_generation;if(r->words[6]!=3||r->words[7]){bad++;return 99;}
 if(op==0x200){if(r->words[4]!=1023){bad++;return 99;}root_requests++;out->words[1]=issue(0,1023,1);out->words[2]=1023;return 0;}
 unsigned slot=(unsigned)(r->words[1]&255);if(!slot||slot>32||!handles[slot-1].live||htoken(slot-1)!=r->words[1]){out->words[0]=0x050c0002;return 0;}Handle*h=&handles[slot-1];unsigned target=(unsigned)h->target;
 if(op==0x203){h->live=0;h->generation++;closes++;return 0;}
 if(op==0x201||op==0x20b||op==0x20c){char path[4097];size_t n=(size_t)r->words[5];if(n>4096){bad++;return 99;}memcpy(path,channel,n);path[n]=0;unsigned file=16;for(unsigned i=0;i<16;i++)if(files[i].live&&!strcmp(files[i].path,path)){file=i;break;}
  if(op==0x201){if(file==16){out->words[0]=0x05040006;return 0;}out->words[1]=issue(file,r->words[4],0);out->words[2]=r->words[4];opens++;return 0;}
  if(file!=16){out->words[0]=0x05040007;return 0;}for(file=1;file<16;file++)if(!files[file].live)break;if(file==16){bad++;return 99;}files[file].live=1;files[file].directory=op==0x20c;files[file].size=0;strcpy(files[file].path,path);invalidate();out->words[6]=fs_generation;return 0;
 }
 uint64_t needed=op==0x204?1:op==0x205?8:op==0x206?2:op==0x207||op==0x208?4:op==0x209?32:op==0x20a?64:0;
 if(!needed||(needed&~h->rights)){bad++;return 99;}if(h->rights!=needed&&h->rights!=3){bad++;return 99;}
 if(op==0x204){return record(out,target,0);}if(op==0x205){if(r->words[2]==0)return record(out,1,1);return 0;}
 if(op==0x206){uint64_t offset=r->words[2],count=r->words[3];if(offset>=files[target].size)count=0;else if(count>files[target].size-offset)count=files[target].size-offset;memcpy(channel+4096,files[target].content+offset,(size_t)count);out->words[1]=count;read_bytes+=count;return 0;}
 if(op==0x207||op==0x208){if(op==0x208&&append_failures){append_failures++;out->words[0]=0x050c0002;return 0;}uint64_t offset=op==0x208?files[target].size:r->words[2],count=r->words[3];if(count>160000-offset){bad++;return 99;}memcpy(files[target].content+offset,channel+4096,(size_t)count);if(offset+count>files[target].size)files[target].size=offset+count;out->words[1]=count;fs_generation++;out->words[6]=fs_generation;return 0;}
 if(op==0x209){if(r->words[2]>160000){bad++;return 99;}files[target].size=r->words[2];fs_generation++;out->words[6]=fs_generation;return 0;}
 if(op==0x20a){files[target].live=0;invalidate();out->words[6]=fs_generation;return 0;}bad++;return 99;
}
static void finish(unsigned id,uint64_t token,uint64_t state,uint64_t status){states[id].process=0;states[id].state=state;states[id].status=status;states[id].sequence=++sequence;events[events_count++]=(Event){1,sequence,id,states[id].generation,token,state,status,0};}
uint64_t SYSV svc_call(uint64_t number,uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e,uint64_t f){
 (void)e;(void)f;
 if(number==0x70){if(b>4096||b>sizeof output-output_size-1){bad++;return 99;}memcpy(output+output_size,(const void*)(uintptr_t)a,(size_t)b);output_size+=b;output[output_size]=0;return 0;}
 if(number==0x22&&a==11)return fs_call((const Message*)(uintptr_t)b,(Message*)(uintptr_t)c);
 if(number==0x80&&a==77&&b<catalog_count){memcpy((void*)(uintptr_t)c,&configs[b],sizeof(Config));if(d)memcpy((void*)(uintptr_t)d,&states[b],sizeof(Snapshot));return 0;}
 if(number==0x81&&a==77&&b>=7&&b<catalog_count&&b!=12&&b!=13){if(c!=states[b].generation){bad++;return 99;}spawns++;states[b].generation++;uint64_t token=(++incarnation<<8)|8;states[b].process=token;states[b].argument=d;states[b].state=1;states[b].status=0;states[b].sequence=++sequence;memcpy((void*)(uintptr_t)e,&states[b],sizeof(Snapshot));if(b==7)finish(7,token,3,d);else if(b==8)finish(8,token,4,14);return 0;}
 if(number==0x82&&a==77){for(unsigned i=0;i<events_count;i++)if(events[i].sequence>b){memcpy((void*)(uintptr_t)c,&events[i],sizeof(Event));events_read++;return 0;}return 0x05110005;}
 if(number==0x83&&a==77){for(unsigned i=7;i<catalog_count;i++)if(states[i].process==b){finish(i,b,5,c);return 0;}return 0x05110003;}
 if(number==0x87&&a==77){uint64_t value[8]={1,1,100,40,131104,0x123000,1,0};if(c||d||e||f){bad++;return 99;}memcpy((void*)(uintptr_t)b,value,sizeof value);return 0;}
 if(number==0x88&&a==77){if((b!=1&&b!=3)||c!=states[b].generation||d||e||f){bad++;return 99;}restarts++;return 0;}
 if(number==0x85&&a==77){const uint8_t*bytes=(const uint8_t*)(uintptr_t)b;if(!c||c>MAX_EXEC_IMAGE||c!=files[2].size||d!=42||memcmp(bytes,files[2].content,(size_t)c)){bad++;return 99;}executions++;states[12].generation++;states[12].process=0xabc001200ULL|states[12].generation;states[12].state=1;states[12].sequence=++sequence;memcpy((void*)(uintptr_t)e,&states[12],sizeof(Snapshot));finish(12,states[12].process,3,42);return 0;}
 bad++;return 99;
}
static int command(const char*line,const char*expected){output_size=0;output[0]=0;CHECK(!shc_command((const uint8_t*)line,strlen(line)));CHECK(strstr(output,expected)!=NULL);CHECK(!bad);return 0;}
int main(void){
#ifdef _WIN32
 CHECK(VirtualAlloc(channel,65536,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)==channel);
#else
 CHECK(mmap(channel,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==channel);
#endif
 static const char*names[]={"shell","fs","block","compositor","input","init","devmgr","echo","fault","waiter","ipc-peer","fs-reader","file-app","xhci","terminal","files","editor","settings"};
 for(unsigned i=0;i<32;i++){char extra[32];snprintf(extra,sizeof extra,"extra%u",i);const char*name=i<18?names[i]:extra;configs[i].version=1;configs[i].id=i;configs[i].length=strlen(name);memcpy(configs[i].name,name,configs[i].length);configs[i].flags=i==13?4:i>=7?8:7;states[i].version=1;states[i].configuration=i;states[i].generation=1;states[i].state=i>=7?0:2;states[i].process=i<7?257+i:0;}
 files[0].live=1;files[0].directory=1;strcpy(files[0].path,"/");files[1].live=1;strcpy(files[1].path,"/README.TXT");memcpy(files[1].content,"fixture",7);files[1].size=7;files[2].live=1;strcpy(files[2].path,"/binary.elf");files[2].size=150000;for(unsigned i=0;i<150000;i++)files[2].content[i]=(uint8_t)(i*73+19);
 boot.words[0]=1;boot.words[3]=11;boot.words[8]=77;boot.words[13]=18;CHECK(!shc_setup(&boot));
 CHECK(!command("cat README.TXT","fixture\r\n"));fs_epoch++;memset(handles,0,sizeof handles);CHECK(!command("cat README.TXT","fixture\r\n"));CHECK(root_requests==2);
 CHECK(!command("ls /","README.TXT 7"));CHECK(!command("write test.txt payload","WRITE OK"));CHECK(!command("append test.txt extra","APPEND OK"));CHECK(!command("cat test.txt","payloadextra"));append_failures=1;CHECK(!command("append test.txt unsafe-retry","ERROR 0x00000000050c0002"));CHECK(append_failures==2);append_failures=0;CHECK(!command("cat test.txt","payloadextra"));
 CHECK(!command("truncate test.txt 7","TRUNCATE OK"));CHECK(!command("cat test.txt","payload\r\n"));CHECK(!command("rm test.txt","RM OK"));CHECK(!command("mkdir directory","MKDIR OK"));
 CHECK(!command("pcid","PCID enabled=1 switches=100 retained=40 cr4=131104 root=1191936 incarnation=1"));CHECK(!command("pcid extra","ERROR 0x0000000005110001"));CHECK(!command("restart block","ERROR 0x0000000005110001"));CHECK(!command("restart compositor extra","ERROR 0x0000000005110001"));CHECK(!command("restart compositor","RESTART OK compositor"));CHECK(!command("restart fs","RESTART REQUEST fs"));CHECK(restarts==2);
 CHECK(!command("ps","PROCESS file-app id=12"));CHECK(!command("run echo","RUN OK echo"));uint64_t old_echo=events[events_count-1].process;CHECK(states[7].process==0);CHECK(!command("wait","WAIT OK"));CHECK(strstr(output," state=3 status=0"));
 CHECK(!command("run echo 18446744073709551615","RUN OK echo"));char old_wait[80];snprintf(old_wait,sizeof old_wait,"wait %llu",(unsigned long long)old_echo);CHECK(!command(old_wait,"state=3 status=0"));CHECK(events_read==1);CHECK(!command("wait","state=3 status=18446744073709551615"));CHECK(!command("run echo 18446744073709551616","ERROR 0x0000000005110001"));CHECK(!command("run shell","ERROR 0x0000000004010003"));CHECK(!command("run file-app","ERROR 0x0000000004010003"));
 CHECK(!command("run fault","RUN OK fault"));CHECK(!command("wait","state=4 status=14"));CHECK(!command("run waiter","RUN OK waiter"));char kill[80];snprintf(kill,sizeof kill,"kill %llu",(unsigned long long)states[9].process);CHECK(!command(kill,"KILL OK"));CHECK(!command("wait","state=5 status=0"));
 CHECK(!command("exec binary.elf 42","EXEC OK binary.elf"));CHECK(executions==1);CHECK(!command("wait","state=3 status=42"));CHECK(!command("exec missing.elf","ERROR 0x0000000005040006"));CHECK(!command("wait 1","ERROR 0x0000000005110003"));
 // Cross the old 256 KiB cap, then exercise the exact new cap through real
 // production chunk reads. The model compares every byte passed to EXEC.
 const uint64_t lengths[]={262145,1048577,MAX_EXEC_IMAGE};
 for(unsigned k=0;k<sizeof lengths/sizeof lengths[0];k++){
  files[2].size=lengths[k];for(uint64_t i=0;i<files[2].size;i++)files[2].content[i]=(uint8_t)(i*73+19);
  uint64_t before_exec=executions,before_read=read_bytes;
  CHECK(!command("exec binary.elf 42","EXEC OK binary.elf"));CHECK(executions==before_exec+1);CHECK(read_bytes==before_read+files[2].size);
  CHECK(!command("wait","state=3 status=42"));
 }
 files[2].size=MAX_EXEC_IMAGE+1;
 uint64_t before_exec=executions,before_read=read_bytes,before_close=closes;
 CHECK(!command("exec binary.elf 42","ERROR 0x0000000005110001"));
 CHECK(executions==before_exec&&read_bytes==before_read&&closes==before_close+1);
 files[2].size=150000;
 unsigned live=0;for(unsigned i=0;i<32;i++)live+=(unsigned)handles[i].live;CHECK(live==1&&spawns==4&&opens>=10&&closes>=10&&read_bytes>=150000);
 CHECK(!command("ps","PROCESS settings id=17"));CHECK(strstr(output,"PROCESS editor id=16"));
 CHECK(!command("run xhci","ERROR 0x0000000004010003"));
 CHECK(!command("run settings","RUN OK settings"));CHECK((states[17].process&255)==8);
 snprintf(kill,sizeof kill,"kill %llu",(unsigned long long)states[17].process);CHECK(!command(kill,"KILL OK"));CHECK(!command("wait","state=5 status=0"));
 catalog_count=32;boot.words[13]=32;CHECK(!command("ps","PROCESS extra31 id=31"));CHECK(!strstr(output,"id=32"));
 boot.words[13]=33;CHECK(!command("ps","ERROR 0x0000000005110001"));
 catalog_count=18;boot.words[13]=18;CHECK(!command("ps","PROCESS settings id=17"));
 printf("Shell production command checks passed checks=%llu opens=%llu closes=%llu readbytes=%llu events=%llu\n",(unsigned long long)checks,(unsigned long long)opens,(unsigned long long)closes,(unsigned long long)read_bytes,(unsigned long long)events_read);return 0;
}
