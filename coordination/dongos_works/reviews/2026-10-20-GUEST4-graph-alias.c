
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct{const void*p;uint64_t n;} Slice;
typedef struct{uint64_t root;Slice path,bytes;} Source;
typedef struct{uint64_t entry,roots,depth;} Options;
typedef struct{uint64_t v[10];} FrontLimits;
typedef struct{Slice arena,sources,units,tokens,strings,nodes,edges,symbols,refs,types,fields,node_types,
 values,value_states,limbs,layouts,field_offsets,info;uint64_t entry;} Graph;
typedef struct{uint64_t status,exit_code,stage,code,detail,source,offset,used;Graph graph;} FrontResult;
typedef struct{uint64_t functions,instructions,arguments,text,piece,parameters,locations;} EmitLimits;
typedef struct{Slice labels,table,text,data;} Workspace;
typedef struct{uint64_t status,stage,code,unit,node,detail,used,text,written;} ImageResult;
typedef struct{uint64_t virtual_addr,file_offset,file_size,memory_size,map_start,map_size,flags,alignment;} Seg;
typedef struct{uint64_t entry,load_bias,segment_count,page_count,relocation_count,rela_offset;Seg segments[16];} Plan;
_Static_assert(sizeof(Options)==24&&sizeof(FrontLimits)==80&&sizeof(Source)==40&&sizeof(Graph)==296&&sizeof(FrontResult)==360,"frontend ABI");
_Static_assert(sizeof(EmitLimits)==56&&sizeof(Workspace)==64&&sizeof(ImageResult)==72&&sizeof(Plan)==1072,"image ABI");
extern uint64_t ABI dong_frontend_check(const Options*,const Source*,uint64_t,const FrontLimits*,void*,uint64_t,FrontResult*);
extern uint64_t ABI dong_guest_compile_image(const Graph*,const EmitLimits*,uint64_t,void*,uint64_t,void*,uint64_t,
 const void*,uint64_t,const Workspace*,void*,uint64_t,ImageResult*);
extern uint64_t ABI kernel_validate(const void*,uint64_t,void*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static void rd(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static int filled(const void*p,uint64_t n){const uint8_t*b=p;for(uint64_t i=0;i<n;i++)if(b[i]!=0xa5)return 0;return 1;}
static void*page_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,(SIZE_T)(n?n:1),MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n?n:1,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static void page_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;if(p&&!VirtualFree(p,0,MEM_RELEASE))exit(98);
#else
 if(p&&munmap(p,n?n:1))exit(98);
#endif
}
static void*readonly_copy(const void*p,uint64_t n){
 void*q=page_alloc(n);if(!q)exit(95);if(n)memcpy(q,p,n);
#ifdef _WIN32
 DWORD old;if(!VirtualProtect(q,n?n:1,PAGE_READONLY,&old))exit(98);
#else
 if(mprotect(q,n?n:1,PROT_READ))exit(98);
#endif
 return q;
}
static void*alloc_guard(uint64_t n){uint8_t*p=malloc(n+64);if(!p)exit(95);memset(p,0xa5,n+64);return p+32;}
static void free_guard(void*p){free((uint8_t*)p-32);}
static int guard(const void*p,uint64_t n){return filled((const uint8_t*)p-32,32)&&filled((const uint8_t*)p+n,32);}
/* Map a validated static ELF at its planned VAs and call entry as SysV, never as _start. */
static uint64_t call_entry(const uint8_t*image,uint64_t written,const Plan*plan,uint64_t arg,uint64_t*out_value){
 if(!plan->segment_count||!plan->entry)return 1;
 uint64_t lo=UINT64_MAX,hi=0;
 for(uint64_t i=0;i<plan->segment_count;i++){
  const Seg*s=&plan->segments[i];
  if(s->map_start<lo)lo=s->map_start;
  if(s->map_start+s->map_size>hi)hi=s->map_start+s->map_size;
 }
 if(hi<=lo)return 2;
 uint64_t span=hi-lo;
#ifdef _WIN32
 void*base=VirtualAlloc((void*)(uintptr_t)lo,(SIZE_T)span,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*base=mmap((void*)(uintptr_t)lo,span,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);
 if(base==MAP_FAILED)base=NULL;
#endif
 if(!base||(uint64_t)(uintptr_t)base!=lo){if(base){
#ifdef _WIN32
  VirtualFree(base,0,MEM_RELEASE);
#else
  munmap(base,span);
#endif
 }return 3;}
 for(uint64_t i=0;i<plan->segment_count;i++){
  const Seg*s=&plan->segments[i];
  if(s->file_offset+s->file_size>written){
#ifdef _WIN32
   VirtualFree(base,0,MEM_RELEASE);
#else
   munmap(base,span);
#endif
   return 4;}
  memset((void*)(uintptr_t)s->virtual_addr,0,(size_t)s->memory_size);
  if(s->file_size)memcpy((void*)(uintptr_t)s->virtual_addr,image+s->file_offset,(size_t)s->file_size);
 }
 for(uint64_t i=0;i<plan->segment_count;i++){
  const Seg*s=&plan->segments[i];
  uint32_t prot;
#ifdef _WIN32
  DWORD old;
  if(s->flags&1)prot=PAGE_EXECUTE_READ;else prot=PAGE_READWRITE;
  if(!VirtualProtect((void*)(uintptr_t)s->map_start,(SIZE_T)s->map_size,prot,&old)){
   VirtualFree(base,0,MEM_RELEASE);return 5;}
#else
  int p=PROT_READ;if(s->flags&1)p|=PROT_EXEC;if(s->flags&2)p|=PROT_WRITE;
  if(mprotect((void*)(uintptr_t)s->map_start,(size_t)s->map_size,p)){munmap(base,span);return 5;}
#endif
 }
 typedef uint64_t ABI (*Fn)(uint64_t);
 *out_value=((Fn)(uintptr_t)plan->entry)(arg);
#ifdef _WIN32
 VirtualFree(base,0,MEM_RELEASE);
#else
 munmap(base,span);
#endif
 return 0;
}
static unsigned invalid_preflights(void){
 static _Alignas(16) unsigned char arena[65536],saved[65536];
 unsigned count=0;
 for(unsigned scenario=0;scenario<18;scenario++){
  memset(arena,0xa5,sizeof arena);
  Graph*g=(Graph*)(arena+256);
  EmitLimits*limits=(EmitLimits*)(arena+1024);
  Workspace*w=(Workspace*)(arena+2048);
  ImageResult*r=(ImageResult*)(arena+4096);
  uint8_t*storage=arena+8192;uint64_t sn=256;
  uint8_t*text=arena+12288;uint64_t tn=256;
  uint8_t*entry=arena+16384;uint64_t en=6;memcpy(entry,"abcdef",6);
  uint8_t*out=arena+20480;uint64_t on=512;
  uint8_t*labels=arena+28672;uint8_t*table=arena+32768;uint8_t*wt=arena+36864;uint8_t*wd=arena+40960;
  memset(g,0,sizeof(*g));*limits=(EmitLimits){8,256,64,1024,128,32,32};
  *w=(Workspace){{labels,4},{table,16},{wt,256},{wd,256}};
  Graph*gp=g;EmitLimits*lp=limits;Workspace*wp=w;ImageResult*rp=r;
  uint8_t*sp=storage;uint8_t*tp=text;uint8_t*ep=entry;uint8_t*op=out;
  switch(scenario){
   case 0:gp=NULL;break;case 1:lp=NULL;break;case 2:wp=NULL;break;case 3:rp=NULL;break;
   case 4:gp=(Graph*)(arena+257);break;case 5:lp=(EmitLimits*)(arena+1025);break;
   case 6:wp=(Workspace*)(arena+2049);break;case 7:rp=(ImageResult*)(arena+4097);break;
   case 8:gp=(Graph*)(uintptr_t)(UINT64_MAX-7);break;
   case 9:lp=(EmitLimits*)(uintptr_t)(UINT64_MAX-7);break;
   case 10:op=sp;break;case 11:tp=op;break;case 12:rp=(ImageResult*)op;break;
   case 13:w->labels.p=op;break;case 14:w->table.n=UINT64_MAX/8+1;break;
   case 15:w->labels.n=UINT64_MAX/32+1;break;case 16:sp=ep;sn=en?en:1;break;
   default:op=(uint8_t*)(uintptr_t)(UINT64_MAX-7);on=16;break;
  }
  memcpy(saved,arena,sizeof arena);
  uint64_t rc=dong_guest_compile_image(gp,lp,0,sp,sn,tp,tn,ep,en,wp,op,on,rp);
  if(rc!=1||memcmp(saved,arena,sizeof arena)){fprintf(stderr,"preflight %u rc=%llu\n",scenario,(unsigned long long)rc);exit(94);}
  count++;
 }
 return count;
}

int main(void){
 const char*body="module a;var g:u64=1;fn f()u64{return g;}";Source source={0,{"a.dg",4},{body,strlen(body)}};
 Options options={0,1,32};FrontLimits fl={{2048,2048,4096,64,2080,4096,65536,65536,2048,65536}};
 const uint64_t cap=16ull<<20;uint8_t*arena=alloc_guard(cap);FrontResult fr={0};
 uint64_t front=dong_frontend_check(&options,&source,1,&fl,arena,cap,&fr);if(front){fprintf(stderr,"front %llu",(unsigned long long)front);return 90;}
 uint8_t*storage=alloc_guard(4<<20),*text=alloc_guard(1<<20),*out=alloc_guard(1<<20);
 Workspace w={{alloc_guard(128*32),128},{alloc_guard(512*8),512},{alloc_guard(1<<20),1<<20},{alloc_guard(1<<20),1<<20}};
 EmitLimits el={64,4096,2048,1<<20,2048,64,128};
 ImageResult*r=(ImageResult*)(arena+cap-72);uint8_t before[72];memcpy(before,r,72);
 const char*entry="__dong_m61_n66";
 uint64_t rc=dong_guest_compile_image(&fr.graph,&el,0,storage,4<<20,text,1<<20,(const uint8_t*)entry,strlen(entry),&w,out,1<<20,r);
 printf("{\"return\":%llu,\"result_status\":%llu,\"stage\":%llu,\"graph_tail_changed\":%d}\n",(unsigned long long)rc,(unsigned long long)r->status,(unsigned long long)r->stage,memcmp(before,r,72)!=0);return 0;
}
