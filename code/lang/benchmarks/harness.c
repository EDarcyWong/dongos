/* Correctness and monotonic timing only; no C version is timed. */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif
#define ABI __attribute__((sysv_abi))
#define DECLARE(P) \
extern uint64_t ABI P##_sum(uint64_t); \
extern uint64_t ABI P##_lcg(uint64_t,uint64_t); \
extern uint64_t ABI P##_mix(uint64_t,uint64_t); \
extern uint64_t ABI P##_array_sum(const uint64_t*,uint64_t); \
extern uint64_t ABI P##_array_copy(uint64_t*,const uint64_t*,uint64_t)
DECLARE(dong);DECLARE(ref);
static uint64_t frequency=0;
static const uint64_t seed=UINT64_C(0x18d46c3b950a27fe),guard=UINT64_C(0xa519ec82b704d36f);
static const char *names[]={"sum","lcg","mix","array_sum","array_copy"};
static uint64_t *source,*dong_target,*ref_target,words,iterations,repeats;
static uint64_t expected[5];
static volatile uint64_t sink;
void ABI __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const void *file,uint64_t length){
 (void)file;(void)length;fprintf(stderr,"unexpected panic kind=%u line=%u\n",kind,line);exit(80);
}
static uint64_t now(void){
#ifdef _WIN32
 LARGE_INTEGER value;if(!QueryPerformanceCounter(&value)){exit(81);}return (uint64_t)value.QuadPart;
#else
 struct timespec value;if(clock_gettime(CLOCK_MONOTONIC,&value)){exit(81);}return (uint64_t)value.tv_sec*UINT64_C(1000000000)+(uint64_t)value.tv_nsec;
#endif
}
static void print_u64(uint64_t value){printf("%08x%08x",(unsigned)(value>>32),(unsigned)value);}
static uint64_t invoke(unsigned kind,unsigned backend){
 switch(kind){
 case 0:return backend?ref_sum(iterations):dong_sum(iterations);
 case 1:return backend?ref_lcg(iterations,seed):dong_lcg(iterations,seed);
 case 2:return backend?ref_mix(iterations,seed):dong_mix(iterations,seed);
 case 3:return backend?ref_array_sum(source+1,words):dong_array_sum(source+1,words);
 default:return backend?ref_array_copy(ref_target+1,source+1,words):dong_array_copy(dong_target+1,source+1,words);
 }
}
static void guards(void){
 if(source[0]!=guard||source[words+1]!=guard||dong_target[0]!=guard||dong_target[words+1]!=guard||ref_target[0]!=guard||ref_target[words+1]!=guard){fprintf(stderr,"array guard changed\n");exit(82);}
}
static void correctness(void){
 uint64_t sum=0,lcg=seed,mix=seed;for(uint64_t i=0;i<iterations;i++){
  sum+=i;lcg=lcg*UINT64_C(6364136223846793005)+UINT64_C(1442695040888963407);
  if(((mix^i)&1)==0){mix=(mix+i)^UINT64_C(0x9e3779b97f4a7c15);}else{mix=(mix*3)^i;}
 }
 expected[0]=sum;expected[1]=lcg;expected[2]=mix;expected[3]=0;expected[4]=words;
 uint64_t original=seed;
 for(uint64_t i=0;i<words;i++){
  original=original*UINT64_C(2862933555777941757)+UINT64_C(3037000493);
  if(source[i+1]!=original){fprintf(stderr,"immutable source changed\n");exit(90);}
  expected[3]+=original;
 }
 for(unsigned kind=0;kind<5;kind++){
  if(invoke(kind,0)!=expected[kind]||invoke(kind,1)!=expected[kind]){fprintf(stderr,"value mismatch %s\n",names[kind]);exit(83);}
  printf("correct\t%s\t",names[kind]);print_u64(expected[kind]);putchar('\n');
 }
 original=seed;
 for(uint64_t i=0;i<words;i++){
  original=original*UINT64_C(2862933555777941757)+UINT64_C(3037000493);
  if(dong_target[i+1]!=original||ref_target[i+1]!=original){fprintf(stderr,"copy mismatch\n");exit(84);}
 }
 guards();
}
static void measure(unsigned sample,unsigned kind,unsigned backend,unsigned order){
 uint64_t checksum=0,last=0,start=now();
 for(uint64_t repeat=0;repeat<repeats;repeat++){last=invoke(kind,backend);checksum+=last^repeat;}
 uint64_t ticks=now()-start;
 uint64_t nanoseconds=(uint64_t)((double)ticks*1000000000.0/(double)frequency);
 sink=checksum;
 if(last!=expected[kind]){fprintf(stderr,"timed result mismatch\n");exit(85);}
 guards();
 printf("sample\t%u\t%s\t%s\t%u\t",sample,names[kind],backend?"reference":"dong",order);
 print_u64(ticks);putchar('\t');print_u64(nanoseconds);putchar('\t');print_u64(checksum);putchar('\n');
}
int main(int argc,char **argv){
 if(argc!=4){return 86;}iterations=strtoull(argv[1],NULL,10);words=strtoull(argv[2],NULL,10);repeats=strtoull(argv[3],NULL,10);
 if(!iterations||iterations>100000000||!words||words>1048576||!repeats||repeats>1024){return 87;}
#ifdef _WIN32
 LARGE_INTEGER hz;if(!QueryPerformanceFrequency(&hz)||hz.QuadPart<=0){return 88;}frequency=(uint64_t)hz.QuadPart;
#else
 frequency=UINT64_C(1000000000);
#endif
 source=malloc((size_t)(words+2)*8);dong_target=malloc((size_t)(words+2)*8);ref_target=malloc((size_t)(words+2)*8);
 if(!source||!dong_target||!ref_target){return 89;}
 source[0]=source[words+1]=dong_target[0]=dong_target[words+1]=ref_target[0]=ref_target[words+1]=guard;
 uint64_t value=seed;for(uint64_t i=0;i<words;i++){value=value*UINT64_C(2862933555777941757)+UINT64_C(3037000493);source[i+1]=value;dong_target[i+1]=ref_target[i+1]=~value;}
 printf("clock_frequency\t");print_u64(frequency);putchar('\n');correctness();
 /* Fixed two warmups; no adaptive selection, best-of run, or discarded sample. */
 for(unsigned warm=0;warm<2;warm++){for(unsigned kind=0;kind<5;kind++){sink=invoke(kind,0);sink=invoke(kind,1);}}
 /* Nine paired samples; kernel order rotates, backend order alternates. */
 for(unsigned sample=0;sample<9;sample++){for(unsigned offset=0;offset<5;offset++){
  unsigned kind=(sample+offset)%5,first=(sample+kind)&1;
  measure(sample,kind,first,0);measure(sample,kind,first^1,1);
 }}
 correctness();free(source);free(dong_target);free(ref_target);return 0;
}
