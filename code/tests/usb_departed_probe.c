#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct {U r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rdx,rcx,rbx,rax,rip,rflags,rsp,cr3,fs,gs,status,syscalls,exit,reserved;} Frame;
static unsigned checks,boundaries;static U last_id,last_inc;static int fail_window;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"USB departed native failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
extern ABI U ud_setup(void),ud_cap(U,U),ud_query(U,Frame*),ud_retire(U,U),ud_restart(void),ud_pending(void),ud_current(U);
extern ABI void ud_change(U,U);
ABI U ud_boundary(U kind,U id,U inc,U logical){if(kind==1){CK(logical==UINT64_MAX);boundaries++;last_id=id;last_inc=inc;return 0;}CK(kind==2||kind==3);return fail_window?1:0;}
ABI U ud_window_boundary(U kind,U id,U inc,U logical){return ud_boundary(kind,id,inc,logical);}
ABI void __dong_panic(U kind,U line,const unsigned char*file,U len){(void)kind;(void)line;(void)file;(void)len;CK(0);abort();}
static U decode_departed(U raw){if(raw){CK(raw>>32==0x55484450&&(raw&0xffffffff)>0&&(raw&0xffffffff)<=0x0fffffff);}return raw&0xffffffff;}
static Frame query(void){Frame f={0};f.rax=0x2e;f.rdi=ud_cap(4,0);return f;}
static void denied(U actor,Frame*f){U before=ud_pending();CK(ud_query(actor,f)!=0);CK(ud_pending()==before);}
int main(int argc,char**argv){CK(argc==2&&ud_setup()==0);const char*s=argv[1];
 if(!strcmp(s,"retire")){CK(!ud_pending()&&ud_current(13)==13);CK(!ud_retire(13,5));CK(ud_pending()==1&&ud_current(13)==UINT64_MAX&&boundaries==1&&last_id==13&&last_inc==1);Frame f=query();CK(!ud_query(4,&f)&&decode_departed(f.rax)==1&&!ud_pending());f=query();CK(!ud_query(4,&f)&&!f.rax);CK(ud_retire(13,5)!=0&&!ud_pending()&&boundaries==1);}
 else if(!strcmp(s,"guards")){CK(!ud_retire(13,5)&&ud_pending()==1);Frame f=query();f.rdi=ud_cap(0,1);denied(0,&f);f=query();f.rdi=ud_cap(13,1);denied(13,&f);
  U*unused[]={&f.rsi,&f.rdx,&f.r10,&f.r8,&f.r9};for(unsigned i=0;i<5;i++){f=query();*unused[i]=1;denied(4,&f);}
  for(U cap=2;cap<=5;cap++){f=query();f.rdi=ud_cap(4,cap);denied(4,&f);}f=query();f.rdi=0;denied(4,&f);
  ud_change(0,0);f=query();denied(4,&f);ud_change(0,1);ud_change(1,0);f=query();denied(4,&f);ud_change(1,1);
  ud_change(2,0);f=query();denied(4,&f);ud_change(2,1);ud_change(3,7);f=query();denied(4,&f);ud_change(3,4);
  f=query();CK(!ud_query(4,&f)&&decode_departed(f.rax)==1&&!ud_pending());}
 else if(!strcmp(s,"coalesce")){CK(!ud_retire(13,5)&&!ud_restart()&&!ud_retire(13,5));CK(ud_pending()==2&&boundaries==2&&last_inc==2);ud_change(4,7);CK(!ud_restart()&&!ud_retire(13,5)&&ud_pending()==7);Frame f=query();CK(!ud_query(4,&f)&&decode_departed(f.rax)==7&&!ud_pending());}
 else if(!strcmp(s,"identity")){CK(!ud_retire(4,5)&&!ud_pending());ud_change(7,7);CK(!ud_retire(13,5)&&!ud_pending());CK(boundaries==2);}
 else if(!strcmp(s,"preconditions")){ud_change(6,13);CK(ud_retire(13,5)!=0&&!ud_pending()&&!boundaries);ud_change(6,16);ud_change(1,0);CK(ud_retire(13,5)!=0&&!ud_pending()&&!boundaries);}
 else if(!strcmp(s,"range")){ud_change(4,0x0fffffff);Frame f=query();CK(!ud_query(4,&f)&&decode_departed(f.rax)==0x0fffffff&&!ud_pending());ud_change(4,0x10000000);f=query();denied(4,&f);CK(ud_pending()==0x10000000);}
 else if(!strcmp(s,"failed-retire")){CK(ud_retire(13,0)!=0&&!ud_pending()&&!boundaries&&ud_current(13)==13);ud_change(8,UINT64_MAX);CK(ud_retire(13,5)!=0&&!ud_pending()&&!boundaries&&ud_current(13)==13);}
 else {CK(0);}printf("USB departed native checks passed %u; scenario=%s; boundaries=%u\n",checks,s,boundaries);return 0;}
