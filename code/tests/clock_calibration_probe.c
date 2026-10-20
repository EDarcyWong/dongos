/* Independent 128-bit interval arithmetic and frequency-plane consensus model. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define ERR(n) (UINT64_C(0x03060000)+(n))
typedef unsigned __int128 Wide;
typedef struct{uint64_t mask,period_fs,hz;} Reference;
typedef struct{uint64_t r0_before,c0,t0,r0_after,r1_before,c1,t1,r1_after;} Sample;
typedef struct{uint64_t reference_lower,reference_upper,ns_lower,ns_upper,tsc_lower_hz,tsc_upper_hz,lapic_lower_hz,lapic_upper_hz,tsc_hz,lapic_hz,uncertainty_ppm;} Estimate;
typedef struct{uint64_t total,accepted,rejected,consistent,accepted_mask,selected_mask,tsc_lower_hz,tsc_upper_hz,tsc_hz,lapic_lower_hz,lapic_upper_hz,lapic_hz,median_tsc_hz,median_lapic_hz,tightest_index,reference_delta,uncertainty_ppm,errors[7];} Result;
extern ABI void clock_sizes(uint64_t *);
extern ABI uint64_t clock_estimate(const Reference *,const Sample *,Estimate *),clock_select(const Reference *,const Sample *,size_t,Result *);
static uint64_t checks,estimates,selections,rejections,physical,negative;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"CLOCK_MODEL_ASSERT line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected clock panic %llu\n",(unsigned long long)code);exit(99);}
ABI void clock_negative_hit(uint64_t kind){negative=kind;fprintf(stderr,"CLOCK_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}
/* Products use independent 128-bit math to detect overflow. Divide only after
   that proof, avoiding MinGW's __udivti3 vector-return ABI under -mno-sse. */
static uint64_t quotient(Wide n,uint64_t d){CHECK(n<=UINT64_MAX);return (uint64_t)n/d;}
static uint64_t ceil_wide(Wide n,uint64_t d){CHECK(n<=UINT64_MAX);uint64_t value=(uint64_t)n;return value/d+(value%d!=0);}
static uint64_t midpoint(uint64_t a,uint64_t b){return a+(b-a)/2;}
static unsigned population(uint64_t x){unsigned n=0;while(x){n+=(unsigned)(x&1);x>>=1;}return n;}
static uint64_t distance(uint64_t a,uint64_t b){return a>b?a-b:b-a;}
static uint64_t reference_error(const Reference *r){
 if(!r||(r->mask!=0xffffff&&r->mask!=UINT32_MAX&&r->mask!=UINT64_MAX))return ERR(2);
 uint64_t horizon;
 if(r->period_fs){if(r->hz||r->period_fs<1000||r->period_fs>100000000)return ERR(2);horizon=ceil_wide((Wide)25000000*1000000,r->period_fs);}
 else{if(r->hz<1000000||r->hz>1000000000)return ERR(2);horizon=ceil_wide((Wide)25000000*r->hz,1000000000);}
 return horizon>=r->mask/2+1?ERR(4):0;
}
static uint64_t model_estimate(const Reference *r,const Sample *s,Estimate *out){
 if(!s||!out){return ERR(1);}uint64_t error=reference_error(r);if(error){return error;}
 if(s->r0_before>r->mask||s->r0_after>r->mask||s->r1_before>r->mask||s->r1_after>r->mask||s->t1<=s->t0||s->c0>UINT32_MAX||!s->c1||s->c1>=s->c0)return ERR(3);
 /* Unsigned reduction is independent of the implementation's wrap branches. */
 uint64_t a=(s->r0_after-s->r0_before)&r->mask,b=(s->r1_before-s->r0_before)&r->mask,c=(s->r1_after-s->r0_before)&r->mask;
 if(c+1>=r->mask/2+1||a>b||b>c){return ERR(4);}if(b-a<=1){return ERR(3);}
 uint64_t low=b-a-1,high=c+1;Wide nl,nh;uint64_t denominator;
 if(r->period_fs){nl=(Wide)low*r->period_fs;nh=(Wide)high*r->period_fs;denominator=1000000;}
 else{nl=(Wide)low*1000000000;nh=(Wide)high*1000000000;denominator=r->hz;}
 if(nl>UINT64_MAX||nh>UINT64_MAX)return ERR(7);
 uint64_t ns_low=quotient(nl,denominator),ns_high=ceil_wide(nh,denominator);
 if(ns_low<5000000||ns_high>25000000||ns_high<=ns_low)return ERR(6);
 if((Wide)(a+1)*100>low||(Wide)(c-b+1)*100>low||(Wide)(a+1+c-b+1)*50>low)return ERR(5);
 uint64_t dt=s->t1-s->t0,dc=s->c0-s->c1;if(dt<=1||dc<=1||dt==UINT64_MAX)return ERR(3);
 Wide numerator[4]={(Wide)(dt-1)*1000000000,(Wide)(dt+1)*1000000000,(Wide)(dc-1)*1000000000,(Wide)(dc+1)*1000000000};
 for(unsigned i=0;i<4;i++)if(numerator[i]>UINT64_MAX)return ERR(7);
 Estimate e={low,high,ns_low,ns_high,quotient(numerator[0],ns_high),ceil_wide(numerator[1],ns_low),quotient(numerator[2],ns_high),ceil_wide(numerator[3],ns_low),0,0,0};
 if(e.tsc_lower_hz<1000000||e.tsc_upper_hz>UINT64_C(16000000000)||e.lapic_lower_hz<1000||e.lapic_upper_hz>UINT64_C(4000000000))return ERR(6);
 e.tsc_hz=midpoint(e.tsc_lower_hz,e.tsc_upper_hz);e.lapic_hz=midpoint(e.lapic_lower_hz,e.lapic_upper_hz);e.uncertainty_ppm=quotient((Wide)(high-low)*1000000,low);*out=e;return 0;
}
static int compare_u64(const void *a,const void *b){uint64_t x=*(const uint64_t *)a,y=*(const uint64_t *)b;return (x>y)-(x<y);}
static uint64_t model_select(const Reference *r,const Sample *s,size_t n,Result *out){
 if(!out||!s||n<3||n>7){return ERR(1);}uint64_t error=reference_error(r);if(error){return error;}
 Estimate e[7];memset(e,0,sizeof e);Result result={0};result.total=n;
 for(unsigned i=0;i<n;i++){result.errors[i]=model_estimate(r,s+i,e+i);if(result.errors[i])result.rejected++;else{result.accepted++;result.accepted_mask|=UINT64_C(1)<<i;}}
 if(result.accepted<3)return ERR(8);
 /* Find maximal consensus by sweeping the 2D frequency interval lower-edge
    intersection grid, rather than enumerating sample subsets as Dong does. */
 unsigned best=0,tied=0;uint64_t chosen=0;
 for(unsigned x=0;x<n;x++)if(result.accepted_mask&(UINT64_C(1)<<x))for(unsigned y=0;y<n;y++)if(result.accepted_mask&(UINT64_C(1)<<y)){
  uint64_t fx=e[x].tsc_lower_hz,fy=e[y].lapic_lower_hz,mask=0;
  for(unsigned j=0;j<n;j++)if((result.accepted_mask&(UINT64_C(1)<<j))&&e[j].tsc_lower_hz<=fx&&fx<=e[j].tsc_upper_hz&&e[j].lapic_lower_hz<=fy&&fy<=e[j].lapic_upper_hz)mask|=UINT64_C(1)<<j;
  unsigned count=population(mask);if(count>best){best=count;chosen=mask;tied=0;}else if(count==best&&mask!=chosen)tied=1;
 }
 if(best<3||tied)return ERR(9);
 result.consistent=best;result.selected_mask=chosen;result.tsc_upper_hz=result.lapic_upper_hz=UINT64_MAX;uint64_t tsc[7],lapic[7],tight=UINT64_MAX;unsigned count=0;
 for(unsigned i=0;i<n;i++)if(chosen&(UINT64_C(1)<<i)){
  if(e[i].tsc_lower_hz>result.tsc_lower_hz){result.tsc_lower_hz=e[i].tsc_lower_hz;}if(e[i].tsc_upper_hz<result.tsc_upper_hz){result.tsc_upper_hz=e[i].tsc_upper_hz;}
  if(e[i].lapic_lower_hz>result.lapic_lower_hz){result.lapic_lower_hz=e[i].lapic_lower_hz;}if(e[i].lapic_upper_hz<result.lapic_upper_hz){result.lapic_upper_hz=e[i].lapic_upper_hz;}
  tsc[count]=e[i].tsc_hz;lapic[count++]=e[i].lapic_hz;
  if(e[i].uncertainty_ppm<tight){tight=e[i].uncertainty_ppm;result.tightest_index=i;result.reference_delta=midpoint(e[i].reference_lower,e[i].reference_upper);}
 }
 qsort(tsc,count,sizeof *tsc,compare_u64);qsort(lapic,count,sizeof *lapic,compare_u64);result.uncertainty_ppm=tight;
 result.median_tsc_hz=count%2?tsc[count/2]:midpoint(tsc[count/2-1],tsc[count/2]);result.median_lapic_hz=count%2?lapic[count/2]:midpoint(lapic[count/2-1],lapic[count/2]);
 result.tsc_hz=result.median_tsc_hz<result.tsc_lower_hz?result.tsc_lower_hz:(result.median_tsc_hz>result.tsc_upper_hz?result.tsc_upper_hz:result.median_tsc_hz);
 result.lapic_hz=result.median_lapic_hz<result.lapic_lower_hz?result.lapic_lower_hz:(result.median_lapic_hz>result.lapic_upper_hz?result.lapic_upper_hz:result.median_lapic_hz);*out=result;return 0;
}
static uint64_t reference_ticks(const Reference *r,uint64_t ns){return r->period_fs?quotient((Wide)ns*1000000,r->period_fs):quotient((Wide)ns*r->hz,1000000000);}
static Sample synthetic(const Reference *r,uint64_t origin,uint64_t first_ns,uint64_t second_ns,uint64_t duration_ns,uint64_t tsc_hz,uint64_t lapic_hz){
 uint64_t c0time=first_ns/3,t0time=first_ns*2/3,c1time=duration_ns+second_ns/3,t1time=duration_ns+second_ns*2/3;
 Sample s={(origin)&r->mask,UINT32_MAX-quotient((Wide)c0time*lapic_hz,1000000000),1000000000+quotient((Wide)t0time*tsc_hz,1000000000),(origin+reference_ticks(r,first_ns))&r->mask,
  (origin+reference_ticks(r,duration_ns))&r->mask,UINT32_MAX-quotient((Wide)c1time*lapic_hz,1000000000),1000000000+quotient((Wide)t1time*tsc_hz,1000000000),(origin+reference_ticks(r,duration_ns+second_ns))&r->mask};return s;
}
static void check_estimate(const Reference *r,const Sample *s,uint64_t true_tsc,uint64_t true_lapic){
 struct{uint64_t pre;Estimate value;uint64_t post;} out;out.pre=UINT64_C(0x123456789abcdef0);out.post=UINT64_C(0xfedcba9876543210);memset(&out.value,0xa5,sizeof out.value);Estimate saved=out.value,expected=out.value;Sample original;if(s)original=*s;
 uint64_t want=model_estimate(r,s,&expected),actual=clock_estimate(r,s,&out.value);CHECK(actual==want);
 if(!actual){if(memcmp(&out.value,&expected,sizeof expected)!=0){for(unsigned field=0;field<sizeof expected/8;field++)if(((uint64_t *)&out.value)[field]!=((uint64_t *)&expected)[field])fprintf(stderr,"CLOCK_ESTIMATE_DIFFERENCE field=%u actual=%llu expected=%llu estimate=%llu\n",field,(unsigned long long)((uint64_t *)&out.value)[field],(unsigned long long)((uint64_t *)&expected)[field],(unsigned long long)estimates);}CHECK(memcmp(&out.value,&expected,sizeof expected)==0);estimates++;if(true_tsc){CHECK(out.value.tsc_lower_hz<=true_tsc&&true_tsc<=out.value.tsc_upper_hz);CHECK(out.value.lapic_lower_hz<=true_lapic&&true_lapic<=out.value.lapic_upper_hz);physical++;}}
 else{CHECK(memcmp(&out.value,&saved,sizeof saved)==0);rejections++;}if(s)CHECK(memcmp(&original,s,sizeof original)==0);CHECK(out.pre==UINT64_C(0x123456789abcdef0)&&out.post==UINT64_C(0xfedcba9876543210));
}
static void check_select(const Reference *r,const Sample *s,size_t n){
 struct{uint64_t pre;Result value;uint64_t post;} out;out.pre=UINT64_C(0x8877665544332211);out.post=UINT64_C(0x1122334455667788);memset(&out.value,0xa5,sizeof out.value);Result saved=out.value,expected=out.value;Sample original[7];if(s&&n<=7)memcpy(original,s,n*sizeof *s);
 uint64_t want=model_select(r,s,n,&expected),actual=clock_select(r,s,n,&out.value);CHECK(actual==want);
 if(!actual){CHECK(memcmp(&out.value,&expected,sizeof expected)==0);CHECK(out.value.consistent>=3);selections++;}else{CHECK(memcmp(&out.value,&saved,sizeof saved)==0);rejections++;}
 if(s&&n<=7){CHECK(memcmp(original,s,n*sizeof *s)==0);}CHECK(out.pre==UINT64_C(0x8877665544332211)&&out.post==UINT64_C(0x1122334455667788));
}
static void old_bias(void){
 Reference r={UINT64_MAX,10000000,0};Sample s[7];s[0]=synthetic(&r,100000,1350000,10000,10000000,UINT64_C(3410000000),62500000);s[1]=synthetic(&r,100000,1200000,10000,10000000,UINT64_C(3410000000),62500000);
 for(unsigned i=2;i<7;i++)s[i]=synthetic(&r,100000+i,1000+i*1000,2000+i*1000,10000000,UINT64_C(3410000000),62500000);
 Result value;CHECK(clock_select(&r,s,7,&value)==0);if(negative)fprintf(stderr,"CLOCK_OLD_SINGLE_RATE %llu\n",(unsigned long long)value.tsc_hz);
 CHECK(distance(value.tsc_hz,UINT64_C(3410000000))<UINT64_C(10000000));CHECK(value.accepted==5&&value.rejected==2&&value.consistent==5&&value.selected_mask==124);CHECK(value.errors[0]==ERR(5)&&value.errors[1]==ERR(5));
 check_select(&r,s,7);check_estimate(&r,s,0,0);check_estimate(&r,s+1,0,0);
}
static uint64_t random_state=UINT64_C(0x1020304050607080);
static uint64_t random64(void){random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return random_state;}
static void positive_and_clusters(void){
 const Reference refs[]={{0xffffff,10000000,0},{UINT32_MAX,30000000,0},{UINT64_MAX,1000,0},{UINT64_MAX,100000000,0},{0xffffff,0,3579545},{UINT32_MAX,0,3579545},{UINT64_MAX,0,1000000000}};
 for(unsigned k=0;k<sizeof refs/sizeof refs[0];k++)for(unsigned iteration=0;iteration<48;iteration++){
  const Reference *r=refs+k;uint64_t origin=iteration%2?r->mask-100:random64()&r->mask,rate=UINT64_C(3410000000)+(iteration%3)*100000000;Sample s[7];
  for(unsigned i=0;i<7;i++){uint64_t a=1000+random64()%40000,b=1000+random64()%40000,d=8000000+random64()%4000000;s[i]=synthetic(r,origin,a,b,d,rate,62500000);check_estimate(r,s+i,rate,62500000);}
  check_select(r,s,7);Sample reverse[7];for(unsigned i=0;i<7;i++)reverse[i]=s[6-i];check_select(r,reverse,7);check_select(r,s,3);check_select(r,s,4);
 }
 Reference r={UINT64_MAX,10000000,0};Sample s[7];
 for(unsigned i=0;i<7;i++){s[i]=synthetic(&r,100,1000,1000,10000000,i<4?UINT64_C(3410000000):UINT64_C(3000000000),62500000);}check_select(&r,s,7);
 Result result;CHECK(clock_select(&r,s,7,&result)==0&&result.consistent==4&&result.selected_mask==15);CHECK(result.tsc_hz<UINT64_C(3411000000));
 for(unsigned i=0;i<7;i++){s[i]=synthetic(&r,100,1000,1000,10000000,i<3?UINT64_C(3410000000):UINT64_C(3000000000),62500000);}s[6].t1=s[6].t0;check_select(&r,s,7);CHECK(clock_select(&r,s,7,&result)==ERR(9));
 /* TSC-only consistency is insufficient if the APIC measurements disagree. */
 for(unsigned i=0;i<7;i++){s[i]=synthetic(&r,100,1000,1000,10000000,UINT64_C(3410000000),i<3?62500000:50000000);}s[6].c1=0;check_select(&r,s,7);CHECK(clock_select(&r,s,7,&result)==ERR(9));
 for(unsigned i=0;i<7;i++){s[i]=synthetic(&r,100,1000,1000,10000000,UINT64_C(3410000000)+i*100000000,62500000);}check_select(&r,s,7);
}
static void invalid_and_boundaries(void){
 Reference r={UINT64_MAX,10000000,0};Sample s=synthetic(&r,UINT64_MAX-100,1000,2000,10000000,UINT64_C(3410000000),62500000);check_estimate(&r,&s,UINT64_C(3410000000),62500000);
 check_estimate(NULL,&s,0,0);check_estimate(&r,NULL,0,0);CHECK(clock_estimate(&r,&s,NULL)==ERR(1));CHECK(clock_select(&r,&s,3,NULL)==ERR(1));check_select(&r,NULL,3);check_select(&r,&s,0);check_select(&r,&s,2);check_select(&r,&s,8);
 Reference invalid[]={ {0,10000000,0},{0xffff,10000000,0},{UINT64_MAX,0,0},{UINT64_MAX,999,0},{UINT64_MAX,100000001,0},{UINT64_MAX,10000000,3579545},{UINT64_MAX,0,999999},{UINT64_MAX,0,1000000001},{0xffffff,1000,0},{UINT32_MAX,1000,0} };
 for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++)check_estimate(invalid+i,&s,0,0);
 Sample bad=s;bad.t1=bad.t0;check_estimate(&r,&bad,0,0);bad=s;bad.t1=bad.t0-1;check_estimate(&r,&bad,0,0);bad=s;bad.c1=0;check_estimate(&r,&bad,0,0);bad=s;bad.c1=bad.c0;check_estimate(&r,&bad,0,0);bad=s;bad.c0=UINT64_MAX;check_estimate(&r,&bad,0,0);
 bad=s;bad.r0_after=bad.r0_before-1;check_estimate(&r,&bad,0,0);bad=s;bad.r1_after=bad.r1_before-1;check_estimate(&r,&bad,0,0);bad=s;bad.r1_before=bad.r0_after;check_estimate(&r,&bad,0,0);
 bad=synthetic(&r,100,1000,1000,4000000,UINT64_C(3410000000),62500000);check_estimate(&r,&bad,0,0);bad=synthetic(&r,100,1000,1000,26000000,UINT64_C(3410000000),62500000);check_estimate(&r,&bad,0,0);
 bad=synthetic(&r,100,200000,1000,10000000,UINT64_C(3410000000),62500000);check_estimate(&r,&bad,0,0);bad=synthetic(&r,100,1000,200000,10000000,UINT64_C(3410000000),62500000);check_estimate(&r,&bad,0,0);
 bad=s;bad.t0=0;bad.t1=UINT64_MAX;check_estimate(&r,&bad,0,0);bad=s;bad.t0=0;bad.t1=UINT64_MAX/1000000000+2;check_estimate(&r,&bad,0,0);
 bad=s;bad.r0_before=0;bad.r0_after=1;bad.r1_before=UINT64_MAX/10000000+10;bad.r1_after=bad.r1_before+1;check_estimate(&r,&bad,0,0);
 bad=synthetic(&r,100,1000,1000,10000000,500000,62500000);check_estimate(&r,&bad,0,0);bad=synthetic(&r,100,1000,1000,10000000,UINT64_C(17000000000),62500000);check_estimate(&r,&bad,0,0);bad=synthetic(&r,100,1000,1000,10000000,UINT64_C(3410000000),500);check_estimate(&r,&bad,0,0);
 Reference small={0xffffff,10000000,0};bad=synthetic(&small,100,1000,1000,10000000,UINT64_C(3410000000),62500000);bad.r1_after=UINT64_C(0x1000000);check_estimate(&small,&bad,0,0);
 Sample group[3]={s,s,s};group[1].c1=0;group[2].t1=group[2].t0;check_select(&r,group,3);
 /* Exactly 1% endpoints are legal; one additional reference tick is not. */
 bad=(Sample){100,UINT32_MAX,1000000,100+9999,100+1010000,UINT32_MAX-631250,1000000+34441000,100+1019999};check_estimate(&r,&bad,0,0);bad.r0_after++;check_estimate(&r,&bad,0,0);
}
int main(void){uint64_t sizes[4];clock_sizes(sizes);CHECK(sizes[0]==sizeof(Reference)&&sizes[1]==sizeof(Sample)&&sizes[2]==sizeof(Estimate)&&sizes[3]==sizeof(Result));old_bias();positive_and_clusters();invalid_and_boundaries();printf("clock calibration oracle passed: estimates=%llu selections=%llu rejected=%llu known-physical-bounds=%llu independent-u128+frequency-plane-grid old-single-underestimate=actual-negative-control masks=24/32/64 atomic+guards=ok checks=%llu\n",(unsigned long long)estimates,(unsigned long long)selections,(unsigned long long)rejections,(unsigned long long)physical,(unsigned long long)checks);return 0;}
