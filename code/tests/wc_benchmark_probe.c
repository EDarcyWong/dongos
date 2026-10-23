/* Real ASM stores into ordinary host RAM; its effective cache type is unknown. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
struct Sample{U version,phase,error,root,va,pa,bytes,hz,flags,backup,capacity,pattern,restored,low,high,cycles[7],leaf_count,leaves[17];};
extern U ABI wb_size(U),wb_init(void*,void*,void*),wb_map(void*,U,U,U),wb_protect(void*,U,U);
extern U ABI wb_measure(void*,U,U,U,U,U,void*,size_t,struct Sample*);
extern U ABI wc_benchmark_trial(U,U,U);
static unsigned checks;
static void ck(int ok,const char*reason){++checks;if(!ok){fprintf(stderr,"WC_ORACLE %s normally\n",reason);exit(1);}}
ABI void __attribute__((noreturn)) __dong_panic(uint32_t a,uint32_t b,const void*c,U d){
 (void)c;(void)d;fprintf(stderr,"unexpected Dong panic %u/%u\n",a,b);exit(2);
}
struct Guard{unsigned char*allocation,*p;size_t n,g;};
static struct Guard guard(size_t n,size_t align){
 struct Guard a={0};a.n=n;a.g=align<16?16:align;
 a.allocation=malloc(n+align+2*a.g);ck(a.allocation!=NULL,"host-allocation");
 a.p=(void*)(((uintptr_t)(a.allocation+a.g)+align-1)&~(uintptr_t)(align-1));
 memset(a.p-a.g,0xa5,a.g);memset(a.p,0,n);memset(a.p+n,0x5a,a.g);return a;
}
static void guards(struct Guard*a,const char*label){
 for(size_t i=0;i<a->g;++i)ck(a->p[-(ptrdiff_t)a->g+(ptrdiff_t)i]==0xa5&&a->p[a->n+i]==0x5a,label);
}
static void unchanged(void*space,struct Guard*w,struct Guard*b,struct Guard*r,U bytes,U pa,U hz,U flags,size_t capacity){
 unsigned char old[sizeof(struct Sample)];memcpy(old,r->p,sizeof old);
 U status=wb_measure(space,(U)(uintptr_t)w->p,pa,bytes,hz,flags,b->p,capacity,(void*)r->p);
 ck(status!=0,"invalid-input-accepted");ck(!memcmp(old,r->p,sizeof old),"invalid-input-report-atomicity");
 for(size_t i=0;i<w->n;++i)ck(w->p[i]==(unsigned char)(i*37+11),"invalid-input-window-atomicity");
}
int main(void){
 ck(wb_size(1)==sizeof(struct Sample),"sample-ABI");
 struct Guard s=guard((size_t)wb_size(0),8),pool=guard(32*4096,4096),meta=guard(32,8);
 struct Guard w=guard(65536,4096),b=guard(65536+16,8),r=guard(sizeof(struct Sample),8);
 for(size_t i=0;i<w.n;++i)w.p[i]=(unsigned char)(i*37+11);
 ck(!wb_init(s.p,pool.p,meta.p),"real-paging-init");
 U va=(U)(uintptr_t)w.p,pa=UINT64_C(0x800000),hz=UINT64_C(1000000000);
 /* Observe the actual ASM write pattern independently of Dong's report and
    restoration checks. This is ordinary RAM with unknown hardware cache type. */
 memcpy(b.p,w.p,w.n);
 ck(wc_benchmark_trial(va,w.n,UINT64_C(0x9e3779b97f4a7c15))>0,"direct-real-timer");
 guards(&w,"write-window-guard");
 for(size_t i=0;i<w.n/8;++i)ck(((U*)w.p)[i]==(UINT64_C(0x9e3779b97f4a7c15)^(U)i),"actual-same-qword-pattern");
 memcpy(w.p,b.p,w.n);
 for(U off=0;off<w.n;off+=4096)ck(!wb_map(s.p,va+off,pa+off,9),"real-UC-selector-map");
 for(unsigned phase=0;phase<2;++phase){
  U flags=phase?17:9;
  if(phase)for(U off=0;off<w.n;off+=4096)ck(!wb_protect(s.p,va+off,flags),"real-WC-selector-protect");
  memset(r.p,0x39,r.n);U status=wb_measure(s.p,va,pa,w.n,hz,flags,b.p,b.n,(void*)r.p);
  guards(&w,"write-window-guard");
  for(size_t i=0;i<w.n;++i)ck(w.p[i]==(unsigned char)(i*37+11),"window-restored");
  ck(status==0,"measure-result");struct Sample*q=(void*)r.p;
  ck(q->version==1&&q->phase==2&&q->error==0&&q->restored==7,"completed-seven-restorations");
  ck(q->root==0x400000&&q->va==va&&q->pa==pa&&q->bytes==w.n&&q->hz==hz&&q->flags==flags,"actual-query-report");
  ck(q->backup==(U)(uintptr_t)b.p&&q->capacity==b.n&&q->pattern==UINT64_C(0x9e3779b97f4a7c15),"sample-window-pattern");
  ck(q->low==UINT64_C(0x736176652d6c6f77)&&q->high==UINT64_C(0x7361766568696768),"backup-inner-guards");
  for(unsigned i=0;i<7;++i)ck(q->cycles[i]>0,"serialized-real-cycles");
  ck(q->leaf_count==16,"complete-raw-leaves");
  for(unsigned i=0;i<16;++i)ck((q->leaves[i]&~UINT64_C(0x60))==((pa+i*4096)|(UINT64_C(1)<<63)|(phase?131:27)),"raw-cache-selector-leaf");
 }
 for(U n=8;n<=16;n+=8){
  ck(wb_measure(s.p,va+4088,pa+4088,n,hz,17,b.p,b.n,(void*)r.p)==0,"bounded-page-tail-sample");
  struct Sample*q=(void*)r.p;ck(q->leaf_count==(n==8?1:2)&&q->restored==7,"exact-page-tail-raw-leaves");
  for(size_t i=0;i<w.n;++i)ck(w.p[i]==(unsigned char)(i*37+11),"page-tail-window-restored");
 }
 memset(r.p,0x39,r.n);
 unchanged(s.p,&w,&b,&r,0,pa,hz,17,b.n);
 unchanged(s.p,&w,&b,&r,65544,pa,hz,17,b.n);
 unchanged(s.p,&w,&b,&r,7,pa,hz,17,b.n);
 unchanged(s.p,&w,&b,&r,w.n,pa,0,17,b.n);
 unchanged(s.p,&w,&b,&r,w.n,pa,hz,1,b.n);
 unchanged(s.p,&w,&b,&r,w.n,pa,hz,9,b.n);
 unchanged(s.p,&w,&b,&r,w.n,pa+4096,hz,17,b.n);
 unchanged(s.p,&w,&b,&r,w.n,pa,hz,17,b.n-1);
 unchanged(s.p,&w,&b,&r,w.n,UINT64_MAX-7,hz,17,b.n);
 ck(wb_measure(s.p,va+1,pa+1,w.n,hz,17,b.p,b.n,(void*)r.p)!=0,"unaligned-window-rejected");
 ck(wb_measure(s.p,va,pa,w.n,hz,17,w.p,w.n+16,(void*)r.p)!=0,"overlapping-backup-rejected");
 for(size_t i=0;i<r.n;++i)ck(r.p[i]==0x39,"invalid-input-report-atomicity");
 ck(!wb_protect(s.p,va+4096,1),"wrong-cache-page-fixture");
 unchanged(s.p,&w,&b,&r,w.n,pa,hz,17,b.n);
 guards(&w,"write-window-guard");guards(&b,"backup-outer-guard");guards(&r,"report-guard");
 guards(&s,"space-guard");guards(&pool,"paging-pool-guard");guards(&meta,"metadata-guard");
 free(s.allocation);free(pool.allocation);free(meta.allocation);free(w.allocation);free(b.allocation);free(r.allocation);
 printf("WC_BENCH_NATIVE_PASS checks=%u hardware_cache=unknown physical_wc_performance=false\n",checks);return 0;
}
