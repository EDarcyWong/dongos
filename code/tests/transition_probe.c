/* Independent nonnegative rational-coordinate model and public ABI oracle. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"TRANSITION_MODEL_ASSERT line %d: %s case=%u\n",__LINE__,#x,cases);exit(1);}}while(0)
typedef struct{int64_t left,top,right,bottom;}Rect;
typedef struct{Rect from,to;uint64_t start,duration;}Track;
extern ABI uint64_t transition_size(void),transition_begin(Track*,const Rect*,const Rect*,const Rect*,uint64_t,uint64_t),transition_sample(const Track*,const Rect*,uint64_t,Rect*,uint64_t*),transition_retarget(Track*,const Rect*,const Rect*,uint64_t,uint64_t),transition_zoom(const Rect*,const Rect*,Rect*);
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected transition panic %llu\n",(unsigned long long)code);exit(99);}
ABI void transition_negative_hit(uint64_t kind){static unsigned seen;if(!seen++)fprintf(stderr,"TRANSITION_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}
static uint64_t checks;static unsigned cases,reversals,failures,zooms;
static const uint64_t PRE=UINT64_C(0xabcdefff12345678),POST=UINT64_C(0x87654321fffedcba);
static struct{uint64_t pre;Track value;uint64_t post;} track;
static struct{uint64_t pre;Rect value;uint64_t post;} output;
static uint64_t rng=UINT64_C(0x9e3779b97f4a7c15);
static uint64_t random64(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static int same(const Rect*a,const Rect*b){return memcmp(a,b,sizeof *a)==0;}
static int valid(const Rect*r,const Rect*s){return r->left>=0&&r->top>=0&&r->left<r->right&&r->top<r->bottom&&r->right<=s->right&&r->bottom<=s->bottom;}
static Rect random_rect(const Rect*s){int64_t x=random64()%(uint64_t)s->right,y=random64()%(uint64_t)s->bottom;return(Rect){x,y,x+1+(int64_t)(random64()%(uint64_t)(s->right-x)),y+1+(int64_t)(random64()%(uint64_t)(s->bottom-y))};}
static Rect model(const Track*t,uint64_t now,uint64_t*active){
 *active=0;if(t->duration==0)return t->to;if(now<t->start){*active=1;return t->from;}uint64_t elapsed=now-t->start;if(elapsed>=t->duration)return t->to;
 *active=1;uint64_t u=(uint64_t)(((__uint128_t)elapsed<<16)/t->duration);uint64_t smooth=(uint64_t)(((__uint128_t)u*u)>>16);smooth=(uint64_t)(((__uint128_t)smooth*(3*65536-2*u))>>16);
 uint64_t weights[]={65536-smooth,smooth};Rect r;const int64_t*a=&t->from.left,*b=&t->to.left;int64_t*out=&r.left;
 for(unsigned i=0;i<4;i++)out[i]=(int64_t)(((__uint128_t)(uint64_t)a[i]*weights[0]+(__uint128_t)(uint64_t)b[i]*weights[1])>>16);
 return r;
}
static void guards(void){CHECK(track.pre==PRE&&track.post==POST&&output.pre==PRE&&output.post==POST);}
static void init(const Rect*s,const Rect*a,const Rect*b,uint64_t start,uint64_t duration){
 memset(&track,0x5a,sizeof track);track.pre=PRE;track.post=POST;memset(&output,0xa5,sizeof output);output.pre=PRE;output.post=POST;
 CHECK(transition_begin(&track.value,s,a,b,start,duration)==0);Track expected={*a,*b,start,duration};CHECK(memcmp(&track.value,&expected,sizeof expected)==0);guards();
}
static void sample(const Rect*s,uint64_t now){
 uint64_t actual_active=UINT64_MAX,expected_active;Track before=track.value;Rect expected=model(&before,now,&expected_active);
 CHECK(transition_sample(&track.value,s,now,&output.value,&actual_active)==0);CHECK(same(&output.value,&expected));CHECK(actual_active==expected_active);CHECK(valid(&output.value,s));CHECK(memcmp(&track.value,&before,sizeof before)==0);guards();cases++;
}
static void failure_begin(const Rect*s,const Rect*a,const Rect*b,uint64_t duration){Track before=track.value;CHECK(transition_begin(&track.value,s,a,b,11,duration)!=0);CHECK(memcmp(&track.value,&before,sizeof before)==0);guards();failures++;}
static void failure_sample(const Rect*s){Rect before=output.value;uint64_t active=UINT64_C(0x1122334455667788);Track frozen=track.value;CHECK(transition_sample(&track.value,s,22,&output.value,&active)!=0);CHECK(same(&before,&output.value)&&active==UINT64_C(0x1122334455667788));CHECK(memcmp(&track.value,&frozen,sizeof frozen)==0);guards();failures++;}
static void reverse(const Rect*s,const Rect*goal,uint64_t now,uint64_t duration){
 uint64_t active;Rect current=model(&track.value,now,&active);CHECK(transition_retarget(&track.value,s,goal,now,duration)==0);CHECK(same(&track.value.from,&current)&&same(&track.value.to,goal)&&track.value.start==now&&track.value.duration==duration);sample(s,now);reversals++;
}
static void zoom(const Rect*s,const Rect*r){
 Rect before=*r;CHECK(transition_zoom(r,s,&output.value)==0);int64_t w=r->right-r->left,h=r->bottom-r->top;int64_t zw=(int64_t)((uint64_t)w*15/16),zh=(int64_t)((uint64_t)h*15/16);if(zw==0)zw=1;if(zh==0)zh=1;
 Rect expected={r->left+(w-zw)/2,r->top+(h-zh)/2,0,0};expected.right=expected.left+zw;expected.bottom=expected.top+zh;CHECK(same(&output.value,&expected)&&valid(&output.value,s));CHECK(same(r,&before));CHECK(output.value.left>=r->left&&output.value.top>=r->top&&output.value.right<=r->right&&output.value.bottom<=r->bottom);guards();zooms++;
}
int main(void){
 CHECK(transition_size()==sizeof(Track)&&sizeof(Track)==80);Rect screen={0,0,1920,1080},a={10,20,410,320},b={100,80,900,680};
 const uint64_t times[]={0,1,2,35,70,105,139,140,141,UINT64_MAX};
 for(unsigned d=0;d<3;d++){uint64_t duration=d==0?0:d==1?1:140;init(&screen,&a,&b,1,duration);for(unsigned t=0;t<sizeof times/sizeof times[0];t++)sample(&screen,times[t]);}
 /* Golden midpoint/quarters, independent from the generic interpolator model. */
 init(&screen,&(Rect){0,0,256,256},&(Rect){256,256,512,512},0,4);sample(&screen,1);CHECK(output.value.left==40&&output.value.right==296);sample(&screen,2);CHECK(output.value.left==128&&output.value.right==384);sample(&screen,3);CHECK(output.value.left==216&&output.value.right==472);
 const unsigned dimensions[][2]={{1,1},{2,3},{800,600},{1280,720},{1920,1080},{4096,2160},{8192,8192}};const unsigned scales[]={256,320,384,448,512};
 for(unsigned size=0;size<sizeof dimensions/sizeof dimensions[0];size++){
  screen=(Rect){0,0,dimensions[size][0],dimensions[size][1]};
  for(unsigned old=0;old<5;old++)for(unsigned next=0;next<5;next++){
   unsigned width=dimensions[size][0],height=dimensions[size][1];unsigned aw=width*scales[old]/1024+1,bw=width*scales[next]/1024+1,ah=height*scales[old]/1024+1,bh=height*scales[next]/1024+1;
   if(aw>width){aw=width;}if(bw>width){bw=width;}if(ah>height){ah=height;}if(bh>height){bh=height;}
   a=(Rect){0,0,aw,ah};b=(Rect){width-bw,height-bh,width,height};init(&screen,&a,&b,9,140);for(unsigned t=0;t<=142;t++)sample(&screen,t);zoom(&screen,&a);zoom(&screen,&b);reverse(&screen,&a,56,140);reverse(&screen,&b,91,140);sample(&screen,231);
  }
 }
 /* Real four-window cache budgets at all five supported DPI scales. The
    transition changes body presentation without reallocating target caches. */
 screen=(Rect){0,0,1920,1080};
 for(unsigned old=0;old<5;old++)for(unsigned next=0;next<5;next++)for(unsigned app=0;app<4;app++){
  Rect ends[2];unsigned choices[]={old,next};
  for(unsigned j=0;j<2;j++){
   uint64_t q=scales[choices[j]],pad=(24*q+128)/256,margin=(110*q+128)/256;
   int64_t w=(1920-(int64_t)margin)/2,limit=((app==2?640:720)*q+128)/256;if(w>limit){w=limit;}
   int64_t h=(260*q+128)/256,cache=300000/(w+(int64_t)pad)-(int64_t)pad;if(h>cache){h=cache;}
   int64_t display=1080-(142*q+128)/256;if(h>display){h=display;}
   CHECK(w>=32&&h>=24&&(w+(int64_t)pad)*(h+(int64_t)pad)<=300000);
   int64_t x=(1920-w)*(app%2),y=app<2?0:1080-h-(90*q+128)/256;
   ends[j]=(Rect){x,y,x+w,y+h};
  }
  init(&screen,&ends[0],&ends[1],1,140);for(unsigned t=1;t<=141;t+=7)sample(&screen,t);zoom(&screen,&ends[1]);
 }
 /* Dense deterministic coordinates, tiny rectangles and times near u64 wrap. */
 for(unsigned i=0;i<20000;i++){
  screen=(Rect){0,0,1+(int64_t)(random64()%8192),1+(int64_t)(random64()%8192)};a=random_rect(&screen);b=random_rect(&screen);uint64_t duration=random64()%60001,start=i%2?random64():UINT64_MAX-60000;init(&screen,&a,&b,start,duration);
  uint64_t now;if(i%4==0)now=0;else if(i%4==1)now=UINT64_MAX;else now=start+(duration?random64()%duration:0);sample(&screen,now);zoom(&screen,&a);if(i%7==0)reverse(&screen,&a,now,random64()%60001);
 }
 screen=(Rect){0,0,8192,8192};a=(Rect){8191,8191,8192,8192};b=(Rect){0,0,1,1};init(&screen,&a,&b,UINT64_MAX-10,60000);sample(&screen,UINT64_MAX);reverse(&screen,&a,UINT64_MAX,0);sample(&screen,0); /* zero duration always resolves to target */
 /* Input aliases are snapshotted before publishing a Track or zoom rectangle. */
 init(&screen,&a,&b,50,140);Track before=track.value;CHECK(transition_begin(&track.value,&screen,&track.value.to,&track.value.from,60,150)==0);CHECK(same(&track.value.from,&before.to)&&same(&track.value.to,&before.from));
 Rect in_place={0,0,101,83};CHECK(transition_zoom(&in_place,&screen,&in_place)==0);CHECK(in_place.left==3&&in_place.top==3&&in_place.right==97&&in_place.bottom==80);guards();
 before=track.value;Rect bads[]={{-1,0,1,1},{0,-1,1,1},{2,0,1,1},{0,2,1,1},{0,0,0,1},{0,0,1,0},{0,0,8193,1},{0,0,1,8193},{INT64_MIN,0,INT64_MAX,1},{0,INT64_MIN,1,INT64_MAX}};
 for(unsigned i=0;i<sizeof bads/sizeof bads[0];i++){failure_begin(&screen,&bads[i],&b,140);failure_begin(&screen,&a,&bads[i],140);track.value.from=bads[i];failure_sample(&screen);track.value=before;track.value.to=bads[i];failure_sample(&screen);track.value=before;Rect old=output.value;CHECK(transition_zoom(&bads[i],&screen,&output.value)!=0&&same(&old,&output.value));Track prior=track.value;CHECK(transition_retarget(&track.value,&screen,&bads[i],100,140)!=0&&memcmp(&prior,&track.value,sizeof prior)==0);}
 Rect badscreens[]={{1,0,10,10},{0,1,10,10},{0,0,0,10},{0,0,10,0},{0,0,8193,10},{0,0,10,8193},{0,0,INT64_MAX,10},{0,0,10,INT64_MAX}};
 for(unsigned i=0;i<sizeof badscreens/sizeof badscreens[0];i++){failure_begin(&badscreens[i],&a,&b,140);failure_sample(&badscreens[i]);Rect old=output.value;CHECK(transition_zoom(&a,&badscreens[i],&output.value)!=0&&same(&old,&output.value));}
 const uint64_t durations[]={60001,UINT64_MAX};for(unsigned i=0;i<2;i++){failure_begin(&screen,&a,&b,durations[i]);track.value.duration=durations[i];failure_sample(&screen);track.value=before;Track prior=track.value;CHECK(transition_retarget(&track.value,&screen,&b,100,durations[i])!=0&&memcmp(&prior,&track.value,sizeof prior)==0);}
 failure_begin(NULL,&a,&b,140);failure_begin(&screen,NULL,&b,140);failure_begin(&screen,&a,NULL,140);CHECK(transition_begin(NULL,&screen,&a,&b,0,140)!=0);
 uint64_t active=99;Rect old=output.value;CHECK(transition_sample(NULL,&screen,0,&output.value,&active)!=0&&active==99&&same(&old,&output.value));CHECK(transition_sample(&track.value,&screen,0,NULL,&active)!=0&&active==99);CHECK(transition_zoom(NULL,&screen,&output.value)!=0&&same(&old,&output.value));CHECK(transition_zoom(&a,NULL,&output.value)!=0&&same(&old,&output.value));CHECK(transition_zoom(&a,&screen,NULL)!=0);CHECK(transition_retarget(NULL,&screen,&a,0,140)!=0);guards();
 printf("transition oracle passed: samples=%u reversals=%u zooms=%u atomic-rejections=%u five-scale-pairs=25 target-cache-budgets=100 all-guards=ok checks=%llu\n",cases,reversals,zooms,failures,(unsigned long long)checks);return 0;
}
