#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#if defined(__GNUC__)
#define SYSV __attribute__((sysv_abi))
#else
#define SYSV
#endif
extern void SYSV svc_present_rows(const uint32_t *,uint32_t *,size_t,size_t,size_t,uint64_t);
extern uint64_t SYSV svc_graphics_features(void);
extern uint64_t svc_avx2;
extern void SYSV svc_composite_rows(const uint32_t *,uint32_t *,size_t,size_t,size_t,size_t);
extern void SYSV svc_composite_opacity_rows(const uint32_t *,uint32_t *,size_t,size_t,size_t,size_t,uint64_t);
extern void SYSV svc_copy_rows(const uint32_t *,uint32_t *,size_t,size_t,size_t,size_t);
/* Only the isolated bad-opacity assembly increments this witness. */
uint64_t presentation_bad_opacity_hits;
void service_main(void){}
static uint32_t src[1024],dst[1024],expected[1024],saved[1024];
static uint32_t opacity_src[512],opacity_dst[512],opacity_expected[512],opacity_saved[512];
static uint32_t opacity_model(uint32_t source,uint32_t destination,unsigned opacity){
 uint32_t scaled=0,result=0;
 for(unsigned shift=0;shift<32;shift+=8){
  unsigned component=(((source>>shift)&255)*opacity+128)/256;
  scaled|=component<<shift;
 }
 unsigned inverse=255-(scaled>>24);
 for(unsigned shift=0;shift<32;shift+=8){
  unsigned component=((scaled>>shift)&255)+(((destination>>shift)&255)*inverse+127)/255;
  if(component>255){component=255;}
  result|=component<<shift;
 }
 return result;
}
static int opacity_tests(void){
 static const size_t widths[]={0,1,2,3,4,5,7,15,16,17,31,32,33,63,64,65};
 static const size_t heights[]={0,1,3};
 unsigned cases=0;
 /* This function is SSE2, independent of the presentation AVX2 feature flag. */
 svc_avx2=0;
 for(unsigned alpha=0;alpha<=256;alpha++)for(unsigned pattern=0;pattern<3;pattern++)
 for(size_t sa=0;sa<4;sa++)for(size_t da=0;da<4;da++)
 for(size_t wi=0;wi<sizeof widths/sizeof widths[0];wi++)for(size_t hi=0;hi<sizeof heights/sizeof heights[0];hi++){
  size_t width=widths[wi],height=heights[hi];
  size_t ss=width+5+alpha%5,ds=width+9+(alpha+pattern)%7;
  for(size_t i=0;i<512;i++){
   unsigned a=pattern==0?0:pattern==1?128:255;
   opacity_src[i]=a<<24|((i*17+alpha*3)%(a+1))<<16|((i*31+pattern)%(a+1))<<8|(i*47+width)%(a+1);
   unsigned d=i%3==0?0:i%3==1?97:255;
   opacity_dst[i]=d<<24|((i*7+width)%(d+1))<<16|((i*19+alpha)%(d+1))<<8|(i*23+pattern)%(d+1);
  }
  memcpy(opacity_expected,opacity_dst,sizeof opacity_dst);memcpy(opacity_saved,opacity_src,sizeof opacity_src);
  for(size_t y=0;y<height;y++)for(size_t x=0;x<width;x++){
   size_t from=16+sa+y*ss+x,to=16+da+y*ds+x;
   opacity_expected[to]=opacity_model(opacity_src[from],opacity_dst[to],alpha);
  }
  svc_composite_opacity_rows(opacity_src+16+sa,opacity_dst+16+da,ss,ds,width,height,alpha);
  if(memcmp(opacity_dst,opacity_expected,sizeof opacity_dst)||memcmp(opacity_src,opacity_saved,sizeof opacity_src)){
   fprintf(stderr,"opacity pixel/guard failed alpha=%u source_alpha=%u sa=%u da=%u ss=%u ds=%u w=%u h=%u bad_hits=%u\n",
    alpha,pattern==0?0:pattern==1?128:255,(unsigned)sa,(unsigned)da,(unsigned)ss,(unsigned)ds,(unsigned)width,(unsigned)height,(unsigned)presentation_bad_opacity_hits);
   return 1;
  }
  cases++;
 }
 printf("opacity oracle passed: %u cases alpha=0..256, source A=0/128/255, independent strides, offsets/tails, complete guards\n",cases);
 return 0;
}
int main(void){unsigned cases=0;uint64_t avx=0;
 for(unsigned mode=0;mode<2;mode++){
 if(mode){avx=svc_graphics_features();if(!avx)break;}
 for(size_t sa=0;sa<4;sa++)for(size_t da=0;da<4;da++)for(size_t w=0;w<66;w++)for(size_t h=0;h<6;h++)for(unsigned f=0;f<2;f++){
  const size_t stride=w+7;
  for(size_t i=0;i<1024;i++){src[i]=(uint32_t)(i*0x0103070bU+0x2513579bU);dst[i]=0xa5a55a5aU;}
  memcpy(expected,dst,sizeof dst);memcpy(saved,src,sizeof src);
  for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++){
   uint32_t v=src[16+sa+y*stride+x];if(!f)v=(v&0xff00ff00U)|((v&255)<<16)|((v>>16)&255);
   expected[16+da+y*stride+x]=v;
  }
  svc_present_rows(src+16+sa,dst+16+da,stride,w,h,f);
  if(memcmp(dst,expected,sizeof dst)||memcmp(src,saved,sizeof src)){fprintf(stderr,"presentation pixel/guard failed sa=%u da=%u w=%u h=%u format=%u\n",(unsigned)sa,(unsigned)da,(unsigned)w,(unsigned)h,f);return 1;}
  cases++;
 }
 }
 printf("presentation oracle passed: %u cases avx2=%u, exact RGB/BGR, source/destination full guards\n",cases,(unsigned)avx);
 unsigned mixed=0;
 for(unsigned mode=0;mode<(avx?2u:1u);mode++){
 svc_avx2=mode;
 for(size_t sa=0;sa<4;sa++)for(size_t da=0;da<4;da++)for(size_t w=0;w<66;w++)for(size_t h=0;h<6;h++){
  size_t ss=w+5,ds=w+9;
  for(size_t i=0;i<1024;i++){
   unsigned a=(unsigned)((i*13+sa*23+w*7)&255);if((i/64)%3==0)a=255;if((i/64)%3==1)a=0;
   src[i]=a<<24|((i*17%(a+1))<<16)|((i*31%(a+1))<<8)|(i*47%(a+1));dst[i]=0xff3579b2;
  }
  memcpy(expected,dst,sizeof dst);memcpy(saved,src,sizeof src);
  for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++){
   uint32_t s=src[16+sa+y*ss+x],d=dst[16+da+y*ds+x],v=0;unsigned a=s>>24;
   for(unsigned sh=0;sh<32;sh+=8){unsigned t=((d>>sh)&255)*(255-a)+128;t=(t+(t>>8))>>8;v|=(((s>>sh)&255)+t)<<sh;}
   expected[16+da+y*ds+x]=v;
  }
  svc_composite_rows(src+16+sa,dst+16+da,ss,ds,w,h);
  if(memcmp(expected,dst,sizeof dst)||memcmp(saved,src,sizeof src)){fprintf(stderr,"composition pixel/guard failed w=%u h=%u\n",(unsigned)w,(unsigned)h);return 1;}
  for(size_t i=0;i<1024;i++)dst[i]=expected[i]=0xa5a55a5a;
  for(size_t y=0;y<h;y++)for(size_t x=0;x<w;x++)expected[16+da+y*ds+x]=src[16+sa+y*ss+x];
  svc_copy_rows(src+16+sa,dst+16+da,ss,ds,w,h);
  if(memcmp(expected,dst,sizeof dst)||memcmp(saved,src,sizeof src)){fprintf(stderr,"copy pixel/guard failed w=%u h=%u\n",(unsigned)w,(unsigned)h);return 1;}
  mixed++;
 }
 }
 printf("composition oracle passed: %u premultiplied alpha cases, distinct strides, full guards\n",mixed);return opacity_tests();
}
