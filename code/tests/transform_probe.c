/* Independent rational-nearest and integer source-over oracle. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct {uint32_t *pixels;size_t length,width,height,stride;} Surface;
typedef struct {int64_t left,top,right,bottom;} Rect;
extern ABI uint64_t transform_scaled(Surface *,const Surface *,const Rect *,const Rect *,uint64_t);
extern ABI void transform_sizes(uint64_t *);
extern ABI uint64_t transform_register_probe(const uint64_t *);
uint64_t transform_negative_hits;
/* The generic native suite forces the complete SSE2 fallback. AVX2 tests
   independently gate CPUID/OSXSAVE/XCR0 before setting this runtime flag. */
uint64_t svc_avx2;
uint64_t svc_gather_fast;
static uint64_t checks,cases,rejections,clip_partitions;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"TRANSFORM_MODEL_ASSERT line %d: %s\n",__LINE__,#x);if(transform_negative_hits)fprintf(stderr,"TRANSFORM_NEGATIVE_HIT %llu\n",(unsigned long long)transform_negative_hits);exit(1);}}while(0)
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected transform panic %llu\n",(unsigned long long)code);exit(99);}
static uint32_t random_state=0x12345678;
static uint32_t random32(void){random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static uint32_t premultiplied(void){uint32_t p=random32(),a=p>>24;return a<<24|((p&255)*a/255)|((((p>>8)&255)*a/255)<<8)|((((p>>16)&255)*a/255)<<16);}
static uint32_t over(uint32_t d,uint32_t s,unsigned opacity){
 uint32_t source=0;for(unsigned shift=0;shift<32;shift+=8)source|=(((((s>>shift)&255)*opacity)+128)>>8)<<shift;
 uint32_t result=0,inv=255-(source>>24);for(unsigned shift=0;shift<32;shift+=8){unsigned c=((source>>shift)&255)+((((d>>shift)&255)*inv+127)/255);if(c>255)c=255;result|=c<<shift;}return result;
}
static void model(Surface *dst,const Surface *src,const Rect *r,const Rect *clip,unsigned opacity){
 for(size_t y=0;y<dst->height;y++)for(size_t x=0;x<dst->width;x++){
  if((int64_t)x<clip->left||(int64_t)x>=clip->right||(int64_t)y<clip->top||(int64_t)y>=clip->bottom||(int64_t)x<r->left||(int64_t)x>=r->right||(int64_t)y<r->top||(int64_t)y>=r->bottom)continue;
  size_t sx=(size_t)(((int64_t)x-r->left)*(int64_t)src->width/(r->right-r->left));
  size_t sy=(size_t)(((int64_t)y-r->top)*(int64_t)src->height/(r->bottom-r->top));
  dst->pixels[y*dst->stride+x]=over(dst->pixels[y*dst->stride+x],src->pixels[sy*src->stride+sx],opacity);
 }
}
enum{SOURCE=1033,DESTINATION=1027};
static uint32_t source[SOURCE],actual[DESTINATION],expected[DESTINATION],split[DESTINATION],saved_source[SOURCE];
static void compare(size_t sw,size_t sh,size_t dw,size_t dh,int64_t x,int64_t y,Rect clip,unsigned opacity){
 for(size_t i=0;i<SOURCE;i++)source[i]=premultiplied();
 /* Exercise exact zero, partial and opaque pixels independently of random data. */
 source[7]=0;source[8]=0xff123456;source[9]=0x80201040;memcpy(saved_source,source,sizeof source);
 for(size_t i=0;i<DESTINATION;i++)actual[i]=premultiplied();memcpy(expected,actual,sizeof actual);memcpy(split,actual,sizeof actual);
 Surface src={source+7,SOURCE-14,sw,sh,sw+3};Surface dst={actual+9,DESTINATION-18,31,23,37};Surface ref=dst;ref.pixels=expected+9;Surface cut=dst;cut.pixels=split+9;
 Rect target={x,y,x+(int64_t)dw,y+(int64_t)dh};model(&ref,&src,&target,&clip,opacity);
 CHECK(transform_scaled(&dst,&src,&target,&clip,opacity)==0);CHECK(memcmp(actual,expected,sizeof actual)==0);CHECK(memcmp(source,saved_source,sizeof source)==0);
 /* Disjoint clip tiles must sample the same rational positions as one clip. */
 Rect a=clip,b=clip;int64_t mid=clip.left+(clip.right-clip.left)/2;a.right=mid;b.left=mid;
 CHECK(transform_scaled(&cut,&src,&target,&a,opacity)==0);CHECK(transform_scaled(&cut,&src,&target,&b,opacity)==0);CHECK(memcmp(actual,split,sizeof actual)==0);clip_partitions++;cases++;
}
static void bad(Surface *dst,const Surface *src,const Rect *r,const Rect *clip,uint64_t opacity){
 memcpy(expected,actual,sizeof actual);memcpy(saved_source,source,sizeof source);CHECK(transform_scaled(dst,src,r,clip,opacity)!=0);CHECK(memcmp(actual,expected,sizeof actual)==0);CHECK(memcmp(source,saved_source,sizeof source)==0);rejections++;
}
static void invalid(void){
 Surface src={source+7,SOURCE-14,17,9,20},dst={actual+9,DESTINATION-18,31,23,37};Rect r={-3,-5,13,17},clip={0,0,31,23};
 bad(NULL,&src,&r,&clip,256);bad(&dst,NULL,&r,&clip,256);bad(&dst,&src,NULL,&clip,256);bad(&dst,&src,&r,NULL,256);bad(&dst,&src,&r,&clip,257);
 Surface q=src;q.pixels=NULL;bad(&dst,&q,&r,&clip,0);q=src;q.pixels=(uint32_t *)((uintptr_t)source+1);bad(&dst,&q,&r,&clip,256);
 q=src;q.length=1;bad(&dst,&q,&r,&clip,256);q=src;q.stride=16;bad(&dst,&q,&r,&clip,256);q=src;q.width=0;bad(&dst,&q,&r,&clip,256);
 q=src;q.pixels=dst.pixels;bad(&dst,&q,&r,&clip,0);q=src;q.pixels=(uint32_t *)(UINTPTR_MAX-3);q.length=16;bad(&dst,&q,&r,&clip,0);
 Rect t=r;t.left=INT64_MIN;bad(&dst,&src,&t,&clip,256);t=r;t.right=INT64_MAX;bad(&dst,&src,&t,&clip,256);t=r;t.bottom=t.top;bad(&dst,&src,&t,&clip,0);
 t=r;t.right=t.left+8193;bad(&dst,&src,&t,&clip,256);t=clip;t.left=t.right+1;bad(&dst,&src,&r,&t,256);
 q=src;q.width=1024;q.height=1024;q.stride=1024;q.length=1024*1024;bad(&dst,&q,&r,&clip,256);
 q=dst;q.length=SIZE_MAX;bad(&q,&src,&r,&clip,256);q=dst;q.stride=SIZE_MAX;bad(&q,&src,&r,&clip,256);
}
static void maximum_sources(void){
 size_t count=524288;uint32_t *large=malloc((count+16)*sizeof *large),*old=malloc((count+16)*sizeof *old);CHECK(large&&old);
 for(unsigned axis=0;axis<2;axis++)for(unsigned opacity=0;opacity<=256;opacity+=128){
  for(size_t i=0;i<count+16;i++)large[i]=premultiplied();memcpy(old,large,(count+16)*4);
  for(size_t i=0;i<DESTINATION;i++)actual[i]=premultiplied();memcpy(expected,actual,sizeof actual);
  Surface src={large+8,count,axis?64:8192,axis?8192:64,axis?64:8192};Surface dst={actual+9,DESTINATION-18,31,23,37},ref=dst;ref.pixels=expected+9;
  Rect target={-8161,-8169,31,23},clip={0,0,31,23};model(&ref,&src,&target,&clip,opacity);
  CHECK(transform_scaled(&dst,&src,&target,&clip,opacity)==0);CHECK(memcmp(actual,expected,sizeof actual)==0);CHECK(memcmp(large,old,(count+16)*4)==0);cases++;
 }
 free(old);free(large);
}
static void guard_pages(void){
 size_t page=4096;uint8_t *a,*b;
#ifdef _WIN32
 a=VirtualAlloc(NULL,page*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);b=VirtualAlloc(NULL,page*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);CHECK(a&&b);DWORD old;CHECK(VirtualProtect(a+page,page,PAGE_NOACCESS,&old));CHECK(VirtualProtect(b+page,page,PAGE_NOACCESS,&old));
#else
 page=(size_t)sysconf(_SC_PAGESIZE);a=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);b=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);CHECK(a!=MAP_FAILED&&b!=MAP_FAILED);CHECK(mprotect(a+page,page,PROT_NONE)==0);CHECK(mprotect(b+page,page,PROT_NONE)==0);
#endif
 for(unsigned sw=1;sw<=7;sw++)for(unsigned dw=1;dw<=9;dw++)for(unsigned opacity=1;opacity<=256;opacity+=51){
  uint32_t *s=(uint32_t *)(a+page)-sw,*d=(uint32_t *)(b+page)-dw;for(unsigned i=0;i<sw;i++)s[i]=(i%3==0)?0:((i%3==1)?0xff123456:0x80201040);for(unsigned i=0;i<dw;i++)d[i]=0xff987654;
  Surface src={s,sw,sw,1,sw},dst={d,dw,dw,1,dw};Rect r={0,0,dw,1};uint32_t want[9];for(unsigned i=0;i<dw;i++)want[i]=over(d[i],s[i*sw/dw],opacity);
  CHECK(transform_scaled(&dst,&src,&r,&r,opacity)==0);CHECK(memcmp(want,d,dw*4)==0);
 }
 /* One literal Command also checks native SysV callee-saved registers. */
 uint32_t *s=(uint32_t *)(a+page)-1,*d=(uint32_t *)(b+page)-1;*s=0xff123456;*d=0;uint16_t offsets[1]={0};uint64_t command[13]={(uintptr_t)s,(uintptr_t)d,4,4,1,1,(uintptr_t)offsets,0,0,1,0,1,256};CHECK(transform_register_probe(command)==0&&*d==*s);
#ifdef _WIN32
 CHECK(VirtualFree(a,0,MEM_RELEASE));CHECK(VirtualFree(b,0,MEM_RELEASE));
#else
 CHECK(munmap(a,page*2)==0);CHECK(munmap(b,page*2)==0);
#endif
}

static void wide_strips(void){
 const size_t n=379*11+16;uint32_t *a=malloc(n*4),*b=malloc(n*4),*c=malloc(n*4);CHECK(a&&b&&c);
 const unsigned widths[]={127,128,129,257,511,8192},opacities[]={0,1,128,255,256};
 for(unsigned k=0;k<6;k++)for(unsigned p=0;p<5;p++){
  for(unsigned i=0;i<SOURCE;i++)source[i]=(k%2)?(0xff000000|(random32()&0xffffff)):premultiplied();memcpy(saved_source,source,sizeof source);
  for(size_t i=0;i<n;i++)a[i]=premultiplied();memcpy(b,a,n*4);memcpy(c,a,n*4);
  Surface src={source+7,SOURCE-14,137,5,140},dst={a+8,n-16,365,11,379},ref=dst,part=dst;ref.pixels=b+8;part.pixels=c+8;
  Rect r={-17,-7,(int64_t)widths[k]-17,16},clip={0,0,365,11};model(&ref,&src,&r,&clip,opacities[p]);CHECK(transform_scaled(&dst,&src,&r,&clip,opacities[p])==0);CHECK(memcmp(a,b,n*4)==0);
  Rect left=clip,right=clip;left.right=129;right.left=129;CHECK(transform_scaled(&part,&src,&r,&left,opacities[p])==0);CHECK(transform_scaled(&part,&src,&r,&right,opacities[p])==0);CHECK(memcmp(a,c,n*4)==0);CHECK(memcmp(source,saved_source,sizeof source)==0);cases++;clip_partitions++;
 }
 free(c);free(b);free(a);
}

int main(void){
 uint64_t sizes[2];transform_sizes(sizes);CHECK(sizes[0]==sizeof(Surface)&&sizes[1]==sizeof(Rect));
 const size_t dimensions[]={1,2,3,7,13,29};const unsigned opacities[]={0,1,63,128,255,256};const Rect clips[]={{-7,-9,40,30},{0,0,31,23},{3,2,21,17},{12,7,13,8},{40,30,50,40},{0,0,0,23}};
 for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++)for(unsigned k=0;k<6;k++)for(unsigned p=0;p<6;p++){
  size_t sw=dimensions[i],sh=(i%3)+1,dw=dimensions[j],dh=dimensions[(j+2)%6];int64_t x=(int64_t)(k*7)-13,y=(int64_t)(k*5)-9;compare(sw,sh,dw,dh,x,y,clips[k],opacities[p]);
 }
 /* Non-power-of-two denominator edges, 8192 maximum destination, strong shrink. */
 compare(29,7,8192,8192,-8180,-8180,clips[1],256);compare(29,7,1,1,2,3,clips[0],128);compare(1,1,8192,8192,-4000,-4000,clips[1],1);
 invalid();maximum_sources();wide_strips();guard_pages();printf("transform oracle passed: cases=%llu partitioned=%llu atomic-invalid=%llu exact-nearest+Q8-over actual-ASM guards+SysV=ok checks=%llu\n",(unsigned long long)cases,(unsigned long long)clip_partitions,(unsigned long long)rejections,(unsigned long long)checks);return 0;
}
