#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
#define BAD 0x05040001ULL
#define UNSUPPORTED 0x05040003ULL
#define IO 0x05040004ULL
#define CORRUPT 0x05040005ULL
#define MISSING 0x05040006ULL
#define EXISTS 0x05040007ULL
#define RO 0x05040009ULL
#define NEEDS_CHECK 0x0504000aULL
#define BUSY 0x0504000bULL
typedef struct{uint64_t context,capacity,max_transfer;uint64_t(SYSV*read)(uint64_t,uint64_t,uint64_t,uint8_t*);uint64_t(SYSV*write)(uint64_t,uint64_t,uint64_t,const uint8_t*);uint64_t(SYSV*flush)(uint64_t);} Device;
typedef struct{const Device*device;uint64_t ready,busy,failed,read_only,dirty,total,spc,reserved,fat_sectors,data_start,clusters,root,fsinfo,backup;} Volume;
typedef struct{uint8_t name[11],attributes;uint64_t cluster,size,sector,offset;} Dir;
typedef struct{Dir entry;uint64_t name_length,has_lfn,raw_index,first_index,group_count;uint8_t name[1020];} PathEntry;
extern void SYSV fpp_sizes(uint64_t*),fpp_reset(Volume*);
extern uint64_t SYSV fpp_mount(Volume*,const Device*,void*),fpp_flush(Volume*,void*);
extern uint64_t SYSV fpp_stat(Volume*,void*,void*,const char*,uint64_t,PathEntry*);
extern uint64_t SYSV fpp_list(Volume*,void*,void*,const char*,uint64_t,uint64_t,PathEntry*,uint64_t*);
extern uint64_t SYSV fpp_create(Volume*,void*,void*,const char*,uint64_t),fpp_mkdir(Volume*,void*,void*,const char*,uint64_t),fpp_remove(Volume*,void*,void*,const char*,uint64_t);
extern uint64_t SYSV fpp_truncate(Volume*,void*,void*,const char*,uint64_t,uint64_t);
extern uint64_t SYSV fpp_read(Volume*,void*,void*,const char*,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*),fpp_write(Volume*,void*,void*,const char*,uint64_t,uint64_t,const uint8_t*,uint64_t,uint64_t*);
typedef struct{uint8_t*base,*value;uint64_t length;} Guard;
static Guard gv,gw,gx;
#define V ((Volume*)gv.value)
#define W ((void*)gw.value)
#define X ((void*)gx.value)
static struct{FILE*disk,*journal;uint64_t sectors,reads,writes,flushes,fail_read,fail_write,fail_flush,fail_data_read,reenter,hit_reenter,bad;} io;
static Device device;
static uint64_t checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"FAT paths check failed line %u case=%s\n",__LINE__,scenario);return 1;}}while(0)
static const char*scenario;
#define CREATE(p) fpp_create(V,W,X,p,strlen(p))
#define MKDIR(p) fpp_mkdir(V,W,X,p,strlen(p))
#define REMOVE(p) fpp_remove(V,W,X,p,strlen(p))
#define STAT(p,e) fpp_stat(V,W,X,p,strlen(p),e)
#define READ(p,o,b,n,g) fpp_read(V,W,X,p,strlen(p),o,b,n,g)
#define WRITE(p,o,b,n,g) fpp_write(V,W,X,p,strlen(p),o,b,n,g)
#define TRUNCATE(p,n) fpp_truncate(V,W,X,p,strlen(p),n)
void SYSV __dong_panic(uint64_t code,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"FAT paths unexpected panic %x\n",(unsigned)code);exit(9);}
static int all(const void*p,size_t n,uint8_t value){const uint8_t*b=p;for(size_t i=0;i<n;i++)if(b[i]!=value)return 0;return 1;}
static int raw_read(uint64_t lba,uint8_t*out){return lba<io.sectors&&!fseek(io.disk,(long)(lba*512),SEEK_SET)&&fread(out,1,512,io.disk)==512;}
static uint64_t SYSV disk_read(uint64_t ctx,uint64_t lba,uint64_t n,uint8_t*out){
 (void)ctx;uint8_t bytes[512];io.reads++;
 if(n!=1||lba>=io.sectors){io.bad++;return 99;}
 if(io.reenter){PathEntry item;memset(&item,0xa5,sizeof item);io.reenter=0;if(STAT("/",&item)!=BUSY||!all(&item,sizeof item,0xa5))io.bad++;else io.hit_reenter++;}
 if((io.fail_read&&io.reads==io.fail_read)||(io.fail_data_read&&lba==io.fail_data_read))return 71;
 if(!raw_read(lba,bytes)){return 72;}memcpy(out,bytes,512);return 0;
}
static uint64_t SYSV disk_write(uint64_t ctx,uint64_t lba,uint64_t n,const uint8_t*input){
 (void)ctx;uint8_t before[512];io.writes++;
 if(n!=1||lba>=io.sectors){io.bad++;return 99;}
 if(io.fail_write&&io.writes==io.fail_write)return 73;
 if(!raw_read(lba,before))return 74;
 if(fwrite(&lba,8,1,io.journal)!=1||fwrite(before,512,1,io.journal)!=1||fwrite(input,512,1,io.journal)!=1)return 75;
 if(fseek(io.disk,(long)(lba*512),SEEK_SET)||fwrite(input,512,1,io.disk)!=1){return 76;}return 0;
}
static uint64_t SYSV disk_flush(uint64_t ctx){(void)ctx;io.flushes++;if(io.fail_flush&&io.flushes==io.fail_flush)return 77;return fflush(io.disk)||fflush(io.journal)?78:0;}
static int mount(void){fpp_reset(V);return (int)fpp_mount(V,&device,W);}
static int remount(const char*path){CHECK(!fclose(io.disk));io.disk=fopen(path,"r+b");CHECK(io.disk!=NULL);return mount();}
static int guards(void){Guard*items[]={&gv,&gw,&gx};for(unsigned i=0;i<3;i++){Guard*g=items[i];CHECK(all(g->base,32,0xa5)&&all(g->value+g->length,32,0xa5));}CHECK(!io.bad);return 0;}
static int bad_stat(const char*p,uint64_t expected){PathEntry item;memset(&item,0xa5,sizeof item);CHECK(STAT(p,&item)==expected&&all(&item,sizeof item,0xa5)&&V->busy==0);return 0;}
static int read_expected(const char*p,const uint8_t*bytes,size_t n){uint8_t output[2200];uint64_t got=0x123456789abcdefULL;memset(output,0xa5,sizeof output);CHECK(n<=sizeof(output)-64);CHECK(READ(p,0,output+32,sizeof(output)-64,&got)==0&&got==n&&!memcmp(output+32,bytes,n));CHECK(all(output,32,0xa5)&&all(output+32+n,sizeof(output)-32-n,0xa5));return 0;}
static int fixture_case(void){
 uint8_t expected[1300],child[850];PathEntry item;uint64_t present=99;
 CHECK(mount()==0&&V->ready==1&&V->read_only==0&&io.hit_reenter==1);
 for(unsigned i=0;i<1300;i++)expected[i]=(uint8_t)(i*19+37);
 for(unsigned i=0;i<850;i++)child[i]=(uint8_t)(i*11+5);
 CHECK(!read_expected("/跨簇😀独立磁盘验证文件.txt",expected,sizeof expected));
 CHECK(!read_expected("/crossc~1.txt",expected,sizeof expected));
 CHECK(!read_expected("/文档与 Space/nested 资料 😀.txt",(const uint8_t*)"子目录 UTF-8 / UTF-16 😀\n",strlen("子目录 UTF-8 / UTF-16 😀\n")));
 CHECK(!read_expected("/DOCUME~1/childf~1/SPARSE.BIN",child,sizeof child));
 CHECK(STAT("//文档与 Space/ChildFolder/.././nested 资料 😀.txt",&item)==0&&item.has_lfn==1&&item.name_length==strlen("nested 资料 😀.txt")&&!memcmp(item.name,"nested 资料 😀.txt",item.name_length));
 CHECK(STAT("/文档与 Space/目录跨簇长文件名数据.bin",&item)==0&&item.first_index==15&&item.raw_index>=16);
 CHECK(!bad_stat("/missing/../README.TXT",MISSING));
 CHECK(!bad_stat("/README.TXT/../README.TXT",UNSUPPORTED));
 CHECK(!bad_stat("/README.TXT/.",UNSUPPORTED));
 CHECK(!bad_stat("/README.TXT/",UNSUPPORTED));
 CHECK(!bad_stat("/../README.TXT",BAD));
 CHECK(!bad_stat("/文档与 Space/../../README.TXT",BAD));
 CHECK(!bad_stat("/\xc0\xaf",BAD));
 char raw_path[4098];raw_path[0]='/';for(unsigned i=0;i<1300;i++){raw_path[1+i*2]='.';raw_path[2+i*2]='/';}memcpy(raw_path+2601,"README.TXT",11);CHECK(STAT(raw_path,&item)==0&&item.entry.size==34);
 memset(raw_path,'x',4097);raw_path[0]='/';raw_path[4097]=0;CHECK(!bad_stat(raw_path,BAD));
 unsigned listed=0;for(uint64_t i=0;i<12;i++){memset(&item,0xa5,sizeof item);present=99;CHECK(fpp_list(V,W,X,"/文档与 Space",strlen("/文档与 Space"),i,&item,&present)==0);if(!present){CHECK(all(&item,sizeof item,0xa5));break;}CHECK(item.entry.name[0]!='.');listed++;}CHECK(listed==3);
 uint64_t writes=io.writes;CHECK(REMOVE("/文档与 Space")==UNSUPPORTED&&io.writes==writes);
 return guards();
}
static int corrupt_case(void){CHECK(mount()==CORRUPT&&V->ready==0&&V->busy==0);return guards();}
static int fallback_case(void){
 uint8_t expected[1300];PathEntry item;CHECK(mount()==0&&V->read_only==1);for(unsigned i=0;i<1300;i++)expected[i]=(uint8_t)(i*19+37);
 CHECK(STAT("/CROSSC~1.TXT",&item)==0&&item.has_lfn==0);CHECK(!read_expected("/CROSSC~1.TXT",expected,sizeof expected));CHECK(!bad_stat("/跨簇😀独立磁盘验证文件.txt",MISSING));
 uint64_t writes=io.writes;CHECK(CREATE("/NO.TXT")==RO&&MKDIR("/NO")==RO&&REMOVE("/CROSSC~1.TXT")==RO&&io.writes==writes);return guards();
}
static int dirty_case(void){CHECK(mount()==0&&V->read_only==1&&V->dirty==1);uint64_t writes=io.writes;CHECK(CREATE("/NO.TXT")==RO&&io.writes==writes);return guards();}
static void alias_path(char*out,const uint8_t*alias){size_t n=0;out[n++]='/';memcpy(out+n,"Projects/图形 桌面/",strlen("Projects/图形 桌面/"));n+=strlen("Projects/图形 桌面/");for(unsigned i=0;i<8&&alias[i]!=' ';i++)out[n++]=(char)alias[i];if(alias[8]!=' '){out[n++]='.';for(unsigned i=8;i<11&&alias[i]!=' ';i++)out[n++]=(char)alias[i];}out[n]=0;}
static const char*FILE_PATH="/Projects/图形 桌面/多语言 report 😀.txt";
static int lifecycle(const char*path){
 uint8_t data[1300],expected[1800],tail[29];uint64_t got=99;PathEntry first,second;char alias[256];
 CHECK(mount()==0&&V->read_only==0&&MKDIR("/Projects")==0&&MKDIR("/Projects/图形 桌面")==0&&MKDIR("/projects")==EXISTS);
 CHECK(CREATE(FILE_PATH)==0&&CREATE("/projects/图形 桌面/多语言 REPORT 😀.TXT")==EXISTS);
 for(unsigned i=0;i<sizeof data;i++){data[i]=(uint8_t)(i*23+41);}for(unsigned i=0;i<sizeof tail;i++){tail[i]=(uint8_t)(i*9+3);}
 CHECK(WRITE(FILE_PATH,0,data,sizeof data,&got)==0&&got==sizeof data);
 CHECK(TRUNCATE(FILE_PATH,300)==0&&TRUNCATE(FILE_PATH,1800)==0);memset(expected,0,sizeof expected);memcpy(expected,data,300);memcpy(expected+1600,tail,sizeof tail);
 CHECK(WRITE(FILE_PATH,1600,tail,sizeof tail,&got)==0&&got==sizeof tail);CHECK(!read_expected(FILE_PATH,expected,sizeof expected));
 CHECK(STAT(FILE_PATH,&first)==0&&first.has_lfn==1);alias_path(alias,first.entry.name);CHECK(CREATE(alias)==EXISTS&& !read_expected(alias,expected,sizeof expected));
 CHECK(CREATE("/Projects/图形 桌面/Project documentation alpha.txt")==0&&CREATE("/Projects/图形 桌面/Project documentation beta.txt")==0);
 CHECK(STAT("/Projects/图形 桌面/Project documentation alpha.txt",&first)==0&&STAT("/Projects/图形 桌面/Project documentation beta.txt",&second)==0&&memcmp(first.entry.name,second.entry.name,11));
 CHECK(CREATE("/Projects/图形 桌面/remove this long filename.txt")==0&&WRITE("/Projects/图形 桌面/remove this long filename.txt",0,data,700,&got)==0&&REMOVE("/Projects/图形 桌面/remove this long filename.txt")==0);
 CHECK(MKDIR("/Projects/图形 桌面/remove directory")==0&&REMOVE("/Projects/图形 桌面/remove directory")==0);
 CHECK(REMOVE("/Projects")==UNSUPPORTED);
 char maximum[320];size_t prefix=strlen("/Projects/图形 桌面/");memcpy(maximum,"/Projects/图形 桌面/",prefix);memset(maximum+prefix,'q',255);maximum[prefix+255]=0;CHECK(CREATE(maximum)==0);maximum[prefix+255]='q';maximum[prefix+256]=0;CHECK(CREATE(maximum)==BAD);
 char bounded[1100];size_t used=0;for(unsigned level=0;level<4;level++){bounded[used++]='/';memset(bounded+used,'r',200);used+=200;bounded[used]=0;CHECK(MKDIR(bounded)==0);}bounded[used++]='/';memset(bounded+used,'s',219);used+=219;bounded[used]=0;CHECK(used==1024&&CREATE(bounded)==0);bounded[used++]='s';bounded[used]=0;uint64_t before=io.writes;CHECK(CREATE(bounded)==BAD&&io.writes==before);
 /* Force a complete 20-slot name group across sectors and directory clusters. */
 CHECK(fpp_flush(V,W)==0&&V->dirty==0&&remount(path)==0&&V->read_only==0);CHECK(!read_expected(FILE_PATH,expected,sizeof expected));
 CHECK(!bad_stat("/Projects/图形 桌面/remove this long filename.txt",MISSING));CHECK(!bad_stat("/Projects/图形 桌面/remove directory",MISSING));
 return guards();
}
static int failure_case(const char*path){
 PathEntry item;uint8_t data[1300],output[1400];uint64_t got=99;memset(data,0x72,sizeof data);CHECK(mount()==0);
 if(!strcmp(scenario,"read-failure")){memset(&item,0xa5,sizeof item);io.fail_read=io.reads+1;CHECK(STAT("/文档与 Space",&item)==IO&&all(&item,sizeof item,0xa5));io.fail_read=0;CHECK(STAT("/文档与 Space",&item)==0);}
 else if(!strcmp(scenario,"late-read-failure")){/* Output contract: count is never published, but bytes already copied may change. */
   CHECK(STAT("/跨簇😀独立磁盘验证文件.txt",&item)==0);io.fail_data_read=V->data_start+13-2;memset(output,0xa5,sizeof output);CHECK(READ("/跨簇😀独立磁盘验证文件.txt",0,output+32,1300,&got)==IO&&got==99&&all(output,32,0xa5)&&all(output+1332,sizeof(output)-1332,0xa5));io.fail_data_read=0;
 }else if(!strcmp(scenario,"flush-failure")){CHECK(MKDIR("/pending directory")==0);io.fail_flush=io.flushes+1;CHECK(fpp_flush(V,W)==IO&&V->failed==1&&CREATE("/NO.TXT")==NEEDS_CHECK);io.fail_flush=0;int result=remount(path);CHECK(result==CORRUPT||(result==0&&V->read_only==1));}
 else{CHECK(MKDIR("/write failure")==0&&CREATE("/write failure/pending long filename.txt")==0&&fpp_flush(V,W)==0);io.fail_write=io.writes+9;CHECK(WRITE("/write failure/pending long filename.txt",0,data,sizeof data,&got)==IO&&got==99&&V->failed==1);CHECK(CREATE("/NO.TXT")==NEEDS_CHECK);io.fail_write=0;int result=remount(path);CHECK(result==CORRUPT||(result==0&&V->read_only==1));}
 return guards();
}
static int fault_prefix_case(const char*path){
 char operation[24],boundary[24];unsigned point=0;uint8_t data[1300],sector[512];uint64_t got=99,result=BAD;PathEntry base;
 CHECK(sscanf(scenario,"fault-%23[^-]-%23[^-]-%u",operation,boundary,&point)==3&&point>0&&point<128);
 memset(data,0x53,sizeof data);CHECK(mount()==0&&MKDIR("/BASE")==0&&CREATE("/BASE/existing long filename.txt")==0&&WRITE("/BASE/existing long filename.txt",0,data,sizeof data,&got)==0&&fpp_flush(V,W)==0);
 /* FAT says bytes after the first 00 are unspecified. Deliberately make them
    plausible live entries; publishing any prefix must not expose them. */
 CHECK(STAT("/BASE",&base)==0);uint64_t directory_lba=V->data_start+(base.entry.cluster-2)*V->spc;CHECK(raw_read(directory_lba,sector));unsigned end=64;while(end<512&&sector[end]!=0)end+=32;CHECK(end+96<512);
 for(unsigned at=end+32;at<512;at+=32){memset(sector+at,0,32);memcpy(sector+at,"GHOST000TXT",11);sector[at+7]=(uint8_t)('A'+at/32);sector[at+11]=0x20;}CHECK(!fseek(io.disk,(long)(directory_lba*512),SEEK_SET)&&fwrite(sector,512,1,io.disk)==1&&!fflush(io.disk));
 io.writes=0;io.flushes=0;if(!strcmp(boundary,"write")){io.fail_write=point;}else{CHECK(!strcmp(boundary,"flush"));io.fail_flush=point;}
 if(!strcmp(operation,"create")){result=CREATE("/BASE/new long filename 😀.txt");}
 else if(!strcmp(operation,"mkdir")){result=MKDIR("/BASE/new directory 😀");}
 else if(!strcmp(operation,"remove")){result=REMOVE("/BASE/existing long filename.txt");}
 else if(!strcmp(operation,"truncate")){result=TRUNCATE("/BASE/existing long filename.txt",300);}
 uint64_t writes=io.writes,flushes=io.flushes;unsigned injected=result==IO;
 CHECK(result==0||result==IO);if(injected){CHECK(V->failed==1&&CREATE("/NO.TXT")==NEEDS_CHECK);}io.fail_write=0;io.fail_flush=0;
 if(!injected){CHECK(fpp_flush(V,W)==0);}
 int recovery=remount(path);CHECK(recovery==0||recovery==CORRUPT);
 if(injected&&recovery==0){CHECK(V->read_only==1||(!strcmp(boundary,"write")&&point==1));}
 printf("FAULT operation=%s boundary=%s point=%u writes=%llu flushes=%llu injected=%u recovery=%u readonly=%llu\n",operation,boundary,point,(unsigned long long)writes,(unsigned long long)flushes,injected,(unsigned)recovery,(unsigned long long)V->read_only);
 return guards();
}
int main(int argc,char**argv){
 if(argc!=4){return 2;}scenario=argv[2];uint64_t sizes[4];fpp_sizes(sizes);if(sizes[0]!=sizeof(Volume)||sizes[3]!=sizeof(PathEntry)||sizes[1]>131072||sizes[2]>131072)return 3;
 Guard*items[]={&gv,&gw,&gx};uint64_t lengths[]={sizes[0],sizes[1],sizes[2]};for(unsigned i=0;i<3;i++){items[i]->length=lengths[i];items[i]->base=malloc((size_t)lengths[i]+64);if(!items[i]->base)return 4;memset(items[i]->base,0xa5,(size_t)lengths[i]+64);items[i]->value=items[i]->base+32;memset(items[i]->value,0,(size_t)lengths[i]);}
 io.disk=fopen(argv[1],"r+b");io.journal=fopen(argv[3],"wb");if(!io.disk||!io.journal)return 5;fseek(io.disk,0,SEEK_END);io.sectors=(uint64_t)ftell(io.disk)/512;device=(Device){0,io.sectors,128,disk_read,disk_write,disk_flush};io.reenter=1;int result;
 if(!strcmp(scenario,"valid"))result=fixture_case();else if(!strcmp(scenario,"lifecycle"))result=lifecycle(argv[1]);else if(!strncmp(scenario,"fault-",6))result=fault_prefix_case(argv[1]);else if(!strncmp(scenario,"lfn-",4))result=fallback_case();else if(!strcmp(scenario,"dirty"))result=dirty_case();else if(strstr(scenario,"failure"))result=failure_case(argv[1]);else result=corrupt_case();
 fflush(io.disk);fflush(io.journal);fclose(io.disk);fclose(io.journal);if(result)return result;
 printf("FAT paths checks passed %llu reads=%llu writes=%llu flushes=%llu\n",(unsigned long long)checks,(unsigned long long)io.reads,(unsigned long long)io.writes,(unsigned long long)io.flushes);return 0;
}
