#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef U (ABI *Config)(U,U,uint32_t*);
typedef U (ABI *Read)(U,U,U,U,U*);
typedef U (ABI *Write)(U,U,U,U,U);
typedef U (ABI *Fence)(U,U);
typedef struct{Config config;Read read;Write write;Fence fence;}Ops;
typedef struct{U physical,length,handle;}Bar;
extern ABI U vq_reset(const Ops*,U,U,const Bar*);
extern ABI void vq_wrapper_setup(const Ops*,const Bar*,U,U,U);
extern ABI U vq_wrapper(U*),vq_wrapper_state(void);
static U wrapper_mode;
static uint8_t cfg[256];static U checks,scenario,writes,reads,fences,identity_reads;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"VirtIO quiesce check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static void w32(unsigned at,uint32_t value){memcpy(cfg+at,&value,4);}
static void cap(unsigned at,unsigned next,unsigned kind,unsigned offset,unsigned length,unsigned size){w32(at,9|(next<<8)|(size<<16)|(kind<<24));w32(at+4,0);w32(at+8,offset);w32(at+12,length);}
static ABI U config(U c,U address,uint32_t*out){
 CK(c==(wrapper_mode?0xe0008000:99)&&address>=0xe0008000&&address<=0xe00080fc&&!(address&3));unsigned at=(unsigned)(address-0xe0008000);
 if(scenario==7){return 1;}memcpy(out,cfg+at,4);
 if(at==0){identity_reads++;if(scenario==5&&identity_reads>1)*out=0x10431af4;}
 if(at==4&&scenario==16&&reads)*out|=4;
 if(at==4&&scenario==19&&reads)*out&=~2u;
 return 0;
}
static ABI U read_status(U c,U h,U at,U width,U*out){
 CK(c==(wrapper_mode?0xe0008000:99)&&h==7&&at==20&&width==1&&writes==1&&fences==1);reads++;
 if(wrapper_mode){U untouched=99;CK(vq_wrapper_state()==1&&vq_wrapper(&untouched)==0x050a0003&&untouched==99);}
 if(scenario==8)return 1;
 *out=scenario==6?15:scenario==15?256:reads<3?15:0;return 0;
}
static ABI U write_status(U c,U h,U at,U width,U value){
 CK(c==(wrapper_mode?0xe0008000:99)&&h==7&&at==20&&width==1&&value==0&&writes==0&&fences==0);writes++;
 return scenario==9?1:0;
}
static ABI U fence(U c,U kind){CK(c==(wrapper_mode?0xe0008000:99)&&kind==3&&writes==1);fences++;return (scenario==10&&fences==1)||(scenario==11&&fences==2);}
ABI void __dong_panic(void){fprintf(stderr,"unexpected panic\n");exit(2);}
int main(void){Ops ops={config,read_status,write_status,fence};
 for(scenario=0;scenario<=19;scenario++){
  memset(cfg,0,sizeof cfg);writes=reads=fences=identity_reads=0;
  w32(0,0x10421af4);w32(4,0x100402);w32(8,0x01000000);w32(12,0);w32(16,0xfc000000);w32(52,0x40);
  cap(0x40,0x50,1,0,56,16);cap(0x50,0x64,2,0x100,0x100,20);w32(0x60,4);
  cap(0x64,0x74,3,0x200,1,16);cap(0x74,0,4,0x300,8,16);
  Bar bars[6]={{0xfc000000,4096,7},{0},{0},{0},{0},{0}};
  if(scenario==1)w32(0,0x10431af4);
  if(scenario==2)w32(4,0x100406);
  if(scenario==3)w32(4,0x100002);
  if(scenario==4)w32(52,0);
  if(scenario==12)w32(16,0xfd000000);
  if(scenario==13)cap(0x74,0x40,4,0x300,8,16);
  if(scenario==14)bars[0].length=0;
  if(scenario==17)w32(12,1<<16);
  if(scenario==18)w32(4,0x100400);
  U result=vq_reset(&ops,99,0xe0008000,bars);
  if(!scenario){CK(!result&&writes==1&&reads==3&&fences==2);}
  else{CK(result!=0);if(scenario==6)CK(reads==1024&&writes==1&&fences==1);}
  if((scenario<=4&&scenario)||scenario==18)CK(!writes&&!reads&&!fences);
  wrapper_mode=1;writes=reads=fences=identity_reads=0;
  vq_wrapper_setup(&ops,bars,1,0xe0008000,1);U out=99;
  result=vq_wrapper(&out);U oldwrites=writes,oldreads=reads,oldfences=fences;
  if(!scenario){CK(!result&&out==1&&vq_wrapper_state()==2);out=99;CK(!vq_wrapper(&out)&&out==1);}
  else{CK(result&&out==99&&vq_wrapper_state()==1);CK(vq_wrapper(&out)==0x050a0003&&out==99);}
  CK(writes==oldwrites&&reads==oldreads&&fences==oldfences);
  for(U guard=0;guard<3;guard++){
   vq_wrapper_setup(&ops,bars,guard==0?2:1,guard==1?0:0xe0008000,guard==2?0:1);
   out=99;result=vq_wrapper(&out);
   if(guard==2)CK(result==0x050a0002&&out==99);else CK(!result&&out==0);
   CK(vq_wrapper_state()==0&&writes==oldwrites&&reads==oldreads&&fences==oldfences);
  }
  wrapper_mode=0;
 }
 printf("VirtIO quiesce native checks passed %llu\n",(unsigned long long)checks);return 0;
}
