/* Independent wire sequences and byte snapshots; no hardware or OS input. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fprintf(stderr,"input oracle line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct {uint64_t kind,code;int64_t a,b;} Event;
typedef struct {size_t head,count;Event items[64];} Queue;
typedef struct {uint64_t down[12],modifiers;} Keys;
typedef struct {Keys keys;uint64_t prefix;size_t pause;} Keyboard;
typedef struct {uint64_t id;size_t count;uint8_t bytes[4];uint64_t buttons;} Mouse;
typedef struct {int64_t minimum,maximum,extent;} Range;
typedef struct {Keys keys,shadow;Event pending[32];size_t count,budget;int64_t rx,ry,wx,wy,ax,ay;Range xr,yr;uint64_t flags,seen,absolute,blocked;} Virtio;
extern ABI size_t input_event_size(void),input_queue_size(void),input_keyboard_size(void),input_mouse_size(void),input_virtio_size(void);
extern ABI void input_init(Queue *,Keyboard *,Mouse *,Virtio *);
extern ABI uint64_t input_pop(Queue *,Event *,uint64_t *),input_push(Queue *,const Event *);
extern ABI uint64_t input_key(Keyboard *,Queue *,uint8_t),input_mouse_init(Mouse *,uint64_t),input_mouse(Mouse *,Queue *,uint8_t);
extern ABI uint64_t input_abs(Virtio *,int64_t,int64_t,int64_t,int64_t,int64_t,int64_t);
extern ABI uint64_t input_virtio(Virtio *,Queue *,uint16_t,uint16_t,int32_t),input_wire(Virtio *,Queue *,const uint8_t *,size_t),input_restart(Virtio *,Queue *);
ABI void __dong_panic(uint64_t kind){fprintf(stderr,"unexpected input panic %u\n",(unsigned)kind);exit(99);}
ABI void input_negative_hit(uint64_t kind){static unsigned seen;if(kind<32&&!(seen&(1u<<(unsigned)kind))){seen|=1u<<(unsigned)kind;fprintf(stderr,"INPUT_NEGATIVE_HIT %u\n",(unsigned)kind);}}
struct Guarded {uint64_t pre;Queue q;Keyboard k;Mouse m;Virtio v;uint64_t post;};
static struct Guarded g;
static unsigned key_sequences,mouse_packets,virtio_frames,snapshots;
static void guards(void){CHECK(g.pre==UINT64_C(0x13b4567813b45678)&&g.post==UINT64_C(0xfedcba98fedcba98));}
static void reset(void){memset(&g,0,sizeof g);g.pre=UINT64_C(0x13b4567813b45678);g.post=UINT64_C(0xfedcba98fedcba98);input_init(&g.q,&g.k,&g.m,&g.v);guards();}
static void empty(void){Event e,before;memset(&e,0xa5,sizeof e);before=e;uint64_t present=9;CHECK(input_pop(&g.q,&e,&present)==0&&present==0);CHECK(memcmp(&e,&before,sizeof e)==0);guards();}
static void event(uint64_t kind,uint64_t code,int64_t a,int64_t b){Event e;uint64_t present=9;CHECK(input_pop(&g.q,&e,&present)==0&&present==1);CHECK(e.kind==kind&&e.code==code&&e.a==a&&e.b==b);guards();}
static void keybytes(const uint8_t *p,size_t n){for(size_t i=0;i<n;i++){CHECK(input_key(&g.k,&g.q,p[i])==0);guards();}key_sequences++;}
static void mousebytes(uint8_t a,uint8_t b,uint8_t c,uint8_t d,unsigned n){uint8_t p[]={a,b,c,d};for(unsigned i=0;i<n;i++){CHECK(input_mouse(&g.m,&g.q,p[i])==0);guards();}mouse_packets++;}
static void vi(uint16_t type,uint16_t code,int32_t value){CHECK(input_virtio(&g.v,&g.q,type,code,value)==0);guards();}
static void syn(void){vi(0,0,0);virtio_frames++;}
static void keyboard_tests(void){
 reset();const uint8_t a[]={0x12,0x1c,0x1c,0xf0,0x1c,0x59,0xf0,0x12,0xf0,0x59};keybytes(a,sizeof a);
 event(1,42,1,1);event(1,30,1,1);event(1,30,2,1);event(1,30,0,1);event(1,54,1,3);event(1,42,0,2);event(1,54,0,0);empty();
 const uint8_t locks[]={0x58,0x58,0xf0,0x58,0x58,0xf0,0x58};keybytes(locks,sizeof locks);
 event(1,58,1,256);event(1,58,2,256);event(1,58,0,256);event(1,58,1,0);event(1,58,0,0);empty();
 const uint8_t ext[]={0xe0,0x14,0xe0,0x11,0xe0,0xf0,0x14,0xe0,0xf0,0x11,0xe0,0x75,0xe0,0xf0,0x75};keybytes(ext,sizeof ext);
 event(1,97,1,8);event(1,100,1,40);event(1,97,0,32);event(1,100,0,0);event(1,103,1,0);event(1,103,0,0);empty();
 const uint8_t pause[]={0xe1,0x14,0x77,0xe1,0xf0,0x14,0xf0,0x77};keybytes(pause,sizeof pause);event(1,119,1,0);event(1,119,0,0);CHECK(g.k.keys.modifiers==0);empty();
 const uint8_t print[]={0xe0,0x12,0xe0,0x7c,0xe0,0xf0,0x7c,0xe0,0xf0,0x12};keybytes(print,sizeof print);event(1,99,1,0);event(1,99,0,0);empty();
 const uint8_t malformed[]={0x12,0xe1,0x14,0x00};keybytes(malformed,sizeof malformed);event(5,3,0,0);CHECK(g.k.keys.modifiers==0&&g.k.pause==0&&g.k.prefix==0);empty();
 const uint8_t mismatch[]={0xe1,0x14,0x76};keybytes(mismatch,sizeof mismatch);event(5,2,0,0);empty();
 const uint8_t prefixes[]={0xe0,0xe0};keybytes(prefixes,sizeof prefixes);event(5,2,0,0);empty();
 // Check every alphabet code independently against the evdev alphabet values.
 const uint8_t scan[]={0x1c,0x32,0x21,0x23,0x24,0x2b,0x34,0x33,0x43,0x3b,0x42,0x4b,0x3a,0x31,0x44,0x4d,0x15,0x2d,0x1b,0x2c,0x3c,0x2a,0x1d,0x22,0x35,0x1a};
 const uint16_t code[]={30,48,46,32,18,33,34,35,23,36,37,38,50,49,24,25,16,19,31,20,22,47,17,45,21,44};
 for(size_t i=0;i<26;i++){uint8_t p[]={scan[i],0xf0,scan[i]};keybytes(p,sizeof p);event(1,code[i],1,0);event(1,code[i],0,0);empty();}
 reset();for(unsigned i=0;i<65;i++)CHECK(input_key(&g.k,&g.q,0x1c)==0);event(5,1,0,0);CHECK(g.k.keys.down[0]==0&&g.k.keys.modifiers==0);empty();
 reset();g.k.prefix=4;struct Guarded old=g;CHECK(input_key(&g.k,&g.q,0x1c)!=0);CHECK(memcmp(&g,&old,sizeof g)==0);snapshots++;
}
static void mouse_tests(void){
 reset();CHECK(input_mouse(&g.m,&g.q,0)==0);empty();
 // All low-byte values and both header sign bits, including 9-bit -256..255.
 for(unsigned sign=0;sign<4;sign++)for(unsigned low=0;low<256;low++){
  int64_t x=(int64_t)low-((sign&1)?256:0),y=-((int64_t)(255-low)-((sign&2)?256:0));
  mousebytes((uint8_t)(8|((sign&1)?16:0)|((sign&2)?32:0)),(uint8_t)low,(uint8_t)(255-low),0,3);
  if(x||y){event(2,0,x,y);}empty();
 }
 mousebytes(0x0b,0,0,0,3);event(1,272,1,0);event(1,273,1,0);empty();
 mousebytes(0xc9,127,127,0,3);event(5,4,0,0);event(1,272,1,0);empty();
 mousebytes(8,0,0,0,3);event(1,272,0,0);empty();
 CHECK(input_mouse_init(&g.m,3)==0);mousebytes(8,0,0,255,4);event(4,0,0,1);empty();
 mousebytes(8,0,0,127,4);event(4,0,0,-127);empty();
 CHECK(input_mouse_init(&g.m,4)==0);mousebytes(8,0,0,0x31,4);event(4,0,0,-1);event(1,275,1,0);event(1,276,1,0);empty();
 mousebytes(8,0,0,0x7f,4);event(4,0,1,0);CHECK(g.m.buttons==24);empty();
 mousebytes(8,0,0,0,4);event(1,275,0,0);event(1,276,0,0);empty();
 mousebytes(8,0,0,0xc0,4);event(5,2,0,0);empty();
 Mouse old=g.m;CHECK(input_mouse_init(&g.m,2)!=0);CHECK(memcmp(&old,&g.m,sizeof old)==0);snapshots++;
}
static void virtio_tests(void){
 reset();vi(1,42,1);vi(2,0,5);vi(2,0,-2);vi(2,1,-4);vi(1,30,1);empty();CHECK(g.v.keys.modifiers==0);syn();
 event(2,0,3,-4);event(1,42,1,1);event(1,30,1,1);empty();
 vi(1,30,2);vi(1,30,0);vi(1,42,0);vi(2,6,-1);vi(2,8,3);syn();event(4,0,-1,3);event(1,30,2,1);event(1,30,0,1);event(1,42,0,0);empty();
 CHECK(input_abs(&g.v,-100,100,0,1000,1920,1080)==0);vi(3,0,0);syn();empty();vi(3,1,1000);vi(1,272,1);syn();event(3,0,959,1079);event(1,272,1,0);empty();
 vi(3,0,INT32_MAX);vi(3,1,INT32_MIN);syn();event(3,0,1919,0);empty();
 Virtio saved=g.v;CHECK(input_abs(&g.v,0,0,0,1,100,100)!=0);CHECK(memcmp(&saved,&g.v,sizeof saved)==0);snapshots++;
 CHECK(input_abs(&g.v,INT32_MIN,INT32_MAX,INT32_MIN,INT32_MAX,1,1)==0);vi(3,0,INT32_MAX);vi(3,1,INT32_MIN);syn();event(3,0,0,0);empty();
 vi(0,3,0);event(5,5,0,0);CHECK(g.v.blocked==1&&g.v.keys.down[0]==0);vi(1,30,1);syn();empty();
 CHECK(input_restart(&g.v,&g.q)==0);event(5,3,0,0);empty();
 const uint8_t raw[]={2,0,0,0,0xfb,0xff,0xff,0xff};uint8_t raw_saved[8];memcpy(raw_saved,raw,8);
 CHECK(input_wire(&g.v,&g.q,raw,8)==0);syn();event(2,0,-5,0);empty();CHECK(memcmp(raw,raw_saved,8)==0);
 struct Guarded old=g;CHECK(input_wire(&g.v,&g.q,raw,7)!=0);CHECK(memcmp(&g,&old,sizeof g)==0);snapshots++;
 // Independent algebra of 1000 SYN frames, with signed32 extremes mixed in.
 for(unsigned frame=0;frame<1000;frame++){
  int64_t x=0,y=0;for(unsigned n=0;n<10;n++){int32_t dx=(int32_t)(frame*7919u+n*104729u)-4000000;int32_t dy=-dx-7;vi(2,0,dx);vi(2,1,dy);x+=dx;y+=dy;}
  syn();event(2,0,x,y);empty();
 }
 vi(1,30,3);event(5,2,0,0);CHECK(g.v.blocked==1);empty();CHECK(input_restart(&g.v,&g.q)==0);event(5,3,0,0);
 for(unsigned i=0;i<257;i++){vi(4,0,0);}event(5,6,0,0);CHECK(g.v.blocked==1);empty();
 CHECK(input_restart(&g.v,&g.q)==0);event(5,3,0,0);for(unsigned i=0;i<33;i++)vi(1,30,1);event(5,6,0,0);empty();
 CHECK(input_restart(&g.v,&g.q)==0);event(5,3,0,0);for(unsigned i=0;i<64;i++){Event e={1,31,1,0};CHECK(input_push(&g.q,&e)==0);}vi(2,0,1);syn();event(5,1,0,0);CHECK(g.v.blocked==1);empty();
}
int main(void){CHECK(input_event_size()==32&&input_queue_size()==sizeof(Queue)&&input_keyboard_size()==sizeof(Keyboard)&&input_mouse_size()==sizeof(Mouse)&&input_virtio_size()==sizeof(Virtio));keyboard_tests();mouse_tests();virtio_tests();guards();printf("input oracle passed: key_sequences=%u mouse_packets=%u virtio_frames=%u unchanged_snapshots=%u all-guards=ok\n",key_sequences,mouse_packets,virtio_frames,snapshots);return 0;}
