
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_guest_compile_memory(const uint64_t*,const uint64_t*,uint64_t,uint64_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){(void)k;(void)l;(void)f;(void)n;exit(87);}
int main(void){uint64_t budget[5]={1,0,0,0,16384},region[4]={1,1,0,0},out[2],r[9];memset(out,0xa5,sizeof out);memset(r,0xa5,sizeof r);uint64_t rc=dong_guest_compile_memory(budget,region,1,out,1,r);int changed=0;for(int i=0;i<72;i++)changed+=((uint8_t*)r)[i]!=0xa5;printf("{\"status\":%llu,\"result_changed_bytes\":%d}\n",(unsigned long long)rc,changed);return 0;}
