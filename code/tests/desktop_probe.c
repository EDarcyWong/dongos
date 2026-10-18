/* Window policy/lifetime oracle, independent geometry and z-order model. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fprintf(stderr,"desktop oracle line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct {int64_t left,top,right,bottom;} Rect;
typedef struct {Rect bounds;size_t count;bool full;Rect rects[16];} Damage;
typedef struct {uint64_t generation,status,owner,buffer,retired_buffer;Rect rect,requested;uint64_t serial,acknowledged;int64_t minw,minh;uint64_t flags;} Slot;
typedef struct {Slot slots[16];uint64_t order[16];size_t count;uint64_t focus,grab,mode;int64_t x,y;uint64_t buttons;int64_t sx,sy;Rect start,screen;Damage damage;} State;
typedef struct {uint64_t kind,code;int64_t a,b;} Event;
extern ABI size_t desktop_size(void),desktop_slot_size(void);
extern ABI uint64_t desktop_init(State *,size_t,size_t),desktop_validate(const State *),desktop_create(State *,uint64_t,uint64_t,const Rect *,int64_t,int64_t,uint64_t,uint64_t *);
extern ABI uint64_t desktop_raise(State *,uint64_t,uint64_t),desktop_visible(State *,uint64_t,uint64_t,bool),desktop_capture(State *,uint64_t,uint64_t,bool),desktop_close(State *,uint64_t,uint64_t);
extern ABI uint64_t desktop_disconnect(State *,uint64_t,size_t *),desktop_released(State *,uint64_t,uint64_t),desktop_reap(State *,uint64_t);
extern ABI uint64_t desktop_request(State *,uint64_t,uint64_t,int64_t,int64_t,uint64_t *),desktop_ack(State *,uint64_t,uint64_t,uint64_t,uint64_t);
extern ABI uint64_t desktop_input(State *,const Event *,uint64_t *),desktop_damage(State *,Damage *);
ABI void __dong_panic(uint64_t kind){fprintf(stderr,"unexpected desktop panic %u\n",(unsigned)kind);exit(99);}
ABI void desktop_negative_hit(uint64_t kind){static unsigned seen;if(kind<32&&!(seen&(1u<<(unsigned)kind))){seen|=1u<<(unsigned)kind;fprintf(stderr,"DESKTOP_NEGATIVE_HIT %u\n",(unsigned)kind);}}
static struct {uint64_t pre;State s;uint64_t post;} g;
static unsigned transitions,failures,model_steps;
static void valid(void){CHECK(g.pre==UINT64_C(0x1a2b3c4d5e6f7890)&&g.post==UINT64_C(0x87654321abcdef01));CHECK(desktop_validate(&g.s)==0);transitions++;}
static void init(void){memset(&g,0xa5,sizeof g);g.pre=UINT64_C(0x1a2b3c4d5e6f7890);g.post=UINT64_C(0x87654321abcdef01);CHECK(desktop_init(&g.s,640,480)==0);valid();}
static uint64_t create(uint64_t owner,uint64_t buffer,Rect rect){uint64_t h=0;CHECK(desktop_create(&g.s,owner,buffer,&rect,64,48,3,&h)==0);valid();return h;}
static uint64_t input(uint64_t kind,uint64_t code,int64_t a,int64_t b){Event e={kind,code,a,b};uint64_t target=UINT64_MAX;CHECK(desktop_input(&g.s,&e,&target)==0);valid();return target;}
static bool contains(Rect r,int64_t x,int64_t y){return x>=r.left&&x<r.right&&y>=r.top&&y<r.bottom;}
static bool damaged(Damage *d,int64_t x,int64_t y){for(size_t i=0;i<d->count;i++)if(contains(d->rects[i],x,y))return true;return false;}
#define FAIL_UNCHANGED(call) do{State before_state=g.s;CHECK((call)!=0);CHECK(memcmp(&before_state,&g.s,sizeof before_state)==0);failures++;valid();}while(0)
static void lifecycle(void){
 init();uint64_t a=create(1,11,(Rect){20,20,220,170}),b=create(2,22,(Rect){100,80,350,280});CHECK(a==257&&b==258&&g.s.focus==b);
 FAIL_UNCHANGED(desktop_raise(&g.s,9,a));FAIL_UNCHANGED(desktop_released(&g.s,a,11));
 Damage d;CHECK(desktop_damage(&g.s,&d)==0);CHECK(damaged(&d,20,20)&&damaged(&d,349,279)&&g.s.damage.count==0);valid();
 CHECK(input(3,0,50,30)==a);CHECK(input(1,272,1,0)==a);CHECK(g.s.focus==a&&g.s.mode==2&&g.s.grab==a&&g.s.order[1]==a);
 CHECK(input(3,0,640,480)==a);CHECK(g.s.x==639&&g.s.y==479);CHECK(g.s.slots[0].rect.left==440&&g.s.slots[0].rect.top==330&&g.s.slots[0].rect.right==640&&g.s.slots[0].rect.bottom==480);
 CHECK(desktop_damage(&g.s,&d)==0);CHECK(damaged(&d,20,20)&&damaged(&d,639,479));valid();CHECK(input(1,272,0,0)==a&&g.s.grab==0);CHECK(input(1,30,1,0)==a);
 input(2,0,INT64_MIN,INT64_MIN);CHECK(g.s.x==0&&g.s.y==0);input(3,0,635,475);input(1,272,1,0);CHECK(g.s.mode==3);
 input(3,0,0,0);Slot *s=&g.s.slots[0];CHECK(s->rect.right==640&&s->rect.bottom==480&&s->requested.right==504&&s->requested.bottom==378);
 uint64_t serial=s->serial;FAIL_UNCHANGED(desktop_ack(&g.s,1,a,serial-1,33));CHECK(desktop_ack(&g.s,1,a,serial,33)==0);valid();CHECK(s->buffer==33&&s->retired_buffer==11&&s->rect.right==504&&s->rect.bottom==378);
 uint64_t newer=0;CHECK(desktop_request(&g.s,1,a,100,100,&newer)==0);valid();CHECK(newer>serial);
 FAIL_UNCHANGED(desktop_ack(&g.s,1,a,newer,44));CHECK(desktop_released(&g.s,a,11)==0);valid();CHECK(desktop_ack(&g.s,1,a,newer,44)==0);valid();CHECK(s->retired_buffer==33);
 CHECK(desktop_released(&g.s,a,33)==0);valid();input(1,272,0,0);
 input(3,0,445,335);input(1,272,1,0);CHECK(g.s.grab==a);CHECK(desktop_close(&g.s,1,a)==0);valid();CHECK(g.s.grab==0&&g.s.focus==b&&s->status==2&&s->buffer==44);input(1,272,0,0);
 FAIL_UNCHANGED(desktop_reap(&g.s,a));uint64_t c=create(1,55,(Rect){0,0,100,100});CHECK((c&255)==3);
 CHECK(desktop_close(&g.s,2,b)==0);valid();CHECK(desktop_released(&g.s,b,22)==0);valid();CHECK(desktop_reap(&g.s,b)==0);valid();uint64_t next=create(2,66,(Rect){10,10,110,110});CHECK(next==514);
 FAIL_UNCHANGED(desktop_raise(&g.s,2,b));FAIL_UNCHANGED(desktop_released(&g.s,b,22));
 CHECK(desktop_visible(&g.s,2,next,false)==0);valid();CHECK(g.s.focus==c);FAIL_UNCHANGED(desktop_raise(&g.s,2,next));
 CHECK(desktop_visible(&g.s,2,next,true)==0);valid();CHECK(g.s.focus==next);FAIL_UNCHANGED(desktop_capture(&g.s,2,next,true));
 input(3,0,50,80);input(1,273,1,0);CHECK(desktop_capture(&g.s,2,next,true)==0);valid();CHECK(g.s.grab==next&&g.s.mode==1);input(3,0,600,400);CHECK(g.s.grab==next);input(5,1,0,0);CHECK(g.s.grab==0&&g.s.buttons==0);
 size_t count=99;CHECK(desktop_disconnect(&g.s,1,&count)==0&&count==1);valid();CHECK(g.s.slots[0].status==2&&g.s.slots[2].status==2);CHECK(desktop_released(&g.s,a,44)==0);valid();CHECK(desktop_reap(&g.s,a)==0);valid();
 // Reuse after release increments generation, with old requests still stale.
 uint64_t reused=create(3,77,(Rect){0,0,100,100});CHECK(reused==513);FAIL_UNCHANGED(desktop_ack(&g.s,1,a,newer,88));
 Rect bad={0,0,10,10};uint64_t out=UINT64_MAX;FAIL_UNCHANGED(desktop_create(&g.s,1,88,&bad,64,48,3,&out));CHECK(out==UINT64_MAX);
 uint64_t badserial=UINT64_MAX;FAIL_UNCHANGED(desktop_request(&g.s,3,reused,INT64_MAX,100,&badserial));CHECK(badserial==UINT64_MAX);
}
static void exhausted_generation_and_capacity(void){
 init();g.s.slots[0].generation=UINT64_C(0x00ffffffffffffff);uint64_t old=create(1,1,(Rect){0,0,100,100});CHECK(old==UINT64_C(0xffffffffffffff01));
 CHECK(desktop_close(&g.s,1,old)==0);valid();CHECK(desktop_released(&g.s,old,1)==0);valid();CHECK(desktop_reap(&g.s,old)==0);valid();CHECK(g.s.slots[0].status==3);
 uint64_t h=create(1,2,(Rect){0,0,100,100});CHECK((h&255)==2);FAIL_UNCHANGED(desktop_raise(&g.s,1,old));
 init();for(unsigned i=0;i<16;i++){uint64_t v=create(1,100+i,(Rect){0,0,100,100});CHECK(v==257+i);}
 Rect r={0,0,100,100};uint64_t out=123;FAIL_UNCHANGED(desktop_create(&g.s,1,999,&r,64,48,3,&out));CHECK(out==123);
 size_t count=0;CHECK(desktop_disconnect(&g.s,1,&count)==0&&count==16);valid();CHECK(g.s.count==0&&g.s.focus==0&&g.s.grab==0);
 for(unsigned i=0;i<16;i++){CHECK(g.s.slots[i].status==2&&g.s.slots[i].buffer==100+i);CHECK(desktop_released(&g.s,257+i,100+i)==0);valid();CHECK(desktop_reap(&g.s,257+i)==0);valid();}
 CHECK(g.s.slots[0].generation==2);
}
static void pending_resize_damage_and_ack_during_drag(void){
 init();uint64_t h=create(1,111,(Rect){20,20,120,100}),serial=0;Damage d;
 CHECK(desktop_request(&g.s,1,h,200,160,&serial)==0);valid();CHECK(desktop_damage(&g.s,&d)==0);valid();
 CHECK(desktop_visible(&g.s,1,h,false)==0);valid();CHECK(desktop_damage(&g.s,&d)==0);CHECK(damaged(&d,219,179));valid();
 CHECK(desktop_visible(&g.s,1,h,true)==0);valid();CHECK(desktop_damage(&g.s,&d)==0);valid();
 CHECK(desktop_close(&g.s,1,h)==0);valid();CHECK(desktop_damage(&g.s,&d)==0);CHECK(damaged(&d,219,179));valid();
 init();h=create(1,112,(Rect){20,20,220,120});CHECK(desktop_request(&g.s,1,h,300,200,&serial)==0);valid();
 input(3,0,50,30);input(1,272,1,0);CHECK(g.s.mode==2);CHECK(desktop_ack(&g.s,1,h,serial,113)==0);valid();
 input(3,0,100,40);CHECK(g.s.slots[0].rect.left==70&&g.s.slots[0].rect.top==30&&g.s.slots[0].rect.right==370&&g.s.slots[0].rect.bottom==230);input(1,272,0,0);
}
static void focus_hit_model(void){
 init();Rect rects[16];unsigned order[16];for(unsigned i=0;i<16;i++){int64_t x=(i%4)*120,y=(i/4)*90;rects[i]=(Rect){x,y,x+160,y+120};order[i]=i;CHECK(create(1,1000+i,rects[i])==257+i);}
 uint32_t rng=0x42b7d913;for(unsigned step=0;step<3000;step++){
  rng=rng*1664525u+1013904223u;int64_t x=rng%640;rng=rng*1664525u+1013904223u;int64_t y=rng%480;unsigned chosen=16,pos=0;
  for(unsigned n=16;n;n--){if(contains(rects[order[n-1]],x,y)){chosen=order[n-1];pos=n-1;break;}}
  uint64_t expected=chosen==16?0:257+chosen;CHECK(input(3,0,x,y)==expected);CHECK(input(1,272,1,0)==expected);
  if(chosen!=16){for(unsigned j=pos;j<15;j++)order[j]=order[j+1];order[15]=chosen;}
  CHECK(g.s.focus==expected);for(unsigned j=0;j<16;j++)CHECK(g.s.order[j]==257+order[j]);
  CHECK(input(1,272,0,0)==expected);CHECK(g.s.grab==0);for(unsigned j=0;j<16;j++)CHECK(memcmp(&g.s.slots[j].rect,&rects[j],sizeof(Rect))==0);model_steps++;
 }
}
int main(void){CHECK(desktop_size()==sizeof(State)&&desktop_slot_size()==sizeof(Slot));lifecycle();exhausted_generation_and_capacity();pending_resize_damage_and_ack_during_drag();focus_hit_model();valid();printf("desktop oracle passed: transitions=%u failures_unchanged=%u independent_focus_steps=%u guards-lifetimes=ok\n",transitions,failures,model_steps);return 0;}
