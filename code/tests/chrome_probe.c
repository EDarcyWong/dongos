/* Independent per-pixel AA/source-over oracle plus the original Dong renderer.
 * No partitioning appears in the oracle. Every pixel, stride pad and guard is
 * compared, so overlapping fast regions and unpainted corner edges are visible.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"CHROME_MODEL_ASSERT line %d: %s case=%u\n",__LINE__,#x,cases);exit(1);}}while(0)
typedef struct { int64_t left,top,right,bottom; } Rect;
typedef struct { uint32_t *pixels;size_t length,width,height,stride; } Surface;
extern ABI void chrome_sizes(uint64_t *);
extern ABI uint64_t chrome_fast(Surface *,const Rect *,const Rect *,int64_t,uint32_t,uint8_t);
extern ABI uint64_t chrome_reference(Surface *,const Rect *,const Rect *,int64_t,uint32_t);
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected chrome panic %llu\n",(unsigned long long)code);exit(99);}
ABI void chrome_negative_hit(uint64_t kind){static unsigned seen;if(!seen++){fprintf(stderr,"CHROME_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}}
enum { W=79,H=53,S=86,N=S*H,TOTAL=N+16 };
static uint32_t actual[TOTAL],reference[TOTAL],expected[TOTAL],initial[TOTAL];
static Surface a={actual+8,N,W,H,S},b={reference+8,N,W,H,S};
static unsigned cases,transparent_cases,opaque_cases,overlay_cases,invalid_cases;
static uint64_t checks;
static uint32_t seed=0xa41f2907;
static uint32_t random32(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static uint32_t cov(uint32_t color,unsigned coverage){uint32_t v=0;for(unsigned shift=0;shift<32;shift+=8)v|=((((color>>shift)&255)*coverage+127)/255)<<shift;return v;}
static uint32_t over(uint32_t dst,uint32_t src){uint32_t v=0;for(unsigned shift=0;shift<32;shift+=8){unsigned x=((src>>shift)&255)+(((dst>>shift)&255)*(255-(src>>24))+127)/255;if(x>255)x=255;v|=x<<shift;}return v;}
static unsigned cover(const Rect *r,int64_t radius,int64_t x,int64_t y){
 int64_t w=r->right-r->left,h=r->bottom-r->top;if(radius>w/2)radius=w/2;if(radius>h/2)radius=h/2;
 int corner_x=x<r->left+radius?0:x>=r->right-radius?1:-1;
 int corner_y=y<r->top+radius?0:y>=r->bottom-radius?1:-1;
 if(radius==0||corner_x<0||corner_y<0)return 255;
 int64_t cx=(corner_x?r->right-radius:r->left+radius)*8,cy=(corner_y?r->bottom-radius:r->top+radius)*8;
 unsigned hits=0;for(int yy=0;yy<4;yy++)for(int xx=0;xx<4;xx++){
  int64_t dx=x*8+1+xx*2-cx,dy=y*8+1+yy*2-cy;
  if(dx*dx+dy*dy<=radius*radius*64)hits++;
 }return (hits*255+8)/16;
}
static void background(const Rect *rect,unsigned transparent){
 for(size_t i=0;i<TOTAL;i++)initial[i]=0x91462907u+(uint32_t)(i*104729u);
 for(int64_t y=0;y<H;y++)for(int64_t x=0;x<W;x++){
  uint32_t p=0xff000000u|((uint32_t)(x*31249+y*8677)&0x00ffffffu);
  if(transparent&&x>=rect->left&&x<rect->right&&y>=rect->top&&y<rect->bottom)p=0;
  else if((x+y)%3==0)p=cov(p,(unsigned)((x*7+y*11)%256));
  initial[8+(size_t)y*S+(size_t)x]=p;
 }
 memcpy(actual,initial,sizeof actual);memcpy(reference,initial,sizeof reference);memcpy(expected,initial,sizeof expected);
}
static void oracle(const Rect *rect,const Rect *clip,int64_t radius,uint32_t color){
 for(int64_t y=0;y<H;y++)for(int64_t x=0;x<W;x++)if(x>=rect->left&&x<rect->right&&y>=rect->top&&y<rect->bottom&&x>=clip->left&&x<clip->right&&y>=clip->top&&y<clip->bottom){
  size_t at=8+(size_t)y*S+(size_t)x;expected[at]=over(expected[at],cov(color,cover(rect,radius,x,y)));
 }
}
static void compare(const Rect *rect,const Rect *clip,int64_t radius,uint32_t color,unsigned transparent){
 background(rect,transparent);oracle(rect,clip,radius,color);
 CHECK(chrome_reference(&b,rect,clip,radius,color)==0);
 CHECK(chrome_fast(&a,rect,clip,radius,color,(uint8_t)transparent)==0);
 CHECK(memcmp(reference,expected,sizeof reference)==0);
 CHECK(memcmp(actual,expected,sizeof actual)==0);
 CHECK(memcmp(actual,reference,sizeof actual)==0);
 for(unsigned y=0;y<H;y++)for(unsigned x=W;x<S;x++)CHECK(actual[8+y*S+x]==initial[8+y*S+x]);
 for(unsigned i=0;i<8;i++)CHECK(actual[i]==initial[i]&&actual[N+8+i]==initial[N+8+i]);
 if(transparent)transparent_cases++;else if((color>>24)==255)opaque_cases++;else overlay_cases++;
 cases++;
}
static void invalid(const Rect *rect,const Rect *clip,int64_t radius,uint32_t color,unsigned bad_surface){
 Rect empty={0,0,0,0};background(&empty,0);Surface sa=a,sb=b;if(bad_surface){sa.stride=W-1;sb.stride=W-1;}
 uint64_t old=chrome_reference(&sb,rect,clip,radius,color),fast=chrome_fast(&sa,rect,clip,radius,color,1);
 CHECK(old!=0&&fast==old);CHECK(memcmp(actual,initial,sizeof actual)==0&&memcmp(reference,initial,sizeof reference)==0);invalid_cases++;
}
int main(void){
 uint64_t sizes[2];chrome_sizes(sizes);CHECK(sizes[0]==sizeof(Surface)&&sizes[1]==sizeof(Rect));
 const Rect full={0,0,W,H};
 const Rect shapes[]={ {8,5,70,49},{0,0,W,H},{-9,-11,41,43},{64,43,90,70},{-20,-20,-1,-1},
  {4,4,4,40},{4,4,40,4},{10,10,11,11},{10,10,12,12},{10,10,13,13},{10,10,11,42},
  {8,9,72,10},{10,10,26,26},{10,10,27,27},{-65536,-65536,65536,65536},{0,0,0,0} };
 const Rect clips[]={ {0,0,W,H},{0,0,0,0},{5,7,61,46},{60,0,79,15},{0,40,20,53},{20,20,25,25} };
 const int64_t radii[]={0,1,2,7,8,12,32,128};
 const uint32_t colors[]={0xff123456,0x80402010,0x50000000,0,0x01010000};
 for(unsigned i=0;i<sizeof shapes/sizeof shapes[0];i++)for(unsigned j=0;j<sizeof clips/sizeof clips[0];j++)for(unsigned k=0;k<sizeof radii/sizeof radii[0];k++){
  unsigned c=(i+j+k)%5;compare(&shapes[i],&clips[j],radii[k],colors[c],(i+j+k)&1);
 }
 for(unsigned n=0;n<320;n++){
  int64_t x=(int64_t)(random32()%120)-20,y=(int64_t)(random32()%90)-20;
  Rect rect={x,y,x+(int64_t)(random32()%100),y+(int64_t)(random32()%80)};
  int64_t left=(int64_t)(random32()%(W+1)),top=(int64_t)(random32()%(H+1));
  Rect clip={left,top,left+(int64_t)(random32()%(W+1-(unsigned)left)),top+(int64_t)(random32()%(H+1-(unsigned)top))};
  unsigned alpha=random32()%256;uint32_t color=cov(0xff000000u|(random32()&0xffffffu),alpha);
  compare(&rect,&clip,(int64_t)(random32()%129),color,n&1);
 }
 Rect invalid_rect={8,9,7,10},low={-65537,0,0,4},high={0,0,65537,4},bad_clip={-1,0,10,10};
 invalid(&invalid_rect,&full,2,0xff123456,0);invalid(&low,&full,2,0xff123456,0);invalid(&high,&full,2,0xff123456,0);
 invalid(&shapes[0],&bad_clip,2,0xff123456,0);invalid(&shapes[0],&full,-1,0xff123456,0);invalid(&shapes[0],&full,129,0xff123456,0);
 invalid(&shapes[0],&full,2,0x10200000,0);invalid(&shapes[0],&full,2,0xff123456,1);
 printf("chrome oracle passed: comparisons=%u transparent=%u opaque=%u overlay=%u atomic-invalid=%u full-array=reference+C stride-and-guards=ok checks=%llu\n",cases,transparent_cases,opaque_cases,overlay_cases,invalid_cases,(unsigned long long)checks);
 return 0;
}
