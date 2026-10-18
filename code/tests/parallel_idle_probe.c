#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
extern U ABI gip_required(void),gip_init(U,U,U,U),gip_run(void),gip_get(U,U),gip_ticks(U),gip_error(void);
extern void ABI gip_fail(void);
static U checks,clocks,now,mode;
static void fail(const char*s,unsigned line){fprintf(stderr,"parallel idle oracle line %u: %s\n",line,s);exit(1);}
#define C(x)do{checks++;if(!(x))fail(#x,__LINE__);}while(0)
void ABI __dong_panic(void){fail("Dong panic",__LINE__);}
U ABI parallel_arch_if0(void){return 1;}
void ABI parallel_arch_lock(U*p){C(!*p);*p=1;}
void ABI parallel_arch_unlock(U*p){C(*p==1);*p=0;}
U ABI parallel_arch_on_scheduler(U a,U b){(void)a;(void)b;return 1;}
U ABI parallel_arch_root(void){return 0x100000;}
void ABI parallel_arch_save(U x){(void)x;C(0);}
void ABI parallel_arch_restore(U x){(void)x;C(0);}
void ABI parallel_arch_copy(U a,U b,U n){(void)a;(void)b;(void)n;C(0);}
void ABI parallel_arch_register(U a,U b){(void)a;(void)b;C(0);}
U ABI parallel_arch_install(U a,U b,U c){(void)a;(void)b;(void)c;C(0);return 1;}
U ABI parallel_arch_timer(U a,U b,U c){(void)a;(void)b;(void)c;C(0);return 1;}
U ABI parallel_arch_clock(void){C(0);return 0;}
void ABI parallel_arch_eoi(U a){(void)a;C(0);}
U ABI parallel_arch_kick(U a,U b){(void)a;(void)b;C(0);return 1;}
void ABI parallel_live_retire(U a,U b,U c){(void)a;(void)b;(void)c;C(0);}
void ABI parallel_live_pause(void){}
U ABI dg_arch_read_tsc(void){
 clocks++;C(clocks<=60000);now+=1000;
 if(mode==1&&clocks==7)(*(U*)(uintptr_t)gip_ticks(1))++;
 if(mode==2)(*(U*)(uintptr_t)gip_ticks(1))++;
 if(mode==3&&clocks==7)*(U*)(uintptr_t)gip_error()=1;
 if(mode==4&&clocks==7)return 0;
 return now;
}
static void*alloc(size_t bytes){
#ifdef _WIN32
 return _aligned_malloc(bytes,4096);
#else
 return aligned_alloc(4096,(bytes+4095)&~(size_t)4095);
#endif
}
int main(int argc,char**argv){
 C(argc==2);if(!strcmp(argv[1],"transient"))mode=1;else if(!strcmp(argv[1],"periodic"))mode=2;else if(!strcmp(argv[1],"worker"))mode=3;else if(!strcmp(argv[1],"rollback"))mode=4;else if(!strcmp(argv[1],"failed-domain"))mode=5;else C(!strcmp(argv[1],"quiet"));
 U size=gip_required();void*arena=alloc((size_t)size),*report=alloc(4096),*template=alloc(4096);C(arena&&report&&template);memset(arena,0xa5,(size_t)size);memset(report,0,4096);memset(template,0,4096);
 C(!gip_init((U)(uintptr_t)arena,size,(U)(uintptr_t)report,(U)(uintptr_t)template));if(mode==5)gip_fail();U result=gip_run();
 if(mode==0||mode==1){C(!result);C(gip_get(1,0)-gip_get(0,0)>=50000);for(U cpu=1;cpu<4;cpu++)C(gip_get(2,cpu)==gip_get(3,cpu));if(mode==1)C(gip_get(0,0)>7000&&gip_get(2,1)==1);}
 else if(mode==2)C(result==0x060a0002&&now>=20000000&&now<21000000);
 else if(mode==3||mode==5)C(result==0x060a0003&&clocks<20);
 else C(result==0x060a0002&&clocks<20);
 printf("parallel idle native checks passed %u scenario=%s clocks=%u real-phase-fragment real-domain asynchronous-ticks\n",(unsigned)checks,argv[1],(unsigned)clocks);return 0;
}
