/* Independent four-window metric model, complete State byte comparisons. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"LAYOUT_MODEL_ASSERT line %d: %s case=%u\n",__LINE__,#x,cases);exit(1);}}while(0)
typedef struct{int64_t left,top,right,bottom;}Rect;
typedef struct{Rect bounds;size_t count;uint8_t full,pad[7];Rect rects[16];}Damage;
typedef struct{uint64_t generation,status,owner,buffer,retired;Rect rect,requested;uint64_t serial,ack;int64_t minw,minh;uint64_t flags;}Slot;
typedef struct{Slot slots[16];uint64_t order[16];size_t count;uint64_t focus,grab,mode;int64_t x,y;uint64_t buttons;int64_t startx,starty;Rect start,screen;Damage damage;}State;
extern ABI void layout_sizes(uint64_t *);
extern ABI uint64_t layout_init(State *,size_t,size_t),layout_rescale(State *,uint64_t,uint64_t),layout_valid(const State *);
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected layout panic %llu\n",(unsigned long long)code);exit(99);}
ABI void layout_negative_hit(uint64_t kind){static unsigned seen;if(!seen++){fprintf(stderr,"LAYOUT_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}}
static uint64_t checks;
static unsigned cases,failed,cancelled,hidden;
static struct{uint64_t pre;State state;uint64_t post;} actual;
static State before,expected;
static int64_t min64(int64_t a,int64_t b){return a<b?a:b;}
static int64_t scaled(unsigned logical,uint64_t q){return (int64_t)(((uint64_t)logical*q+128)/256);}
static uint64_t handle(unsigned i){return (actual.state.slots[i].generation<<8)|(i+1);}
static ABI void guard(void){CHECK(actual.pre==UINT64_C(0x1020304050607080)&&actual.post==UINT64_C(0x8070605040302010));}
static ABI void setup(unsigned width,unsigned height,unsigned grab){
 memset(&actual,0,sizeof actual);actual.pre=UINT64_C(0x1020304050607080);actual.post=UINT64_C(0x8070605040302010);
 CHECK(layout_init(&actual.state,width,height)==0);State *s=&actual.state;
 s->x=width-1;s->y=height-1;
 for(unsigned i=0;i<4;i++){
  Slot *slot=&s->slots[i];int64_t w=min64(width/3,330),h=min64(height/3,180);if(w<32)w=32;if(h<24)h=24;
  int64_t x=((int64_t)width-w)*(i+1)/5,y=((int64_t)height-h)*(i+1)/5;
  slot->generation=0x1234+i;slot->owner=101+i;slot->buffer=0x100001+i;slot->retired=0x200001+i;
  slot->rect=(Rect){x,y,x+w,y+h};slot->requested=slot->rect;
  if(slot->requested.right<width)slot->requested.right++;
  slot->serial=100+i;slot->ack=slot->serial-1;slot->minw=32;slot->minh=24;slot->flags=i==1?2:3;
 }
 const unsigned order[]={2,0,3,1};for(unsigned i=0;i<4;i++)s->order[i]=handle(order[i]);
 for(unsigned i=4;i<16;i++)s->order[i]=UINT64_C(0x1111222233334400)+i;
 s->focus=handle(2);s->slots[8].status=3;s->slots[8].generation=77;s->slots[8].owner=0x7777;s->slots[8].buffer=0x8888;
 s->startx=-19;s->starty=-20;s->start=(Rect){-3,-2,-1,0};
 if(grab){s->grab=handle(0);s->mode=grab;s->buttons=9;s->startx=10;s->starty=11;s->start=s->slots[0].rect;}
 memset(&s->damage,0,sizeof s->damage);s->damage.bounds=s->screen;s->damage.count=1;s->damage.rects[0]=s->slots[0].rect;
 CHECK(layout_valid(s)==0);guard();
}
static ABI void model(uint64_t old,uint64_t next){
 expected=before;int64_t sw=before.screen.right,sh=before.screen.bottom,pad=scaled(24,next);
 for(unsigned i=0;i<4;i++){
  Slot *s=&expected.slots[i];int64_t w=min64((sw-scaled(110,next))/2,scaled(i==2?640:720,next));
  int64_t h=min64(scaled(sh<850?180:260,next),min64(300000/(w+pad)-pad,sh-scaled(142,next)));
  int64_t x=(int64_t)((uint64_t)before.slots[i].rect.left*next/old),y=(int64_t)((uint64_t)before.slots[i].rect.top*next/old);
  if(x>sw-w){x=sw-w;}if(y>sh-h-scaled(90,next)){y=sh-h-scaled(90,next);}if(x<0){x=0;}if(y<0){y=0;}
  s->rect=(Rect){x,y,x+w,y+h};s->requested=s->rect;s->serial++;s->ack=s->serial;s->minw=min64(200,w);s->minh=min64(120,h);
 }
 expected.grab=0;expected.mode=0;expected.buttons=0;expected.startx=0;expected.starty=0;expected.start=(Rect){0,0,0,0};
 memset(&expected.damage,0,sizeof expected.damage);expected.damage.bounds=before.screen;expected.damage.count=1;expected.damage.full=1;expected.damage.rects[0]=before.screen;
}
static ABI void success(uint64_t old,uint64_t next){
 before=actual.state;model(old,next);CHECK(layout_rescale(&actual.state,old,next)==0);
 CHECK(memcmp(&actual.state,&expected,sizeof expected)==0);CHECK(layout_valid(&actual.state)==0);guard();
 State *s=&actual.state;CHECK(s->focus==before.focus&&s->x==before.x&&s->y==before.y&&memcmp(s->order,before.order,sizeof s->order)==0);
 for(unsigned i=0;i<4;i++){
  Slot *n=&s->slots[i],*p=&before.slots[i];CHECK(n->generation==p->generation&&n->owner==p->owner&&n->status==p->status&&n->buffer==p->buffer&&n->retired==p->retired&&n->flags==p->flags);
  CHECK(n->serial==p->serial+1&&n->ack==n->serial&&memcmp(&n->rect,&n->requested,sizeof(Rect))==0);
  int64_t pad=scaled(24,next),w=n->rect.right-n->rect.left,h=n->rect.bottom-n->rect.top;
  CHECK(w>=32&&h>=24&&(w+pad)*(h+pad)<=300000&&n->rect.left>=0&&n->rect.right<=s->screen.right&&n->rect.top>=0&&n->rect.bottom<=s->screen.bottom-scaled(90,next));
 }
 CHECK(s->damage.count==1&&s->damage.full==1&&memcmp(&s->damage.rects[0],&s->screen,sizeof(Rect))==0);
 cancelled+=before.grab!=0;hidden++;cases++;
}
static ABI void failure(uint64_t old,uint64_t next){
 before=actual.state;CHECK(layout_rescale(&actual.state,old,next)!=0);CHECK(memcmp(&actual.state,&before,sizeof before)==0);guard();failed++;
}
int main(void){
 uint64_t sizes[3];layout_sizes(sizes);CHECK(sizes[0]==sizeof(State)&&sizes[0]==3128&&sizes[1]==sizeof(Slot)&&sizes[1]==144&&sizes[2]==sizeof(Damage)&&sizes[2]==560);
 const uint64_t scales[]={256,320,384,448,512};const unsigned screens[][2]={{800,600},{1280,720},{1920,1080},{1024,849},{1024,850},{8192,8192},{284,332}};
 for(unsigned size=0;size<sizeof screens/sizeof screens[0];size++)for(unsigned old=0;old<5;old++)for(unsigned next=0;next<5;next++)for(unsigned grab=0;grab<4;grab++){
  setup(screens[size][0],screens[size][1],grab);success(scales[old],scales[next]);
 }
 /* Repeated forward/reverse changes preserve handles and resources each time. */
 setup(1920,1080,2);uint64_t current=256;for(unsigned round=0;round<3;round++){for(unsigned i=0;i<5;i++){success(current,scales[i]);current=scales[i];}for(unsigned i=5;i>0;i--){success(current,scales[i-1]);current=scales[i-1];}}
 const uint64_t invalid_scales[]={0,255,257,319,321,383,385,447,449,511,513,UINT64_MAX};
 for(unsigned i=0;i<sizeof invalid_scales/sizeof invalid_scales[0];i++){setup(1920,1080,2);failure(invalid_scales[i],256);failure(256,invalid_scales[i]);}
 for(unsigned i=0;i<4;i++){setup(1920,1080,2);actual.state.slots[i].serial=UINT64_MAX;actual.state.slots[i].ack=UINT64_MAX;failure(256,512);}
 setup(1920,1080,2);actual.state.slots[3].generation=0;failure(256,512);
 setup(1920,1080,2);actual.state.slots[3].requested.right=1921;failure(256,512);
 setup(1920,1080,2);actual.state.order[3]=actual.state.order[0];failure(256,512);
 setup(1920,1080,2);actual.state.focus=handle(1);failure(256,512);
 setup(1920,1080,2);actual.state.mode=4;failure(256,512);
 setup(1920,1080,2);actual.state.buttons=32;failure(256,512);
 setup(1920,1080,2);actual.state.x=1920;failure(256,512);
 setup(1920,1080,2);actual.state.damage.bounds.right=1919;failure(256,512);
 setup(1920,1080,2);actual.state.damage.count=17;failure(256,512);
 setup(1920,1080,0);actual.state.slots[4].status=2;actual.state.slots[4].owner=909;actual.state.slots[4].rect=actual.state.slots[0].rect;actual.state.slots[4].requested=actual.state.slots[4].rect;actual.state.slots[4].minw=32;actual.state.slots[4].minh=24;CHECK(layout_valid(&actual.state)==0);failure(256,512);
 setup(1920,1080,0);actual.state.count=3;failure(256,512);
 setup(64,64,0);failure(256,512);setup(256,400,0);failure(256,512);setup(800,300,0);failure(256,512);
 CHECK(layout_rescale(NULL,256,512)!=0);
 printf("layout oracle passed: full-State=%u hidden=%u cancelled-grab=%u atomic-rejections=%u five-scale-pairs=25 stride-guards=ok checks=%llu\n",cases,hidden,cancelled,failed,(unsigned long long)checks);
 return 0;
}
