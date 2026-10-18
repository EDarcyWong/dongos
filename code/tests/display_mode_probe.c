#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define EFI __attribute__((ms_abi))
typedef struct {uint32_t version,width,height,format,masks[4],stride;} Info;
typedef struct {uint32_t max,current;uint64_t info,size,base,bytes;} Mode;
typedef struct {void *query,*set,*blt;Mode *mode;} Gop;
extern uint64_t EFI desktop_graphics_mode(Gop *,void *);
static Info info;static Mode mode;static Gop gop;static uint64_t bs[64];
static unsigned variant,queries,frees,sets,held,errors;
static uint64_t EFI query(Gop *p,uint32_t index,uint64_t *size,Info **out){
 queries++;if(p!=&gop||held){errors++;return 1;}
 if(variant==3)return 1;
 held=1;*out=&info;*size=sizeof info;info=(Info){0,1280,800,1,{0},1280};
 if(index==2){info.width=1920;info.height=1080;info.stride=1920;}
 if(variant==4)*size=20;if(variant==5)info.format=2;
 if(variant==6)info.stride=1919;if(variant==7)info.stride=2049;
 if(variant==8)info.version=1;if(variant==9)info.format=0;
 return 0;
}
static uint64_t EFI free_pool(void *p){frees++;if(p!=&info||!held)errors++;held=0;return variant==10?1:0;}
static uint64_t EFI set(Gop *p,uint32_t index){sets++;if(p!=&gop||index!=2||held)errors++;mode.current=index;return variant==11?1:0;}
int main(void){unsigned cases=0;
 for(variant=0;variant<12;variant++){
  memset(bs,0,sizeof bs);bs[9]=(uintptr_t)free_pool;mode=(Mode){3,0,0,0,0,0};gop=(Gop){query,set,0,&mode};
  queries=frees=sets=held=errors=0;
  if(variant==1)mode.max=257;if(variant==2)mode.max=0;
  uint64_t result=desktop_graphics_mode(&gop,bs);int success=variant==0||variant==9;
  if((result==0)!=success||held||errors||(success&&(queries!=3||frees!=3||sets!=1))||((variant==1||variant==2)&&(queries||frees||sets))||(!success&&variant!=11&&sets)){
   fprintf(stderr,"GOP oracle failed variant=%u result=%u query=%u free=%u set=%u held=%u errors=%u\n",variant,(unsigned)result,queries,frees,sets,held,errors);return 1;
  }cases++;
 }
 puts("GOP native oracle passed: 12 actual mode/cleanup cases");return cases==12?0:1;
}
