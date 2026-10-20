
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define ABI __attribute__((sysv_abi))
typedef struct {uint64_t status,stage,code,written,total,attempts,stalls,flushes;} State;
typedef int64_t (ABI *W)(uint64_t,uint64_t,const uint8_t*,uint64_t);
typedef int64_t (ABI *F)(uint64_t);
extern uint64_t ABI dong_guest_artifact_commit_init(State*,uint64_t);
extern uint64_t ABI dong_guest_artifact_commit_step(State*,uint64_t,const uint8_t*,uint64_t,W,F);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){(void)k;(void)l;(void)f;(void)n;exit(87);}
static unsigned writes,flushes;
static int64_t ABI wr(uint64_t h,uint64_t o,const uint8_t*p,uint64_t n){(void)h;(void)o;(void)p;writes++;return n;}
static int64_t ABI fl(uint64_t h){(void)h;flushes++;return 0;}
int main(void){State s;uint8_t src[4]={1,2,3,4};dong_guest_artifact_commit_init(&s,4);s.status=1;s.attempts=UINT64_MAX;uint64_t r=dong_guest_artifact_commit_step(&s,7,src,4,wr,fl);printf("{\"return\":%llu,\"status\":%llu,\"written\":%llu,\"total\":%llu,\"write_calls\":%u,\"flush_calls\":%u}\n",(unsigned long long)r,(unsigned long long)s.status,(unsigned long long)s.written,(unsigned long long)s.total,writes,flushes);printf("attempts=%llu\n",(unsigned long long)s.attempts);r=dong_guest_artifact_commit_step(&s,7,src,4,wr,fl);printf("next=%llu;flush_calls=%u\n",(unsigned long long)r,flushes);return 0;}
