#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fprintf(stderr,"ui oracle line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct{int64_t l,t,r,b;} Rect;
typedef struct{Rect bounds;size_t count;bool full;Rect rects[16];} Damage;
typedef struct{uint32_t bg,surface,text,muted,accent,border,shadow,selection,danger;uint64_t radius,blur,scale,duration;} Theme;
typedef struct{int64_t from,to;uint64_t start,duration;} Animation;
typedef struct{uint8_t *bytes;size_t cap,len,caret,anchor;uint64_t revision;} Text;
typedef struct{const uint8_t *bytes;size_t len;} Label;
typedef struct{uint64_t id,kind;Rect rect;uint64_t flags;int64_t value;size_t scroll;int64_t row;const Label *labels;size_t count;Text *text;Animation hover;} Control;
typedef struct{Control c[32];size_t count;uint64_t focus,hot,pressed;int64_t x,y;uint64_t duration;Rect bounds;Damage damage;} Model;
typedef struct{uint64_t kind,code;int64_t a,b;} Event;
typedef struct{uint64_t kind,id;int64_t value;uint64_t revision;} Action;
typedef struct{uint32_t *ptr;size_t len,w,h,stride;} Surface;
typedef struct{const uint8_t *ptr;size_t len,count,pixels,records,bitmap,bitmap_size;int64_t ascent,descent;} Atlas;
extern ABI void ui_sizes(uint64_t *),ui_default(Theme *);
extern ABI uint64_t ui_theme(const uint8_t *,size_t,Theme *),ui_sample(const Animation *,uint64_t,int64_t *);
extern ABI uint64_t ui_text_init(Text *,uint8_t *,size_t),ui_insert(Text *,const uint8_t *,size_t),ui_scalar(Text *,uint32_t),ui_caret(Text *,size_t,bool),ui_edit(Text *,const Event *,bool,uint64_t *);
extern ABI uint64_t ui_init(Model *,size_t,size_t,uint64_t),ui_add(Model *,const Control *),ui_input(Model *,const Event *,int64_t,int64_t,uint64_t,Action *),ui_tick(Model *,uint64_t),ui_flags(Model *,uint64_t,uint64_t),ui_damage(Model *,Damage *);
extern ABI uint64_t ui_round(Surface *,const Rect *,const Rect *,int64_t,uint32_t),ui_open_font(const uint8_t *,size_t,Atlas *),ui_draw_text(Surface *,const Atlas *,const uint8_t *,size_t,int64_t,int64_t,uint32_t,const Rect *),ui_render(Surface *,const Atlas *,const Model *,const Theme *,const Damage *,uint64_t);
ABI void __dong_panic(uint64_t k){fprintf(stderr,"ui panic %u\n",(unsigned)k);exit(99);}
ABI void ui_negative_hit(uint64_t kind){static unsigned seen;if(kind<32&&!(seen&(1u<<(unsigned)kind))){seen|=1u<<(unsigned)kind;fprintf(stderr,"UI_NEGATIVE_HIT %u\n",(unsigned)kind);}}
static unsigned themes,edits,rounds,frames,actions;
static Theme style;
static Model model,old_model;
static struct{uint64_t pre;uint8_t bytes[128];uint64_t post;} storage;
static Text text;
enum{W=64,H=48,S=69,N=S*H,TOTAL=N+16};
static uint32_t actual[TOTAL],expected[TOTAL],saved[TOTAL];
static Surface surface={actual+8,N,W,H,S};
static Rect screen={0,0,W,H};
static uint32_t cov(uint32_t color,uint8_t a){uint32_t r=0;for(unsigned s=0;s<32;s+=8)r|=((((color>>s)&255)*a+127)/255)<<s;return r;}
static uint32_t over(uint32_t d,uint32_t s){uint32_t r=0;for(unsigned b=0;b<32;b+=8){uint32_t x=((s>>b)&255)+(((d>>b)&255)*(255-(s>>24))+127)/255;if(x>255)x=255;r|=x<<b;}return r;}
static void reset_pixels(void){for(size_t i=0;i<TOTAL;i++)actual[i]=expected[i]=0xff123456u+(uint32_t)i;}
static void guards(void){for(size_t i=0;i<8;i++){CHECK(actual[i]==0xff123456u+(uint32_t)i);CHECK(actual[N+8+i]==0xff123456u+(uint32_t)(N+8+i));}for(size_t y=0;y<H;y++)for(size_t x=W;x<S;x++)CHECK(actual[8+y*S+x]==0xff123456u+(uint32_t)(8+y*S+x));}
static void theme_tests(void){
 ui_default(&style);const char *good="background=#112233\r\naccent=#4477ff\nradius=11\nshadow_size=3\nscale_q8=384\nduration_ms=250\n";CHECK(ui_theme((const uint8_t *)good,strlen(good),&style)==0);CHECK(style.bg==0xff112233&&style.radius==11&&style.scale==384&&style.duration==250);themes++;
 const char *bad[]={"scale_q8=0","scale_q8=1025","radius=33","duration_ms=1001","accent=#ffgg00","accent=#00112233","radius=2\nradius=3","what=4","radius=2 trailing","radius=2\rX","background=#80112233"};
 for(size_t i=0;i<sizeof bad/sizeof bad[0];i++){Theme old=style;CHECK(ui_theme((const uint8_t *)bad[i],strlen(bad[i]),&style)!=0);CHECK(memcmp(&old,&style,sizeof old)==0);themes++;}
 Animation a={0,256,100,100};int64_t value=-1;CHECK(ui_sample(&a,99,&value)==0&&value==0);CHECK(ui_sample(&a,150,&value)==0&&value==128);CHECK(ui_sample(&a,200,&value)==0&&value==256);a.duration=UINT64_MAX;value=-9;CHECK(ui_sample(&a,150,&value)!=0&&value==-9);ui_default(&style);
}
static void text_tests(void){
 memset(&storage,0xa5,sizeof storage);storage.pre=UINT64_C(0x1020304050607080);storage.post=UINT64_C(0x8070605040302010);CHECK(ui_text_init(&text,storage.bytes,128)==0);
 const uint8_t initial[]={65,0xe4,0xb8,0xad,0xf0,0x9f,0x98,0x80};CHECK(ui_insert(&text,initial,sizeof initial)==0&&text.len==8);edits++;
 Text old=text;uint8_t before[128];memcpy(before,storage.bytes,128);CHECK(ui_caret(&text,2,false)!=0&&memcmp(&old,&text,sizeof old)==0);CHECK(memcmp(before,storage.bytes,128)==0);
 CHECK(ui_caret(&text,4,false)==0);Event e={1,14,1,0};uint64_t handled=0;CHECK(ui_edit(&text,&e,true,&handled)==0&&handled==1);CHECK(text.len==5&&storage.bytes[0]==65&&storage.bytes[1]==0xf0);edits++;
 CHECK(ui_caret(&text,1,false)==0);e.code=111;CHECK(ui_edit(&text,&e,true,&handled)==0&&text.len==1);edits++;
 CHECK(ui_scalar(&text,0x4e2d)==0);CHECK(ui_scalar(&text,0x1f600)==0);edits+=2;CHECK(text.len==8);
 e=(Event){1,30,1,4};CHECK(ui_edit(&text,&e,true,&handled)==0&&text.anchor==0&&text.caret==8);CHECK(ui_scalar(&text,90)==0&&text.len==1&&storage.bytes[0]==90);edits++;
 old=text;memcpy(before,storage.bytes,128);const uint8_t invalid[]={65,0xed,0xa0,0x80};CHECK(ui_insert(&text,invalid,sizeof invalid)!=0);CHECK(memcmp(&old,&text,sizeof old)==0&&memcmp(before,storage.bytes,128)==0);
 CHECK(ui_insert(&text,storage.bytes,1)!=0&&memcmp(&old,&text,sizeof old)==0);uint8_t huge[128];memset(huge,'x',128);CHECK(ui_insert(&text,huge,128)!=0&&memcmp(&old,&text,sizeof old)==0&&memcmp(before,storage.bytes,128)==0);
 CHECK(storage.pre==UINT64_C(0x1020304050607080)&&storage.post==UINT64_C(0x8070605040302010));
}
static unsigned coverage(Rect r,int64_t radius,int64_t x,int64_t y){
 if(radius>(r.r-r.l)/2){radius=(r.r-r.l)/2;}if(radius>(r.b-r.t)/2){radius=(r.b-r.t)/2;}if(!radius){return 255;}
 int64_t cx=x*8+4,cy=y*8+4;if(x<r.l+radius)cx=(r.l+radius)*8;else if(x>=r.r-radius)cx=(r.r-radius)*8;if(y<r.t+radius)cy=(r.t+radius)*8;else if(y>=r.b-radius)cy=(r.b-radius)*8;
 if(cx==x*8+4||cy==y*8+4){return 255;}unsigned hits=0;for(int64_t yy=1;yy<8;yy+=2)for(int64_t xx=1;xx<8;xx+=2){int64_t dx=x*8+xx-cx,dy=y*8+yy-cy;if(dx*dx+dy*dy<=radius*radius*64)hits++;}return(hits*255+8)/16;
}
static void rounded_tests(void){
 uint32_t rng=0x74d53719;for(unsigned k=0;k<500;k++){rng=rng*1664525u+1013904223u;int64_t x=(int64_t)(rng%100)-20;rng=rng*1664525u+1013904223u;int64_t y=(int64_t)(rng%80)-20;Rect r={x,y,x+1+(int64_t)(rng%60),y+1+(int64_t)(rng%40)};int64_t radius=rng%21;uint32_t color=0x80402010;reset_pixels();CHECK(ui_round(&surface,&r,&screen,radius,color)==0);
 for(int64_t yy=0;yy<H;yy++)for(int64_t xx=0;xx<W;xx++)if(xx>=r.l&&xx<r.r&&yy>=r.t&&yy<r.b){size_t at=8+(size_t)yy*S+(size_t)xx;expected[at]=over(expected[at],cov(color,(uint8_t)coverage(r,radius,xx,yy)));}
 CHECK(memcmp(actual,expected,sizeof actual)==0);guards();rounds++;}
 Rect bad={4,4,2,8};memcpy(saved,actual,sizeof actual);CHECK(ui_round(&surface,&bad,&screen,3,~0u)!=0&&memcmp(saved,actual,sizeof actual)==0);
}
static uint8_t font[124];static Atlas atlas;
static void p16(uint8_t *p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}static void p32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static void font_init(void){memset(font,0,sizeof font);memcpy(font,"DGFONT01",8);p32(font+8,1);p32(font+12,48);p32(font+16,2);p32(font+20,14);p32(font+24,48);p32(font+28,112);p32(font+32,12);p32(font+36,3);p32(font+40,1);for(unsigned i=0;i<2;i++){uint8_t *r=font+48+32*i;p32(r,i?0xfffd:65);p16(r+4,2);p16(r+6,3);p16(r+10,2);p32(r+12,192);p32(r+16,i*6);p16(r+20,2);for(unsigned j=0;j<6;j++)font[112+i*6+j]=(uint8_t)((i*57+j*43)%256);}CHECK(ui_open_font(font,sizeof font,&atlas)==0);}
static Action input(uint64_t kind,uint64_t code,int64_t a,int64_t b,uint64_t now){Event e={kind,code,a,b};Action out;CHECK(ui_input(&model,&e,0,0,now,&out)==0);actions++;return out;}
static void dynamic_model_tests(void){
 Label labels[4]={{(const uint8_t *)"A",1},{(const uint8_t *)"AA",2},{(const uint8_t *)"A",1},{(const uint8_t *)"AAA",3}};CHECK(ui_init(&model,W,H,100)==0);Control c={.id=1,.kind=1,.rect={2,2,24,18},.flags=3,.value=-1,.row=8,.labels=labels,.count=1};CHECK(ui_add(&model,&c)==0);c=(Control){.id=2,.kind=2,.rect={26,2,62,18},.flags=3,.value=-1,.row=8,.text=&text};CHECK(ui_add(&model,&c)==0);c=(Control){.id=3,.kind=3,.rect={2,22,40,46},.flags=3,.value=-1,.row=8,.labels=labels,.count=4};CHECK(ui_add(&model,&c)==0);
 Damage d;CHECK(ui_damage(&model,&d)==0&&d.full==false&&d.count==1);reset_pixels();CHECK(ui_render(&surface,&atlas,&model,&style,&d,0)==0);guards();frames++;
 memcpy(saved,actual,sizeof actual);input(3,0,10,8,1);Action a=input(1,272,1,0,2);CHECK(model.focus==1&&model.pressed==1&&a.kind==4);CHECK(ui_damage(&model,&d)==0);CHECK(ui_render(&surface,&atlas,&model,&style,&d,2)==0);CHECK(memcmp(saved,actual,sizeof actual)!=0);guards();frames++;
 a=input(1,272,0,0,3);CHECK(a.kind==1&&a.id==1);input(3,0,10,8,4);input(1,272,1,0,5);input(3,0,-100,-100,6);a=input(1,272,0,0,7);CHECK(a.kind==0&&model.hot==0);
 input(1,15,1,0,8);CHECK(model.focus==2);input(1,15,1,1,9);CHECK(model.focus==1);input(1,15,1,0,10);a=input(16,0,0x4e2d,0,11);CHECK(a.kind==3&&a.id==2);
 input(3,0,10,40,12);a=input(1,272,1,0,13);CHECK(a.kind==2&&a.id==3&&a.value==2);input(1,272,0,0,14);input(4,0,0,-9,15);CHECK(model.c[2].scroll==1);input(1,108,1,0,16);CHECK(model.c[2].value==3&&model.c[2].scroll==1);
 CHECK(ui_flags(&model,1,1)==0);input(1,15,1,0,17);CHECK(model.focus==2);CHECK(ui_tick(&model,1000)==0);CHECK(ui_damage(&model,&d)==0);CHECK(ui_render(&surface,&atlas,&model,&style,&d,1000)==0);guards();frames++;
 // Malicious late geometry must reject before clearing even one frame byte.
 old_model=model;model.c[model.count-1].rect.r=1000;memcpy(saved,actual,sizeof actual);CHECK(ui_render(&surface,&atlas,&model,&style,&d,1000)!=0);CHECK(memcmp(saved,actual,sizeof actual)==0);model=old_model;
 // A late invalid label must likewise preserve the entire target and padding.
 const uint8_t invalid[]={0xf0,0x80,0x80,0x80};Label bad[4];memcpy(bad,labels,sizeof bad);bad[3]=(Label){invalid,sizeof invalid};model.c[2].labels=bad;memcpy(saved,actual,sizeof actual);CHECK(ui_render(&surface,&atlas,&model,&style,&d,1000)!=0);CHECK(memcmp(saved,actual,sizeof actual)==0);model=old_model;
}
int main(void){uint64_t sizes[4];ui_sizes(sizes);CHECK(sizes[0]==sizeof(Theme)&&sizes[1]==sizeof(Text)&&sizes[2]==sizeof(Control)&&sizes[3]==sizeof(Model));theme_tests();text_tests();rounded_tests();font_init();dynamic_model_tests();printf("ui oracle passed: themes=%u text_edits=%u rounded_pixel_models=%u dynamic_frames=%u routed_actions=%u full-byte-guards=ok\n",themes,edits,rounds,frames,actions);return 0;}
