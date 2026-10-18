#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"POWER_MODEL_ASSERT line %d: %s scenario=%s\n",__LINE__,#x,label);exit(1);}}while(0)
typedef struct{uint64_t io_start,io_end,mmio_start,mmio_end;}Policy;
typedef struct{uint64_t space,address,width,value;}Write;
typedef struct{uint64_t a,b,table,offset;}Sleep;
typedef struct{Write a,b;uint64_t clear,enable,has_b;Sleep source;}Shutdown;
typedef struct{const uint8_t*bytes;size_t length;}Table;
typedef struct{uint8_t bytes[8192];size_t length;}Buffer;
extern ABI void pwr_sizes(uint64_t*);
extern ABI uint64_t pwr_reset(const uint8_t*,size_t,const Policy*,Write*),pwr_s5(const Table*,size_t,Sleep*),pwr_shutdown(const uint8_t*,size_t,const Table*,size_t,const Policy*,Shutdown*);
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected power panic %llu\n",(unsigned long long)code);exit(99);}
ABI void power_negative_hit(uint64_t kind){static uint64_t seen;uint64_t bit=1ull<<kind;if(!(seen&bit)){seen|=bit;fprintf(stderr,"POWER_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}}
static const char*label="start";static uint64_t checks;static unsigned resets,sleeps,rejects,shutdowns;
static uint8_t fadt[512],dsdt[8192],ssdt[8192];static size_t flen,dlen,slen;
static Policy allowed={0x600,0xd00,0xfed00000,0xfed01000};
static const uint64_t PRE=UINT64_C(0x12345678abcdef01),POST=UINT64_C(0x10fedcba87654321);
static void put32(uint8_t*p,uint64_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
static void put64(uint8_t*p,uint64_t v){for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(v>>(i*8));}
static uint64_t get(const uint8_t*p,unsigned n){uint64_t v=0;for(unsigned i=0;i<n;i++)v|=(uint64_t)p[i]<<(8*i);return v;}
static void checksum(uint8_t*raw,size_t length){raw[9]=0;unsigned sum=0;for(size_t i=0;i<length;i++)sum+=raw[i];raw[9]=(uint8_t)(0-sum);}
static void header(uint8_t*raw,size_t length,const char*signature){memset(raw,0,length);memcpy(raw,signature,4);put32(raw+4,length);raw[8]=6;memcpy(raw+10,"DONGOS",6);checksum(raw,length);}
static void add(Buffer*b,const void*p,size_t n){CHECK(n<=sizeof b->bytes-b->length);memcpy(b->bytes+b->length,p,n);b->length+=n;}
static void one(Buffer*b,unsigned value){uint8_t byte=(uint8_t)value;add(b,&byte,1);}
static void integer(Buffer*b,uint64_t n,unsigned width){
 if(width==0&&(n==0||n==1)){one(b,(unsigned)n);return;}if(width==0)width=8;
 one(b,width==1?10:width==2?11:width==4?12:14);for(unsigned i=0;i<width;i++)one(b,(unsigned)(n>>(8*i)));
}
static void package(Buffer*b,unsigned op,const Buffer*body){
 one(b,op);size_t length=body->length+1,bytes=1;while((bytes==1&&length>=64)||(bytes>1&&length>=(1ull<<(4+8*(bytes-1))))){bytes++;length=body->length+bytes;}
 if(bytes==1)one(b,(unsigned)length);else{one(b,(unsigned)(((bytes-1)<<6)|(length&15)));for(size_t i=0;i<bytes-1;i++)one(b,(unsigned)(length>>(4+8*i)));}add(b,body->bytes,body->length);
}
static Buffer s5name(const char*name,uint64_t a,uint64_t b,unsigned width){Buffer out={0},values={0};one(&out,8);add(&out,name,strlen(name));one(&values,4);integer(&values,a,width);integer(&values,b,width);integer(&values,0,0);integer(&values,0,0);package(&out,18,&values);return out;}
static void aml_table(uint8_t*raw,size_t*length,const char*signature,const Buffer*body){*length=36+body->length;header(raw,*length,signature);memcpy(raw+36,body->bytes,body->length);checksum(raw,*length);}
static void setup(void){flen=276;header(fadt,flen,"FACP");put32(fadt+112,1024);fadt[116]=1;fadt[117]=8;fadt[119]=1;put64(fadt+120,0xcf9);fadt[128]=6;fadt[89]=2;put32(fadt+64,0x604);put32(fadt+68,0x608);checksum(fadt,flen);}
static int reset_model(const uint8_t*raw,size_t length,const Policy*p,Write*out){
 if(!raw||!p||length<36||length>1048576||memcmp(raw,"FACP",4)||get(raw+4,4)!=length||raw[8]==0)return 0;
 unsigned sum=0;for(size_t i=0;i<length;i++)sum+=raw[i];if(sum%256||length<129||raw[8]<2||!(get(raw+112,4)&1024))return 0;
 if(p->io_start>p->io_end||p->io_end>65536||p->mmio_start>p->mmio_end||p->mmio_end>UINT64_C(0x10000000000000))return 0;
 unsigned space=raw[116];uint64_t address=get(raw+120,8);if(space>1||raw[117]!=8||raw[118]||(raw[119]!=0&&raw[119]!=1)||!address)return 0;
 uint64_t lo=space?p->io_start:p->mmio_start,hi=space?p->io_end:p->mmio_end;if(address<lo||address>=hi)return 0;
 *out=(Write){space,address,8,raw[128]};return 1;
}
static void reset_case(void){struct{uint64_t pre;Write value;uint64_t post;}actual={PRE,{99,98,97,96},POST};Write expected={0};Write old=actual.value;int ok=reset_model(fadt,flen,&allowed,&expected);uint64_t result=pwr_reset(fadt,flen,&allowed,&actual.value);CHECK((result==0)==ok);CHECK(memcmp(&actual.value,ok?&expected:&old,sizeof old)==0);CHECK(actual.pre==PRE&&actual.post==POST);resets++;if(!ok)rejects++;}
static void sleep_case(int success,uint64_t a,uint64_t b,unsigned count){
 Table tables[]={{dsdt,dlen},{ssdt,slen}};struct{uint64_t pre;Sleep value;uint64_t post;}actual={PRE,{99,98,97,96},POST};Sleep old=actual.value;uint64_t result=pwr_s5(tables,count,&actual.value);
 CHECK((result==0)==success);if(success){CHECK(actual.value.a==a&&actual.value.b==b&&actual.value.table<count&&actual.value.offset>=36);}else{CHECK(memcmp(&actual.value,&old,sizeof old)==0);rejects++;}CHECK(actual.pre==PRE&&actual.post==POST);sleeps++;
}
static void shutdown_case(int success,int has_b,unsigned space,uint64_t a,uint64_t b){
 Table tables[]={{dsdt,dlen}};struct{uint64_t pre;Shutdown value;uint64_t post;}actual;memset(&actual,0x6a,sizeof actual);actual.pre=PRE;actual.post=POST;Shutdown before=actual.value;uint64_t result=pwr_shutdown(fadt,flen,tables,1,&allowed,&actual.value);CHECK((result==0)==success);
 if(success){CHECK(actual.value.a.space==space&&actual.value.a.width==16&&actual.value.a.value==(a<<10)&&actual.value.clear==0x3c00&&actual.value.enable==0x2000&&actual.value.has_b==(unsigned)has_b);CHECK(actual.value.source.a==a&&actual.value.source.b==b);if(has_b){CHECK(actual.value.b.space==space&&actual.value.b.width==16&&actual.value.b.value==(b<<10));}else{Write zero={0};CHECK(memcmp(&actual.value.b,&zero,sizeof zero)==0);}
  for(unsigned old=0;old<65536;old+=31){uint64_t typed=(old&~actual.value.clear)|actual.value.a.value;uint64_t enabled=typed|actual.value.enable;CHECK((enabled&~UINT64_C(0x3c00))==(old&~UINT64_C(0x3c00)));CHECK(((enabled>>10)&7)==a&&(enabled&0x2000));}
 }else{CHECK(memcmp(&actual.value,&before,sizeof before)==0);rejects++;}CHECK(actual.pre==PRE&&actual.post==POST);shutdowns++;
}
static void field_length(Buffer*b,uint32_t n){
 unsigned bytes=n<64?1:n<4096?2:n<1048576?3:4;
 if(bytes==1)one(b,n);else{one(b,((bytes-1)<<6)|(n&15));for(unsigned i=0;i<bytes-1;i++)one(b,n>>(4+8*i));}
}
static Buffer region(const char*name,int dynamic){Buffer b={0};one(&b,91);one(&b,128);add(&b,name,strlen(name));one(&b,1);if(dynamic)add(&b,"CALL",4);else integer(&b,0x402,2);integer(&b,1,0);return b;}
static Buffer field_object(unsigned code,const char*name,unsigned badflags){
 Buffer b={0},payload={0};add(&payload,"REGN",4);if(code==134||code==135)add(&payload,"INDX",4);if(code==135)integer(&payload,1,0);one(&payload,badflags?128:1);
 one(&payload,0);field_length(&payload,65536);one(&payload,1);one(&payload,1);one(&payload,0);one(&payload,3);one(&payload,1);one(&payload,11);one(&payload,1);
 add(&payload,name,4);field_length(&payload,8);one(&b,91);package(&b,code,&payload);return b;
}
static void extended_static_cases(void){
 Buffer good=s5name("_S5_",5,6,1),body={0},item=region("REGN",0);add(&body,item.bytes,item.length);add(&body,good.bytes,good.length);
 aml_table(dsdt,&dlen,"DSDT",&body);label="static OperationRegion constants";sleep_case(1,5,6,1);
 item=region("_S5_",0);body.length=0;add(&body,item.bytes,item.length);add(&body,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&body);label="OperationRegion root S5 is not a sleep package";sleep_case(0,0,0,1);
 item=region("REGN",1);body.length=0;add(&body,good.bytes,good.length);add(&body,item.bytes,item.length);aml_table(dsdt,&dlen,"DSDT",&body);label="late dynamic Region offset refuses earlier candidate";sleep_case(0,0,0,1);
 for(unsigned code=129;code<=135;code++){if(code!=129&&code!=134&&code!=135)continue;
  item=field_object(code,"FLD0",0);body.length=0;add(&body,item.bytes,item.length);add(&body,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&body);label="Field named/reserved/access/extended bit-length structure";sleep_case(1,5,6,1);
  item=field_object(code,"_S5_",0);body.length=0;add(&body,good.bytes,good.length);add(&body,item.bytes,item.length);aml_table(dsdt,&dlen,"DSDT",&body);label="late Field/IndexField/BankField root S5 name rejects atomically";sleep_case(0,0,0,1);
  item=field_object(code,"FLD0",1);body.length=0;add(&body,good.bytes,good.length);add(&body,item.bytes,item.length);aml_table(dsdt,&dlen,"DSDT",&body);label="Field reserved flags";sleep_case(0,0,0,1);
 }
 item=field_object(129,"_S5_",0);Buffer scoped={0},payload={0};add(&payload,"DEV0",4);add(&payload,item.bytes,item.length);one(&scoped,91);package(&scoped,130,&payload);add(&scoped,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&scoped);label="child Field S5 does not shadow root";sleep_case(1,5,6,1);
 Buffer connect={0},buffer={0};add(&connect,"REGN",4);one(&connect,1);one(&connect,2);integer(&buffer,good.length,1);add(&buffer,good.bytes,good.length);package(&connect,17,&buffer);add(&connect,"FLD0",4);field_length(&connect,8);body.length=0;one(&body,91);package(&body,129,&connect);add(&body,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&body);label="ConnectField Buffer fake S5 bytes stay inert";sleep_case(1,5,6,1);
 for(unsigned cut=0;cut<item.length;cut++){body=good;add(&body,item.bytes,cut);aml_table(dsdt,&dlen,"DSDT",&body);label="all truncated late Field terms";sleep_case(cut==0,5,6,1);}
 for(unsigned code=1;code<=2;code++){body.length=0;one(&body,91);one(&body,code);add(&body,"_S5_",4);if(code==1)one(&body,0);add(&body,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&body);label="Mutex/Event root S5 name rejects";sleep_case(0,0,0,1);}
 for(unsigned code=131;code<=132;code++){payload.length=0;add(&payload,"CPU0",4);for(unsigned i=0;i<(code==131?6u:3u);i++)one(&payload,0);add(&payload,good.bytes,good.length);body.length=0;one(&body,91);package(&body,code,&payload);add(&body,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&body);label="Processor/PowerResource body is an actual child namespace";sleep_case(1,5,6,1);}
 Buffer nested={0},values={0},entry={0};one(&entry,4);integer(&entry,0xffff,2);integer(&entry,1,0);add(&entry,"LNKA",4);integer(&entry,0,0);one(&values,128);for(unsigned i=0;i<128;i++)package(&values,18,&entry);one(&nested,8);add(&nested,"PRTP",4);package(&nested,18,&values);add(&nested,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&nested);label="128-entry inert PCI routing package with reference elements";sleep_case(1,5,6,1);
 body.length=0;one(&body,8);add(&body,"_S5_",4);package(&body,18,&values);aml_table(dsdt,&dlen,"DSDT",&body);label="nested root S5 package is never a literal sleep candidate";sleep_case(0,0,0,1);
 values.length=0;one(&values,4);integer(&values,5,1);integer(&values,6,1);add(&values,"CALL",4);integer(&values,0,0);body.length=0;one(&body,8);add(&body,"_S5_",4);package(&body,18,&values);aml_table(dsdt,&dlen,"DSDT",&body);label="root S5 reference member unsupported";sleep_case(0,0,0,1);
 Buffer bounded=s5name("FAKE",1,2,1);for(unsigned i=0;i<18;i++){values.length=0;one(&values,1);add(&values,bounded.bytes+5,bounded.length-5);body.length=0;one(&body,8);add(&body,"FAKE",4);package(&body,18,&values);bounded=body;}
 add(&bounded,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&bounded);label="package depth bound fails closed";sleep_case(0,0,0,1);
}
int main(void){
 uint64_t sizes[5];pwr_sizes(sizes);CHECK(sizes[0]==32&&sizes[1]==32&&sizes[2]==32&&sizes[3]==120&&sizes[4]==16);
 for(unsigned space=0;space<2;space++)for(unsigned access=0;access<5;access++)for(unsigned width=0;width<=64;width+=8)for(unsigned offset=0;offset<3;offset++){
  setup();fadt[116]=(uint8_t)space;fadt[117]=(uint8_t)width;fadt[118]=(uint8_t)offset;fadt[119]=(uint8_t)access;put64(fadt+120,space?0xcf9:0xfed00003);checksum(fadt,flen);label="reset GAS matrix";reset_case();
 }
 const uint64_t addresses[]={0,1,0x5ff,0x600,0xcff,0xd00,65535,65536,0xfecfffff,0xfed00000,0xfed00fff,0xfed01000,UINT64_MAX};
 for(unsigned space=0;space<2;space++)for(unsigned i=0;i<sizeof addresses/sizeof addresses[0];i++){setup();fadt[116]=(uint8_t)space;put64(fadt+120,addresses[i]);checksum(fadt,flen);label="reset allowed ranges";reset_case();}
 setup();fadt[116]=2;checksum(fadt,flen);label="PCI GAS unsupported";reset_case();setup();fadt[9]^=1;label="reset checksum";reset_case();setup();flen=128;put32(fadt+4,flen);checksum(fadt,flen);label="reset short FADT";reset_case();setup();put32(fadt+112,0);checksum(fadt,flen);label="reset flag absent";reset_case();
 for(unsigned width=0;width<=8;width=width?width*2:1)for(unsigned a=0;a<8;a++)for(unsigned b=0;b<8;b++){
  Buffer body=s5name("\\_S5_",a,b,width);aml_table(dsdt,&dlen,"DSDT",&body);label="root literal S5 widths and types";sleep_case(1,a,b,1);
 }
 Buffer good=s5name("_S5_",5,6,1),empty={0};aml_table(dsdt,&dlen,"DSDT",&good);aml_table(ssdt,&slen,"SSDT",&empty);label="empty SSDT";sleep_case(1,5,6,2);
 Buffer nested={0},scope={0};add(&scope,"_SB_",4);add(&scope,good.bytes,good.length);package(&nested,16,&scope);aml_table(dsdt,&dlen,"DSDT",&nested);label="non-root _S5 must not authorize shutdown";sleep_case(0,0,0,1);
 Buffer absolute=s5name("\\_S5_",3,4,1);scope.length=0;add(&scope,"_SB_",4);add(&scope,absolute.bytes,absolute.length);nested.length=0;package(&nested,16,&scope);aml_table(dsdt,&dlen,"DSDT",&nested);label="absolute root from nested scope";sleep_case(1,3,4,1);
 Buffer parent=s5name("^_S5_",2,7,1);scope.length=0;add(&scope,"_SB_",4);add(&scope,parent.bytes,parent.length);nested.length=0;one(&nested,91);package(&nested,130,&scope);aml_table(dsdt,&dlen,"DSDT",&nested);label="parent-prefix Device namespace";sleep_case(1,2,7,1);
 Buffer decoys={0},buffer={0},method={0};one(&decoys,8);add(&decoys,"BUFF",4);integer(&buffer,good.length,1);add(&buffer,good.bytes,good.length);package(&decoys,17,&buffer);
 one(&decoys,8);add(&decoys,"STRG",4);one(&decoys,13);add(&decoys,"_S5_ Package Name bytes",22);one(&decoys,0);
 add(&method,"FAKE",4);one(&method,0);add(&method,good.bytes,good.length);package(&decoys,20,&method);aml_table(dsdt,&dlen,"DSDT",&decoys);label="buffer string method decoys";sleep_case(0,0,0,1);
 add(&decoys,absolute.bytes,absolute.length);aml_table(dsdt,&dlen,"DSDT",&decoys);label="decoys plus true static root";sleep_case(1,3,4,1);
 Buffer huge={0};add(&huge,"FAKE",4);one(&huge,0);for(unsigned i=0;i<300;i++)one(&huge,0xcc);Buffer long_method={0};package(&long_method,20,&huge);add(&long_method,good.bytes,good.length);aml_table(dsdt,&dlen,"DSDT",&long_method);label="multi-byte package length excludes method bytes";sleep_case(1,5,6,1);
 aml_table(dsdt,&dlen,"DSDT",&good);aml_table(ssdt,&slen,"SSDT",&absolute);label="duplicate across tables";sleep_case(0,0,0,2);
 aml_table(dsdt,&dlen,"DSDT",&empty);aml_table(ssdt,&slen,"SSDT",&absolute);label="S5 defined by SSDT";sleep_case(1,3,4,2);
 Buffer dynamic={0};one(&dynamic,0xa0);one(&dynamic,0x03);one(&dynamic,1);one(&dynamic,0xa3);aml_table(dsdt,&dlen,"DSDT",&good);aml_table(ssdt,&slen,"SSDT",&dynamic);label="late dynamic module term rejects earlier candidate atomically";sleep_case(0,0,0,2);
 for(unsigned i=0;i<good.length;i++){Buffer broken=good;broken.length=i;aml_table(dsdt,&dlen,"DSDT",&broken);label="all AML truncations";sleep_case(0,0,0,1);}
 Buffer bad=s5name("_S5_",8,1,1);aml_table(dsdt,&dlen,"DSDT",&bad);label="sleep type outside field";sleep_case(0,0,0,1);
 bad=good;bad.bytes[6]=0xff;aml_table(dsdt,&dlen,"DSDT",&bad);label="malformed package size";sleep_case(0,0,0,1);
 aml_table(dsdt,&dlen,"DSDT",&good);dsdt[9]^=1;label="DSDT checksum";sleep_case(0,0,0,1);
 aml_table(dsdt,&dlen,"DSDT",&good);setup();label="legacy PM1a/b RMW plan";shutdown_case(1,1,1,5,6);
 put32(fadt+68,0);checksum(fadt,flen);label="optional PM1b";shutdown_case(1,0,1,5,6);
 setup();put32(fadt+64,0);put32(fadt+68,0);fadt[172]=0;fadt[173]=16;fadt[175]=2;put64(fadt+176,0xfed00020);checksum(fadt,flen);label="bounded MMIO PM1a";shutdown_case(1,0,0,5,6);
 fadt[175]=3;checksum(fadt,flen);label="PM1 access-size mismatch";shutdown_case(0,0,0,5,6);
 setup();put32(fadt+112,1024|0x100000);checksum(fadt,flen);label="hardware-reduced sleep unsupported";shutdown_case(0,0,1,5,6);
 setup();put32(fadt+68,0x604);checksum(fadt,flen);label="alias PM1a/b rejected";shutdown_case(0,0,1,5,6);
 setup();put32(fadt+64,0xd00);checksum(fadt,flen);label="PM1 authority boundary";shutdown_case(0,0,1,5,6);
 Write output={1,2,3,4};Sleep sleep={1,2,3,4};Shutdown shut={0};Table table={dsdt,dlen};CHECK(pwr_reset(NULL,0,&allowed,&output)!=0&&output.address==2);CHECK(pwr_reset(fadt,flen,NULL,&output)!=0&&output.address==2);CHECK(pwr_reset(fadt,flen,&allowed,NULL)!=0);CHECK(pwr_s5(NULL,0,&sleep)!=0&&sleep.b==2);CHECK(pwr_s5(&table,17,&sleep)!=0&&sleep.b==2);CHECK(pwr_s5(&table,1,NULL)!=0);CHECK(pwr_shutdown(fadt,flen,&table,1,&allowed,NULL)!=0);CHECK(pwr_shutdown(fadt,flen,NULL,0,&allowed,&shut)!=0);
 extended_static_cases();
 printf("power oracle passed: reset-model=%u static-S5=%u shutdown-plans=%u atomic-rejections=%u all-guards=ok checks=%llu\n",resets,sleeps,shutdowns,rejects,(unsigned long long)checks);return 0;
}
