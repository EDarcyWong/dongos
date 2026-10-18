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
#define ARG UINT64_C(0x050b0001)
#define CORRUPT UINT64_C(0x050b0002)
#define UNICODE UINT64_C(0x050b0003)
#define BADNAME UINT64_C(0x050b0004)
#define LONG UINT64_C(0x050b0005)
#define PARG UINT64_C(0x050a0001)
#define PUTF UINT64_C(0x050a0002)
#define PNAME UINT64_C(0x050a0003)
#define PLONG UINT64_C(0x050a0004)
typedef struct {uint64_t count;uint8_t bytes[672];} Group;
typedef struct {uint64_t length,units;uint8_t bytes[1020];} Name;
_Static_assert(sizeof(Group)==680,"Group ABI");
_Static_assert(sizeof(Name)==1040,"Name ABI");
extern ABI void lfn_sizes(uint64_t*);
extern ABI uint64_t lfn_checksum(const uint8_t*,size_t,uint64_t*);
extern ABI uint64_t lfn_encode(const uint8_t*,size_t,const uint8_t*,size_t,Group*);
extern ABI uint64_t lfn_decode(const uint8_t*,size_t,Name*);
static uint64_t checks,encodes,decodes,randoms,aliases;
static const char *scenario="start";
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"LFN_MODEL_ASSERT line %d: %s scenario=%s\n",__LINE__,#x,scenario);exit(1);}}while(0)
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected panic %llu\n",(unsigned long long)code);exit(99);}
ABI void lfn_negative_hit(uint64_t kind){fprintf(stderr,"LFN_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}
static const unsigned offsets[13]={1,3,5,7,9,14,16,18,20,22,24,28,30};
static uint8_t sum11(const uint8_t *p){uint8_t v=0;for(unsigned i=0;i<11;i++)v=(uint8_t)(v/2+(v%2)*128+p[i]);return v;}
static uint16_t read16(const uint8_t*p){return (uint16_t)(p[0]+256u*p[1]);}
static void write16(uint8_t*p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v/256);}
static int short_ok(const uint8_t *s){
 if(!s[0]||s[0]==0xe5||s[0]==' '||(s[11]&0xc8))return 0;
 for(unsigned part=0;part<2;part++){
  unsigned begin=part?8:0,end=part?11:8;int tail=0;
  for(unsigned i=begin;i<end;i++){
   unsigned ch=s[i];if(ch==' '){tail=1;continue;}
   if(tail||(ch<32&&!(i==0&&ch==5))||(ch<128&&strchr("\"*+,./:;<=>?[\\]|",(int)ch)))return 0;
  }
 }return 1;
}
/* Unicode Table 3-7 rows are independent of the DG validated-conversion pass. */
typedef struct {unsigned lo,hi,slo,shi,n,mask;} Row;
static const Row rows[]={
 {0,0x7f,0,0,1,0x7f},{0xc2,0xdf,0x80,0xbf,2,31},
 {0xe0,0xe0,0xa0,0xbf,3,15},{0xe1,0xec,0x80,0xbf,3,15},
 {0xed,0xed,0x80,0x9f,3,15},{0xee,0xef,0x80,0xbf,3,15},
 {0xf0,0xf0,0x90,0xbf,4,7},{0xf1,0xf3,0x80,0xbf,4,7},{0xf4,0xf4,0x80,0x8f,4,7}};
static uint64_t utf8(const uint8_t*p,size_t n,size_t*at,uint32_t*cp){
 for(size_t i=0;i<sizeof rows/sizeof rows[0];i++){
  Row r=rows[i];const uint8_t*q=p+*at;if(q[0]<r.lo||q[0]>r.hi)continue;
  if(n-*at<r.n||(r.n>1&&(q[1]<r.slo||q[1]>r.shi)))return PUTF;
  uint32_t v=q[0]&r.mask;for(unsigned k=1;k<r.n;k++){if(q[k]<128||q[k]>191)return PUTF;v=64*v+(q[k]&63);}
  *at+=r.n;*cp=v;return 0;
 }return PUTF;
}
static size_t put8(uint32_t cp,uint8_t*p){
 if(cp<128){p[0]=(uint8_t)cp;return 1;}
 if(cp<2048){p[0]=(uint8_t)(192+cp/64);p[1]=(uint8_t)(128+cp%64);return 2;}
 if(cp<65536){p[0]=(uint8_t)(224+cp/4096);p[1]=(uint8_t)(128+(cp/64)%64);p[2]=(uint8_t)(128+cp%64);return 3;}
 p[0]=(uint8_t)(240+cp/262144);p[1]=(uint8_t)(128+(cp/4096)%64);p[2]=(uint8_t)(128+(cp/64)%64);p[3]=(uint8_t)(128+cp%64);return 4;
}
static int forbidden(uint32_t cp){return cp<32||cp==0xffff||(cp<128&&strchr("\"*/:<>?\\|",(int)cp));}
static int dots(const uint8_t*p,size_t n){return (n==1&&p[0]=='.')||(n==2&&p[0]=='.'&&p[1]=='.');}
static uint64_t name_words(const uint8_t*p,size_t n,uint16_t*w,size_t*units){
 if(n>1020)return PLONG;
 if((n&&!p)||(uintptr_t)p>UINTPTR_MAX-n)return PARG;
 if(!n||dots(p,n)||p[0]==' '||p[n-1]==' '||p[n-1]=='.')return PNAME;
 size_t at=0,count=0;while(at<n){uint32_t cp=0;uint64_t e=utf8(p,n,&at,&cp);if(e)return e;if(forbidden(cp))return PNAME;
  unsigned need=cp>=65536?2:1;if(count+need>255)return PLONG;
  if(need==2){w[count++]=(uint16_t)(0xd800+(cp-65536)/1024);w[count++]=(uint16_t)(0xdc00+(cp-65536)%1024);}else w[count++]=(uint16_t)cp;
 }*units=count;return 0;
}
/* Independent encoder: visit logical units, map each into reversed raw slot. */
static void raw_group(const uint16_t*w,size_t units,const uint8_t*short_entry,Group*out){
 memset(out,0,sizeof *out);size_t n=(units+12)/13;out->count=n+1;
 for(size_t physical=0;physical<n;physical++){
  uint8_t*slot=out->bytes+physical*32;slot[0]=(uint8_t)(n-physical);if(!physical)slot[0]+=64;slot[11]=15;slot[13]=sum11(short_entry);
 }
 for(size_t i=0;i<n*13;i++){
  uint16_t v=i<units?w[i]:(i==units?0:0xffff);
  size_t logical_slot=i/13,physical=n-1-logical_slot;write16(out->bytes+physical*32+offsets[i%13],v);
 }memcpy(out->bytes+n*32,short_entry,32);
}
static uint64_t model_encode(const uint8_t*p,size_t n,const uint8_t*s,size_t sn,Group*out){
 if(sn>32)return LONG;
 if((sn&&!s)||(uintptr_t)s>UINTPTR_MAX-sn)return ARG;
 if(sn!=32)return ARG;
 if(!short_ok(s))return CORRUPT;
 uint16_t w[260];size_t count=0;uint64_t e=name_words(p,n,w,&count);if(e)return e;
 raw_group(w,count,s,out);return 0;
}
/* Independent decoder first gathers a logical uint16 array, then validates
   termination and Unicode in separate passes; DG is one-pass pending-state. */
static uint64_t model_decode(const uint8_t*p,size_t n,Name*out){
 if(n>672)return LONG;
 if((n&&!p)||(uintptr_t)p>UINTPTR_MAX-n)return ARG;
 if(n<64||n%32)return CORRUPT;
 size_t slots=n/32-1;const uint8_t*s=p+32*slots;if(!short_ok(s))return CORRUPT;
 uint16_t w[260];size_t used=0;
 for(size_t logical_slot=0;logical_slot<slots;logical_slot++){
  const uint8_t*q=p+(slots-1-logical_slot)*32;unsigned ordinal=(unsigned)logical_slot+1;if(logical_slot+1==slots)ordinal+=64;
  if(q[0]!=ordinal||q[11]!=15||q[12]||q[26]||q[27]||q[13]!=sum11(s))return CORRUPT;
  for(unsigned i=0;i<13;i++)w[used++]=read16(q+offsets[i]);
 }
 size_t length=0;while(length<used&&w[length]){if(w[length]==0xffff)return CORRUPT;length++;}
 if(!length||(length+12)/13!=slots)return CORRUPT;
 if(length<used)for(size_t j=length+1;j<used;j++)if(w[j]!=0xffff)return CORRUPT;
 if(length>255)return LONG;
 Name result;memset(&result,0,sizeof result);result.units=length;
 for(size_t i=0;i<length;i++){
  uint32_t cp=w[i];if(cp>=0xd800&&cp<=0xdbff){if(++i==length||w[i]<0xdc00||w[i]>0xdfff)return UNICODE;cp=65536+(cp-0xd800)*1024+(w[i]-0xdc00);}
  else if(cp>=0xdc00&&cp<=0xdfff)return UNICODE;
  if(forbidden(cp))return BADNAME;
  result.length+=put8(cp,result.bytes+result.length);
 }if(dots(result.bytes,(size_t)result.length))return BADNAME;
 memcpy(out,&result,sizeof result);return 0;
}
static void one_encode(const uint8_t*p,size_t n,const uint8_t*s,size_t sn){
 Group expected;uint64_t error=model_encode(p,n,s,sn,&expected);
 struct{uint64_t pre;Group out;uint64_t post;} box;memset(&box,0x6a,sizeof box);box.pre=0x1234;box.post=0x5678;Group before=box.out;
 uint64_t actual=lfn_encode(p,n,s,sn,&box.out);CHECK(actual==error);CHECK(box.pre==0x1234&&box.post==0x5678);
 if(error)CHECK(!memcmp(&box.out,&before,sizeof before));else CHECK(!memcmp(&box.out,&expected,sizeof expected));encodes++;
}
static void one_decode(const uint8_t*p,size_t n){
 Name expected;uint64_t error=model_decode(p,n,&expected);
 struct{uint64_t pre;Name out;uint64_t post;} box;memset(&box,0x9b,sizeof box);box.pre=0x123456;box.post=0x789abc;Name before=box.out;
 uint64_t actual=lfn_decode(p,n,&box.out);CHECK((actual==0)==(error==0));CHECK(box.pre==0x123456&&box.post==0x789abc);
 if(error)CHECK(!memcmp(&box.out,&before,sizeof before));else {CHECK(box.out.length==expected.length&&box.out.units==expected.units);CHECK(!memcmp(&box.out,&expected,sizeof expected));}
 decodes++;
}
static void short_seed(uint8_t*p){memset(p,0,32);memcpy(p,"EXAMPL~1TXT",11);p[11]=32;p[13]=0xa3;p[20]=0xff;p[26]=0x75;p[28]=0x12;}
static void basics(void){
 scenario="all 1..255 logical-unit lengths and exact raw 13-word slots";
 uint8_t short_entry[32],text[1024];short_seed(short_entry);
 for(size_t n=1;n<=256;n++){
  memset(text,'a',n);one_encode(text,n,short_entry,32);
  uint16_t words[260];for(size_t i=0;i<n;i++)words[i]=(uint16_t)('a'+i%26);Group g;raw_group(words,n,short_entry,&g);one_decode(g.bytes,(size_t)g.count*32);
 }
 scenario="Microsoft worked example and opaque OEM raw05 checksum";
 memcpy(short_entry,"THEQUI~1FOX",11);const char*worked="The quick brown.fox";one_encode((const uint8_t*)worked,strlen(worked),short_entry,32);
 uint64_t sum=999;CHECK(lfn_checksum(short_entry,11,&sum)==0&&sum==sum11(short_entry));
 for(unsigned first=0;first<256;first++){
  short_seed(short_entry);short_entry[0]=(uint8_t)first;one_encode((const uint8_t*)"longname",8,short_entry,32);
  CHECK(lfn_checksum(short_entry,11,&sum)==0&&sum==sum11(short_entry));
 }
 scenario="each UTF16 single unit, noncharacters, low/high surrogate rejection";
 short_seed(short_entry);for(unsigned cp=0;cp<=65535;cp++){
  uint16_t words[3]={'A',(uint16_t)cp,'Z'};Group g;raw_group(words,3,short_entry,&g);one_decode(g.bytes,(size_t)g.count*32);
 }
 scenario="paired surrogates at each side of all 13-unit boundaries";
 for(size_t boundary=1;boundary<20;boundary++)for(int delta=-1;delta<=1;delta++){
  uint16_t words[260];size_t high=boundary*13+(size_t)delta;for(size_t i=0;i<255;i++)words[i]='a';
  if(high+1>=255){continue;}
  words[high]=0xdbff;words[high+1]=0xdfff;Group g;raw_group(words,255,short_entry,&g);one_decode(g.bytes,(size_t)g.count*32);
 }
 const char*bad[]={"",".",".."," leading","trailing ","trailing.","a/b","a\\b","a:b","a\"b","a|b","a?b","a*b","a<b","a>b"};
 for(size_t i=0;i<sizeof bad/sizeof bad[0];i++)one_encode((const uint8_t*)bad[i],strlen(bad[i]),short_entry,32);
 const uint8_t malformed[][5]={{0xc0,0x80},{0xed,0xa0,0x80},{0xf4,0x90,0x80,0x80},{0xf0,0x9f,0x92},{0xe0,0x80,0x80},{0x80}};
 const size_t lens[]={2,3,4,3,3,1};for(size_t i=0;i<6;i++)one_encode(malformed[i],lens[i],short_entry,32);
 /* Raw recovery deliberately accepts edge spelling that create refuses. */
 uint16_t raw[]={' ','.','x','.',' '};Group g;raw_group(raw,5,short_entry,&g);one_decode(g.bytes,(size_t)g.count*32);
}
static void broken_groups(void){
 scenario="every byte value in ordinal, attr, type, checksum and cluster fields";
 uint8_t s[32];short_seed(s);uint16_t w[40];for(unsigned i=0;i<40;i++)w[i]=(uint16_t)('A'+i%26);Group g;raw_group(w,40,s,&g);
 const unsigned fields[]={0,11,12,13,26,27};
 for(size_t slot=0;slot<g.count-1;slot++)for(size_t f=0;f<sizeof fields/sizeof fields[0];f++)for(unsigned v=0;v<256;v++){
  Group changed=g;changed.bytes[slot*32+fields[f]]=(uint8_t)v;one_decode(changed.bytes,(size_t)changed.count*32);
 }
 scenario="all truncations, lost first LAST, duplicated/reordered slots and wrong short alias";
 for(size_t n=0;n<(size_t)g.count*32;n++)one_decode(g.bytes,n);
 for(size_t first=1;first<g.count;first++)one_decode(g.bytes+32*first,(size_t)(g.count-first)*32);
 for(size_t from=0;from<g.count-1;from++)for(size_t to=0;to<g.count-1;to++)if(from!=to){Group changed=g;memcpy(changed.bytes+to*32,g.bytes+from*32,32);one_decode(changed.bytes,(size_t)g.count*32);}
 for(unsigned i=0;i<11;i++){Group changed=g;changed.bytes[(g.count-1)*32+i]^=1;one_decode(changed.bytes,(size_t)g.count*32);}
 for(unsigned at=0;at<32;at++)for(unsigned v=0;v<256;v+=17){Group changed=g;changed.bytes[(g.count-1)*32+at]=(uint8_t)v;one_decode(changed.bytes,(size_t)g.count*32);}
 scenario="terminator/filler, extra padding slot, data past zero, unpaired endpoints";
 for(size_t n=1;n<=255;n++){
  uint16_t words[260];for(size_t i=0;i<260;i++)words[i]='a';Group valid;raw_group(words,n,s,&valid);
  size_t slots=(size_t)valid.count-1;
  for(size_t pos=n;pos<slots*13;pos++){
   const uint16_t values[]={0,0xffff,'x',0xd800,0xdc00};
   for(size_t j=0;j<5;j++){Group changed=valid;size_t physical=slots-1-pos/13;write16(changed.bytes+physical*32+offsets[pos%13],values[j]);one_decode(changed.bytes,(size_t)changed.count*32);}
  }
  if(slots<20){Group changed;memset(&changed,0,sizeof changed);changed.count=valid.count+1;memcpy(changed.bytes+32,valid.bytes,(size_t)valid.count*32);changed.bytes[0]=(uint8_t)(64+slots+1);changed.bytes[11]=15;changed.bytes[13]=sum11(s);changed.bytes[32]&=31;
   for(size_t j=0;j<13;j++){write16(changed.bytes+offsets[j],j?0xffff:0);}
   one_decode(changed.bytes,(size_t)changed.count*32);
  }
 }
}
static uint64_t rng=UINT64_C(0xe52a3b407d1869cf);
static uint64_t next_random(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static void random_cases(void){
 scenario="independent deterministic random scalars and byte corruption";
 uint8_t s[32];short_seed(s);
 for(unsigned k=0;k<5000;k++){
  uint8_t text[1024];size_t bytes=0;unsigned scalars=1+(unsigned)(next_random()%180);
  for(unsigned j=0;j<scalars;j++){
   uint32_t cp=(uint32_t)(next_random()%0x110000);if(cp>=0xd800&&cp<=0xdfff)cp='a';if(forbidden(cp))cp='z';
   bytes+=put8(cp,text+bytes);
  }
  one_encode(text,bytes,s,32);Group g;uint64_t e=model_encode(text,bytes,s,32,&g);
  if(!e){one_decode(g.bytes,(size_t)g.count*32);for(unsigned j=0;j<4;j++){Group changed=g;size_t at=(size_t)(next_random()%(g.count*32));changed.bytes[at]^=(uint8_t)(1u<<(next_random()%8));one_decode(changed.bytes,(size_t)g.count*32);}}
  randoms++;
 }
 for(unsigned k=0;k<3000;k++){
  uint8_t text[64];size_t n=(size_t)(next_random()%65);for(size_t i=0;i<n;i++)text[i]=(uint8_t)next_random();one_encode(text,n,s,32);randoms++;
 }
 for(unsigned k=0;k<2000;k++){
  uint8_t bytes[672];size_t n=(size_t)(next_random()%673);for(size_t i=0;i<n;i++)bytes[i]=(uint8_t)next_random();one_decode(bytes,n);randoms++;
 }
}
static void metadata_and_alias(void){
 scenario="metadata rejection and complete output atomicity";
 uint8_t s[32];short_seed(s);Group g;memset(&g,0x45,sizeof g);Group oldg=g;Name n;memset(&n,0x78,sizeof n);Name oldn=n;
 CHECK(lfn_encode((const uint8_t*)"x",1,s,32,NULL)==ARG);
 CHECK(lfn_encode((const uint8_t*)"x",1,s,32,(Group*)((uint8_t*)&g+1))==ARG);
 CHECK(lfn_encode((const uint8_t*)"x",1,s,32,(Group*)(uintptr_t)(UINTPTR_MAX-7))==ARG);
 CHECK(lfn_encode(NULL,1,s,32,&g)==PARG&&!memcmp(&g,&oldg,sizeof g));
 CHECK(lfn_encode((const uint8_t*)(uintptr_t)(UINTPTR_MAX-1),4,s,32,&g)==PARG);
 CHECK(lfn_encode((const uint8_t*)"x",1021,s,32,&g)==PLONG);
 CHECK(lfn_encode((const uint8_t*)"x",1,NULL,32,&g)==ARG);
 CHECK(lfn_encode((const uint8_t*)"x",1,s,33,&g)==LONG);
 CHECK(lfn_encode((const uint8_t*)"x",1,s,31,&g)==ARG);
 CHECK(lfn_decode(NULL,64,&n)==ARG&&!memcmp(&n,&oldn,sizeof n));
 CHECK(lfn_decode((const uint8_t*)(uintptr_t)(UINTPTR_MAX-1),64,&n)==ARG);
 CHECK(lfn_decode((const uint8_t*)"x",673,&n)==LONG);
 CHECK(lfn_decode(s,32,NULL)==ARG);
 CHECK(lfn_decode(s,32,(Name*)((uint8_t*)&n+1))==ARG);
 CHECK(lfn_decode(s,32,(Name*)(uintptr_t)(UINTPTR_MAX-7))==ARG);
 CHECK(!memcmp(&g,&oldg,sizeof g)&&!memcmp(&n,&oldn,sizeof n));
 uint64_t sum=UINT64_C(0x123456789abcdef);CHECK(lfn_checksum(NULL,11,&sum)==ARG&&sum==UINT64_C(0x123456789abcdef));
 CHECK(lfn_checksum(s,10,&sum)==ARG);CHECK(lfn_checksum(s,12,&sum)==LONG);
 scenario="borrow overlap for encode and decode with atomic private candidate";
 for(unsigned kind=0;kind<4;kind++){
  Group store;memset(&store,0x31,sizeof store);memcpy(store.bytes+48,"alias overlap",13);memcpy(store.bytes+96,s,32);Group expected;
  CHECK(model_encode(store.bytes+48,13,store.bytes+96,32,&expected)==0);
  const uint8_t*text=kind&1?(const uint8_t*)"alias overlap":store.bytes+48;const uint8_t*entry=kind&2?s:store.bytes+96;
  CHECK(lfn_encode(text,13,entry,32,&store)==0&&!memcmp(&store,&expected,sizeof store));aliases++;
 }
 {
  Name store;memset(&store,0x54,sizeof store);uint16_t w[255];for(unsigned i=0;i<255;i++)w[i]=0x4e2d;Group source;raw_group(w,255,s,&source);memcpy(store.bytes,source.bytes,672);Name expected;
  CHECK(model_decode(store.bytes,672,&expected)==0);CHECK(lfn_decode(store.bytes,672,&store)==0);CHECK(store.length==expected.length&&store.units==255&&!memcmp(store.bytes,expected.bytes,1020));aliases++;
 }
 {
  Name store;memset(&store,0x54,sizeof store);Name before=store;CHECK(lfn_decode(store.bytes,64,&store)!=0&&!memcmp(&store,&before,sizeof store));aliases++;
 }
}
static void guard_pages(void){
 scenario="actual no-access page at exact source and output endpoint";
 size_t page=4096;
#ifdef _WIN32
 SYSTEM_INFO info;GetSystemInfo(&info);page=info.dwPageSize;uint8_t*memory=VirtualAlloc(NULL,page*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);CHECK(memory!=NULL);DWORD old;CHECK(VirtualProtect(memory+page,page,PAGE_NOACCESS,&old));
#else
 long count=sysconf(_SC_PAGESIZE);CHECK(count>0);page=(size_t)count;uint8_t*memory=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);CHECK(memory!=MAP_FAILED);CHECK(mprotect(memory+page,page,PROT_NONE)==0);
#endif
 uint8_t s[32];short_seed(s);uint16_t w[255];for(size_t i=0;i<255;i++)w[i]='a';Group g;raw_group(w,255,s,&g);
 uint8_t*source=memory+page-672;memcpy(source,g.bytes,672);one_decode(source,672);
 uint8_t*entry=memory+page-32;memcpy(entry,s,32);one_encode((const uint8_t*)"guard",5,entry,32);
 for(size_t len=1;len<=4;len++){uint8_t*text=memory+page-len;memset(text,0x80,len);text[0]=0xf0;one_encode(text,len,s,32);}
 Group*outg=(Group*)(void*)(memory+page-sizeof(Group));CHECK(lfn_encode((const uint8_t*)"guard",5,s,32,outg)==0);CHECK(outg->count==2);
 Name*outn=(Name*)(void*)(memory+page-sizeof(Name));CHECK(lfn_decode(g.bytes,672,outn)==0&&outn->units==255);
#ifdef _WIN32
 CHECK(VirtualFree(memory,0,MEM_RELEASE));
#else
 CHECK(munmap(memory,page*2)==0);
#endif
}
int main(void){
 uint64_t sizes[2]={0};lfn_sizes(sizes);CHECK(sizes[0]==680&&sizes[1]==1040);
 basics();broken_groups();random_cases();metadata_and_alias();guard_pages();
 printf("lfn native byte oracle passed: encodes=%llu decodes=%llu random=%llu aliases=%llu checks=%llu raw32+utf16+atomic+real-guardpages=ok\n",(unsigned long long)encodes,(unsigned long long)decodes,(unsigned long long)randoms,(unsigned long long)aliases,(unsigned long long)checks);return 0;
}
