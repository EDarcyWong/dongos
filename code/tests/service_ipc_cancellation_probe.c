#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(__x86_64__) && defined(_WIN32)
#define ABI __attribute__((sysv_abi))
#else
#define ABI
#endif
typedef struct {uint64_t reg[15],rip,rflags,rsp,cr3,fs,gs,status,calls,exit_code,reserved;} Frame;
extern uint64_t ABI fixture_initialize(void);
extern void ABI fixture_waiting(uint64_t,uint64_t);
extern uint64_t ABI fixture_perform(uint64_t,Frame*,uint64_t*);
extern uint64_t ABI fixture_retire(uint64_t);
extern uint64_t ABI fixture_get(uint64_t,uint64_t);
void ABI __dong_panic(uint64_t code){fprintf(stderr,"unexpected Dong panic %x\n",(unsigned)code);exit(2);}
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"service IPC oracle failed line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static uint64_t request[8]={0x11223344},response[8]={0x88776655},receive_a[8],receive_b[8],receive_block[8],answer[8];
static uint64_t invoke(uint64_t actor,uint64_t code,uint64_t ep,uint64_t ticket,uint64_t* out,uint64_t* next){
 Frame f;memset(&f,0,sizeof(f));f.reg[14]=code;f.reg[8]=ep+1;
 if(code==0x22){f.reg[9]=(uint64_t)(uintptr_t)request;f.reg[11]=(uint64_t)(uintptr_t)out;}
 else if(code==0x23)f.reg[9]=(uint64_t)(uintptr_t)out;
 else{f.reg[9]=ticket;f.reg[11]=(uint64_t)(uintptr_t)response;f.reg[5]=(uint64_t)(uintptr_t)out;}
 return fixture_perform(actor,&f,next);
}
static int nested(void){
 uint64_t next=99;CHECK(fixture_initialize()==0);fixture_waiting(1,2);fixture_waiting(2,2);
 /* Populate real receive pointers through RECEIVE, then place all owners in
    their intended blocked states. No privileged instructions execute. */
 CHECK(invoke(1,0x23,1,0,receive_a,&next)==0);CHECK(invoke(2,0x23,2,0,receive_block,&next)==0);
 CHECK(invoke(7,0x22,1,0,answer,&next)==0);CHECK(next==1);uint64_t a=fixture_get(8,1);
 CHECK(invoke(1,0x22,2,0,answer,&next)==0);CHECK(next==2);uint64_t block=fixture_get(8,2);
 CHECK(fixture_get(0,1)==1);CHECK(fixture_retire(7)==0);CHECK(fixture_get(1,1)==a);
 CHECK(invoke(8,0x22,1,0,answer,&next)==0);CHECK(fixture_get(0,1)==1);CHECK(next!=1);
 CHECK(fixture_get(2,1)==1);CHECK(fixture_get(3,1)==9);
 CHECK(invoke(2,0x26,2,block,receive_block,&next)==0);CHECK(next==1);CHECK(fixture_get(0,1)==0);
 CHECK(invoke(1,0x26,1,a,receive_b,&next)==0);CHECK(fixture_get(1,1)==0);CHECK(fixture_get(2,1)==2);CHECK(fixture_get(3,1)==9);
 CHECK(receive_b[0]==request[0]);uint64_t b=fixture_get(8,1);
 CHECK(invoke(1,0x26,1,b,receive_b,&next)==0);CHECK(next==8);CHECK(answer[0]==response[0]);CHECK(fixture_get(0,8)==0);
 CHECK(fixture_get(5,0)==3&&fixture_get(4,0)==3);return 0;
}
static int double_cancel(void){
 uint64_t next=99;CHECK(fixture_initialize()==0);CHECK(invoke(1,0x23,1,0,receive_a,&next)==0);
 CHECK(invoke(7,0x22,1,0,answer,&next)==0);uint64_t a=fixture_get(8,1);
 CHECK(fixture_retire(7)==0);CHECK(fixture_get(1,1)==a);
 CHECK(invoke(8,0x22,1,0,answer,&next)==0);CHECK(fixture_get(2,1)==1);
 CHECK(fixture_retire(8)==0);CHECK(fixture_get(1,1)==a);
 CHECK(invoke(1,0x26,1,a,receive_b,&next)==0);CHECK(fixture_get(1,1)==0);CHECK(fixture_get(0,1)==2);CHECK(fixture_get(2,1)==0);
 CHECK(fixture_get(5,0)==2&&fixture_get(4,0)==2);return 0;
}
static int receive_abandons_old_response(void){
 uint64_t next=99;CHECK(fixture_initialize()==0);CHECK(invoke(1,0x23,1,0,receive_a,&next)==0);
 CHECK(invoke(7,0x22,1,0,answer,&next)==0);uint64_t a=fixture_get(8,1);CHECK(fixture_retire(7)==0);CHECK(fixture_get(1,1)==a);
 CHECK(invoke(8,0x22,1,0,answer,&next)==0);uint64_t b=fixture_get(8,1);
 CHECK(invoke(1,0x23,1,0,receive_b,&next)==0);CHECK(fixture_get(1,1)==0);CHECK(fixture_get(2,1)==2);
 CHECK(fixture_retire(8)==0);CHECK(fixture_get(1,1)==b);
 CHECK(invoke(1,0x26,1,b,receive_b,&next)==0);CHECK(fixture_get(1,1)==0);return 0;
}
static int pending_and_owner_exit(void){
 uint64_t next=99;CHECK(fixture_initialize()==0);
 CHECK(invoke(7,0x22,1,0,answer,&next)==0);CHECK(fixture_get(2,1)==1);CHECK(fixture_retire(7)==0);CHECK(fixture_get(1,1)==0);
 CHECK(fixture_initialize()==0);CHECK(invoke(1,0x23,1,0,receive_a,&next)==0);CHECK(invoke(7,0x22,1,0,answer,&next)==0);
 CHECK(fixture_retire(1)==0);CHECK(fixture_get(0,7)==0);CHECK(fixture_get(6,7)==0x05110008);CHECK(fixture_get(7,1)==0);
 return 0;
}
int main(void){if(nested()||double_cancel()||receive_abandons_old_response()||pending_and_owner_exit())return 1;
 printf("service IPC cancellation checks passed: %u\n",checks);return 0;}

void ABI fixture_boundary_fail(uint64_t code){fprintf(stderr,"unexpected unsupported fixture boundary %x\n",(unsigned)code);exit(3);}
