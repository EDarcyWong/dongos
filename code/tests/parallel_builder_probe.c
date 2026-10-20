#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;typedef struct{U physical,virtual,pages;} Block;
extern U ABI pb_begin(U),pb_get(U,U),pb_leaf(U),pb_space_init(void),pb_more(U*);
static Block blocks[32];static unsigned count,checks,barriers,kicks,fail_at;static U tops[16];
#define C(x) do{checks++;if(!(x)){fprintf(stderr,"parallel builder oracle line %u: %s\n",__LINE__,#x);exit(1);}}while(0)
static void*alloc(size_t n){
#ifdef _WIN32
 void*p=_aligned_malloc(n,4096);
#else
 void*p=aligned_alloc(4096,(n+4095)&~(size_t)4095);
#endif
 C(p!=NULL);memset(p,0,n);return p;
}
void ABI __dong_panic(void){C(0);}
/* Builder never dispatches or retires a live thread. */
void ABI parallel_live_retire(U cpu,U slot,U frame){(void)cpu;(void)slot;(void)frame;C(0);}
U ABI pb_allocate(U pages,Block*out){count++;if(count==fail_at)return 1;C(count<32&&pages&&pages<64);
 blocks[count-1]=(Block){0x400000+count*0x40000,(U)(uintptr_t)alloc((size_t)pages*4096),pages};*out=blocks[count-1];return 0;}
void ABI pb_barrier(void){barriers++;C(barriers<=18);}
U ABI parallel_arch_if0(void){return 1;}
void ABI parallel_arch_lock(U*p){C(!*p);*p=1;}
void ABI parallel_arch_unlock(U*p){C(*p==1);*p=0;}
U ABI parallel_arch_on_scheduler(U a,U b){(void)a;(void)b;C(0);return 0;}
U ABI parallel_arch_root(void){return 0x100000;}
void ABI parallel_arch_save(U p){(void)p;C(0);}
void ABI parallel_arch_restore(U p){(void)p;C(0);}
void ABI parallel_arch_copy(U d,U s,U n){C(n==1024);memcpy((void*)(uintptr_t)d,(void*)(uintptr_t)s,(size_t)n);}
void ABI parallel_arch_seed(U template,U backup){C(template&&backup==template+1024);memset((void*)(uintptr_t)template,0x5a,1024);memset((void*)(uintptr_t)backup,0xa5,1024);}
U ABI parallel_arch_entry(void){return 0x80000010;}
U ABI parallel_arch_text_begin(void){return 0x80000000;}
U ABI parallel_arch_text_end(void){return 0x80010000;}
U ABI parallel_probe_entry(void){return 0x80000200;}
void ABI parallel_arch_register(U cpu,U top){C(cpu>=1&&cpu<=3&&top);tops[cpu]=top;}
U ABI parallel_arch_install(U a,U b,U c){(void)a;(void)b;(void)c;C(0);return 1;}
U ABI parallel_arch_timer(U a,U b,U c){(void)a;(void)b;(void)c;C(0);return 1;}
U ABI parallel_arch_clock(void){return 1000;}
void ABI parallel_arch_eoi(U a){(void)a;C(0);}
U ABI parallel_arch_kick(U lapic,U apic){C(lapic==0xfec00000&&apic>=17&&apic<=19&&pb_get(3,0)==1);kicks++;return 0;}
int main(int argc,char**argv){C(argc==2);C(!pb_space_init());void*idle=alloc(4*16384);if(!strcmp(argv[1],"early"))fail_at=1;if(!strcmp(argv[1],"late"))fail_at=8;
 U result=pb_begin((U)(uintptr_t)idle);
 if(fail_at){C(result&&pb_get(2,0)&&!pb_get(3,0)&&!kicks);if(fail_at>1)C(pb_get(0,0));}
 else{C(!result&&!pb_get(2,0)&&pb_get(1,0)==6&&pb_get(3,0)==1&&pb_get(4,0)==6&&pb_get(5,0)&&kicks==3&&barriers==18&&count==11);
  for(unsigned i=0;i<count;i++){Block*b=&blocks[i];for(U p=0;p<b->pages;p++){U leaf=pb_leaf(b->virtual+p*4096);
   if(b->pages==6&&(p==0||p==5))C(!leaf);else C(leaf==(b->physical+p*4096+1));}}
  for(unsigned cpu=1;cpu<=3;cpu++){C(tops[cpu]==pb_get(6,cpu));}
  for(unsigned i=0;i<6;i++){C(pb_get(7,i)>255);}
  fail_at=count+1;U out=0xa5;C(pb_more(&out)!=0&&out==0xa5&&pb_get(2,0)&&pb_get(0,0));C(pb_more(&out)!=0&&out==0xa5&&count==fail_at);
 }printf("parallel builder checks passed %u; scenario=%s real-paging double-guards acknowledged-retire arena-only failed-allocation-held\n",checks,argv[1]);return 0;}
