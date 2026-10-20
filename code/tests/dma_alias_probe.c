#include <stdint.h>
#include <stdio.h>
extern uint64_t alias_check(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
#define CHECK(x) do {if(!(x)){fprintf(stderr,"DMA alias check failed line %d\n",__LINE__);return 1;}}while(0)
int main(void){
 for(uint64_t owner=0;owner<16;owner++)for(uint64_t state=1;state<=2;state++)for(uint64_t write=0;write<=1;write++){
  for(uint64_t page=0;page<32;page++)CHECK(alias_check(0x200000+page*4096,0x200000,32,state,owner,write)==0x04060004);
  CHECK(alias_check(0x1ff000,0x200000,32,state,owner,write)==0);
  CHECK(alias_check(0x220000,0x200000,32,state,owner,write)==0);
 }
 CHECK(alias_check(0x200000,0x200000,32,0,2,1)==0);
 CHECK(alias_check(0x200000,0,32,1,2,1)==0);
 CHECK(alias_check(0x1000,0xfffffffffffff000ULL,32,1,2,1)==0);
 CHECK(alias_check(0xfffffffffffff000ULL,0xfffffffffffff000ULL,32,1,2,1)==0x04060004);
 puts("DMA alias native checks passed");return 0;
}
