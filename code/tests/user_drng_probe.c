#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#define SYSV __attribute__((sysv_abi))
uint64_t drng_max,drng_seed,drng_random,seed_failures,random_failures,seed_calls,random_calls,cpuid_calls;
extern uint64_t SYSV user_entropy64(uint64_t*,uint64_t*);
void* SYSV dong_user_dispatch(void*p){(void)p;return NULL;}
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"DRNG retry failed line %u\n",__LINE__);return 1;}}while(0)
int main(void){
 for(unsigned maximum=0;maximum<=7;maximum++)for(unsigned seed=0;seed<2;seed++)for(unsigned random=0;random<2;random++)
 for(unsigned sf=0;sf<=33;sf++)for(unsigned rf=0;rf<=11;rf++){
  drng_max=maximum;drng_seed=seed;drng_random=random;seed_failures=sf;random_failures=rf;seed_calls=random_calls=cpuid_calls=0;
  uint64_t value=0xabc7,source=0x1239;
  unsigned seed_available=maximum>=7&&seed,random_available=maximum>=1&&random;
  uint64_t expected_seed=seed_available?(sf<32?sf+1:32):0;
  unsigned seed_ok=seed_available&&sf<32;
  uint64_t expected_random=(!seed_ok&&random_available)?(rf<10?rf+1:10):0;
  unsigned random_ok=!seed_ok&&random_available&&rf<10;
  CHECK(user_entropy64(&value,&source)==(seed_ok||random_ok));
  CHECK(seed_calls==expected_seed&&random_calls==expected_random);
  if(seed_ok)CHECK(value==UINT64_C(0x93be10ad73c84521)&&source==1);
  else if(random_ok)CHECK(value==UINT64_C(0xe327d813ab7ce410)&&source==2);
  else CHECK(value==0xabc7&&source==0x1239);
  CHECK(cpuid_calls==1u+(maximum>=7)+(!seed_ok&&maximum>=1));
 }
 printf("user DRNG capability/carry/retry checks passed %u; hardware instructions mocked\n",checks);return 0;
}
