#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{U kind,code;int64_t a,b;}Event;
typedef struct{U w[8];}Message;
extern U ABI ip_reset(void),ip_key(U,U,int64_t),ip_lost(U),ip_report(U,U,const Message*,Message*),ip_pop(Event*),ip_size(U),ip_pointer(U),ip_bits(U,U),ip_mods(void);
extern U ABI ip_departed(U);
extern void ABI ip_fill(void);
static U checks;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"INPUT_SOURCE_ASSERT %d %s\n",__LINE__,#x);exit(1);}}while(0)
void ABI __dong_panic(U c,const char*p,U n){(void)c;(void)p;(void)n;fprintf(stderr,"INPUT_SOURCE_PANIC\n");exit(9);}
static void empty(void){Event e;CK(ip_pop(&e)==0);}
static Event next(U code,U value){Event e;CK(ip_pop(&e)==1&&e.kind==1&&e.code==code&&(U)e.a==value);return e;}
static Message keyboard(U source,U sequence,U epoch,U modifiers,U usage){Message r={{0x4447554849440001ULL,source,1,8,sequence,(usage<<16)|modifiers,epoch,0}};return r;}
static Message mouse(U source,U sequence,U epoch,U buttons){Message r={{0x4447554849440001ULL,source,2,3,sequence,buttons,epoch,0}};return r;}
static U session(U epoch){return (7ULL<<32)|epoch;}
static void accepted(Message*r){Message out;memset(&out,0xaa,sizeof out);CK(ip_report(14,session(r->w[6]),r,&out)==0);CK(out.w[0]==0&&out.w[1]==r->w[1]&&out.w[2]==r->w[4]);for(U i=3;i<8;i++)CK(out.w[i]==0);}
static void refused(U peer,U identity,Message*r){unsigned char before[3][4096];Message out,old;memset(&out,0xa5,sizeof out);old=out;for(U i=0;i<3;i++){CK(ip_size(i)<=4096);memcpy(before[i],(void*)(uintptr_t)ip_pointer(i),(size_t)ip_size(i));}
 CK(ip_report(peer,identity,r,&out)!=0);CK(!memcmp(&out,&old,sizeof out));for(U i=0;i<3;i++)CK(!memcmp(before[i],(void*)(uintptr_t)ip_pointer(i),(size_t)ip_size(i)));}
static void logical_merge(void){
 CK(!ip_reset());CK(!ip_key(0,30,1));next(30,1);CK(!ip_key(1,30,1));empty();CK(!ip_key(0,30,0));empty();CK(ip_bits(4,0)&(1ULL<<30));CK(!ip_lost(1));next(30,0);empty();
 CK(!ip_key(0,42,1));next(42,1);CK(ip_mods()==1);CK(!ip_key(2,42,1));empty();CK(!ip_lost(0));empty();CK(ip_mods()==1);CK(!ip_key(2,42,0));next(42,0);CK(ip_mods()==0);
 CK(!ip_key(0,272,1));next(272,1);CK(!ip_key(3,272,1));empty();CK(!ip_lost(3));empty();CK(!ip_key(0,272,0));next(272,0);
 CK(!ip_key(0,58,1));Event e=next(58,1);CK(e.b==256);CK(!ip_key(1,58,1));empty();CK(!ip_key(0,58,0));empty();CK(!ip_lost(1));next(58,0);CK(ip_mods()==256);
}
static void reports(void){
 CK(!ip_reset());CK(!ip_key(0,30,1));next(30,1);Message r=keyboard(1,1,1,2,4);accepted(&r);Event shift=next(42,1);CK(shift.b==1);empty();
 r=keyboard(1,2,1,0,0);accepted(&r);next(42,0);empty();CK(ip_bits(4,0)&(1ULL<<30));
 r=keyboard(1,3,1,0,5);accepted(&r);next(48,1);empty();
 Message valid=keyboard(1,4,1,0,0);for(U k=0;k<13;k++){r=valid;U peer=14,id=session(1);switch(k){case 0:peer=3;break;case 1:id=(6ULL<<32)|1;break;case 2:id=(7ULL<<32);break;case 3:r.w[0]++;break;case 4:r.w[1]=4;break;case 5:r.w[2]=3;break;case 6:r.w[3]=7;break;case 7:r.w[4]=3;break;case 8:r.w[5]=4ULL<<16|4ULL<<24;break;case 9:r.w[5]=1ULL<<8;break;case 10:r.w[6]=2;break;case 11:r.w[7]=1;break;case 12:r=mouse(1,4,1,0);break;}refused(peer,id,&r);}
 r=keyboard(1,4,1,0,1);accepted(&r);next(48,0);empty();CK(ip_bits(4,0)&(1ULL<<30)); // rollover releases only this source
 r=keyboard(1,5,1,0,6);accepted(&r);next(46,1);empty();
 r=keyboard(2,1,2,0,7);accepted(&r);next(46,0);next(32,1);empty();CK(ip_bits(4,0)&(1ULL<<30));
 r=keyboard(1,99,1,0,9);refused(14,session(1),&r);
 r=mouse(3,1,2,1);accepted(&r);next(272,1);empty();CK(!ip_key(0,272,1));empty();r=mouse(3,2,2,0);accepted(&r);empty();CK(ip_bits(4,4)&(1ULL<<16));
 U*queue=(U*)(uintptr_t)ip_pointer(2);U head=queue[0];queue[0]=64;r=keyboard(2,2,2,0,7);refused(14,session(2),&r);queue[0]=head;
 ip_fill();r=keyboard(2,2,2,0,8);refused(14,session(2),&r);
}
static void departures(void){
 CK(!ip_reset());CK(!ip_key(0,30,1));next(30,1);Message r=keyboard(1,1,2,0,5);accepted(&r);next(48,1);empty();
 // Old1 is above the still-zero retired watermark, so the peer-epoch guard
 // itself must protect live2. A repeated retired1 guard cannot mask this.
 CK(!ip_departed(0));empty();CK(!ip_departed(1));empty();CK(!ip_departed(0));empty();
 CK(!ip_departed(2));next(48,0);empty();CK(ip_bits(4,0)&(1ULL<<30));r=keyboard(1,2,2,0,5);refused(14,session(2),&r);
 r=keyboard(1,1,3,0,6);accepted(&r);next(46,1);empty();CK(!ip_departed(2));empty();CK(!ip_departed(3));next(46,0);empty();CK(ip_bits(4,0)&(1ULL<<30));CK(!ip_departed(3));empty();
}
static void randomized(void){unsigned char down[4][64]={{0}};CK(!ip_reset());U state=0x1234567;for(U step=0;step<4000;step++){state=state*6364136223846793005ULL+1;U source=state>>61&3,code=30+(state>>19)%15,value=(state>>27)%3;
 U was=down[source][code],all=0;for(U s=0;s<4;s++)all|=down[s][code];int expected=-1;
 if(value==0&&was){down[source][code]=0;U others=0;for(U s=0;s<4;s++)others|=down[s][code];if(!others)expected=0;}
 if(value==1&&!was){down[source][code]=1;if(!all)expected=1;}
 if(value==2&&was)expected=2;
 CK(!ip_key(source,code,(int64_t)value));if(expected>=0)next(code,(U)expected);empty();
 U combined=0;for(U s=0;s<4;s++)if(down[s][code])combined=1;CK(!!(ip_bits(4,0)&(1ULL<<code))==combined);
 }}
int main(void){logical_merge();reports();departures();randomized();printf("INPUT_SOURCES_NATIVE_PASS checks=%llu\n",(unsigned long long)checks);return 0;}
