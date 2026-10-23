/* Independent RAM oracle for actual source-extracted production rendering.
 * This process executes no CR/MSR/port/interrupt entry and is not a VM test. */
#ifndef _WIN32
#define _GNU_SOURCE
#endif
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
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
#define CLOSED (UINT64_C(1)<<63)
#define CLOSING (UINT64_C(1)<<62)
#define SENTINEL UINT32_C(0xa5a5a5a5)
#define WHITE UINT32_C(0x00f4f4f4)

typedef struct { U word,epoch,drained,opened; } Gate;
/* Independently stated public display and fatal exception ABIs. */
typedef struct { U framebuffer_base,framebuffer_size,width,height,stride,pixel_format; } Display;
typedef struct {
 U cr2,r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rdx,rcx,rbx,rax;
 U vector,error,rip,cs,rflags,rsp,ss;
} Raw;
_Static_assert(sizeof(Gate)==32,"Gate size");
_Static_assert(offsetof(Gate,word)==0&&offsetof(Gate,epoch)==8&&
               offsetof(Gate,drained)==16&&offsetof(Gate,opened)==24,"Gate offsets");
_Static_assert(sizeof(Display)==48,"RuntimeDisplay size");
_Static_assert(offsetof(Display,pixel_format)==40,"RuntimeDisplay pixel format");
_Static_assert(sizeof(Raw)==184&&offsetof(Raw,vector)==128&&offsetof(Raw,rip)==144,
               "ExceptionContext ABI");

extern U DG probe_screen_draw(const Display*),probe_panic_screen(const Raw*,const Display*);
extern Gate *DG probe_gate_get(void),*DG probe_gate_storage(void);
extern U DG probe_gate_storage_size(void),probe_gate_enter(void),probe_gate_leave(void);
extern U DG runtime_cache_gate_close(Gate*,U),runtime_cache_gate_drain(Gate*,U),runtime_cache_gate_open(Gate*,U);
extern U probe_abi_failures;
U panic_saved_frames[16];
U panic_saved_frame_count;

typedef struct { unsigned char *allocation,*bytes,*before; size_t size; } Guard;
static Guard fb;
static Gate *gate;
static Display display;
static Raw context;
static U checks;
static const char *where="setup";
static int fail(const char *why,int line){
 fprintf(stderr,"framebuffer gate oracle case=%s check=%s line=%d; returned normally\n",where,why,line);
 return 1;
}
#define REQUIRE(x) do { ++checks; if(!(x)){return fail(#x,__LINE__);} } while(0)
static int allocate_fb(void){
 fb.size=(size_t)672*480*4;
 fb.allocation=malloc(fb.size+191);
 fb.before=malloc(fb.size);
 if(!fb.allocation||!fb.before){return 0;}
 uintptr_t p=((uintptr_t)fb.allocation+127)&~(uintptr_t)63;
 fb.bytes=(unsigned char*)p;
 memset(fb.bytes-64,0x3c,64);memset(fb.bytes+fb.size,0xc3,64);
 display=(Display){(U)(uintptr_t)fb.bytes,(U)fb.size,640,480,672,0};
 return 1;
}
static void reset_pixels(void){memset(fb.bytes,0xa5,fb.size);}
static void snapshot_pixels(void){memcpy(fb.before,fb.bytes,fb.size);}
static int boundary_ok(void){
 for(size_t i=0;i<64;i++){
  if(fb.bytes[(ptrdiff_t)i-64]!=0x3c||fb.bytes[fb.size+i]!=0xc3){return 0;}
 }
 return 1;
}
static int pixels_unchanged(void){return !memcmp(fb.before,fb.bytes,fb.size)&&boundary_ok();}
static int metadata_equal(const Gate *before){
 return gate->epoch==before->epoch&&gate->drained==before->drained&&gate->opened==before->opened;
}
static void initial_gate(U word){
 *gate=(Gate){word,UINT64_C(0x1122334455667788),UINT64_C(0x2233445566778899),UINT64_C(0x33445566778899aa)};
}
static uint32_t pixel(unsigned x,unsigned y){
 uint32_t value;memcpy(&value,fb.bytes+((size_t)y*672+x)*4,4);return value;
}
static int fill_and_padding(uint32_t background){
 if(!boundary_ok()){return 0;}
 for(unsigned y=0;y<480;y++){
  if(pixel(0,y)!=background||pixel(639,y)!=background){return 0;}
  for(unsigned x=640;x<672;x++){if(pixel(x,y)!=SENTINEL){return 0;}}
 }
 for(unsigned x=0;x<640;x++){
  if(pixel(x,0)!=background||pixel(x,479)!=background){return 0;}
 }
 return 1;
}
/* The oracle describes glyph pixels directly; it never reads production
 * glyphs, invokes text_draw itself, or asks production code for expectations. */
static int glyph(unsigned x,unsigned y,const unsigned char rows[7],uint32_t background){
 for(unsigned row=0;row<7;row++){
  for(unsigned col=0;col<5;col++){
   uint32_t expected=(rows[row]&(1u<<(4-col)))?WHITE:background;
   for(unsigned dy=0;dy<2;dy++){for(unsigned dx=0;dx<2;dx++){
    if(pixel(x+2*col+dx,y+2*row+dy)!=expected){return 0;}
   }}
  }
  for(unsigned col=10;col<14;col++){
   if(pixel(x+col,y+2*row)!=background||pixel(x+col,y+2*row+1)!=background){return 0;}
  }
 }
 return 1;
}
static const unsigned char letter_d[7]={30,17,17,17,17,17,30};
static const unsigned char letter_o[7]={14,17,17,17,17,17,14};
static const unsigned char hex_rows[16][7]={
 {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},{30,1,1,14,1,1,30},
 {2,6,10,18,31,2,2},{31,16,16,30,1,1,30},{14,16,16,30,17,17,14},{31,1,2,4,8,8,8},
 {14,17,17,14,17,17,14},{14,17,17,15,1,1,14},{14,17,17,31,17,17,17},{30,17,17,30,17,17,30},
 {14,17,16,16,16,17,14},{30,17,17,17,17,17,30},{31,16,16,30,16,16,31},{31,16,16,30,16,16,16}
};
static int hex_pixels(unsigned x,unsigned y,U value,uint32_t background){
 for(unsigned i=0;i<16;i++){
  unsigned digit=(unsigned)((value>>(60-4*i))&15);
  if(!glyph(x+14*i,y,hex_rows[digit],background)){return 0;}
 }
 return 1;
}
static int gate_abi_and_helpers(void){
 where="gate-fixed-abi";
 gate=probe_gate_get();
 REQUIRE(gate!=NULL&&gate==probe_gate_storage()&&probe_gate_get()==gate);
 REQUIRE(((uintptr_t)gate&63)==0&&probe_gate_storage_size()==32);
 REQUIRE(gate->word==0&&gate->epoch==0&&gate->drained==0&&gate->opened==0);
 static const U denied[]={CLOSED,CLOSING,CLOSED|CLOSING,UINT64_C(1)<<32,
                         UINT64_C(1)<<61,UINT64_C(0xffffffff),CLOSED|7,CLOSING|9};
 for(size_t i=0;i<sizeof(denied)/sizeof(denied[0]);i++){
  where="helper-enter-denied";initial_gate(denied[i]);Gate before=*gate;
  REQUIRE(probe_gate_enter()==0);REQUIRE(!memcmp(gate,&before,sizeof(before)));
 }
 static const U accepted[]={0,1,UINT64_C(0xfffffffe)};
 for(size_t i=0;i<sizeof(accepted)/sizeof(accepted[0]);i++){
  where="helper-enter-leave";initial_gate(accepted[i]);Gate before=*gate;
  REQUIRE(probe_gate_enter()==1);REQUIRE(gate->word==before.word+1&&metadata_equal(&before));
  REQUIRE(probe_gate_leave()==1);REQUIRE(!memcmp(gate,&before,sizeof(before)));
 }
 static const U leaving[]={1,7,CLOSED|1,CLOSING|1,CLOSED|CLOSING|3};
 for(size_t i=0;i<sizeof(leaving)/sizeof(leaving[0]);i++){
  where="helper-leave-closed";initial_gate(leaving[i]);Gate before=*gate;
  REQUIRE(probe_gate_leave()==1);REQUIRE(gate->word==before.word-1&&metadata_equal(&before));
 }
 static const U not_leaving[]={0,CLOSED,CLOSING,CLOSED|CLOSING,(UINT64_C(1)<<32)|1};
 for(size_t i=0;i<sizeof(not_leaving)/sizeof(not_leaving[0]);i++){
  where="helper-leave-denied";initial_gate(not_leaving[i]);Gate before=*gate;
  REQUIRE(probe_gate_leave()==0);REQUIRE(!memcmp(gate,&before,sizeof(before)));
 }
 REQUIRE(probe_abi_failures==0);return 0;
}
static int denied_ram(void){
 static const U words[]={CLOSED,CLOSING,CLOSED|CLOSING,(UINT64_C(1)<<32),UINT64_C(0xffffffff)};
 for(size_t i=0;i<sizeof(words)/sizeof(words[0]);i++){
  where="screen-denied-ram";reset_pixels();snapshot_pixels();initial_gate(words[i]);Gate before=*gate;
  REQUIRE(probe_screen_draw(&display)==0);
  REQUIRE(pixels_unchanged()&&!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
  where="panic-denied-ram";
  (void)probe_panic_screen(&context,&display);
  REQUIRE(pixels_unchanged()&&!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
 }
 return 0;
}
static int normal_rendering(void){
 for(U format=0;format<2;format++){
  for(U active=0;active<2;active++){
   display.pixel_format=format;reset_pixels();initial_gate(active);Gate before=*gate;
   where=active?"screen-nested-writer":"screen-normal";
   REQUIRE(probe_screen_draw(&display)==1);
   REQUIRE(!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
   uint32_t background=format?UINT32_C(0x0020141b):UINT32_C(0x001b1420);
   REQUIRE(fill_and_padding(background));
   REQUIRE(glyph(56,48,letter_d,background)&&glyph(70,48,letter_o,background));
   where=active?"panic-nested-writer":"panic-normal";
   reset_pixels();(void)probe_panic_screen(&context,&display);
   REQUIRE(!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
   background=format?UINT32_C(0x00601818):UINT32_C(0x00181860);
   REQUIRE(fill_and_padding(background));
   REQUIRE(glyph(16,30,letter_d,background)&&glyph(30,30,letter_o,background));
   REQUIRE(hex_pixels(72,70,context.vector,background));
   REQUIRE(hex_pixels(392,94,context.rsp,background));
   REQUIRE(hex_pixels(392,142,panic_saved_frame_count,background));
   REQUIRE(hex_pixels(72,374,panic_saved_frames[0],background));
   REQUIRE(hex_pixels(72,394,panic_saved_frames[1],background));
  }
 }
 display.pixel_format=0;return 0;
}
static int invalid_geometry(void){
 Display baseline=display;
 for(unsigned which=0;which<12;which++){
  Display bad=baseline;
  switch(which){
   case 0:bad.pixel_format=2;break;case 1:bad.width=639;break;
   case 2:bad.width=8193;break;case 3:bad.height=479;break;
   case 4:bad.height=8193;break;case 5:bad.stride=639;break;
   case 6:bad.stride=16385;break;case 7:bad.framebuffer_size--;break;
   case 8:bad.framebuffer_base=0;break;case 9:bad.width=UINT64_MAX;break;
   case 10:bad.height=UINT64_MAX;break;default:bad.stride=UINT64_MAX;break;
  }
  where="screen-invalid-geometry";reset_pixels();snapshot_pixels();initial_gate(1);Gate before=*gate;
  REQUIRE(probe_screen_draw(&bad)==0);
  REQUIRE(pixels_unchanged()&&!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
  where="panic-invalid-geometry";(void)probe_panic_screen(&context,&bad);
  REQUIRE(pixels_unchanged()&&!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
 }
 where="panic-null-display";initial_gate(1);Gate before=*gate;
 (void)probe_panic_screen(&context,NULL);
 REQUIRE(!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
 return 0;
}
static int close_drain_open(void){
 where="actual-cache-close-with-writer";*gate=(Gate){0,0,0,0};
 REQUIRE(probe_gate_enter()==1&&gate->word==1);
 REQUIRE(runtime_cache_gate_close(gate,1)==1);
 REQUIRE(gate->word==(CLOSED|1)&&gate->epoch==1&&gate->drained==0&&gate->opened==0);
 REQUIRE(runtime_cache_gate_drain(gate,1)==0&&runtime_cache_gate_open(gate,1)==0);
 reset_pixels();snapshot_pixels();Gate before=*gate;
 REQUIRE(probe_screen_draw(&display)==0);(void)probe_panic_screen(&context,&display);
 REQUIRE(pixels_unchanged()&&!memcmp(gate,&before,sizeof(before)));
 REQUIRE(probe_gate_leave()==1&&gate->word==CLOSED&&metadata_equal(&before));
 REQUIRE(runtime_cache_gate_drain(gate,1)==1);
 REQUIRE(runtime_cache_gate_open(gate,1)==1);
 REQUIRE(gate->word==0&&gate->epoch==1&&gate->drained==1&&gate->opened==1);
 where="actual-cache-reopened-render";before=*gate;reset_pixels();
 REQUIRE(probe_screen_draw(&display)==1&&!memcmp(gate,&before,sizeof(before)));
 REQUIRE(fill_and_padding(UINT32_C(0x001b1420))&&probe_abi_failures==0);
 REQUIRE(runtime_cache_gate_close(gate,2)==1&&runtime_cache_gate_drain(gate,2)==1);
 REQUIRE(runtime_cache_gate_open(gate,1)==0&&gate->word==CLOSED);
 REQUIRE(runtime_cache_gate_open(gate,2)==1);
 REQUIRE(gate->word==0&&gate->epoch==2&&gate->drained==2&&gate->opened==2);
 return 0;
}
static void *noaccess_page(size_t *bytes){
#ifdef _WIN32
 SYSTEM_INFO info;GetSystemInfo(&info);*bytes=(size_t)info.dwPageSize;
 return VirtualAlloc(NULL,*bytes,MEM_COMMIT|MEM_RESERVE,PAGE_NOACCESS);
#else
 long page=sysconf(_SC_PAGESIZE);if(page<=0){return NULL;}*bytes=(size_t)page;
 void *p=mmap(NULL,*bytes,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 return p==MAP_FAILED?NULL:p;
#endif
}
static void free_noaccess(void *p,size_t bytes){
#ifdef _WIN32
 (void)bytes;(void)VirtualFree(p,0,MEM_RELEASE);
#else
 (void)munmap(p,bytes);
#endif
}
static int denied_noaccess(void){
 size_t bytes=0;void *unreadable=noaccess_page(&bytes);
 where="noaccess-allocation";REQUIRE(unreadable!=NULL&&bytes>=sizeof(Display));
 Display inaccessible_fb=display;inaccessible_fb.framebuffer_base=(U)(uintptr_t)unreadable;
 static const U words[]={CLOSED,CLOSING,CLOSED|CLOSING,UINT64_C(1)<<32,UINT64_C(0xffffffff)};
 for(size_t i=0;i<sizeof(words)/sizeof(words[0]);i++){
  initial_gate(words[i]);Gate before=*gate;
  where="screen-noaccess-framebuffer";REQUIRE(probe_screen_draw(&inaccessible_fb)==0);
  where="panic-noaccess-framebuffer";(void)probe_panic_screen(&context,&inaccessible_fb);
  REQUIRE(!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
  where="screen-noaccess-display";REQUIRE(probe_screen_draw((const Display*)unreadable)==0);
  where="panic-noaccess-display";(void)probe_panic_screen((const Raw*)unreadable,(const Display*)unreadable);
  REQUIRE(!memcmp(gate,&before,sizeof(before))&&probe_abi_failures==0);
 }
 free_noaccess(unreadable,bytes);return 0;
}
int main(void){
 if(!allocate_fb()){fprintf(stderr,"framebuffer gate host allocation failed\n");return 97;}
 memset(&context,0,sizeof(context));
 context.vector=UINT64_C(0x0123456789abcdef);context.rsp=UINT64_C(0x13579bdf02468ace);
 context.rip=UINT64_C(0xffff800012345678);context.cs=8;context.rflags=2;
 panic_saved_frames[0]=UINT64_C(0xfedcba9876543210);
 panic_saved_frames[1]=UINT64_C(0xa5a50f0f12345678);panic_saved_frame_count=2;
 /* Keep all mutant-sensitive writable RAM oracles ahead of NOACCESS probes.
  * A crash is never an accepted negative result; ordinary mutants return 1. */
 if(gate_abi_and_helpers()||denied_ram()||normal_rendering()||invalid_geometry()||
    close_drain_open()||denied_noaccess()){return 1;}
 where="final-abi";REQUIRE(probe_abi_failures==0&&boundary_ok());
 free(fb.before);free(fb.allocation);
 printf("framebuffer gate production renderers passed checks=%llu; privileged entry and actual guest not executed\n",
        (unsigned long long)checks);
 return 0;
}
