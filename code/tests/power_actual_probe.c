#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { checks++; if(!(x)){fprintf(stderr,"POWER_ACTUAL_ASSERT line %d: %s\n",__LINE__,#x);exit(1);} } while(0)
typedef struct { uint64_t io_start,io_end,mmio_start,mmio_end; } Policy;
typedef struct { uint64_t space,address,width,value; } Write;
typedef struct { uint64_t a,b,table,offset; } Sleep;
typedef struct { Write a,b;uint64_t clear,enable,has_b;Sleep source; } Shutdown;
typedef struct { const uint8_t *bytes;size_t length; } Table;
extern ABI uint64_t pwr_reset(const uint8_t*,size_t,const Policy*,Write*);
extern ABI uint64_t pwr_s5(const Table*,size_t,Sleep*);
extern ABI uint64_t pwr_shutdown(const uint8_t*,size_t,const Table*,size_t,const Policy*,Shutdown*);
static unsigned checks;
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected power actual panic %llu\n",(unsigned long long)code);exit(99);}
static uint8_t *load(const char *name,size_t *size){
 FILE *file=fopen(name,"rb");CHECK(file!=NULL);CHECK(fseek(file,0,SEEK_END)==0);long n=ftell(file);CHECK(n>=36&&n<=1048576);CHECK(fseek(file,0,SEEK_SET)==0);
 uint8_t *raw=malloc((size_t)n+16);CHECK(raw!=NULL);CHECK(fread(raw,1,(size_t)n,file)==(size_t)n);CHECK(fclose(file)==0);*size=(size_t)n;return raw;
}
static void put32(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
static void checksum(uint8_t *raw,size_t size){raw[9]=0;unsigned sum=0;for(size_t i=0;i<size;i++)sum+=raw[i];raw[9]=(uint8_t)(0-sum);}
static void reject_actual(uint8_t *fadt,size_t flen,uint8_t *dsdt,size_t dlen){
 Table table={dsdt,dlen};Sleep sleep={91,92,93,94},old=sleep;Policy allowed={0x604,0x606,0,0};Shutdown shutdown,before;memset(&shutdown,0x6a,sizeof shutdown);before=shutdown;
 CHECK(pwr_s5(&table,1,&sleep)!=0);CHECK(memcmp(&sleep,&old,sizeof sleep)==0);
 CHECK(pwr_shutdown(fadt,flen,&table,1,&allowed,&shutdown)!=0);CHECK(memcmp(&shutdown,&before,sizeof shutdown)==0);
}
int main(int argc,char **argv){
 CHECK(argc==3);size_t flen,dlen;uint8_t *fadt=load(argv[1],&flen),*dsdt=load(argv[2],&dlen);CHECK(flen==244&&dlen==8716);
 CHECK(memcmp(fadt,"FACP",4)==0&&memcmp(dsdt,"DSDT",4)==0);
 /* The offset is independently derived by a full namespace/TermList walk in
    aml_reference.py and fixture SHA is checked by the Python test. No search. */
 const uint8_t literal[]={8,'_','S','5','_',18,6,4,0,0,0,0};CHECK(memcmp(dsdt+8159,literal,sizeof literal)==0);
 Policy reset_policy={0xcf9,0xcfa,0,0},sleep_policy={0x604,0x606,0,0};Write reset={0};Table table={dsdt,dlen};Sleep sleep={0};Shutdown shutdown={0};
 CHECK(pwr_reset(fadt,flen,&reset_policy,&reset)==0);CHECK(reset.space==1&&reset.address==0xcf9&&reset.width==8&&reset.value==15);
 CHECK(pwr_s5(&table,1,&sleep)==0);CHECK(sleep.a==0&&sleep.b==0&&sleep.table==0&&sleep.offset==8159);
 CHECK(pwr_shutdown(fadt,flen,&table,1,&sleep_policy,&shutdown)==0);
 CHECK(shutdown.a.space==1&&shutdown.a.address==0x604&&shutdown.a.width==16&&shutdown.a.value==0);
 CHECK(shutdown.b.address==0&&shutdown.has_b==0&&shutdown.clear==0x3c00&&shutdown.enable==0x2000);
 CHECK(shutdown.source.offset==8159&&shutdown.source.a==0&&shutdown.source.b==0);
 for(unsigned old=0;old<65536;old++){
  uint64_t typed=(old&~shutdown.clear)|shutdown.a.value,enabled=typed|shutdown.enable;
  CHECK((enabled&~UINT64_C(0x3c00))==(old&~UINT64_C(0x3c00)));CHECK((enabled&0x3c00)==0x2000);
 }
 uint8_t *copy=malloc(dlen+16);CHECK(copy!=NULL);memcpy(copy,dsdt,dlen);
 CHECK(memcmp(dsdt+43,"DBG_",4)==0);memcpy(dsdt+43,"_S5_",4);checksum(dsdt,dlen);reject_actual(fadt,flen,dsdt,dlen);
 memcpy(dsdt,copy,dlen);CHECK(memcmp(dsdt+60,"DBGB",4)==0);memcpy(dsdt+60,"_S5_",4);checksum(dsdt,dlen);reject_actual(fadt,flen,dsdt,dlen);
 memcpy(dsdt,copy,dlen);memcpy(dsdt+8160,"_S6_",4);checksum(dsdt,dlen);reject_actual(fadt,flen,dsdt,dlen);
 memcpy(dsdt,copy,dlen);const uint8_t dynamic[]={0xa0,3,1,0xa3};memcpy(dsdt+dlen,dynamic,sizeof dynamic);put32(dsdt+4,(uint32_t)(dlen+sizeof dynamic));checksum(dsdt,dlen+sizeof dynamic);reject_actual(fadt,flen,dsdt,dlen+sizeof dynamic);
 memcpy(dsdt,copy,dlen);dsdt[9]^=1;reject_actual(fadt,flen,dsdt,dlen);
 free(copy);free(dsdt);free(fadt);
 printf("power actual OVMF passed: S5=0/0 offset=8159 reset=IO:0xcf9/8:15 PM1a=IO:0x604/16 no-PM1b actual-root-field-region-dynamic-rejections=5 checks=%u\n",checks);return 0;
}
