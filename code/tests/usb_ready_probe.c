#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct {U r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rdx,rcx,rbx,rax,rip,rflags,rsp,cr3,fs,gs,status,syscalls,exit,reserved;} Frame;
static unsigned checks;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"USB_READY_ASSERT line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
extern ABI U ud_setup(void),ud_cap(U,U),ud_query(U,Frame*),ud_retire(U,U),ud_restart(void),ud_pending(void);
extern ABI void ud_change(U,U),ur_change(U,U);
ABI U ud_boundary(U kind,U id,U inc,U logical){CK(kind==1&&id==13&&inc>0&&logical==UINT64_MAX);return 0;}
ABI void __dong_panic(U kind,U line,const unsigned char*file,U len){(void)kind;(void)line;(void)file;(void)len;CK(0);abort();}
static Frame query(void){Frame f={0};f.rax=0x2f;f.rdi=ud_cap(4,0);return f;}
static U read_ready(void){Frame f=query();CK(ud_query(4,&f)==0);if(f.rax){CK(f.rax>>32==0x55485244&&(f.rax&0xffffffff)>0&&(f.rax&0xffffffff)<=0x0fffffff);}return f.rax&0xffffffff;}
static void denied(U actor,Frame*f){U before=ud_pending(),sentinel=f->rax;CK(ud_query(actor,f)!=0);CK(ud_pending()==before&&f->rax==sentinel);}
int main(int argc,char**argv){CK(argc==2&&ud_setup()==0);const char*s=argv[1];
 if(!strcmp(s,"ready")){CK(read_ready()==1&&read_ready()==1);ud_change(4,9);CK(read_ready()==1&&ud_pending()==9);CK(!ud_retire(13,5));CK(!read_ready());}
 else if(!strcmp(s,"guards")){Frame f=query();f.rdi=ud_cap(13,1);denied(13,&f);f=query();f.rdi=ud_cap(0,1);denied(0,&f);
  for(unsigned i=0;i<5;i++){f=query();U*unused[]={&f.rsi,&f.rdx,&f.r10,&f.r8,&f.r9};*unused[i]=1;denied(4,&f);}
  for(U cap=2;cap<=5;cap++){f=query();f.rdi=ud_cap(4,cap);denied(4,&f);}f=query();f.rdi=0;denied(4,&f);
  ud_change(0,0);f=query();denied(4,&f);ud_change(0,1);ud_change(1,0);f=query();denied(4,&f);ud_change(1,1);
  ud_change(2,0);f=query();denied(4,&f);ud_change(2,1);ud_change(3,7);f=query();denied(4,&f);ud_change(3,4);CK(read_ready()==1);
 }
 else if(!strcmp(s,"driver")){ur_change(0,0);CK(!read_ready());ur_change(0,1);ur_change(1,1);CK(!read_ready());ur_change(1,2);CK(read_ready()==1);
  ud_change(7,7);CK(!read_ready());ud_change(7,13);CK(read_ready()==1);ur_change(3,0);Frame f=query();denied(4,&f);ur_change(3,1);
  CK(!ud_retire(13,5)&&!read_ready());
 }
 else if(!strcmp(s,"incarnation")){CK(!ud_retire(13,5)&&!read_ready());CK(!ud_restart()&&read_ready()==2);ur_change(2,0x0fffffff);CK(read_ready()==0x0fffffff);
  ur_change(2,0);Frame f=query();denied(4,&f);ur_change(2,0x10000000);f=query();denied(4,&f);
 }
 else if(!strcmp(s,"call-cap")){Frame f=query();f.rdi=ud_cap(4,2);denied(4,&f);}
 else{CK(0);}printf("USB_READY_NATIVE_PASS checks=%u scenario=%s\n",checks,s);return 0;
}
