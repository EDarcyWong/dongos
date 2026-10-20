/* mm.paging tests: public ABI plus an independent walk of x86-64 page entries.
 * No private Space offsets are used. Physical pool addresses are numbers and
 * deliberately differ from the aligned C heap addresses backing the tables. */
#define _GNU_SOURCE
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define PAGE UINT64_C(4096)
#define NX (UINT64_C(1)<<63)
#define P UINT64_C(1)
#define W UINT64_C(2)
#define U UINT64_C(4)
#define PWT UINT64_C(8)
#define PCD UINT64_C(16)
#define CACHE (PWT|PCD)
#define A UINT64_C(32)
#define D UINT64_C(64)
#define ADDRESS UINT64_C(0x000ffffffffff000)
#define E_NOT_INIT UINT64_C(0x02000001)
#define E_ALREADY_INIT UINT64_C(0x02000002)
#define E_INVALID UINT64_C(0x02000003)
#define E_META UINT64_C(0x02000004)
#define E_OOM UINT64_C(0x02000007)
#define E_MAPPED UINT64_C(0x02030001)
#define E_NOT_MAPPED UINT64_C(0x02030002)
#define E_MALFORMED UINT64_C(0x02030003)
#define E_NO_NX UINT64_C(0x02030004)
struct Mapping {uint64_t physical,flags;};
extern uint64_t DG pg_space_size(void),pg_space_align(void),pg_table_size(void),pg_table_align(void),pg_mapping_size(void);
extern uint64_t DG pg_uncached_flag(void);
extern void DG pg_reset(void*);
extern uint64_t DG pg_init(void*,void*,uint64_t,uint64_t,void*,uint64_t,uint64_t,uint8_t);
extern uint64_t DG pg_root(const void*,uint64_t*),pg_used(const void*,uint64_t*);
extern uint64_t DG pg_map(void*,uint64_t,uint64_t,uint64_t),pg_unmap(void*,uint64_t),pg_protect(void*,uint64_t,uint64_t);
extern uint64_t DG pg_query(const void*,uint64_t,struct Mapping*);
static const char *phase="startup";
static unsigned step;
#define CHECK(X) do{if(!(X)){fprintf(stderr,"paging failure %s step=%u line=%d: %s\n",phase,step,__LINE__,#X);exit(1);}}while(0)
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
 fprintf(stderr,"unexpected paging panic kind=%u line=%u file=%.*s phase=%s step=%u\n",kind,line,(int)length,(const char*)file,phase,step);exit(99);
}
struct Guard {uint8_t *raw,*data;size_t size,guard;};
static struct Guard guarded(size_t size,size_t alignment){
 struct Guard b={0};b.size=size;b.guard=alignment<16?16:alignment;
 b.raw=malloc(size+3*b.guard+alignment);CHECK(b.raw!=NULL);
 b.data=(uint8_t*)(((uintptr_t)(b.raw+b.guard)+alignment-1)&~(uintptr_t)(alignment-1));
 memset(b.data-b.guard,0xa5,b.guard);memset(b.data,0x6b,size);memset(b.data+size,0x5a,b.guard);return b;
}
static void guards(const struct Guard *b){for(size_t i=0;i<b->guard;i++){CHECK(b->data[-(ptrdiff_t)b->guard+(ptrdiff_t)i]==0xa5);CHECK(b->data[b->size+i]==0x5a);}}
struct Fixture {struct Guard state,pool,meta;size_t count;uint64_t physical;unsigned bits;};
static struct Fixture fixture(size_t count,uint64_t physical,unsigned bits,int nx,int initialize){
 struct Fixture f={guarded((size_t)pg_space_size(),(size_t)pg_space_align()),guarded(count*4096,4096),guarded(count+16,8),count,physical,bits};
 pg_reset(f.state.data);
 CHECK((uintptr_t)f.pool.data!=physical);
 if(initialize)CHECK(pg_init(f.state.data,f.pool.data,count,physical,f.meta.data,count+16,bits,(uint8_t)nx)==0);
 return f;
}
static void intact(const struct Fixture *f){guards(&f->state);guards(&f->pool);guards(&f->meta);for(size_t i=f->count;i<f->meta.size;i++)CHECK(f->meta.data[i]==0x6b);}
static void destroy(struct Fixture *f){intact(f);free(f->state.raw);free(f->pool.raw);free(f->meta.raw);}
struct Snapshot {uint8_t *state,*pool,*meta;};
static struct Snapshot snapshot(const struct Fixture *f){
 struct Snapshot s={malloc(f->state.size),malloc(f->pool.size),malloc(f->meta.size)};CHECK(s.state&&s.pool&&s.meta);
 memcpy(s.state,f->state.data,f->state.size);memcpy(s.pool,f->pool.data,f->pool.size);memcpy(s.meta,f->meta.data,f->meta.size);return s;
}
static void unchanged(const struct Fixture *f,struct Snapshot s){
 CHECK(!memcmp(s.state,f->state.data,f->state.size));CHECK(!memcmp(s.pool,f->pool.data,f->pool.size));CHECK(!memcmp(s.meta,f->meta.data,f->meta.size));intact(f);
 free(s.state);free(s.pool);free(s.meta);
}
#define FAIL_UNCHANGED(F,CALL,CODE) do{struct Snapshot before=snapshot(F);CHECK((CALL)==(CODE));unchanged(F,before);}while(0)
static uint64_t used(const struct Fixture *f){uint64_t n=UINT64_MAX;CHECK(pg_used(f->state.data,&n)==0);return n;}
static uint64_t root(const struct Fixture *f){uint64_t n=UINT64_MAX;CHECK(pg_root(f->state.data,&n)==0);return n;}
static unsigned index_at(uint64_t va,unsigned level){return (unsigned)((va>>(39-9*level))&511);}
struct Path {uint64_t *entry[4];size_t slot[4];};
/* Independent hardware-format oracle: resolve physical table numbers to the
 * C backing pool, then interpret raw P/W/U/NX/PCD/PWT and the 4KiB offset. */
static int raw_walk(const struct Fixture *f,uint64_t va,struct Mapping *out,struct Path *path){
 size_t slot=0;uint64_t *tables=(uint64_t*)f->pool.data;
 for(unsigned level=0;level<4;level++){
  CHECK(slot<f->count);CHECK(f->meta.data[slot]==1);
  uint64_t *where=&tables[slot*512+index_at(va,level)],e=*where;
  if(path){path->entry[level]=where;path->slot[level]=slot;}
  if(!(e&P)){CHECK(e==0);return 0;}
  if(level==3){
   CHECK(!(e&~(ADDRESS|P|W|U|CACHE|A|D|NX)));
   CHECK((e&CACHE)==0||(e&CACHE)==CACHE);
   CHECK(!((e&W)&&!(e&NX)));
   out->physical=(e&ADDRESS)|(va&4095);
   out->flags=((e&W)?1:0)|((e&U)?2:0)|((e&NX)?0:4)|((e&CACHE)?8:0);return 1;
  }
  CHECK((e&7)==7);CHECK(!(e&~(ADDRESS|7|A)));
  uint64_t address=e&ADDRESS;CHECK(address>=f->physical);CHECK((address-f->physical)%PAGE==0);
  slot=(size_t)((address-f->physical)/PAGE);
 }
 return 0;
}
static void mapping(const struct Fixture *f,uint64_t va,uint64_t physical,uint64_t flags){
 struct Mapping raw={0};struct {uint64_t before;struct Mapping got;uint64_t after;} out={UINT64_C(0xabcdef0123456789),{UINT64_MAX,UINT64_MAX},UINT64_C(0x9876543210fedcba)};CHECK(raw_walk(f,va,&raw,NULL));CHECK(raw.physical==physical&&raw.flags==flags);
 CHECK(pg_query(f->state.data,va,&out.got)==0);CHECK(out.got.physical==physical&&out.got.flags==flags);CHECK(out.before==UINT64_C(0xabcdef0123456789)&&out.after==UINT64_C(0x9876543210fedcba));intact(f);
}
static void query_fail(const struct Fixture *f,uint64_t va,uint64_t code){
 struct {uint64_t before;struct Mapping value;uint64_t after;} out={UINT64_C(0x1122334455667788),{UINT64_C(0x123456789abcdef0),UINT64_C(0xfedcba9876543210)},UINT64_C(0x8877665544332211)},before=out;
 FAIL_UNCHANGED(f,pg_query(f->state.data,va,&out.value),code);CHECK(!memcmp(&out,&before,sizeof out));
}
static void init_tests(void){
 phase="init/layout";CHECK(pg_table_size()==4096&&pg_table_align()==4096&&pg_mapping_size()==16);CHECK(pg_space_align()>=8);CHECK(pg_uncached_flag()==8);
 struct Fixture f=fixture(8,UINT64_C(0x0008000000000000),52,1,0);
 uint64_t out=UINT64_C(0xaabbccddeeff0011);
 FAIL_UNCHANGED(&f,pg_root(f.state.data,&out),E_NOT_INIT);CHECK(out==UINT64_C(0xaabbccddeeff0011));
 FAIL_UNCHANGED(&f,pg_used(f.state.data,&out),E_NOT_INIT);CHECK(out==UINT64_C(0xaabbccddeeff0011));
 FAIL_UNCHANGED(&f,pg_map(f.state.data,0,0,1),E_NOT_INIT);
 FAIL_UNCHANGED(&f,pg_unmap(f.state.data,0),E_NOT_INIT);
 FAIL_UNCHANGED(&f,pg_protect(f.state.data,0,0),E_NOT_INIT);query_fail(&f,0,E_NOT_INIT);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,0,f.physical,f.meta.data,8,52,1),E_INVALID);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,NULL,8,f.physical,f.meta.data,8,52,1),E_INVALID);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,UINT64_MAX,0,f.meta.data,UINT64_MAX,52,1),E_INVALID);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,8,f.physical,NULL,0,52,1),E_META);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data+8,8,f.physical,f.meta.data,8,52,1),E_INVALID);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,8,f.physical+1,f.meta.data,8,52,1),E_INVALID);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,8,f.physical,f.meta.data,7,52,1),E_META);
 for(unsigned bits=0;bits<=64;bits++)if(bits<32||bits>52)FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,8,0,f.meta.data,8,bits,1),E_INVALID);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,8,UINT64_C(0xfffffffffffff000),f.meta.data,8,52,1),E_INVALID);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,8,(UINT64_C(1)<<32)-PAGE,f.meta.data,8,32,1),E_INVALID);
 CHECK(pg_init(f.state.data,f.pool.data,8,f.physical,f.meta.data,8,52,1)==0);CHECK(root(&f)==f.physical&&used(&f)==1);
 for(size_t i=0;i<4096;i++)CHECK(f.pool.data[i]==0);
 for(size_t i=4096;i<f.pool.size;i++)CHECK(f.pool.data[i]==0x6b);
 CHECK(f.meta.data[0]==1);for(size_t i=1;i<8;i++)CHECK(f.meta.data[i]==0);
 FAIL_UNCHANGED(&f,pg_init(f.state.data,f.pool.data,8,f.physical,f.meta.data,8,52,1),E_ALREADY_INIT);destroy(&f);
 f=fixture(1,(UINT64_C(1)<<32)-PAGE,32,0,1);CHECK(root(&f)==(UINT64_C(1)<<32)-PAGE);destroy(&f);
 f=fixture(1,0,32,1,1);CHECK(root(&f)==0);destroy(&f);
}
static void basic_tests(void){
 phase="raw bits/canonical/alias";struct Fixture f=fixture(64,UINT64_C(0x0008000000000000),52,1,1);
 const uint64_t vas[]={0,0x1000,0x1ff000,0x200000,0x3ffff000,0x40000000,UINT64_C(0x7ffffff000),UINT64_C(0x8000000000),UINT64_C(0x7ffffffff000),UINT64_C(0xffff800000000000),UINT64_C(0xfffffffffffff000)};
 const uint64_t flags[]={0,1,2,3,4,6,0,1,4,1,4};
 for(size_t i=0;i<sizeof vas/sizeof vas[0];i++){
  uint64_t pa=i==0?0:UINT64_C(0x0009000000000000)+i*PAGE;
  CHECK(pg_map(f.state.data,vas[i],pa,flags[i])==0);mapping(&f,vas[i],pa,flags[i]);mapping(&f,vas[i]+4095,pa+4095,flags[i]);
  struct Path path;struct Mapping got;CHECK(raw_walk(&f,vas[i],&got,&path));CHECK(!(*path.entry[3]&(A|D)));
 }
 uint64_t same=UINT64_C(0x0009000000001000);
 CHECK(pg_map(f.state.data,0x6000,same,1)==0);CHECK(pg_map(f.state.data,0x7000,same,4)==0);
 CHECK(pg_protect(f.state.data,0x6000,0)==0);mapping(&f,0x6000,same,0);mapping(&f,0x7000,same,4);
 struct Path path;struct Mapping got;CHECK(raw_walk(&f,0x6000,&got,&path));
 for(unsigned i=0;i<3;i++){*path.entry[i]|=A;}*path.entry[3]|=A|D;
 CHECK(pg_protect(f.state.data,0x6000,1)==0);mapping(&f,0x6000,same,1);CHECK((*path.entry[3]&(A|D))==(A|D));for(unsigned i=0;i<3;i++)CHECK(*path.entry[i]&A);
 CHECK(pg_protect(f.state.data,0x6000,4)==0);mapping(&f,0x6000,same,4);CHECK((*path.entry[3]&(A|D))==(A|D));CHECK(!(*path.entry[3]&NX));
 CHECK(pg_protect(f.state.data,0x6000,1)==0);mapping(&f,0x6000,same,1);CHECK((*path.entry[3]&(A|D))==(A|D));
 FAIL_UNCHANGED(&f,pg_map(f.state.data,0,same,1),E_MAPPED);query_fail(&f,0x3000,E_NOT_MAPPED);
 FAIL_UNCHANGED(&f,pg_unmap(f.state.data,0x3000),E_NOT_MAPPED);FAIL_UNCHANGED(&f,pg_protect(f.state.data,0x3000,1),E_NOT_MAPPED);
 const uint64_t badva[]={1,0xfff,UINT64_C(0x0000800000000000),UINT64_C(0xffff7ffffffff000)};
 for(size_t i=0;i<sizeof badva/sizeof badva[0];i++){
  FAIL_UNCHANGED(&f,pg_map(f.state.data,badva[i],same,1),E_INVALID);FAIL_UNCHANGED(&f,pg_unmap(f.state.data,badva[i]),E_INVALID);FAIL_UNCHANGED(&f,pg_protect(f.state.data,badva[i],1),E_INVALID);
  if(badva[i]&~UINT64_C(4095))query_fail(&f,badva[i],E_INVALID);
 }
 FAIL_UNCHANGED(&f,pg_map(f.state.data,0x8000,1,1),E_INVALID);FAIL_UNCHANGED(&f,pg_map(f.state.data,0x8000,UINT64_C(1)<<52,1),E_INVALID);
 const uint64_t badflags[]={5,7,13,15,24,32,UINT64_MAX};for(size_t i=0;i<sizeof badflags/sizeof badflags[0];i++){
  FAIL_UNCHANGED(&f,pg_map(f.state.data,0x8000,same,badflags[i]),E_INVALID);FAIL_UNCHANGED(&f,pg_protect(f.state.data,0,badflags[i]),E_INVALID);
 }
 FAIL_UNCHANGED(&f,pg_map(f.state.data,UINT64_C(0xffff800000001000),same,2),E_INVALID);FAIL_UNCHANGED(&f,pg_protect(f.state.data,UINT64_C(0xffff800000000000),2),E_INVALID);
 destroy(&f);
 f=fixture(8,0x100000,32,0,1);FAIL_UNCHANGED(&f,pg_map(f.state.data,0,0,0),E_NO_NX);CHECK(pg_map(f.state.data,0,0xfffff000,4)==0);mapping(&f,123,UINT64_C(0xfffff07b),4);
 FAIL_UNCHANGED(&f,pg_protect(f.state.data,0,0),E_NO_NX);CHECK(pg_protect(f.state.data,0,4)==0);FAIL_UNCHANGED(&f,pg_map(f.state.data,0x1000,UINT64_C(1)<<32,4),E_INVALID);destroy(&f);
}
static void physical_width_tests(void){
 phase="physical widths32..52";
 for(unsigned bits=32;bits<=52;bits++){
  struct Fixture f=fixture(4,0x100000,bits,1,1);uint64_t last=(UINT64_C(1)<<bits)-PAGE;
  CHECK(pg_map(f.state.data,0,last,1)==0);mapping(&f,4095,last+4095,1);
  FAIL_UNCHANGED(&f,pg_map(f.state.data,0x1000,UINT64_C(1)<<bits,1),E_INVALID);
  CHECK(pg_unmap(f.state.data,0)==0);CHECK(used(&f)==1);destroy(&f);
 }
}
static void exhaustion_tests(void){
 phase="OOM transaction/recycle";
 for(size_t count=1;count<=3;count++){
  struct Fixture f=fixture(count,0x200000,40,1,1);FAIL_UNCHANGED(&f,pg_map(f.state.data,0,0x100000000,1),E_OOM);CHECK(used(&f)==1);destroy(&f);
 }
 const uint64_t missing_va[]={0x200000,0x40000000,UINT64_C(0x8000000000)};
 for(unsigned missing=1;missing<=3;missing++)for(unsigned spare=0;spare<missing;spare++){
  struct Fixture f=fixture(4+spare,0x300000,40,1,1);CHECK(pg_map(f.state.data,0,0x100000000,1)==0);CHECK(used(&f)==4);
  FAIL_UNCHANGED(&f,pg_map(f.state.data,missing_va[missing-1],0x100001000,1),E_OOM);CHECK(used(&f)==4);mapping(&f,0,0x100000000,1);destroy(&f);
 }
 struct Fixture f=fixture(4,0x400000,40,1,1);
 CHECK(pg_map(f.state.data,0,0x100000000,1)==0);CHECK(pg_map(f.state.data,0x1000,0x100001000,1)==0);CHECK(used(&f)==4);
 CHECK(pg_unmap(f.state.data,0)==0);CHECK(used(&f)==4);CHECK(pg_unmap(f.state.data,0x1000)==0);CHECK(used(&f)==1);
 for(unsigned i=0;i<120;i++){
  uint64_t va=((uint64_t)(i%256)<<39)|((uint64_t)(i%512)<<30)|((uint64_t)i<<21);
  CHECK(pg_map(f.state.data,va,0x100000000+(uint64_t)i*PAGE,1)==0);CHECK(used(&f)==4);CHECK(pg_unmap(f.state.data,va)==0);CHECK(used(&f)==1);query_fail(&f,va,E_NOT_MAPPED);
  for(size_t j=1;j<f.count;j++)CHECK(f.meta.data[j]==0);
 }
 destroy(&f);
 struct Fixture a=fixture(4,0x500000,40,1,1),b=fixture(4,0x500000,40,1,1);
 CHECK(pg_map(a.state.data,0x1000,0x11111000,1)==0);CHECK(pg_map(b.state.data,0x1000,0x22222000,4)==0);
 CHECK(pg_unmap(a.state.data,0x1000)==0);mapping(&b,0x1000,0x22222000,4);CHECK(used(&a)==1&&used(&b)==4);destroy(&a);destroy(&b);
}
static void malformed_failure(struct Fixture *f,uint64_t va){
 query_fail(f,va+17,E_MALFORMED);
 FAIL_UNCHANGED(f,pg_map(f->state.data,va,0x100000000,1),E_MALFORMED);
 FAIL_UNCHANGED(f,pg_unmap(f->state.data,va),E_MALFORMED);
 FAIL_UNCHANGED(f,pg_protect(f->state.data,va,0),E_MALFORMED);
}
static void cache_tests(void){
 phase="PAT0/PAT3 raw cache bits";
 struct Fixture f=fixture(8,0x100000,52,1,1);
 /* Exhaust the public low-four-bit flag domain; UC does not relax W^X. */
 for(uint64_t flags=0;flags<16;flags++){
  const uint64_t va=0x5000,pa=UINT64_C(0x0009000000000000);
  if((flags&5)==5){FAIL_UNCHANGED(&f,pg_map(f.state.data,va,pa,flags),E_INVALID);continue;}
  CHECK(pg_map(f.state.data,va,pa,flags)==0);mapping(&f,va+4095,pa+4095,flags);
  struct Path path;struct Mapping got;CHECK(raw_walk(&f,va,&got,&path));
  uint64_t expected=pa|P|((flags&1)?W:0)|((flags&2)?U:0)|((flags&4)?0:NX)|((flags&8)?CACHE:0);
  CHECK(*path.entry[3]==expected);CHECK(!(*path.entry[3]&128));
  for(unsigned level=0;level<3;level++)CHECK((*path.entry[level]&~ADDRESS)==7);
  FAIL_UNCHANGED(&f,pg_map(f.state.data,va,pa,flags),E_MAPPED);
  CHECK(pg_unmap(f.state.data,va)==0);CHECK(used(&f)==1);intact(&f);
 }
 /* Protect replaces cache selection while retaining PA and hardware A/D. */
 const uint64_t va=0x6000,pa=UINT64_C(0x0009000000001000);
 CHECK(pg_map(f.state.data,va,pa,1)==0);
 struct Path path;struct Mapping got;CHECK(raw_walk(&f,va,&got,&path));
 for(unsigned level=0;level<3;level++)*path.entry[level]|=A;
 *path.entry[3]|=A|D;
 const uint64_t changes[]={9,12,8,0,4,9,1};
 for(size_t i=0;i<sizeof changes/sizeof changes[0];i++){
  uint64_t flags=changes[i];CHECK(pg_protect(f.state.data,va,flags)==0);mapping(&f,va+123,pa+123,flags);
  CHECK((*path.entry[3]&(ADDRESS|A|D))==(pa|A|D));
  CHECK((*path.entry[3]&CACHE)==((flags&8)?CACHE:0));CHECK(!(*path.entry[3]&128));
  for(unsigned level=0;level<3;level++)CHECK((*path.entry[level]&~ADDRESS)==(7|A));
 }
 FAIL_UNCHANGED(&f,pg_protect(f.state.data,va,13),E_INVALID);
 FAIL_UNCHANGED(&f,pg_protect(f.state.data,va,15),E_INVALID);
 FAIL_UNCHANGED(&f,pg_protect(f.state.data,va,24),E_INVALID); /* UC|WC */
 FAIL_UNCHANGED(&f,pg_protect(f.state.data,va,32),E_INVALID);
 /* Both partial encodings are malformed, from either supported cache mode. */
 for(unsigned cached=0;cached<2;cached++){
  CHECK(pg_protect(f.state.data,va,cached?9:1)==0);uint64_t original=*path.entry[3];
  const uint64_t partial[]={PWT,PCD};
  for(size_t i=0;i<sizeof partial/sizeof partial[0];i++){
   *path.entry[3]=(original&~CACHE)|partial[i];malformed_failure(&f,va);*path.entry[3]=original;
  }
  /* PAT selector bit 7 is WC on its own; combined with UC it is malformed. */
  if(cached){*path.entry[3]=original|128;malformed_failure(&f,va);*path.entry[3]=original;}
  mapping(&f,va,pa,cached?9:1);
 }
 CHECK(pg_unmap(f.state.data,va)==0);CHECK(used(&f)==1);
 const uint64_t high=UINT64_C(0xffff800000000000);
 CHECK(pg_map(f.state.data,high,0,9)==0);mapping(&f,high+4095,4095,9);
 FAIL_UNCHANGED(&f,pg_protect(f.state.data,high,11),E_INVALID);
 FAIL_UNCHANGED(&f,pg_map(f.state.data,high+PAGE,0,10),E_INVALID);
 FAIL_UNCHANGED(&f,pg_map(f.state.data,high+PAGE,0,14),E_INVALID);
 CHECK(pg_unmap(f.state.data,high)==0);CHECK(used(&f)==1);destroy(&f);
 f=fixture(3,0x200000,40,1,1);FAIL_UNCHANGED(&f,pg_map(f.state.data,0,0,9),E_OOM);destroy(&f);
 f=fixture(4,0x300000,32,0,1);
 FAIL_UNCHANGED(&f,pg_map(f.state.data,0,0,8),E_NO_NX);
 CHECK(pg_map(f.state.data,0,0,12)==0);mapping(&f,17,17,12);
 FAIL_UNCHANGED(&f,pg_protect(f.state.data,0,8),E_NO_NX);
 CHECK(pg_protect(f.state.data,0,4)==0);mapping(&f,0,0,4);
 CHECK(pg_protect(f.state.data,0,12)==0);mapping(&f,0,0,12);
 CHECK(pg_unmap(f.state.data,0)==0);CHECK(used(&f)==1);destroy(&f);
}
static void malformed_tests(void){
 phase="malformed bounded traversal";struct Fixture f=fixture(8,0x800000,40,1,1);
 CHECK(pg_map(f.state.data,0x1000,0x100000000,1)==0);
 struct Path path;struct Mapping out;CHECK(raw_walk(&f,0x1000,&out,&path));
 for(unsigned level=0;level<3;level++){
  uint64_t original=*path.entry[level];
  uint64_t bad[]={f.physical-PAGE+7,f.physical+f.count*PAGE+7,f.physical+7*PAGE+7,f.physical+path.slot[level]*PAGE+7,f.physical+7,
                  original|128,original|NX,original|D,original|PWT,original|PCD,original|CACHE,original&~U,original&~P,original|(UINT64_C(1)<<52),original|(UINT64_C(1)<<62)};
  for(size_t i=0;i<sizeof bad/sizeof bad[0];i++){*path.entry[level]=bad[i];malformed_failure(&f,0x1000);*path.entry[level]=original;}
  uint64_t child=((*path.entry[level]&ADDRESS)-f.physical)/PAGE;
  f.meta.data[child]=0;malformed_failure(&f,0x1000);f.meta.data[child]=2;malformed_failure(&f,0x1000);f.meta.data[child]=1;
 }
 uint64_t original=*path.entry[3];
 uint64_t badleaf[]={original|128|PWT|PCD,original|512,original|PWT,original|PCD,original|(UINT64_C(1)<<52),original|(UINT64_C(1)<<62),original&~P,original&~NX,2};
 for(size_t i=0;i<sizeof badleaf/sizeof badleaf[0];i++){*path.entry[3]=badleaf[i];malformed_failure(&f,0x1000);*path.entry[3]=original;}
 f.meta.data[0]=0;malformed_failure(&f,0x1000);f.meta.data[0]=2;malformed_failure(&f,0x1000);f.meta.data[0]=1;
 mapping(&f,0x1000,0x100000000,1);destroy(&f);
 f=fixture(8,0x900000,40,1,1);uint64_t high=UINT64_C(0xffff800000001000);CHECK(pg_map(f.state.data,high,0x100000000,1)==0);CHECK(raw_walk(&f,high,&out,&path));
 original=*path.entry[3];*path.entry[3]|=U;malformed_failure(&f,high);*path.entry[3]=original;destroy(&f);
 f=fixture(8,0xa00000,32,0,1);CHECK(pg_map(f.state.data,0,0x200000,4)==0);CHECK(raw_walk(&f,0,&out,&path));
 original=*path.entry[3];*path.entry[3]|=NX;query_fail(&f,0,E_MALFORMED);*path.entry[3]=original|(UINT64_C(1)<<32);query_fail(&f,0,E_MALFORMED);*path.entry[3]=original;destroy(&f);
}
#define MODEL_COUNT 64
struct Model {uint64_t va,pa,flags;int present;};
static uint64_t random_state=UINT64_C(0xabcddcba12344321);
static uint64_t random_next(void){random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return random_state;}
/* Count distinct nonempty prefixes, independently of allocation order/table
 * numbers: root + distinct 9-,18-,27-bit virtual-page prefixes. */
static uint64_t model_tables(const struct Model *m){
 uint64_t count=1;
 for(unsigned i=0;i<MODEL_COUNT;i++)if(m[i].present)for(unsigned level=0;level<3;level++){
  unsigned shift=39-9*level;uint64_t prefix=(m[i].va&UINT64_C(0x0000ffffffffffff))>>shift;int first=1;
  for(unsigned j=0;j<i;j++)if(m[j].present&&((m[j].va&UINT64_C(0x0000ffffffffffff))>>shift)==prefix){first=0;break;}
  count+=(uint64_t)first;
 }
 return count;
}
static void model_verify(struct Fixture *f,struct Model *m){
 CHECK(used(f)==model_tables(m));size_t meta_used=0;for(size_t i=0;i<f->count;i++){CHECK(f->meta.data[i]<=1);meta_used+=f->meta.data[i];}CHECK(meta_used==used(f));
 for(unsigned i=0;i<MODEL_COUNT;i++){
  uint64_t offset=(i*137u)&4095;struct Mapping got={0},raw={0};int found=raw_walk(f,m[i].va+offset,&raw,NULL);
  CHECK(found==m[i].present);
  if(found){CHECK(raw.physical==m[i].pa+offset&&raw.flags==m[i].flags);CHECK(pg_query(f->state.data,m[i].va+offset,&got)==0);CHECK(got.physical==raw.physical&&got.flags==raw.flags);}
  else{uint64_t marker=UINT64_C(0x5a5a5a5a5a5a5a5a);got.physical=marker;got.flags=marker;CHECK(pg_query(f->state.data,m[i].va+offset,&got)==E_NOT_MAPPED);CHECK(got.physical==marker&&got.flags==marker);}
 }
 intact(f);
}
static void random_tests(void){
 phase="seeded mapping model";struct Fixture f=fixture(88,UINT64_C(0x0008000000000000),52,1,1);struct Model m[MODEL_COUNT]={0};
 for(unsigned i=0;i<MODEL_COUNT;i++){
  uint64_t a=(i&1)?(uint64_t)(256+(i/2)%8):(uint64_t)((i/2)%8);
  uint64_t va=(a<<39)|((uint64_t)((i/8)%4)<<30)|((uint64_t)((i/32)%2)<<21)|((uint64_t)i<<12);
  if(a&256){va|=UINT64_C(0xffff000000000000);}m[i].va=va;
 }
 const uint64_t options[]={0,1,2,3,4,6,8,9,10,11,12,14};
 for(step=0;step<2500;step++){
  unsigned i=(unsigned)(random_next()%MODEL_COUNT),op=(unsigned)(random_next()%4);uint64_t flags=options[random_next()%(sizeof options/sizeof options[0])];if(m[i].va>>63)flags&=~UINT64_C(2);
  if(op==0){
   uint64_t pa=UINT64_C(0x0009000000000000)+(random_next()%32)*PAGE;
   if(m[i].present)FAIL_UNCHANGED(&f,pg_map(f.state.data,m[i].va,pa,flags),E_MAPPED);
   else{
    m[i].present=1;uint64_t needed=model_tables(m);m[i].present=0;
    if(needed>f.count)FAIL_UNCHANGED(&f,pg_map(f.state.data,m[i].va,pa,flags),E_OOM);
    else{CHECK(pg_map(f.state.data,m[i].va,pa,flags)==0);m[i].present=1;m[i].pa=pa;m[i].flags=flags;}
   }
  }else if(op==1){
   if(!m[i].present)FAIL_UNCHANGED(&f,pg_unmap(f.state.data,m[i].va),E_NOT_MAPPED);
   else{CHECK(pg_unmap(f.state.data,m[i].va)==0);m[i].present=0;}
  }else if(op==2){
   if(!m[i].present)FAIL_UNCHANGED(&f,pg_protect(f.state.data,m[i].va,flags),E_NOT_MAPPED);
   else{CHECK(pg_protect(f.state.data,m[i].va,flags)==0);m[i].flags=flags;}
  }else if(!m[i].present)query_fail(&f,m[i].va+4095,E_NOT_MAPPED);else mapping(&f,m[i].va+4095,m[i].pa+4095,m[i].flags);
  if(step%23==0)model_verify(&f,m);
 }
 model_verify(&f,m);for(unsigned i=0;i<MODEL_COUNT;i++)if(m[i].present){CHECK(pg_unmap(f.state.data,m[i].va)==0);m[i].present=0;}
 CHECK(used(&f)==1);model_verify(&f,m);destroy(&f);
}
int main(void){init_tests();basic_tests();physical_width_tests();exhaustion_tests();cache_tests();malformed_tests();random_tests();puts("paging independent raw walk/model/atomicity/malformed checks passed");return 0;}
