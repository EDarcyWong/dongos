/* Independent raw forest/permission oracle; actual production paging creates it. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
#define NX (UINT64_C(1)<<63)
#define FRAME UINT64_C(0x10000000)
#define VA UINT64_C(0xffffa90000000000)
#define HIDDEN (VA+8192)
#define LOW UINT64_C(0x0000008000002000)
#define LARGE UINT64_C(0xffffaa0000000000)
#define NROOT 3
#define NTABLE 32
struct Root{const void*space;U identity,generation;};
struct Alias{U root,identity,generation,va,pa,bytes,flags,leaf_bytes;};
struct Report{U roots,tables,leaves,aliases,shared_entries,kernel_scans,physical,bytes;};
extern DG U rr_size(U),rr_init(void*,void*,size_t,U,void*),rr_map(void*,U,U,U,U),rr_unmap(void*,U,void*);
extern DG U rr_init_width(void*,void*,size_t,U,void*,size_t);
extern DG U rr_split(void*,U),rr_protect(void*,U,U),rr_replace(void*,U,U,U);
extern DG U rr_audit(const void*,const struct Root*,size_t,U,U,struct Alias*,size_t,struct Report*,void*);
static unsigned checks,scenarios;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"roots fixture line %d: %s\n",__LINE__,#x);exit(2);}}while(0)
DG void __attribute__((noreturn)) __dong_panic(uint32_t a,uint32_t b,const void*c,U d){(void)c;(void)d;fprintf(stderr,"unexpected Dong panic %u/%u\n",a,b);exit(3);}
struct Guard{unsigned char*allocation,*p;size_t n,g;};
static struct Guard guard(size_t n,size_t alignment){struct Guard a={0};a.n=n;a.g=alignment<16?16:alignment;a.allocation=malloc(n+alignment+2*a.g);CK(a.allocation);a.p=(void*)(((uintptr_t)(a.allocation+a.g)+alignment-1)&~(uintptr_t)(alignment-1));memset(a.p-a.g,0xa5,a.g);memset(a.p,0,n);memset(a.p+n,0x5a,a.g);return a;}
static void intact(struct Guard*a){for(size_t i=0;i<a->g;i++)CK(a->p[-(ptrdiff_t)a->g+(ptrdiff_t)i]==0xa5&&a->p[a->n+i]==0x5a);}
struct Space{struct Guard object,pool,meta;U pa;};
struct Fixture{struct Space s[NROOT];struct Guard roots,output,report,retired,scratch;};
static U mask_of(const struct Space*s){U mask;memcpy(&mask,s->object.p+40,sizeof mask);U end=mask+4096;CK(!(mask&4095)&&end>=UINT64_C(0x100000000)&&end<=UINT64_C(0x10000000000000)&&!(end&(end-1)));return mask;}
static U limit_of(struct Fixture*f,size_t r){U hw=mask_of(&f->s[0]),own=mask_of(&f->s[r]);return hw<own?hw:own;}
static U*table(struct Space*s,size_t n){CK(n<NTABLE);return (U*)(void*)(s->pool.p+n*4096);}
static U*leaf(struct Space*s,U va){
 size_t t=0;
 for(unsigned level=0;level<4;level++){
  U*e=table(s,t)+((va>>(39-level*9))&511);
  CK(*e&1);
  if(level==3||(level==2&&(*e&128))){return e;}
  CK((*e&mask_of(s))>=s->pa);
  t=(size_t)(((*e&mask_of(s))-s->pa)/4096);
 }
 CK(0);return NULL;
}
static void clone(struct Fixture*f){for(size_t r=1;r<NROOT;r++)memcpy(table(&f->s[r],0)+1,table(&f->s[0],0)+1,511*sizeof(U));}
static struct Fixture*fixture_width(size_t hardware,size_t private_bits,U kernel_pool,U user_pool){scenarios++;struct Fixture*f=calloc(1,sizeof*f);CK(f);for(size_t i=0;i<NROOT;i++){struct Space*s=&f->s[i];s->pa=UINT64_C(0x400000)+i*UINT64_C(0x100000);if(i==0&&kernel_pool){s->pa=kernel_pool;}if(i==1&&user_pool){s->pa=user_pool;}s->object=guard((size_t)rr_size(0),64);s->pool=guard(NTABLE*4096,4096);s->meta=guard(NTABLE,64);CK(!rr_init_width(s->object.p,s->pool.p,NTABLE,s->pa,s->meta.p,i?private_bits:hardware));}
 CK(!rr_map(f->s[0].object.p,VA,FRAME,1,0));CK(!rr_map(f->s[0].object.p,HIDDEN,FRAME,0,0));
 CK(!rr_map(f->s[0].object.p,LOW,FRAME,1,0));CK(!rr_map(f->s[0].object.p,LARGE,FRAME,0,1));
 CK(!rr_map(f->s[1].object.p,UINT64_C(0x40000000),FRAME,3,0));CK(!rr_map(f->s[2].object.p,UINT64_C(0x50000000),FRAME,6,0));clone(f);
 f->roots=guard(2*sizeof(struct Root),64);struct Root*r=(void*)f->roots.p;r[0]=(struct Root){f->s[1].object.p,3,71};r[1]=(struct Root){f->s[2].object.p,9,103};
 f->output=guard(64*sizeof(struct Alias),64);f->report=guard(sizeof(struct Report),64);f->retired=guard((size_t)rr_size(5),64);f->scratch=guard((size_t)rr_size(6),64);memset(f->scratch.p,0xc3,f->scratch.n);return f;}
static struct Fixture*fixture(void){return fixture_width(48,48,0,0);}
static size_t guards(struct Fixture*f,struct Guard**g){size_t n=0;for(size_t r=0;r<NROOT;r++){g[n++]=&f->s[r].object;g[n++]=&f->s[r].pool;g[n++]=&f->s[r].meta;}g[n++]=&f->roots;g[n++]=&f->output;g[n++]=&f->report;g[n++]=&f->retired;g[n++]=&f->scratch;return n;}
static void destroy(struct Fixture*f){struct Guard*g[14];size_t n=guards(f,g);for(size_t i=0;i<n;i++){intact(g[i]);free(g[i]->allocation);}free(f);}
struct Model{struct Alias aliases[64];size_t count;U tables,leaves;};
static void raw(struct Fixture*f,size_t r,size_t t,unsigned level,U prefix,int wr,int us,int nx,U physical,U bytes,unsigned char*seen,struct Model*m){
 struct Space*s=&f->s[r];U phys_limit=limit_of(f,r);CK(s->pa<=phys_limit&&(NTABLE-1)*4096<=phys_limit-s->pa);CK(t<NTABLE&&!seen[t]&&s->meta.p[t]==1);seen[t]=1;m->tables++;
 size_t slot_limit=(r&&level==0)?1:512;
 for(size_t slot=0;slot<slot_limit;slot++){
  U e=table(s,t)[slot];
  if(!e){continue;}
  CK(e&1);
  U va=prefix|((U)slot<<(39-level*9));
  if(!level&&slot>=256){va|=UINT64_C(0xffff000000000000);}
  int w=wr&&!!(e&2),u=us&&!!(e&4),x=nx||!!(e&NX);
  if(level<3&&!(e&128)){
   CK(!(e&~(phys_limit|NX|UINT64_C(39))));
   U pa=e&phys_limit;CK(pa>=s->pa&&pa-s->pa<NTABLE*4096);
   raw(f,r,(size_t)((pa-s->pa)/4096),level+1,va,w,u,x,physical,bytes,seen,m);
   continue;
  }
  CK(level==3||level==2);
  CK(!(e&~(phys_limit|NX|(level==2?UINT64_C(0x10ff):UINT64_C(255)))));
  CK(level!=2||!(e&UINT64_C(0x1fe000)));
  U size=level==2?UINT64_C(0x200000):4096,pa=(e&phys_limit)&~(size-1),pat=e&(level==2?UINT64_C(0x1000):128),cache=e&24;
  CK(pa<=phys_limit+4096-size&&!(w&&!x)&&!((va>>63)&&u));
  CK((cache==0||cache==24)&&!(pat&&cache));
  U flags=(w?1:0)|(u?2:0)|(!x?4:0)|(cache?8:0)|(pat?16:0);m->leaves++;
  if(pa>=physical+bytes||physical>=pa+size){continue;}
  U first=pa>physical?pa:physical,end=pa+size<physical+bytes?pa+size:physical+bytes;
  const struct Root*ids=(void*)f->roots.p;
  struct Alias next={s->pa,r?ids[r-1].identity:UINT64_MAX,r?ids[r-1].generation:0,va+(first-pa),first,end-first,flags,size};
  if(m->count){struct Alias*last=&m->aliases[m->count-1];if(last->root==next.root&&last->identity==next.identity&&last->generation==next.generation&&last->flags==next.flags&&last->leaf_bytes==next.leaf_bytes&&last->va<=UINT64_MAX-last->bytes&&last->va+last->bytes==next.va&&last->pa+last->bytes==next.pa){last->bytes+=next.bytes;continue;}}
  CK(m->count<64);m->aliases[m->count++]=next;
 }
}
static struct Model model(struct Fixture*f,U pa,U bytes){struct Model m={0};U hardware=mask_of(&f->s[0]);CK(pa&&bytes&&pa<=hardware+4095&&bytes-1<=hardware+4095-pa);for(size_t r=0;r<NROOT;r++){if(r)for(size_t i=1;i<512;i++){U expected=table(&f->s[0],0)[i],actual=table(&f->s[r],0)[i];CK(((actual^expected)&~UINT64_C(32))==0&&!(expected==0&&actual!=0));}unsigned char seen[NTABLE]={0};raw(f,r,0,0,0,1,1,0,pa,bytes,seen,&m);for(size_t i=0;i<NTABLE;i++)CK((f->s[r].meta.p[i]==1)==!!seen[i]);}return m;}
static void mismatch(const char*tag,U got){fprintf(stderr,"roots oracle: %s; audit returned 0x%llx normally\n",tag,(unsigned long long)got);exit(1);}
static U invoke(struct Fixture*f,const struct Root*roots,size_t count,U pa,U bytes,struct Alias*out,size_t capacity,struct Report*report){return rr_audit(f->s[0].object.p,roots,count,pa,bytes,out,capacity,report,f->scratch.p);}
static void audited(struct Fixture*f,U pa,U bytes){struct Model m=model(f,pa,bytes);struct Guard*g[14];size_t n=guards(f,g);unsigned char*before[14];for(size_t i=0;i<n;i++){before[i]=malloc(g[i]->n);CK(before[i]);memcpy(before[i],g[i]->p,g[i]->n);}U rc=invoke(f,(void*)f->roots.p,2,pa,bytes,(void*)f->output.p,64,(void*)f->report.p);if(rc||memcmp(f->output.p,m.aliases,m.count*sizeof(struct Alias)))mismatch("hidden-alias",rc);struct Report expected={3,m.tables,m.leaves,m.count,1022,1,pa,bytes};if(memcmp(f->report.p,&expected,sizeof expected))mismatch("raw-report",rc);
 for(size_t i=0;i<n;i++){if(g[i]==&f->output)CK(!memcmp(g[i]->p+m.count*sizeof(struct Alias),before[i]+m.count*sizeof(struct Alias),g[i]->n-m.count*sizeof(struct Alias)));else if(g[i]!=&f->report&&g[i]!=&f->scratch)CK(!memcmp(g[i]->p,before[i],g[i]->n));intact(g[i]);free(before[i]);}}
static void rejected(struct Fixture*f,U expected,const char*tag,const struct Root*roots,size_t count,U pa,U bytes,struct Alias*out,size_t capacity,struct Report*report){struct Guard*g[14];size_t n=guards(f,g);unsigned char*before[14];for(size_t i=0;i<n;i++){before[i]=malloc(g[i]->n);CK(before[i]);memcpy(before[i],g[i]->p,g[i]->n);}U rc=invoke(f,roots,count,pa,bytes,out,capacity,report);if(rc!=expected)mismatch(tag,rc);for(size_t i=0;i<n;i++){if(g[i]!=&f->scratch&&memcmp(g[i]->p,before[i],g[i]->n))mismatch("failure-atomic",rc);intact(g[i]);free(before[i]);}}
static void reject(struct Fixture*f,U expected,const char*tag){rejected(f,expected,tag,(void*)f->roots.p,2,FRAME+17,100,(void*)f->output.p,64,(void*)f->report.p);}
static void width_positive(void){
 const size_t bits[]={36,40,46,52};
 for(size_t i=0;i<sizeof bits/sizeof bits[0];i++){
  struct Fixture*f=fixture_width(bits[i],48,0,0);
  CK(mask_of(&f->s[0])==((UINT64_C(1)<<bits[i])-4096));
  CK(mask_of(&f->s[1])==((UINT64_C(1)<<48)-4096));
  audited(f,FRAME+17,100);
  audited(f,(UINT64_C(1)<<bits[i])-1,1);
  destroy(f);
 }
 /* Shared branches are canonical hardware-width objects, not private48
    trees. Both their high table pointers and high leaves remain legitimate. */
 U high=UINT64_C(1)<<48;
 struct Fixture*f=fixture_width(52,48,high+UINT64_C(0x400000),0);
 CK(table(&f->s[1],0)[1]&high);
 CK(!rr_map(f->s[0].object.p,LARGE+UINT64_C(0x400000),high,1,0));
 clone(f);
 audited(f,FRAME+17,100);
 audited(f,high+17,100);
 CK(((struct Report*)(void*)f->report.p)->aliases==1);
 destroy(f);
 printf("runtime roots widths=36,40,46,52 private48; canonical52 shared-high passed\n");
}
/* A raw corruption has a precisely independently decoded cause before the
   production audit runs. Rejection snapshots check every source/output byte. */
static void width_reject(size_t hardware,int private_bound,unsigned kind){
 struct Fixture*f=fixture_width(hardware,48,0,0);
 struct Space*s=&f->s[1];
 U limit=limit_of(f,1),high=UINT64_C(1)<<(private_bound?48:hardware);
 const char*tag=private_bound?"private-width":"hardware-width";
 U expected=5;
 if(kind<2){
  U physical=kind==0?(s->pa|high):(limit+4096-16*4096);
  ((U*)(void*)s->object.p)[3]=physical;
  CK(physical>limit||(NTABLE-1)*4096>limit-physical);
  expected=1;
 }else if(kind==2){
  table(s,0)[0]|=high;
  CK(table(s,0)[0]&~(limit|NX|UINT64_C(39)));
 }else if(kind==3){
  U*entry=leaf(s,UINT64_C(0x40000000));
  *entry|=high;
  CK(*entry&~(limit|NX|UINT64_C(255)));
  tag=private_bound?"private-leaf-width":"hardware-leaf-width";
 }else if(kind==4){
  CK(!rr_map(s->object.p,UINT64_C(0x2000000),FRAME,3,1));
  U*entry=leaf(s,UINT64_C(0x2000000));
  *entry|=high;
  CK(*entry&~(limit|NX|UINT64_C(0x10ff)));
 }else{
  U pa=mask_of(&f->s[0])+4096;
  rejected(f,1,"hardware-query-width",(void*)f->roots.p,2,pa,1,
           (void*)f->output.p,64,(void*)f->report.p);
  /* The final valid byte followed by two bytes also crosses the hardware
     boundary without a u64 overflow; this must be refused independently. */
  rejected(f,1,"hardware-query-tail",(void*)f->roots.p,2,pa-1,2,
           (void*)f->output.p,64,(void*)f->report.p);
  destroy(f);
  return;
 }
 reject(f,expected,tag);
 destroy(f);
}
static void width_boundaries(void){
 const size_t bits[]={36,40,46};
 for(size_t i=0;i<sizeof bits/sizeof bits[0];i++){
  for(unsigned kind=0;kind<6;kind++){width_reject(bits[i],0,kind);}
 }
 for(unsigned kind=0;kind<5;kind++){width_reject(52,1,kind);}
}
static void touched(struct Space*s,size_t t,unsigned level,int private_only){
 size_t limit=private_only&&!level?1:512;
 for(size_t i=0;i<limit;i++){
  U*e=table(s,t)+i;
  if(!(*e&1)){continue;}
  if(level==3||(level==2&&(*e&128))){*e|=96;}
  else{
   *e|=32;
   touched(s,(size_t)(((*e&mask_of(s))-s->pa)/4096),level+1,private_only);
  }
 }
}
static void positive(void){struct Fixture*f=fixture();audited(f,FRAME+17,100);CK(((struct Report*)(void*)f->report.p)->aliases==6);audited(f,FRAME+4090,20);audited(f,FRAME+UINT64_C(0x1ffff0),16);audited(f,UINT64_C(0x90000000),100);table(&f->s[1],0)[1]|=32;table(&f->s[1],0)[0]&=~UINT64_C(2);table(&f->s[2],0)[0]|=NX;audited(f,FRAME,4096);destroy(f);
 f=fixture();for(unsigned r=0;r<NROOT;r++)touched(&f->s[r],0,0,r!=0);audited(f,FRAME+17,100);destroy(f);
 f=fixture();CK(!rr_map(f->s[1].object.p,UINT64_C(0x70000000),FRAME,19,0));CK(!rr_map(f->s[1].object.p,UINT64_C(0x70001000),FRAME,11,0));CK(!rr_map(f->s[0].object.p,UINT64_C(0xffffac0000000000),FRAME,16,1));clone(f);audited(f,FRAME+23,97);destroy(f);
}
static void shared(void){struct Fixture*f=fixture();table(&f->s[1],0)[1]^=2;reject(f,3,"shared-slot1");destroy(f);f=fixture();table(&f->s[1],0)[2]=32;reject(f,3,"shared-zero-A");destroy(f);f=fixture();table(&f->s[1],0)[1]|=64;reject(f,3,"shared-nonleaf-D");destroy(f);}
static void foreign(void){struct Fixture*f=fixture();table(&f->s[1],0)[0]=f->s[0].pa|7;reject(f,4,"foreign-private");destroy(f);}
static void invalids(void){for(unsigned k=0;k<26;k++){struct Fixture*f=fixture();struct Root*r=(void*)f->roots.p;U expected=5;switch(k){
 case 0:table(&f->s[1],0)[0]=f->s[1].pa|7;break;
 case 1:table(&f->s[1],0)[0]&=~UINT64_C(1);break;
 case 2:f->s[1].meta.p[NTABLE-1]=1;expected=6;break;
 case 3:f->s[1].meta.p[NTABLE-1]=2;expected=7;break;
 case 4:f->s[1].meta.p[0]=0;expected=6;break;
 case 5:r[1].identity=r[0].identity;expected=1;break;
 case 6:r[0].generation=0;expected=1;break;
 case 7:r[0].identity=16;expected=1;break;
 case 8:r[1].space=r[0].space;expected=8;break;
 case 9:r[0].space=(void*)(uintptr_t)(UINT64_MAX-7);expected=1;break;
 case 10:{U*e=table(&f->s[1],0);U child=(*e&mask_of(&f->s[1]))-f->s[1].pa;table(&f->s[1],(size_t)(child/4096))[1]=*e;break;}
 case 11:table(&f->s[1],0)[0]|=128;break;
 case 12:table(&f->s[1],0)[0]|=64;break;
 case 13:f->s[1].meta.p[NTABLE-1]=3;break;
 case 14:((U*)(void*)f->s[1].object.p)[5]=UINT64_MAX;expected=1;break;
 case 15:((U*)(void*)f->s[1].object.p)[7]=NTABLE+1;expected=1;break;
 case 16:((U*)(void*)f->s[1].object.p)[3]=f->s[0].pa;expected=8;break;
 case 17:*leaf(&f->s[1],UINT64_C(0x40000000))&=~NX;break;
 case 18:*leaf(&f->s[1],UINT64_C(0x40000000))|=256;break;
 case 19:*leaf(&f->s[0],VA)|=4;break;
 case 20:*leaf(&f->s[0],LARGE)|=8192;break;
 case 21:*leaf(&f->s[1],UINT64_C(0x40000000))|=152;break;
 case 22:((U*)(void*)f->s[1].object.p)[4]=(U)(uintptr_t)f->s[1].pool.p;expected=8;break;
 case 23:((U*)(void*)f->s[1].object.p)[2]=257;expected=1;break;
 case 24:((U*)(void*)f->s[1].object.p)[1]=UINT64_MAX-4095;expected=1;break;
 case 25:((U*)(void*)f->s[1].object.p)[3]=UINT64_MAX-4095;expected=1;break;
 }reject(f,expected,"malformed-forest");destroy(f);}}
static void boundary(void){struct Fixture*f=fixture();struct Root*r=(void*)f->roots.p;struct Alias*a=(void*)f->output.p;struct Report*p=(void*)f->report.p;
 rejected(f,1,"zero-pa",r,2,0,1,a,64,p);rejected(f,1,"zero-bytes",r,2,FRAME,0,a,64,p);rejected(f,1,"range-overflow",r,2,UINT64_MAX-1,3,a,64,p);rejected(f,1,"range-width",r,2,UINT64_C(1)<<48,1,a,64,p);
 rejected(f,1,"users-bound",r,17,FRAME,1,a,64,p);rejected(f,1,"output-bound",r,2,FRAME,1,a,65,p);rejected(f,2,"output-capacity",r,2,FRAME,1,a,5,p);rejected(f,2,"output-zero",r,2,FRAME,1,NULL,0,p);
 rejected(f,1,"bad-users",(void*)(uintptr_t)(UINT64_MAX-7),2,FRAME,1,a,64,p);rejected(f,1,"bad-output",r,2,FRAME,1,(void*)(uintptr_t)(UINT64_MAX-7),64,p);rejected(f,1,"bad-report",r,2,FRAME,1,a,64,(void*)(uintptr_t)(UINT64_MAX-7));
 rejected(f,1,"unaligned-output",r,2,FRAME,1,(void*)(f->output.p+1),63,p);rejected(f,8,"output-report",r,2,FRAME,1,a,64,(void*)(f->output.p+8));
 struct Guard*g[14];size_t n=guards(f,g);for(size_t i=0;i<n;i++)if(g[i]!=&f->output&&g[i]!=&f->report&&g[i]!=&f->retired){size_t offset=g[i]->n>=sizeof(struct Alias)?g[i]->n-sizeof(struct Alias):0;offset&=~(size_t)7;rejected(f,8,"output-input",r,2,FRAME,1,(void*)(g[i]->p+offset),1,p);offset=g[i]->n>=sizeof(struct Report)?g[i]->n-sizeof(struct Report):0;offset&=~(size_t)7;rejected(f,8,"report-input",r,2,FRAME,1,a,64,(void*)(g[i]->p+offset));}
 destroy(f);
}
static void workspace_rejected(struct Fixture*f,void*scratch,U expected,const char*tag){struct Guard*g[14];size_t n=guards(f,g);unsigned char*before[14];for(size_t i=0;i<n;i++){before[i]=malloc(g[i]->n);CK(before[i]);memcpy(before[i],g[i]->p,g[i]->n);}U rc=rr_audit(f->s[0].object.p,(void*)f->roots.p,2,FRAME,1,(void*)f->output.p,64,(void*)f->report.p,scratch);if(rc!=expected)mismatch(tag,rc);for(size_t i=0;i<n;i++){if(memcmp(g[i]->p,before[i],g[i]->n))mismatch("workspace-preflight-write",rc);intact(g[i]);free(before[i]);}}
static void workspace_boundaries(void){struct Fixture*f=fixture();workspace_rejected(f,NULL,1,"workspace-null");workspace_rejected(f,f->scratch.p+1,1,"workspace-unaligned");workspace_rejected(f,(void*)(uintptr_t)(UINT64_MAX-63),1,"workspace-overflow");struct Guard*g[14];size_t n=guards(f,g);for(size_t i=0;i<n;i++)if(g[i]!=&f->scratch&&g[i]!=&f->retired)workspace_rejected(f,g[i]->p,8,"workspace-input-output-overlap");workspace_rejected(f,f->s[0].pool.p+f->s[0].pool.n-64,8,"workspace-partial-pool-overlap");audited(f,FRAME,1);memset(f->scratch.p,0x5c,f->scratch.n);audited(f,FRAME+17,100);destroy(f);}
static void capacity(void){struct Fixture*f=fixture();for(U i=0;i<65;i++)CK(!rr_map(f->s[0].object.p,VA+UINT64_C(0x100000)+i*4096,FRAME,0,0));reject(f,2,"internal-capacity");destroy(f);}
static void splits(void){struct Fixture*f=fixture();U base=UINT64_C(0x2000000),at=base+237*4096;CK(!rr_map(f->s[1].object.p,base,FRAME,3,1));audited(f,FRAME,UINT64_C(0x400000));CK(!rr_split(f->s[1].object.p,base));audited(f,FRAME,UINT64_C(0x400000));CK(((struct Report*)(void*)f->report.p)->leaves==518&&((struct Report*)(void*)f->report.p)->aliases==7);
 CK(!rr_protect(f->s[1].object.p,at,2));audited(f,FRAME,UINT64_C(0x400000));CK(((struct Report*)(void*)f->report.p)->aliases==9);
 CK(!rr_replace(f->s[1].object.p,at,FRAME+UINT64_C(0x300000),3));audited(f,FRAME,UINT64_C(0x400000));CK(((struct Report*)(void*)f->report.p)->aliases==9);
 CK(!rr_map(f->s[0].object.p,LARGE+UINT64_C(0x200000),FRAME+UINT64_C(0x200000),0,0));audited(f,FRAME+UINT64_C(0x1ffff0),32);CK(((struct Report*)(void*)f->report.p)->aliases==3);struct Alias*a=(void*)f->output.p;CK(a[0].leaf_bytes==UINT64_C(0x200000)&&a[1].leaf_bytes==4096);destroy(f);}
static void maximum(void){struct Space s[17];memset(s,0,sizeof s);struct Root roots[16];unsigned char*copies[17][3];for(size_t i=0;i<17;i++){s[i].pa=UINT64_C(0x2000000)+i*UINT64_C(0x100000);s[i].object=guard((size_t)rr_size(0),8);s[i].pool=guard(NTABLE*4096,4096);s[i].meta=guard(NTABLE,8);CK(!rr_init(s[i].object.p,s[i].pool.p,NTABLE,s[i].pa,s[i].meta.p));}CK(!rr_map(s[0].object.p,VA,FRAME,1,0));for(size_t i=1;i<17;i++){memcpy(table(&s[i],0)+1,table(&s[0],0)+1,511*sizeof(U));roots[i-1]=(struct Root){s[i].object.p,i-1,i+10};}
 for(size_t i=0;i<17;i++){struct Guard*g[]={&s[i].object,&s[i].pool,&s[i].meta};for(size_t j=0;j<3;j++){copies[i][j]=malloc(g[j]->n);CK(copies[i][j]);memcpy(copies[i][j],g[j]->p,g[j]->n);}}
 struct Guard workspace=guard((size_t)rr_size(6),64);memset(workspace.p,0x7b,workspace.n);struct Alias a[64];struct Report report;memset(a,0x73,sizeof a);struct Root saved[16];memcpy(saved,roots,sizeof saved);CK(!rr_audit(s[0].object.p,roots,16,FRAME,1,a,64,&report,workspace.p));struct Report expected={17,20,1,1,16*511,1,FRAME,1};CK(!memcmp(&report,&expected,sizeof report));struct Alias alias={s[0].pa,UINT64_MAX,0,VA,FRAME,1,1,4096};CK(!memcmp(a,&alias,sizeof alias)&&!memcmp(saved,roots,sizeof saved));for(size_t i=sizeof alias;i<sizeof a;i++)CK(((unsigned char*)a)[i]==0x73);
 CK(!rr_audit(s[0].object.p,NULL,0,FRAME,1,a,64,&report,workspace.p)&&report.roots==1&&report.tables==4&&report.shared_entries==0&&report.aliases==1);intact(&workspace);free(workspace.allocation);
 for(size_t i=0;i<17;i++){struct Guard*g[]={&s[i].object,&s[i].pool,&s[i].meta};for(size_t j=0;j<3;j++){CK(!memcmp(copies[i][j],g[j]->p,g[j]->n));intact(g[j]);free(copies[i][j]);free(g[j]->allocation);}}scenarios++;}
static void pending(void){struct Fixture*f=fixture();CK(!rr_map(f->s[1].object.p,UINT64_C(0x6000000000),FRAME+4096,3,0));CK(!rr_unmap(f->s[1].object.p,UINT64_C(0x6000000000),f->retired.p));int found=0;for(size_t i=0;i<NTABLE;i++)found|=f->s[1].meta.p[i]==2;CK(found);reject(f,7,"retired-isolated");destroy(f);}
int main(int argc,char**argv){CK(argc==2&&rr_size(0)==64&&rr_size(1)==sizeof(struct Root)&&rr_size(2)==sizeof(struct Alias)&&rr_size(3)==sizeof(struct Report)&&rr_size(4)==56&&rr_size(6)>=64*sizeof(struct Alias)+17*56&&rr_size(6)%64==0);if(!strcmp(argv[1],"shared"))shared();else if(!strcmp(argv[1],"foreign"))foreign();else if(!strcmp(argv[1],"hardware-width"))width_reject(36,0,3);else if(!strcmp(argv[1],"private-width"))width_reject(52,1,3);else if(!strcmp(argv[1],"hidden")){struct Fixture*f=fixture();audited(f,FRAME+17,100);destroy(f);}else{positive();width_positive();width_boundaries();shared();foreign();invalids();boundary();workspace_boundaries();capacity();splits();maximum();pending();}printf("runtime roots raw oracle checks=%u scenarios=%u passed; privileged instructions not executed\n",checks,scenarios);return 0;}
