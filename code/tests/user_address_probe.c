#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
typedef struct { uint64_t bias,stack,source; } Layout;
extern uint64_t SYSV address_layout(uint64_t,uint64_t,uint64_t,Layout*),address_generate(Layout*);
static unsigned calls,fail_at,checks;
static uint64_t source=1;
uint64_t SYSV user_entropy64(uint64_t*out,uint64_t*kind){
 ++calls;if(calls==fail_at)return 0;
 *out=calls==1?UINT64_C(0xbca7e12d8a4310f5):UINT64_C(0xaec2f3278bd23a60);*kind=source;return 1;
}
void SYSV __dong_panic(void){fputs("unexpected Dong panic\n",stderr);}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"address policy failed line %u\n",__LINE__);return 1;}}while(0)
int main(void){
 struct{uint64_t lo;Layout value;uint64_t hi;} box={0x182734ab,{0,0,0},0xcba73482};
 for(unsigned i=0;i<262144;i++){
  uint64_t a=(UINT64_C(0xd6e8feb86659fd93)*i)^UINT64_C(0x4129d83cefa567ba),s=~a;
  CHECK(!address_layout(a,s,1+(i%3),&box.value));
  CHECK(box.value.bias==UINT64_C(0x10000000)+(a%4096)*65536);
  CHECK(box.value.stack==UINT64_C(0x7ffff00000)-(s%262144)*4096);
  CHECK(box.value.source==1+i%3&&box.lo==0x182734ab&&box.hi==0xcba73482);
  CHECK(box.value.bias>=0x10000000&&box.value.bias<0x20000000&&!(box.value.bias%65536));
  CHECK(box.value.stack>=UINT64_C(0x7fbff01000)&&box.value.stack<=UINT64_C(0x7ffff00000)&&!(box.value.stack%4096));
 }
 for(unsigned s=0;s<6;s++)if(s==0||s>3){
  Layout before=box.value;CHECK(address_layout(1,2,s,&box.value)==0x04080002);CHECK(!memcmp(&before,&box.value,sizeof before));
 }
 CHECK(address_layout(0,0,1,NULL)==0x04080002&&address_generate(NULL)==0x04080002);
 for(unsigned failure=1;failure<=2;failure++){
  calls=0;fail_at=failure;Layout before=box.value;
  CHECK(address_generate(&box.value)==0x04080001&&calls==failure&&!memcmp(&before,&box.value,sizeof before));
 }
 for(source=1;source<=2;source++){
  calls=0;fail_at=0;CHECK(!address_generate(&box.value)&&calls==2&&box.value.source==source);
 }
 printf("user address checks passed %u; hardware DRNG mocked, exact production policy executed\n",checks);return 0;
}
