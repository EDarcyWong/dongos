#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
typedef struct {
 uint64_t r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rdx,rcx,rbx,rax;
 uint64_t rip,rflags,rsp,cr3,fs_base,gs_base,status,syscalls,exit_code,reserved;
} Frame;
extern uint64_t SYSV user_validate_frame(const Frame*),user_frame_size(void);
extern uint64_t SYSV user_validate_interrupt_frame(const Frame*);
extern void SYSV user_probe_offsets(uint64_t*),user_probe_capture(const Frame*,Frame*);
extern uint64_t SYSV user_copy_from(void*,const void*,uint64_t),user_copy_to(void*,const void*,uint64_t);
extern uint64_t user_copy_active,user_copy_source,user_copy_destination,user_copy_length,user_copy_direction;
void* SYSV dong_user_dispatch(Frame*frame){(void)frame;return NULL;}
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"user context check failed line %u\n",__LINE__);return 1;}}while(0)
static uint64_t rng=0xe57c3104ab9846d2ULL;
static uint64_t random64(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static unsigned reference(const Frame*f){
 const uint64_t top=UINT64_C(0x8000000000),allowed=0xad7;
 return f->rip>=0x10000&&f->rip<top&&f->rsp>=0x10000&&f->rsp<top&&(f->rflags&2)&&!(f->rflags&~allowed)
   &&f->cr3&&f->cr3<UINT64_C(0x100000000)&&!(f->cr3&4095)&&!f->fs_base&&!f->gs_base&&!f->reserved;
}
int main(void){
 struct{uint64_t lo;Frame f;uint64_t hi;} input={0},output={0};Frame before;
 input.lo=0x123456789abcdef0ULL;input.hi=~input.lo;output.lo=input.lo;output.hi=input.hi;
 Frame good={0};good.rip=0x40000000;good.rsp=0x40003000;good.rflags=0x202;good.cr3=0x400000;
 input.f=good;CHECK(user_frame_size()==200&&sizeof(Frame)==200&&user_validate_frame(&input.f)==1);
 CHECK(user_validate_frame(NULL)==0&&user_validate_frame((Frame*)((char*)&input.f+1))==0);
 CHECK(user_validate_interrupt_frame(NULL)==0&&user_validate_interrupt_frame((Frame*)((char*)&input.f+1))==0);
 for(unsigned bit=0;bit<64;bit++){
  input.f=good;input.f.rflags|=UINT64_C(1)<<bit;before=input.f;
  unsigned expected=!(input.f.rflags&~UINT64_C(0x10ed7));
  CHECK(user_validate_interrupt_frame(&input.f)==expected&&!memcmp(&before,&input.f,sizeof before));
 }
 input.f=good;input.f.rflags=0x10616;before=input.f;
 CHECK(user_validate_interrupt_frame(&input.f)==1&&user_validate_frame(&input.f)==0&&!memcmp(&before,&input.f,sizeof before));
 uint64_t offsets[27];user_probe_offsets(offsets);
#define FIELD(name) CHECK(offsets[offsetof(Frame,name)/8]==offsetof(Frame,name))
 FIELD(r15);FIELD(r14);FIELD(r13);FIELD(r12);FIELD(r11);FIELD(r10);FIELD(r9);FIELD(r8);
 FIELD(rdi);FIELD(rsi);FIELD(rbp);FIELD(rdx);FIELD(rcx);FIELD(rbx);FIELD(rax);
 FIELD(rip);FIELD(rflags);FIELD(rsp);FIELD(cr3);FIELD(fs_base);FIELD(gs_base);
 FIELD(status);FIELD(syscalls);FIELD(exit_code);FIELD(reserved);CHECK(offsets[25]==200&&offsets[26]==64);
 const uint64_t addresses[]={0,1,0xffff,0x10000,0x7fffffffffULL,0x8000000000ULL,0x7fffffffffffULL,0x800000000000ULL,0xffff800000000000ULL,UINT64_MAX};
 for(unsigned i=0;i<sizeof addresses/sizeof addresses[0];i++){
  input.f=good;input.f.rip=addresses[i];before=input.f;CHECK(user_validate_frame(&input.f)==reference(&input.f)&&!memcmp(&before,&input.f,sizeof before));
  input.f=good;input.f.rsp=addresses[i];before=input.f;CHECK(user_validate_frame(&input.f)==reference(&input.f)&&!memcmp(&before,&input.f,sizeof before));
 }
 for(unsigned bit=0;bit<64;bit++){
  input.f=good;input.f.rflags|=UINT64_C(1)<<bit;before=input.f;
  CHECK(user_validate_frame(&input.f)==reference(&input.f)&&!memcmp(&before,&input.f,sizeof before));
 }
 input.f=good;input.f.rflags=0;CHECK(user_validate_frame(&input.f)==0);
 const uint64_t roots[]={0,1,4095,4096,0xfffff000ULL,0x100000000ULL,UINT64_MAX};
 for(unsigned i=0;i<sizeof roots/sizeof roots[0];i++){input.f=good;input.f.cr3=roots[i];CHECK(user_validate_frame(&input.f)==reference(&input.f));}
 input.f=good;input.f.fs_base=1;CHECK(user_validate_frame(&input.f)==0);
 input.f=good;input.f.gs_base=1;CHECK(user_validate_frame(&input.f)==0);
 input.f=good;input.f.reserved=1;CHECK(user_validate_frame(&input.f)==0);
 for(unsigned i=0;i<4096;i++){
  input.f=good;uint64_t*p=(uint64_t*)&input.f;for(unsigned j=0;j<15;j++)p[j]=random64();
  input.f.status=random64();input.f.syscalls=random64();input.f.exit_code=random64();
  input.f.rip=(random64()%0x7ffffeffffULL)+0x10000;input.f.rsp=(random64()%0x7ffffeffffULL)+0x10000;
  input.f.rflags=(random64()&0xad7)|2;input.f.cr3=((random64()%0xfffff)+1)*4096;
  before=input.f;CHECK(user_validate_frame(&input.f)==1&&!memcmp(&before,&input.f,sizeof before));
  memset(&output.f,0xa5,sizeof output.f);user_probe_capture(&input.f,&output.f);
  CHECK(!memcmp(&input.f,&output.f,15*8));
  const uint8_t*q=(const uint8_t*)&output.f;for(unsigned j=15*8;j<sizeof(Frame);j++)CHECK(q[j]==0xa5);
 }
 uint8_t src[96],dst[96],src_before[96];for(unsigned i=0;i<96;i++)src[i]=(uint8_t)(i*7+9);memcpy(src_before,src,96);
 for(unsigned n=0;n<=64;n++){
  memset(dst,0xa5,96);CHECK(user_copy_from(dst+16,src+16,n)==0&&user_copy_active==0&&user_copy_direction==1);
  CHECK(user_copy_source==(uint64_t)(uintptr_t)(src+16)&&user_copy_destination==(uint64_t)(uintptr_t)(dst+16)&&user_copy_length==n);
  for(unsigned i=0;i<96;i++)CHECK(dst[i]==(i>=16&&i<16+n?src[i]:0xa5));
  memset(dst,0xa5,96);CHECK(user_copy_to(dst+16,src+16,n)==0&&user_copy_direction==2&&user_copy_active==0);
  for(unsigned i=0;i<96;i++)CHECK(dst[i]==(i>=16&&i<16+n?src[i]:0xa5));
 }
 user_copy_active=1;memset(dst,0xa5,96);CHECK(user_copy_from(dst,src,64)==0x04050002ULL&&user_copy_active==1);user_copy_active=0;
 CHECK(!memcmp(src,src_before,96));CHECK(input.lo==0x123456789abcdef0ULL&&input.hi==~input.lo&&output.lo==input.lo&&output.hi==input.hi);
 printf("user context native checks passed %u\n",checks);return 0;
}
