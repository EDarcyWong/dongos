#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{U physical,virtual,pages;} Block;
#ifndef DONGOS_FRAME_METADATA_PAGES
#define DONGOS_FRAME_METADATA_PAGES 109
#endif
_Static_assert(DONGOS_FRAME_METADATA_PAGES==109||DONGOS_FRAME_METADATA_PAGES==128,"unsupported metadata profile");
static unsigned checks,allocations,comp_allocations,ordinary_allocations,binds,unbinds,flushes;
static U alias,previous_generation;static int fail_comp;static unsigned char*meta,*comp,*ordinary;static U prefixes[3][512];static unsigned counts[3];
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"compositor pool native failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
extern ABI U cp_setup(U),cp_enable(void),cp_start(const void*,U,U,U,U),cp_prepare(U),cp_get(U,U),cp_map(U,U,U,U),cp_destroy(U),cp_abort(void),cp_clean(void),cp_share_high(U),cp_kernel_setup(void);
extern ABI void cp_pin(U);
ABI void __dong_panic(void){CK(0);abort();}
ABI U cpp_allocate(U pages,U alignment,Block*out){CK(alignment==1&&out);allocations++;if(allocations==1){CK(pages==DONGOS_FRAME_METADATA_PAGES);*out=(Block){0x30000000,(U)(uintptr_t)(meta+4096),pages};return 0;}if(pages==128){comp_allocations++;if(fail_comp)return 1;CK(comp_allocations==1||fail_comp==2);*out=(Block){0x31000000,(U)(uintptr_t)(comp+4096),pages};return 0;}if(pages==32){ordinary_allocations++;CK(ordinary_allocations==1);*out=(Block){0x32000000,(U)(uintptr_t)(ordinary+4096),pages};return 0;}CK(0);return 1;}
ABI U user_current_root(void){return 0;}
ABI U user_pcid_bind(U id,U root,U generation){CK(id==3&&root==0x31000000&&generation==previous_generation+1);previous_generation=generation;binds++;return 1;}
ABI U user_pcid_unbind(U id,U root){CK((id==3&&root==0x31000000)||(id==0&&root==0x100000));CK(!cp_get(6,id)&&flushes);unbinds++;return 1;}
ABI void user_pcid_flush_all(void){flushes++;}
ABI void user_pcid_invalidate_root(U root){CK(root==0x31000000||root==0x100000||(root==0&&!cp_get(6,3)));}
ABI void runtime_invalidate(U address){CK((address>=alias&&address<alias+512*4096)||(address>=0x10000&&address<0x8000000000));}
ABI void runtime_copy_bytes(void*d,const void*s,U bytes){memcpy(d,s,(size_t)bytes);}
static void*aligned(U bytes){
#ifdef _WIN32
 return _aligned_malloc((size_t)bytes,4096);
#else
 return aligned_alloc(4096,(size_t)bytes);
#endif
}
static void guards(unsigned char*p,unsigned pages){for(unsigned i=0;i<4096;i++){CK(p[i]==0xa5);CK(p[(pages+1)*4096+i]==0xa5);}}
static unsigned char image[1024];static void p16(unsigned at,unsigned value){uint16_t v=(uint16_t)value;memcpy(image+at,&v,2);}static void p64(unsigned at,U value){memcpy(image+at,&value,8);}static void p32(unsigned at,unsigned value){memcpy(image+at,&value,4);}
static void elf(void){memset(image,0,sizeof image);memcpy(image,"\177ELF",4);image[4]=2;image[5]=1;image[6]=1;p16(16,3);p16(18,62);p32(20,1);p64(24,0x103c0);p64(32,64);p16(52,64);p16(54,56);p16(56,1);p32(64,1);p32(68,5);p64(80,0x10000);p64(96,sizeof image);p64(104,0x80000);p64(112,4096);}
static void add(U address){U keys[]={address>>39,address>>30,address>>21};for(unsigned level=0;level<3;level++){unsigned i=0;while(i<counts[level]&&prefixes[level][i]!=keys[level])i++;if(i==counts[level]){CK(i<512);prefixes[level][counts[level]++]=keys[level];}}}
static unsigned expected(void){return 1+counts[0]+counts[1]+counts[2];}
static void map(U address,U pages,U flags){U error=cp_map(address,pages,0x40000000+(address&0x1fffffff),flags);if(error)fprintf(stderr,"map failed va=%x pages=%u error=%x used=%u\n",(unsigned)address,(unsigned)pages,(unsigned)error,(unsigned)cp_get(1,3));CK(!error);for(U i=0;i<pages;i++)add(address+i*4096);CK(cp_get(1,3)==expected());}
static void seed(U sample,U stack){memset(counts,0,sizeof counts);U bias=0x10000000+((sample&4095)<<16),top=0x7ffff00000-((stack&0x3ffff)<<12);for(U i=0;i<128;i++)add(bias+0x10000+i*4096);for(U i=1;i<=4;i++)add(top-i*4096);CK(cp_get(1,3)==expected());}
static void fixed(U stride){U pages=(stride*1080*4+4095)/4096;map(0x70000000,2,3);map(0x52000000,16,3);map(0x54000000,1,3);map(0x60000000,pages,11);map(0x58000000,pages,3);map(0x55000000,pages,3);map(0x56000000,2048,3);map(0x72000000,2048,2);}
static void apertures(int maximal){U charged=0;unsigned count=maximal?32:4;for(unsigned i=0;i<count;i++){U pages=maximal?(i<3?513:1):300;charged+=pages*4096;CK(charged<=8388608);map(0x78000000+i*0x400000ull,pages,3);}CK(cp_get(1,3)<=72);}
static unsigned leaf_table(U address){U*pool=(void*)(uintptr_t)cp_get(2,3);U index=0;unsigned shifts[]={39,30,21};for(unsigned level=0;level<3;level++){U entry=pool[index*512+((address>>shifts[level])&511)];CK((entry&5)==5);U physical=entry&0x000ffffffffff000ull;CK(physical>=0x31000000&&physical<0x31080000);index=(physical-0x31000000)/4096;}return (unsigned)index;}
static U fill(void){U last=0;for(U i=0;cp_get(1,3)+2<=128;i++){U v=0x100000000+i*0x40000000;map(v,1,3);last=v;}if(cp_get(1,3)==127){map(0x78e00000,1,3);last=0x78e00000;}CK(cp_get(1,3)==128&&leaf_table(last)==127);CK(cp_map(0x6000000000,1,0x50000000,3)==0x02000007&&cp_get(1,3)==128);return last;}
int main(int argc,char**argv){CK(argc==2);meta=aligned((DONGOS_FRAME_METADATA_PAGES+2)*4096);comp=aligned(130*4096);ordinary=aligned(34*4096);void*ram=aligned(512*4096);CK(meta&&comp&&ordinary&&ram);memset(meta,0xa5,(DONGOS_FRAME_METADATA_PAGES+2)*4096);memset(meta+4096,0,DONGOS_FRAME_METADATA_PAGES*4096);memset(comp,0xa5,130*4096);memset(comp+4096,0,128*4096);memset(ordinary,0xa5,34*4096);memset(ordinary+4096,0,32*4096);alias=(U)(uintptr_t)ram;memset(ram,0xa5,512*4096);CK(!cp_setup(alias)&&!cp_kernel_setup());elf();const char*s=argv[1];
 if(!strcmp(s,"legacy")){CK(cp_get(9,0)==3*32*4096);for(U i=0;i<16;i++)CK(cp_get(0,i)==32);for(U i=0;i<3;i++)CK(!cp_prepare(i)&&!allocations&&!cp_get(2,i));}
 else {CK(!cp_enable());for(U i=0;i<16;i++)CK(cp_get(0,i)==(i==3?128:32));
  if(strcmp(s,"allocation-failure")){CK(!cp_prepare(3)&&cp_get(12,3)==cp_get(2,3));}
  if(!strcmp(s,"budget")){for(U sample=0;sample<32;sample++){U stack=sample&1?0x3fefe:0x3ffff;CK(!cp_start(image,sizeof image,sample,stack,1));seed(sample,stack);fixed(sample&1?2048:1920);apertures(1);CK(cp_get(1,3)>=65&&cp_get(1,3)<=72);CK(!cp_destroy(3)&&cp_clean()==1&&comp_allocations==1);}CK(binds==32&&unbinds==32);}
  else if(!strcmp(s,"allocation-failure")){fail_comp=1;CK(cp_start(image,sizeof image,0,0,1)==0x09000001&&!cp_get(2,3)&&!cp_get(6,3));CK(cp_get(11,0)==16&&!binds);}
  else {CK(!cp_start(image,sizeof image,30,0x3fefe,!strcmp(s,"abort")?0:1));seed(30,0x3fefe);fixed(2048);apertures(1);U high=fill();
   if(!strcmp(s,"abort")){CK(!cp_abort()&&cp_clean()==1&&!cp_get(6,3));CK(!cp_start(image,sizeof image,0,0,1)&&cp_get(5,3)==2&&comp_allocations==1);}
   else if(!strcmp(s,"lifecycle")){U index=cp_share_high(high);CK(index<512&&leaf_table(high)==127);memset((void*)(uintptr_t)(alias+index*4096),0xa5,4096);CK(!cp_destroy(0)&&cp_get(7,index)==0);for(unsigned i=0;i<4096;i++)CK(*(unsigned char*)(uintptr_t)(alias+index*4096+i)==0xa5);cp_pin(1);CK(cp_destroy(3)==0x04060001&&cp_get(1,3)==128);cp_pin(0);CK(!cp_destroy(3)&&cp_get(7,index)==1&&cp_clean()==1);CK(!cp_start(image,sizeof image,0,0,1)&&cp_get(5,3)==2&&comp_allocations==1);CK(!cp_prepare(4)&&cp_get(0,4)==32&&cp_get(3,4)==0x32000000&&ordinary_allocations==1);}
   else {CK(0);}
  }
 }
 guards(meta,DONGOS_FRAME_METADATA_PAGES);guards(comp,128);guards(ordinary,32);printf("compositor pool native checks passed %u; scenario=%s; held128_allocations=%u; binds=%u; unbinds=%u; metadata_pages=%u\n",checks,s,comp_allocations,binds,unbinds,DONGOS_FRAME_METADATA_PAGES);return 0;}
