
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_guest_source_path(uint64_t,const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){(void)k;(void)l;(void)f;(void)n;exit(87);}
int main(void){_Alignas(16) uint8_t b[96];const uint8_t s[]="a.dg";memset(b,0xa5,sizeof b);uint64_t rc=dong_guest_source_path(0,s,4,b,64,(uint64_t*)(b+32));int changed=0;for(int i=4;i<64;i++)changed+=b[i]!=0xa5;printf("{\"status\":%llu,\"out_tail_changed_bytes\":%d}\n",(unsigned long long)rc,changed);return 0;}
