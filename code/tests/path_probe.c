#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif
#define ABI __attribute__((sysv_abi))
#define ARG UINT64_C(0x050a0001)
#define UTF UINT64_C(0x050a0002)
#define NAME UINT64_C(0x050a0003)
#define LONG UINT64_C(0x050a0004)
#define ESC UINT64_C(0x050a0005)
#define CWD UINT64_C(0x050a0006)
typedef struct {uint64_t length,components,directory_hint;uint8_t bytes[1024];} Path;
_Static_assert(sizeof(Path)==1048,"Path ABI");
extern ABI void path_sizes(uint64_t*);
extern ABI uint64_t path_name(const uint8_t*,size_t,uint64_t*);
extern ABI uint64_t path_normalize(const uint8_t*,size_t,const uint8_t*,size_t,Path*);
static uint64_t checks,names,paths,aliases,randoms;
static const char *scenario="start";
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"PATH_MODEL_ASSERT line %d: %s scenario=%s\n",__LINE__,#x,scenario);exit(1);}}while(0)
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected panic %llu\n",(unsigned long long)code);exit(99);}
ABI void path_negative_hit(uint64_t kind){fprintf(stderr,"PATH_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}

/* Independent Unicode Table 3-7 range rows, not the DG minimum-value decoder. */
typedef struct {unsigned low,high,second_low,second_high,count,mask;} Row;
static const Row rows[]={
 {0,0x7f,0,0,1,0x7f},{0xc2,0xdf,0x80,0xbf,2,31},
 {0xe0,0xe0,0xa0,0xbf,3,15},{0xe1,0xec,0x80,0xbf,3,15},
 {0xed,0xed,0x80,0x9f,3,15},{0xee,0xef,0x80,0xbf,3,15},
 {0xf0,0xf0,0x90,0xbf,4,7},{0xf1,0xf3,0x80,0xbf,4,7},
 {0xf4,0xf4,0x80,0x8f,4,7}};
static uint64_t scalar(const uint8_t*p,size_t n,size_t*at,uint32_t*out){
 size_t left=n-*at;const uint8_t*q=p+*at;
 for(size_t j=0;j<sizeof rows/sizeof rows[0];j++){
  const Row*r=&rows[j];if(q[0]<r->low||q[0]>r->high)continue;
  if(left<r->count)return UTF;
  if(r->count>1&&(q[1]<r->second_low||q[1]>r->second_high))return UTF;
  uint32_t cp=q[0]&r->mask;
  for(unsigned i=1;i<r->count;i++){if(q[i]<0x80||q[i]>0xbf)return UTF;cp=(cp<<6)|(q[i]&63);}
  *at+=r->count;*out=cp;return 0;
 }return UTF;
}
static int dot(const uint8_t*p,size_t n){return (n==1&&p[0]=='.')||(n==2&&p[0]=='.'&&p[1]=='.');}
static uint64_t model_name(const uint8_t*p,size_t n,uint64_t*out){
 if(n>1020)return LONG;
 if((n&&!p)||(uintptr_t)p>UINTPTR_MAX-n)return ARG;
 if(!n||dot(p,n)||p[0]==' '||p[n-1]==' '||p[n-1]=='.')return NAME;
 size_t at=0;uint64_t units=0;
 while(at<n){uint32_t cp=0;uint64_t error=scalar(p,n,&at,&cp);if(error)return error;
  if(cp<32||cp==0xffff||(cp<128&&strchr("\"*/:<>?\\|",(int)cp)))return NAME;
  units+=cp>=0x10000?2:1;if(units>255)return LONG;
 }*out=units;return 0;
}
typedef struct {const uint8_t*p;size_t n;} Part;
static size_t path_length(const Part*p,size_t count){size_t n=1;for(size_t i=0;i<count;i++)n+=p[i].n+(i!=0);return n;}
static uint64_t model_normalize(const uint8_t*cwd,size_t cn,const uint8_t*input,size_t n,Path*out){
 if(cn>1024||n>4096)return LONG;
 if((cn&&!cwd)||(n&&!input)||(uintptr_t)cwd>UINTPTR_MAX-cn||(uintptr_t)input>UINTPTR_MAX-n)return ARG;
 if(!cn||cwd[0]!='/')return CWD;
 if(cn>1&&cwd[cn-1]=='/')return CWD;
 Part parts[128];size_t count=0,at=1;
 while(at<cn){size_t begin=at;while(at<cn&&cwd[at]!='/')at++;size_t len=at-begin;
  if(!len||dot(cwd+begin,len)){return CWD;}
  uint64_t units=0,error=model_name(cwd+begin,len,&units);if(error)return error;
  if(count==128){return LONG;}
  parts[count++]=(Part){cwd+begin,len};if(at<cn)at++;
 }
 if(n&&input[0]=='/')count=0;
 at=0;int hint=!n;
 while(at<n){if(input[at]=='/'){at++;continue;}size_t begin=at;while(at<n&&input[at]!='/')at++;size_t len=at-begin;hint=0;
  if(len==1&&input[begin]=='.')hint=1;
  else if(len==2&&input[begin]=='.'&&input[begin+1]=='.'){if(!count)return ESC;count--;hint=1;}
  else {uint64_t units=0,error=model_name(input+begin,len,&units);if(error)return error;
   if(count==128){return LONG;}
   parts[count++]=(Part){input+begin,len};if(path_length(parts,count)>1024)return LONG;
  }
 }
 Path result={0};result.length=path_length(parts,count);result.components=count;result.directory_hint=!count||hint||(n&&input[n-1]=='/');
 result.bytes[0]='/';size_t pos=1;
 for(size_t i=0;i<count;i++){if(i)result.bytes[pos++]='/';memcpy(result.bytes+pos,parts[i].p,parts[i].n);pos+=parts[i].n;}
 *out=result;return 0;
}
static void one_name(const uint8_t*p,size_t n){
 uint64_t expected=0,err=model_name(p,n,&expected);
 struct {uint64_t pre,value,post;} out={0x98765432,UINT64_C(0xa1b2c3d4e5f60718),0xabcdef09};
 uint64_t actual=path_name(p,n,&out.value);CHECK(actual==err);CHECK(out.pre==0x98765432&&out.post==0xabcdef09);
 if(err)CHECK(out.value==UINT64_C(0xa1b2c3d4e5f60718));else CHECK(out.value==expected);names++;
}
static void one_path(const uint8_t*c,size_t cn,const uint8_t*p,size_t n){
 uint8_t cwd[1040],input[4112];CHECK(cn<=1024&&n<=4096);memset(cwd,0xa3,sizeof cwd);memset(input,0xb4,sizeof input);
 memcpy(cwd+8,c,cn);memcpy(input+8,p,n);Path expected;uint64_t error=model_normalize(cwd+8,cn,input+8,n,&expected);
 struct {uint64_t pre;Path value;uint64_t post;} out;memset(&out,0x6a,sizeof out);out.pre=0x11223344;out.post=0x55667788;Path before=out.value;
 uint64_t actual=path_normalize(cwd+8,cn,input+8,n,&out.value);CHECK(actual==error);
 CHECK(out.pre==0x11223344&&out.post==0x55667788);
 if(error)CHECK(!memcmp(&out.value,&before,sizeof before));else CHECK(!memcmp(&out.value,&expected,sizeof expected));
 CHECK(!memcmp(cwd+8,c,cn)&&!memcmp(input+8,p,n));for(size_t i=0;i<8;i++)CHECK(cwd[i]==0xa3&&input[i]==0xb4);
 for(size_t i=8+cn;i<sizeof cwd;i++)CHECK(cwd[i]==0xa3);
 for(size_t i=8+n;i<sizeof input;i++){CHECK(input[i]==0xb4);}paths++;
}
#define PATH(c,p) one_path((const uint8_t*)(c),strlen(c),(const uint8_t*)(p),strlen(p))
static size_t encode(uint32_t cp,uint8_t*out){
 if(cp<128){out[0]=(uint8_t)cp;return 1;}
 if(cp<2048){out[0]=(uint8_t)(0xc0|(cp>>6));out[1]=(uint8_t)(0x80|(cp&63));return 2;}
 if(cp<65536){out[0]=(uint8_t)(0xe0|(cp>>12));out[1]=(uint8_t)(0x80|((cp>>6)&63));out[2]=(uint8_t)(0x80|(cp&63));return 3;}
 out[0]=(uint8_t)(0xf0|(cp>>18));out[1]=(uint8_t)(0x80|((cp>>12)&63));out[2]=(uint8_t)(0x80|((cp>>6)&63));out[3]=(uint8_t)(0x80|(cp&63));return 4;
}
static void basics(void){
 scenario="lexical paths and immediate root escape";
 PATH("/","../safe");PATH("/","/../../safe");PATH("/","..");PATH("/a","../../safe");
 PATH("/","");PATH("/a/b","");PATH("/a/b","../c//./d/");PATH("/a/b","/x/./y/../z");PATH("/a/b","../../x");
 PATH("/","////");PATH("/a",".");PATH("/a","..");PATH("/",".hidden");PATH("/","bad:/../good");
 const char*badcwd[]={"","relative","//","/a/","/a//b","/a/./b","/a/../b","/ leading","/a."};
 for(size_t i=0;i<sizeof badcwd/sizeof badcwd[0];i++)PATH(badcwd[i],"/absolute");
 const char*bad[]={".","..",""," "," leading","trailing ","trailing.","A/B","A\\B","A:B","A|B","A?B","A*B","A<B","A>B","A\"B"};
 for(size_t i=0;i<sizeof bad/sizeof bad[0];i++)one_name((const uint8_t*)bad[i],strlen(bad[i]));
 one_name((const uint8_t*)"CON",3);one_name((const uint8_t*)"e\xcc\x81",3);one_name((const uint8_t*)"\xc3\xa9",2);
 uint8_t boundary[1024];memset(boundary,'a',sizeof boundary);one_name(boundary,255);one_name(boundary,256);one_name(boundary,1020);one_name(boundary,1021);
 for(size_t i=0;i<128;i++){encode(0x1f9ea,boundary+4*i);}
 one_name(boundary,127*4);one_name(boundary,128*4);boundary[127*4]='a';one_name(boundary,127*4+1);
 scenario="strict UTF8 table 3-7 and UTF16 units";
 for(uint32_t cp=0;cp<=0x10ffff;cp+=257){uint8_t raw[4];size_t n=encode(cp,raw);one_name(raw,n);}
 for(uint32_t cp=0xd800;cp<=0xdfff;cp++){uint8_t raw[4];one_name(raw,encode(cp,raw));}
 uint32_t edges[]={0x7f,0x80,0x7ff,0x800,0xd7ff,0xe000,0xfffd,0xfffe,0xffff,0x10000,0x10ffff,0x110000};
 for(size_t i=0;i<sizeof edges/sizeof edges[0];i++){uint8_t raw[4];one_name(raw,encode(edges[i],raw));}
 for(unsigned a=0;a<256;a++)for(unsigned b=0;b<256;b++){uint8_t raw[2]={(uint8_t)a,(uint8_t)b};one_name(raw,2);}
}
static void bounds(void){
 scenario="1024 bytes 128 components and 4096 raw prefix bounds";
 uint8_t maximal[1024];size_t pos=0;for(unsigned c=0;c<4;c++){maximal[pos++]='/';memset(maximal+pos,'a'+c,255);pos+=255;}CHECK(pos==1024);
 one_path((const uint8_t*)"/",1,maximal,1024);one_path(maximal,1024,(const uint8_t*)"",0);one_path(maximal,1024,(const uint8_t*)"x/..",4);
 uint8_t input[4096];size_t n=0;for(unsigned i=0;i<128;i++){input[n++]='/';input[n++]='a';}one_path((const uint8_t*)"/",1,input,n);input[n++]='/';input[n++]='a';one_path((const uint8_t*)"/",1,input,n);
 memset(input,'/',sizeof input);one_path((const uint8_t*)"/",1,input,sizeof input);
 for(size_t i=0;i<sizeof input;i+=2){input[i]='.';input[i+1]='/';}one_path((const uint8_t*)"/",1,input,sizeof input);
 uint64_t units=17;CHECK(path_name(NULL,1,&units)==ARG&&units==17);CHECK(path_name((const uint8_t*)(uintptr_t)(UINTPTR_MAX-1),4,&units)==ARG);
 CHECK(path_name((const uint8_t*)"x",1021,&units)==LONG);
 Path out;memset(&out,0x75,sizeof out);Path old=out;
 CHECK(path_normalize(NULL,1,(const uint8_t*)"x",1,&out)==ARG&&!memcmp(&out,&old,sizeof old));
 CHECK(path_normalize((const uint8_t*)"/",1,NULL,1,&out)==ARG&&!memcmp(&out,&old,sizeof old));
 CHECK(path_normalize((const uint8_t*)"/",1,(const uint8_t*)(uintptr_t)(UINTPTR_MAX-1),4,&out)==ARG);
 CHECK(path_normalize((const uint8_t*)"/",1025,(const uint8_t*)"x",1,&out)==LONG);
 CHECK(path_normalize((const uint8_t*)"/",1,(const uint8_t*)"x",4097,&out)==LONG);
 CHECK(path_normalize((const uint8_t*)"/",1,(const uint8_t*)"x",1,NULL)==ARG);
 CHECK(path_normalize((const uint8_t*)"/",1,(const uint8_t*)"x",1,(Path*)((uint8_t*)&out+1))==ARG);
 CHECK(path_normalize((const uint8_t*)"/",1,(const uint8_t*)"x",1,(Path*)(uintptr_t)(UINTPTR_MAX-7))==ARG);
 CHECK(!memcmp(&out,&old,sizeof old));
}
static uint64_t rng=UINT64_C(0x8bcfa5314d720e99);
static uint64_t next_random(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static void random_cases(void){
 scenario="deterministic independent random bytes and component-stack oracle";
 for(unsigned k=0;k<5000;k++){uint8_t raw[48];size_t n=(size_t)(next_random()%49);for(size_t i=0;i<n;i++)raw[i]=(uint8_t)next_random();one_name(raw,n);randoms++;}
 for(unsigned k=0;k<5000;k++){
  uint8_t raw[2048];size_t n=0;unsigned count=(unsigned)(next_random()%160);
  if(next_random()&1)raw[n++]='/';
  for(unsigned j=0;j<count;j++){
   if(j){raw[n++]='/';}
   unsigned kind=(unsigned)(next_random()%12);
   if(kind==0)raw[n++]='.';
   else if(kind==1){raw[n++]='.';raw[n++]='.';}
   else if(kind==2){raw[n++]='x';raw[n++]=':';}
   else if(kind==3){raw[n++]=0xed;raw[n++]=0xa0;raw[n++]=0x80;}
   else if(kind==4)n+=encode(0x1f9ea,raw+n);
   else if(kind==5)n+=encode(0x4e2d,raw+n);
   else {raw[n++]=(uint8_t)('A'+next_random()%26);if(next_random()&1)raw[n++]=(uint8_t)('0'+next_random()%10);}
   if(next_random()%8==0)raw[n++]='/';
  }
  if(next_random()%8==0){raw[n++]='/';}
  one_path((const uint8_t*)"/base/child",11,raw,n);randoms++;
 }
}
static void alias_cases(void){
 scenario="input and cwd borrow overlap with atomic output";
 for(unsigned kind=0;kind<4;kind++){
  struct{uint64_t pre;Path out;uint64_t post;} storage;memset(&storage,0x53,sizeof storage);storage.pre=0x1234;storage.post=0x5678;
  uint8_t*c=storage.out.bytes,*p=c+128;memcpy(c,"/a/b",4);const char *value=kind==3?"../../..":"../c//./d/";size_t n=strlen(value);memcpy(p,value,n);
  Path expected;uint64_t error=model_normalize(c,4,p,n,&expected);Path before=storage.out;
  const uint8_t*cc=kind==0?(const uint8_t*)"/a/b":c;const uint8_t*pp=kind==1?(const uint8_t*)value:p;
  CHECK(path_normalize(cc,4,pp,n,&storage.out)==error);
  if(error)CHECK(!memcmp(&storage.out,&before,sizeof before));else CHECK(!memcmp(&storage.out,&expected,sizeof expected));
  CHECK(storage.pre==0x1234&&storage.post==0x5678);aliases++;
 }
}
static void guard_pages(void){
 scenario="actual inaccessible pages at exact input/output end";
 size_t page=4096;
#ifdef _WIN32
 SYSTEM_INFO info;GetSystemInfo(&info);page=info.dwPageSize;uint8_t*memory=VirtualAlloc(NULL,page*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);CHECK(memory!=NULL);DWORD old;CHECK(VirtualProtect(memory+page,page,PAGE_NOACCESS,&old));
#else
 long count=sysconf(_SC_PAGESIZE);CHECK(count>0);page=(size_t)count;uint8_t*memory=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);CHECK(memory!=MAP_FAILED);CHECK(mprotect(memory+page,page,PROT_NONE)==0);
#endif
 const uint8_t bad[3][3]={{0xc2,0,0},{0xe0,0xa0,0},{0xf0,0x90,0x80}};
 for(size_t n=1;n<=3;n++){uint8_t*source=memory+page-n;memcpy(source,bad[n-1],n);one_name(source,n);}
 Path*at_end=(Path*)(void*)(memory+page-sizeof(Path));Path expected;CHECK(model_normalize((const uint8_t*)"/",1,(const uint8_t*)"guard",5,&expected)==0);
 CHECK(path_normalize((const uint8_t*)"/",1,(const uint8_t*)"guard",5,at_end)==0&&!memcmp(at_end,&expected,sizeof expected));
#ifdef _WIN32
 CHECK(VirtualFree(memory,0,MEM_RELEASE));
#else
 CHECK(munmap(memory,page*2)==0);
#endif
}
int main(void){
 uint64_t sizes[5]={0};path_sizes(sizes);CHECK(sizes[0]==1048&&sizes[1]==1024&&sizes[2]==4096&&sizes[3]==128&&sizes[4]==255);
 basics();bounds();random_cases();alias_cases();guard_pages();
 printf("path native oracle passed: names=%llu paths=%llu random=%llu aliases=%llu checks=%llu table3-7+component-stack atomic+guards+real-guardpages=ok\n",(unsigned long long)names,(unsigned long long)paths,(unsigned long long)randoms,(unsigned long long)aliases,(unsigned long long)checks);return 0;
}
