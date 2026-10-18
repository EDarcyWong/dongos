#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"PWR_RUNTIME_ASSERT line %d: %s case=%s\n",__LINE__,#x,label);exit(1);}}while(0)
typedef struct {uint64_t space,address,width,value;} Write;
typedef struct {uint64_t a,b,index,offset;} Sleep;
typedef struct {Write a,b;uint64_t clear,enable,has_b;Sleep source;} Shutdown;
typedef struct {uint64_t version,tables,reset_error,shutdown_error;Write reset;Shutdown shutdown;} Prepared;
typedef struct {uint64_t words[307];} Inventory;
extern ABI void pwr_runtime_sizes(uint64_t*);
extern ABI uint64_t pwr_capture(uint64_t,const Inventory*,Prepared*),pwr_execute(const Prepared*,uint64_t);
extern ABI uint64_t pwr_io_reset(const Write*),pwr_io_shutdown(const Shutdown*);
static const char *label="start";static uint64_t checks;static unsigned scenarios;
ABI void __dong_panic(uint64_t n){fprintf(stderr,"unexpected runtime panic %llu\n",(unsigned long long)n);exit(99);}
enum {ENTER=1,IN16,OUT16,OUT8,LEAVE};
typedef struct {uint64_t op,port,width,value;} Event;
static Event events[8];static unsigned used;static uint64_t flags,cpl;static uint16_t control;
static void event(uint64_t op,uint64_t port,uint64_t width,uint64_t value){CHECK(used<8);events[used++]=(Event){op,port,width,value};}
ABI uint64_t pwr_model_cpl(void){return cpl;}
ABI uint64_t pwr_model_enter(void){uint64_t old=flags;flags&=~UINT64_C(0x40200);event(ENTER,0,0,old);return old;}
ABI void pwr_model_leave(uint64_t saved){CHECK((flags&0x40200)==0);flags=(flags&~UINT64_C(0x40200))|(saved&0x200);event(LEAVE,0,0,flags);}
ABI uint64_t pwr_model_read16(uint64_t port){CHECK((flags&0x40200)==0&&port==0x604);event(IN16,port,16,control);return control;}
ABI void pwr_model_write16(uint64_t port,uint64_t value){CHECK((flags&0x40200)==0&&port==0x604&&value<=65535);event(OUT16,port,16,value);}
ABI void pwr_model_write8(uint64_t port,uint64_t value){CHECK((flags&0x40200)==0&&port==0xcf9&&value<=255);event(OUT8,port,8,value);}
static void hardware(unsigned if_on,unsigned ac_on,unsigned privilege,uint16_t old){used=0;flags=2|(if_on?0x200:0)|(ac_on?0x40000:0);cpl=privilege;control=old;}
static void event_is(unsigned i,uint64_t op,uint64_t port,uint64_t width,uint64_t value){CHECK(i<used&&events[i].op==op&&events[i].port==port&&events[i].width==width&&events[i].value==value);}
static Write reset={1,0xcf9,8,15};
static Shutdown sleep_plan={{1,0x604,16,0},{0},0x3c00,0x2000,0,{0,0,0,36}};
static void executor_cases(void){
 for(unsigned iff=0;iff<2;iff++)for(unsigned ac=0;ac<2;ac++)for(unsigned value=0;value<256;value++){
  label="exact byte reset and IF/AC";Write plan=reset;plan.value=value;hardware(iff,ac,0,1);CHECK(pwr_io_reset(&plan)==0);CHECK(used==3);event_is(0,ENTER,0,0,2|(iff?0x200:0)|(ac?0x40000:0));event_is(1,OUT8,0xcf9,8,value);CHECK(events[2].op==LEAVE&&flags==(2|(iff?0x200:0)));scenarios++;
 }
 for(unsigned type=0;type<8;type++)for(unsigned old=0;old<65536;old+=31){
  label="complete word PM1 two-step RMW";Shutdown plan=sleep_plan;plan.a.value=type<<10;plan.source.a=type;hardware(1,1,0,(uint16_t)old);uint64_t result=pwr_io_shutdown(&plan);
  if(!(old&1)){CHECK(result==2&&used==3);event_is(1,IN16,0x604,16,old);CHECK(events[2].op==LEAVE);}
  else{uint64_t typed=(old&~0x3c00u)|(type<<10);CHECK(result==0&&used==5);event_is(1,IN16,0x604,16,old);event_is(2,OUT16,0x604,16,typed);event_is(3,OUT16,0x604,16,typed|0x2000);CHECK((events[3].value&~UINT64_C(0x3c00))==(old&~UINT64_C(0x3c00)));CHECK(events[4].op==LEAVE);}
  CHECK(flags==0x202);scenarios++;
 }
 for(unsigned field=0;field<4;field++){
  label="reset malformed no side effects";Write bad=reset;((uint64_t*)&bad)[field]=field==3?256:0;hardware(1,1,0,1);uint64_t before=flags;CHECK(pwr_io_reset(&bad)==1&&used==0&&flags==before);scenarios++;
 }
 for(unsigned field=0;field<15;field++){
  label="sleep complete malformed-plan validation precedes I/O";Shutdown bad=sleep_plan;uint64_t *v=(uint64_t*)&bad;
  if(field==0)v[field]=0;else if(field==1)v[field]=0x608;else if(field==2)v[field]=8;else if(field==3)v[field]=1;
  else if(field>=4&&field<=7)v[field]=1;else if(field==8)v[field]=0;else if(field==9)v[field]=0;else if(field==10)v[field]=1;
  else if(field==11||field==12)v[field]=8;else if(field==13)v[field]=16;else v[field]=35;
  hardware(1,1,0,1);uint64_t before=flags;CHECK(pwr_io_shutdown(&bad)==1&&used==0&&flags==before);scenarios++;
 }
 label="privilege and pointer rejection";hardware(1,1,3,1);CHECK(pwr_io_reset(&reset)==1&&used==0);CHECK(pwr_io_shutdown(&sleep_plan)==1&&used==0);
 CHECK(pwr_io_reset(NULL)==1&&used==0);CHECK(pwr_io_shutdown(NULL)==1&&used==0);CHECK(pwr_io_reset((const Write*)((const uint8_t*)&reset+1))==1&&used==0);
}

typedef struct {uint64_t pa;size_t length;uint8_t bytes[2048];} Region;
enum {RSDP,XSDT,FADT,DSDT,SSDT0,REGIONS=21};
static Region regions[REGIONS];static Inventory inventory;static uint64_t denied;static unsigned reads;static int poisoned;
static const uint64_t tag=UINT64_C(0x5057525245414445);
static void put32(uint8_t*p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
static void put64(uint8_t*p,uint64_t n){for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(n>>(8*i));}
static uint32_t get32(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint64_t get64(const uint8_t*p){return get32(p)|((uint64_t)get32(p+4)<<32);}
static void sum_at(uint8_t*p,size_t n,size_t at){unsigned sum=0;p[at]=0;for(size_t i=0;i<n;i++)sum+=p[i];p[at]=(uint8_t)(0-sum);}
static void table(unsigned i,const char*sig,size_t n){Region*r=&regions[i];r->length=n;memcpy(r->bytes,sig,4);put32(r->bytes+4,(uint32_t)n);r->bytes[8]=3;sum_at(r->bytes,n,9);}
static void root_entries(unsigned ssdt){Region*r=&regions[XSDT];size_t n=44+ssdt*8;table(XSDT,"XSDT",n);put64(r->bytes+36,regions[FADT].pa);for(unsigned i=0;i<ssdt;i++)put64(r->bytes+44+i*8,regions[SSDT0+i].pa);sum_at(r->bytes,n,9);inventory.words[7]=ssdt+1;}
static void fixture(unsigned ssdt){
 memset(regions,0,sizeof regions);memset(&inventory,0,sizeof inventory);reads=0;denied=0;poisoned=0;
 for(unsigned i=0;i<REGIONS;i++)regions[i].pa=0x100000+(uint64_t)i*0x110000;
 Region*r=&regions[RSDP];r->length=36;memcpy(r->bytes,"RSD PTR ",8);r->bytes[15]=2;put32(r->bytes+20,36);put64(r->bytes+24,regions[XSDT].pa);sum_at(r->bytes,20,8);sum_at(r->bytes,36,32);
 table(FADT,"FACP",244);r=&regions[FADT];put32(r->bytes+40,(uint32_t)regions[DSDT].pa);put32(r->bytes+64,0x604);r->bytes[89]=2;put32(r->bytes+112,1024);r->bytes[116]=1;r->bytes[117]=8;put64(r->bytes+120,0xcf9);r->bytes[128]=15;sum_at(r->bytes,r->length,9);
 table(DSDT,"DSDT",48);const uint8_t aml[]={8,'_','S','5','_',18,6,4,0,0,0,0};memcpy(regions[DSDT].bytes+36,aml,sizeof aml);sum_at(regions[DSDT].bytes,48,9);
 for(unsigned i=0;i<17;i++)table(SSDT0+i,"SSDT",36);
 inventory.words[0]=regions[RSDP].pa;inventory.words[1]=regions[XSDT].pa;inventory.words[3]=regions[FADT].pa;inventory.words[19]=regions[DSDT].pa;root_entries(ssdt);
}
static const uint8_t*actual_fadt,*actual_dsdt;static size_t actual_flen,actual_dlen;static int actual_on;
ABI const uint8_t *pwr_reader(uint64_t context,uint64_t pa,size_t n){
 CHECK(context==tag&&pa&&pa<UINT64_C(0x100000000)&&n&&n<=1048576&&n<=UINT64_C(0x100000000)-pa);CHECK(!poisoned);reads++;
 if(pa==denied)return NULL;
 if(actual_on&&pa==regions[FADT].pa){CHECK(n<=actual_flen);return actual_fadt;}
 if(actual_on&&pa==regions[DSDT].pa){CHECK(n<=actual_dlen);return actual_dsdt;}
 for(unsigned i=0;i<REGIONS;i++)if(regions[i].pa==pa){CHECK(n<=regions[i].length);return regions[i].bytes;}
 return NULL;
}
static Prepared capture(int reset_ok,int sleep_ok){
 struct{uint64_t pre;Prepared plan;uint64_t post;}out;memset(&out,0x6a,sizeof out);out.pre=0x1234;out.post=0x5678;
 CHECK(pwr_capture(tag,&inventory,&out.plan)==0);CHECK(out.pre==0x1234&&out.post==0x5678&&out.plan.version==1);
 CHECK((out.plan.reset_error==0)==reset_ok&&(out.plan.shutdown_error==0)==sleep_ok);
 if(!reset_ok){Write zero={0};CHECK(memcmp(&out.plan.reset,&zero,sizeof zero)==0);}if(!sleep_ok){Shutdown zero={0};CHECK(memcmp(&out.plan.shutdown,&zero,sizeof zero)==0);}
 scenarios++;return out.plan;
}
static void capture_cases(void){
 fixture(0);label="base trusted Reader capture";Prepared plan=capture(1,1);CHECK(plan.tables==1&&plan.reset.address==0xcf9&&plan.shutdown.a.address==0x604);
 unsigned before=reads;poisoned=1;memset(regions,0xaa,sizeof regions);label="no borrowed firmware pointer retained after capture";hardware(1,1,0,1);CHECK(pwr_execute(&plan,1)==0&&used==3);hardware(1,1,0,1);CHECK(pwr_execute(&plan,2)==0&&used==5);CHECK(reads==before);
 for(unsigned ssdt=1;ssdt<=15;ssdt++){fixture(ssdt);label="all SSDTs collected within sixteen AML tables";plan=capture(1,1);CHECK(plan.tables==ssdt+1);}
 fixture(16);label="seventeenth AML table refuses both plans";capture(0,0);
 for(unsigned i=RSDP;i<=SSDT0;i++){
  fixture(1);denied=regions[i].pa;label="Reader denial fails both plans";capture(0,0);
  fixture(1);regions[i].bytes[i==RSDP?8:9]^=1;label="late checksum fails both plans";capture(0,0);
 }
 fixture(0);inventory.words[0]=UINT64_C(0xfffffff8);label="range checked before callback";plan=capture(0,0);CHECK(reads==0);
 fixture(0);inventory.words[19]+=4096;label="DSDT inventory link mismatch";capture(0,0);
 fixture(1);put64(regions[XSDT].bytes+44,regions[FADT].pa);sum_at(regions[XSDT].bytes,regions[XSDT].length,9);label="duplicate root address";capture(0,0);
 fixture(0);put32(regions[FADT].bytes+4,35);label="bad length checked before full Reader request";capture(0,0);
 fixture(0);put64(regions[FADT].bytes+120,0x604);sum_at(regions[FADT].bytes,244,9);label="reset whitelist fails independently";capture(0,1);
 fixture(0);Region*r=&regions[DSDT];r->bytes[r->length++]=0xa0;r->bytes[r->length++]=3;r->bytes[r->length++]=1;r->bytes[r->length++]=0xa3;put32(r->bytes+4,(uint32_t)r->length);sum_at(r->bytes,r->length,9);label="dynamic AML fails shutdown independently";plan=capture(1,0);hardware(1,1,0,1);CHECK(pwr_execute(&plan,2)!=0&&used==0);CHECK(pwr_execute(&plan,1)==0&&used==3);
 fixture(0);plan=capture(1,1);hardware(1,1,0,1);plan.version=0;CHECK(pwr_execute(&plan,1)!=0&&used==0);plan.version=1;plan.tables=17;CHECK(pwr_execute(&plan,2)!=0&&used==0);plan.tables=1;CHECK(pwr_execute(&plan,3)!=0&&used==0);CHECK(pwr_execute(NULL,1)!=0&&used==0);
}
static uint8_t*load(const char*name,size_t*n){FILE*f=fopen(name,"rb");CHECK(f);CHECK(fseek(f,0,SEEK_END)==0);long size=ftell(f);CHECK(size>=36&&size<=1048576);CHECK(fseek(f,0,SEEK_SET)==0);uint8_t*p=malloc((size_t)size);CHECK(p&&fread(p,1,(size_t)size,f)==(size_t)size);CHECK(fclose(f)==0);*n=(size_t)size;return p;}
int main(int argc,char**argv){
 uint64_t sizes[2];pwr_runtime_sizes(sizes);CHECK(sizes[0]==184&&sizes[1]==2456);executor_cases();capture_cases();
 if(argc==3){actual_fadt=load(argv[1],&actual_flen);actual_dsdt=load(argv[2],&actual_dlen);fixture(0);actual_on=1;uint64_t pa=get32(actual_fadt+40);if(actual_flen>=148&&get64(actual_fadt+140))pa=get64(actual_fadt+140);regions[DSDT].pa=pa;inventory.words[19]=pa;label="actual OVMF immutable FADT/DSDT Reader";Prepared plan=capture(1,1);CHECK(plan.shutdown.source.offset==8159&&plan.reset.value==15);actual_on=0;free((void*)actual_fadt);free((void*)actual_dsdt);}
 printf("power runtime model passed: plans=184 inventory=2456 scenarios=%u assertions=%llu exact-I/O-order IF-restore AC-clear no-retained-borrows no-SMI no-MMIO\n",scenarios,(unsigned long long)checks);return 0;
}
