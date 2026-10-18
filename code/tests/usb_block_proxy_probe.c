#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
typedef struct {uint64_t w[8];} Message;
extern uint64_t SYSV ub_init(uint64_t),ub_execute(const Message*,Message*),ub_value(uint64_t);
extern void SYSV ub_reset(void);
static unsigned checks,calls,accepted,yields,busy,kind;
static uint64_t completed;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"USB_PROXY_ASSERT %d calls=%u accepted=%u yields=%u\n",__LINE__,calls,accepted,yields);return 1;}}while(0)
void SYSV __dong_panic(uint64_t c,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"panic %llu\n",(unsigned long long)c);exit(9);}
uint64_t SYSV ub_yield(void){yields++;return kind==4?0x12340001:0;}
uint64_t SYSV ub_rpc(uint64_t ep,const Message*r,Message*out){
    calls++;if(ep!=0x3456)return 0x12340002;
    if(busy){busy--;return 0x04020003;}
    accepted++;if(kind==1){out->w[0]=0x04020003;return 0;}
    if(kind==2)return 0x04020007;
    out->w[2]=4096;out->w[3]=0;out->w[4]=completed;
    if(r->w[0]==2||r->w[0]==3){out->w[1]=r->w[2];out->w[4]=++completed;}
    if(r->w[0]==4)out->w[4]=++completed;
    if(kind==3)out->w[2]++;
    if(kind==5)out->w[7]=1;
    if(kind==6)out->w[1]++;
    return 0;
}
static void reset(void){ub_reset();calls=accepted=yields=busy=kind=0;completed=0;}
int main(void){
    Message r={{0}},o;unsigned before;
    reset();CHECK(ub_init(0)==0x081d0001&&calls==0);CHECK(ub_init(0x3456)==0&&ub_value(0)==1&&ub_value(1)==4096);
    CHECK(ub_init(0x3456)==0x081d0001&&calls==1);
    r.w[0]=3;r.w[1]=4095;r.w[2]=1;r.w[4]=65024;memset(&o,0xaa,sizeof(o));
    CHECK(ub_execute(&r,&o)==0&&o.w[1]==1&&accepted==2&&ub_value(2)==1);
    r.w[0]=2;CHECK(ub_execute(&r,&o)==0&&o.w[4]==2);
    before=calls;r.w[2]=2;r.w[4]=0;CHECK(ub_execute(&r,&o)==0x081d0001&&calls==before);
    r.w[1]=0;r.w[2]=128;r.w[4]=0;CHECK(ub_execute(&r,&o)==0&&o.w[1]==128);
    r.w[2]=129;before=calls;CHECK(ub_execute(&r,&o)==0x081d0001&&calls==before);
    r.w[2]=1;r.w[4]=65025;CHECK(ub_execute(&r,&o)==0x081d0001&&calls==before);
    r.w[4]=UINT64_MAX;CHECK(ub_execute(&r,&o)==0x081d0001&&calls==before);
    r.w[4]=0;r.w[1]=UINT64_MAX;CHECK(ub_execute(&r,&o)==0x081d0001&&calls==before);
    r.w[1]=0;r.w[3]=1;CHECK(ub_execute(&r,&o)==0x081d0001&&calls==before);r.w[3]=0;
    r.w[0]=4;r.w[2]=0;busy=17;before=accepted;CHECK(ub_execute(&r,&o)==0&&accepted==before+1&&yields==17&&o.w[4]==4);
    kind=1;before=calls;memset(&o,0xaa,sizeof(o));CHECK(ub_execute(&r,&o)==0x04020003&&calls==before+1&&o.w[0]==0xaaaaaaaaaaaaaaaaULL);
    kind=2;before=calls;CHECK(ub_execute(&r,&o)==0x04020007&&calls==before+1);
    kind=3;before=ub_value(2);CHECK(ub_execute(&r,&o)==0x081d0002&&ub_value(2)==before);
    kind=5;CHECK(ub_execute(&r,&o)==0x081d0002&&ub_value(2)==before);
    kind=6;CHECK(ub_execute(&r,&o)==0x081d0002&&ub_value(2)==before);
    reset();busy=257;CHECK(ub_init(0x3456)==0x04020003&&calls==257&&yields==256&&accepted==0&&ub_value(0)==0);
    reset();busy=1;kind=4;CHECK(ub_init(0x3456)==0x12340001&&calls==1&&yields==1&&ub_value(0)==0);
    reset();kind=1;CHECK(ub_init(0x3456)==0x04020003&&calls==1&&accepted==1&&ub_value(0)==0);
    reset();kind=3;CHECK(ub_init(0x3456)==0&&ub_value(1)==4097);
    printf("USB proxy checks passed: %u\n",checks);return 0;
}
