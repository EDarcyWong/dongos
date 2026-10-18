#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
#define N 16384u
static unsigned checks,flushes,unbinds;static U alias,scan_limit=4*N;static int watching;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"reuse cursor native failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
extern ABI U cursor_setup(U),cursor_kernel_setup(void),cursor_fresh(void),cursor_get(U,U),cursor_map(U,U,U),cursor_abort(void),cursor_unshare(U,U),cursor_destroy(U);
extern ABI void cursor_change(U,U,U),cursor_recycle_wave(void),cursor_stage(const uint16_t*,U),cursor_resources_setup(U);
ABI void __dong_panic(void){CK(0);abort();}
ABI void cursor_scan_event(U count){CK(count<=scan_limit);}
ABI U user_current_root(void){return 0;}
ABI U user_pcid_unbind(U id,U root){CK(id==0&&root==0x100000&&flushes);if(watching)CK(!cursor_get(6,0));unbinds++;return 1;}
ABI void user_pcid_flush_all(void){flushes++;}
ABI void user_pcid_invalidate_root(U root){CK(root==0x100000||root==0x120000);}
ABI void runtime_invalidate(U address){CK(address>=alias&&address<alias+N*4096ull);}
ABI void runtime_copy_bytes(void*d,const void*s,U bytes){memcpy(d,s,(size_t)bytes);}
static void zero(U index){unsigned char*p=(void*)(uintptr_t)(alias+index*4096);for(unsigned i=0;i<4096;i++)CK(!p[i]);}
static void marker(U index){unsigned char*p=(void*)(uintptr_t)(alias+index*4096);for(unsigned i=0;i<4096;i++)CK(p[i]==0xa5);}
static void grow(unsigned count){for(unsigned i=0;i<count;i++){CK(cursor_fresh()==i);CK(cursor_get(2,0)==i+1);}CK(cursor_get(1,0)==count-1);}
int main(int argc,char**argv){CK(argc==2);
#ifdef _WIN32
 void*ram=_aligned_malloc(N*4096ull,4096);void*scratch=_aligned_malloc(12*4096,4096);
#else
 void*ram=aligned_alloc(4096,N*4096ull);void*scratch=aligned_alloc(4096,12*4096);
#endif
 CK(ram&&scratch);alias=(U)(uintptr_t)ram;memset(ram,0xa5,N*4096ull);memset(scratch,0,12*4096);cursor_resources_setup((U)(uintptr_t)scratch);CK(!cursor_setup(alias)&&!cursor_kernel_setup());const char*s=argv[1];
 if(!strcmp(s,"linear-new")){grow(N);CK(cursor_fresh()==0x04060002);CK(cursor_get(0,0)==N&&cursor_get(1,0)==N);zero(0);zero(N-1);}
 else if(!strcmp(s,"linear-reuse")){grow(N);for(unsigned wave=0;wave<3;wave++){cursor_recycle_wave();memset(ram,0xa5,N*4096ull);for(unsigned i=0;i<N;i++){CK(cursor_fresh()==i);CK(cursor_get(0,0)==i+1);}CK(cursor_get(1,0)==N&&cursor_get(2,0)==N);zero(0);zero(N-1);}}
 else {grow(64);cursor_change(0,0,64);memset(ram,0xa5,64*4096);
  if(!strcmp(s,"stage")){uint16_t indices[]={17,3,2,7};cursor_change(1,2,2);CK(!cursor_map(1,7,0x45000000));cursor_stage(indices,4);watching=1;CK(!cursor_abort());watching=0;CK(cursor_get(0,0)==3&&cursor_get(3,3)==1&&cursor_get(3,17)==1&&cursor_get(3,2)==2&&!cursor_get(3,7));marker(2);marker(7);zero(3);CK(cursor_fresh()==3&&cursor_fresh()==17);}
  else if(!strcmp(s,"unshare")){CK(!cursor_map(0,5,0x44000000));CK(!cursor_unshare(0,0x44000000));CK(cursor_get(0,0)==5&&cursor_get(3,5)==1);zero(5);CK(cursor_fresh()==5&&cursor_get(0,0)==6);}
  else if(!strcmp(s,"destroy")){CK(!cursor_map(0,9,0x44000000)&&!cursor_map(0,20,0x44001000)&&!cursor_map(1,20,0x45000000)&&!cursor_map(0,2,0x44002000));cursor_change(1,2,2);watching=1;CK(!cursor_destroy(0));watching=0;CK(unbinds==1&&cursor_get(0,0)==9&&cursor_get(3,9)==1&&!cursor_get(3,20)&&cursor_get(3,2)==2);marker(2);marker(20);CK(cursor_fresh()==9);zero(9);}
  else if(!strcmp(s,"held")){cursor_change(1,2,2);cursor_change(0,0,0);CK(cursor_fresh()==64&&cursor_get(3,2)==2);marker(2);CK(!cursor_map(0,3,0x44000000));cursor_change(2,0,1);U before=cursor_get(0,0);CK(cursor_destroy(0)==0x04060001&&cursor_get(0,0)==before&&!cursor_get(3,3));CK(cursor_unshare(0,0x44000000)==0x04060001&&cursor_get(0,0)==before);marker(3);cursor_change(3,0,1);CK(cursor_fresh()==0x04060001);cursor_change(3,0,0);cursor_change(0,0,100);CK(cursor_fresh()==0x04060001);}
  else {CK(0);}
 }
 printf("reuse cursor native checks passed %u; scenario=%s; frames=%u; scans=%u; cursor=%u\n",checks,s,(unsigned)cursor_get(2,0),(unsigned)cursor_get(1,0),(unsigned)cursor_get(0,0));return 0;}
