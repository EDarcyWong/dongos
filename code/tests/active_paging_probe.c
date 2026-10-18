/* Independent x86-64 entry walk and invalidation observer. Pool physical
 * addresses are numeric and deliberately differ from their native pointers.
 * No private Context, Space or Retired field offsets are used by this oracle. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif
#define DG __attribute__((sysv_abi))
#define PAGE UINT64_C(4096)
#define NX (UINT64_C(1)<<63)
#define ADDRESS UINT64_C(0x000ffffffffff000)
#define AD UINT64_C(0x60)
#define E_NOT_INIT UINT64_C(0x02000001)
#define E_ALREADY_INIT UINT64_C(0x02000002)
#define E_INVALID UINT64_C(0x02000003)
#define E_OOM UINT64_C(0x02000007)
#define E_MAPPED UINT64_C(0x02030001)
#define E_NOT_MAPPED UINT64_C(0x02030002)
#define E_MALFORMED UINT64_C(0x02030003)
#define E_RECEIPT UINT64_C(0x02030005)
#define E_CONTROLS UINT64_C(0x020a0002)
#define E_BUSY UINT64_C(0x020a0003)
struct State {uint64_t cr0,cr3,cr4,efer,rflags,pat;};
struct Stats {uint64_t invlpg,full_flush,retired_tables;};
struct Mapping {uint64_t physical,flags;};
typedef void DG Flush(uint64_t,uint64_t);
extern uint64_t DG ap_context_size(void),ap_context_align(void),ap_space_size(void),ap_space_align(void),ap_retired_size(void),ap_retired_align(void);
extern void DG ap_context_reset(void*),ap_space_reset(void*),ap_retired_reset(void*);
extern uint64_t DG ap_init(void*,void*,uint64_t,uint64_t,void*,uint64_t);
extern uint64_t DG ap_bind(void*,void*,const struct State*,uint64_t,uint64_t,uint64_t,uint64_t,Flush*);
extern uint64_t DG ap_map(void*,const struct State*,uint64_t,uint64_t,uint64_t),ap_protect(void*,const struct State*,uint64_t,uint64_t);
extern uint64_t DG ap_replace(void*,const struct State*,uint64_t,uint64_t,uint64_t),ap_unmap(void*,const struct State*,uint64_t);
extern uint64_t DG ap_stats(const void*,struct Stats*),ap_query(const void*,uint64_t,struct Mapping*),ap_used(const void*,uint64_t*);
extern uint64_t DG ap_map_live(void*,uint64_t,uint64_t,uint64_t),ap_protect_live(void*,uint64_t,uint64_t),ap_replace_live(void*,uint64_t,uint64_t,uint64_t);
extern uint64_t DG ap_unmap_live(void*,uint64_t,void*),ap_reclaim(void*,void*);
static const char *phase="init";
static unsigned callbacks;
#define CHECK(X) do{if(!(X)){fprintf(stderr,"active paging failure phase=%s callback=%u line=%d: %s\n",phase,callbacks,__LINE__,#X);exit(1);}}while(0)
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
 fprintf(stderr,"unexpected live paging panic kind=%u line=%u file=%.*s phase=%s\n",kind,line,(int)length,(const char*)file,phase);exit(99);
}
struct Guard {uint8_t *raw,*data;size_t size,guard;};
static struct Guard guarded(size_t size,size_t alignment){
 struct Guard b={0};b.size=size;b.guard=alignment<16?16:alignment;
 b.raw=malloc(size+3*b.guard+alignment);CHECK(b.raw!=NULL);
 b.data=(uint8_t*)(((uintptr_t)(b.raw+b.guard)+alignment-1)&~(uintptr_t)(alignment-1));
 memset(b.data-b.guard,0xa5,b.guard);memset(b.data,0x6b,size);memset(b.data+size,0x5a,b.guard);return b;
}
static void guards(const struct Guard *b){for(size_t i=0;i<b->guard;i++){CHECK(b->data[-(ptrdiff_t)b->guard+(ptrdiff_t)i]==0xa5);CHECK(b->data[b->size+i]==0x5a);}}
struct Fixture {struct Guard context,space,pool,meta;size_t count;uint64_t physical,va,pages,frame,frames;struct State state;};
static struct Fixture fixture(size_t count){
 struct Fixture f={guarded((size_t)ap_context_size(),(size_t)ap_context_align()),guarded((size_t)ap_space_size(),(size_t)ap_space_align()),guarded(count*4096,4096),guarded(count+16,8),count,0x200000,UINT64_C(0xffffa00000001000),1,UINT64_C(0x900000000),2,{0x80010033,0x200000,0x668,0xd00,2,UINT64_C(0x0007040600070406)}};
 ap_context_reset(f.context.data);ap_space_reset(f.space.data);
 CHECK(ap_init(f.space.data,f.pool.data,count,f.physical,f.meta.data,52)==0);return f;
}
static void intact(const struct Fixture *f){guards(&f->context);guards(&f->space);guards(&f->pool);guards(&f->meta);for(size_t i=f->count;i<f->meta.size;i++)CHECK(f->meta.data[i]==0x6b);}
static void destroy(struct Fixture *f){intact(f);free(f->context.raw);free(f->space.raw);free(f->pool.raw);free(f->meta.raw);}
struct Snapshot {uint8_t *context,*space,*pool,*meta;struct State state;};
static struct Snapshot snapshot(const struct Fixture *f){
 struct Snapshot s={malloc(f->context.size),malloc(f->space.size),malloc(f->pool.size),malloc(f->meta.size),f->state};CHECK(s.context&&s.space&&s.pool&&s.meta);
 memcpy(s.context,f->context.data,f->context.size);memcpy(s.space,f->space.data,f->space.size);memcpy(s.pool,f->pool.data,f->pool.size);memcpy(s.meta,f->meta.data,f->meta.size);return s;
}
static void unchanged(const struct Fixture *f,struct Snapshot s){
 CHECK(!memcmp(s.context,f->context.data,f->context.size));CHECK(!memcmp(s.space,f->space.data,f->space.size));CHECK(!memcmp(s.pool,f->pool.data,f->pool.size));CHECK(!memcmp(s.meta,f->meta.data,f->meta.size));CHECK(!memcmp(&s.state,&f->state,sizeof s.state));intact(f);
 free(s.context);free(s.space);free(s.pool);free(s.meta);
}
#define FAIL(F,CALL,CODE) do{struct Snapshot before=snapshot(F);unsigned calls=callbacks;CHECK((CALL)==(CODE));CHECK(callbacks==calls);unchanged(F,before);}while(0)
static uint64_t used(const struct Fixture *f){uint64_t n=UINT64_MAX;CHECK(ap_used(f->space.data,&n)==0);return n;}
struct Path {uint64_t *entries[4];size_t slots[4];};
static int raw_walk(const struct Fixture *f,uint64_t va,struct Mapping *out,struct Path *path){
 size_t slot=0;uint64_t *pool=(uint64_t*)f->pool.data;
 for(unsigned level=0;level<4;level++){
  CHECK(slot<f->count&&f->meta.data[slot]==1);
  uint64_t *where=&pool[slot*512+((va>>(39-level*9))&511)],entry=*where;
  if(path){path->entries[level]=where;path->slots[level]=slot;}
  if(!(entry&1)){CHECK(entry==0);return 0;}
  if(level==3){CHECK(!(entry&~(ADDRESS|UINT64_C(0x67)|NX)));out->physical=(entry&ADDRESS)|(va&4095);out->flags=((entry&2)?1:0)|((entry&4)?2:0)|((entry&NX)?0:4);return 1;}
  CHECK((entry&7)==7&&!(entry&~(ADDRESS|UINT64_C(0x27))));CHECK((entry&ADDRESS)>=f->physical);
  slot=(size_t)(((entry&ADDRESS)-f->physical)/PAGE);
 }
 return 0;
}
static void mapping(const struct Fixture *f,uint64_t va,uint64_t pa,uint64_t flags){
 struct Mapping raw={0},got={UINT64_MAX,UINT64_MAX};CHECK(raw_walk(f,va,&raw,NULL));CHECK(raw.physical==pa&&raw.flags==flags);
 CHECK(ap_query(f->context.data,va,&got)==0);CHECK(got.physical==pa&&got.flags==flags);intact(f);
}
static size_t meta_count(const struct Fixture *f,unsigned value){size_t count=0;for(size_t i=0;i<f->count;i++){CHECK(f->meta.data[i]<=2);if(f->meta.data[i]==value)count++;}return count;}
static void empty_quarantine(const struct Fixture *f,size_t expected){
 CHECK(meta_count(f,2)==expected);for(size_t i=0;i<f->count;i++)if(f->meta.data[i]==2)for(size_t j=0;j<4096;j++)CHECK(f->pool.data[i*4096+j]==0);
}
struct Expectation {struct Fixture *f;uint64_t kind,va,pa,flags,tables;size_t retired;uint64_t ad;};
static struct Expectation expected;
static void DG flush_callback(uint64_t kind,uint64_t va){
 struct Fixture *f=expected.f;CHECK(f!=NULL);callbacks++;CHECK(kind==expected.kind&&va==expected.va);CHECK(used(f)==expected.tables);
 struct Mapping got={0};struct Path path;
 if(kind==1){CHECK(raw_walk(f,va,&got,&path));CHECK(got.physical==expected.pa&&got.flags==expected.flags);CHECK((*path.entries[3]&AD)==expected.ad);}
 else{CHECK(kind==2);CHECK(!raw_walk(f,va,&got,NULL));}
 empty_quarantine(f,expected.retired);
 /* The callback observes committed entries, still-owned retired pages, and
  * rejects nested mutations before they can touch bytes or invoke this hook. */
 FAIL(f,ap_map(f->context.data,&f->state,va,f->frame,1),E_BUSY);
 FAIL(f,ap_protect(f->context.data,&f->state,va,0),E_BUSY);
 FAIL(f,ap_replace(f->context.data,&f->state,va,f->frame,1),E_BUSY);
 FAIL(f,ap_unmap(f->context.data,&f->state,va),E_BUSY);
}
static void expect(struct Fixture *f,uint64_t kind,uint64_t va,uint64_t pa,uint64_t flags,uint64_t tables,size_t retired,uint64_t ad){expected=(struct Expectation){f,kind,va,pa,flags,tables,retired,ad};}
static void bind_fixture(struct Fixture *f){unsigned before=callbacks;CHECK(ap_bind(f->context.data,f->space.data,&f->state,f->va,f->pages,f->frame,f->frames,flush_callback)==0);CHECK(callbacks==before);}
static void stats_equal(const struct Fixture *f,uint64_t pages,uint64_t roots,uint64_t retired){
 struct {uint64_t before;struct Stats value;uint64_t after;} s={UINT64_C(0x1122334455667788),{0,0,0},UINT64_C(0x8877665544332211)};
 CHECK(ap_stats(f->context.data,&s.value)==0);CHECK(s.value.invlpg==pages&&s.value.full_flush==roots&&s.value.retired_tables==retired);CHECK(s.before==UINT64_C(0x1122334455667788)&&s.after==UINT64_C(0x8877665544332211));
}
static void basic_tests(void){
 phase="commit/invalidate/reclaim";struct Fixture f=fixture(8);bind_fixture(&f);stats_equal(&f,0,0,0);
 expect(&f,1,f.va,f.frame,1,4,0,0);CHECK(ap_map(f.context.data,&f.state,f.va,f.frame,1)==0);mapping(&f,f.va+4095,f.frame+4095,1);
 struct Mapping got={0};struct Path path;CHECK(raw_walk(&f,f.va,&got,&path));for(unsigned i=0;i<3;i++)*path.entries[i]|=UINT64_C(0x20);*path.entries[3]|=AD;
 expect(&f,1,f.va,f.frame,0,4,0,AD);CHECK(ap_protect(f.context.data,&f.state,f.va,0)==0);mapping(&f,f.va,f.frame,0);
 for(unsigned i=0;i<3;i++)CHECK(*path.entries[i]&UINT64_C(0x20));
 expect(&f,1,f.va,f.frame,1,4,0,AD);CHECK(ap_protect(f.context.data,&f.state,f.va,1)==0);mapping(&f,f.va,f.frame,1);
 for(unsigned i=0;i<3;i++)CHECK(*path.entries[i]&UINT64_C(0x20));
 expect(&f,1,f.va,f.frame+PAGE,1,4,0,0);CHECK(ap_replace(f.context.data,&f.state,f.va,f.frame+PAGE,1)==0);mapping(&f,f.va,f.frame+PAGE,1);
 expect(&f,2,f.va,0,0,4,3,0);CHECK(ap_unmap(f.context.data,&f.state,f.va)==0);CHECK(used(&f)==1&&meta_count(&f,2)==0);for(size_t i=1;i<f.count;i++)CHECK(f.meta.data[i]==0);
 expect(&f,1,f.va,f.frame,1,4,0,0);CHECK(ap_map(f.context.data,&f.state,f.va,f.frame,1)==0);CHECK(raw_walk(&f,f.va,&got,&path));CHECK(path.slots[1]==1&&path.slots[2]==2&&path.slots[3]==3);
 expect(&f,2,f.va,0,0,4,3,0);CHECK(ap_unmap(f.context.data,&f.state,f.va)==0);CHECK(used(&f)==1);stats_equal(&f,5,2,6);destroy(&f);
}
static void bind_failure_tests(void){
 phase="bind/control/range failures";struct Fixture f=fixture(8);struct Stats output={1,2,3},saved=output;
 FAIL(&f,ap_stats(f.context.data,&output),E_NOT_INIT);CHECK(!memcmp(&output,&saved,sizeof output));
 FAIL(&f,ap_map(f.context.data,&f.state,f.va,f.frame,1),E_NOT_INIT);FAIL(&f,ap_protect(f.context.data,&f.state,f.va,1),E_NOT_INIT);
 FAIL(&f,ap_replace(f.context.data,&f.state,f.va,f.frame,1),E_NOT_INIT);FAIL(&f,ap_unmap(f.context.data,&f.state,f.va),E_NOT_INIT);
 struct {unsigned field;uint64_t mask;} bad[]={
  {0,1},{0,UINT64_C(1)<<16},{0,UINT64_C(1)<<31},{0,UINT64_C(1)<<29},{0,UINT64_C(1)<<30},
  {1,PAGE},{1,1},{2,UINT64_C(1)<<5},{2,UINT64_C(1)<<7},{2,UINT64_C(1)<<12},{2,UINT64_C(1)<<17},{2,UINT64_C(1)<<23},
  {3,UINT64_C(1)<<8},{3,UINT64_C(1)<<10},{3,UINT64_C(1)<<11},{4,2},{4,UINT64_C(1)<<9},{4,UINT64_C(1)<<10},{4,UINT64_C(1)<<17},{4,UINT64_C(1)<<18},
  {5,1},{5,UINT64_C(1)<<24}};
 for(size_t i=0;i<sizeof bad/sizeof bad[0];i++){
  struct State state=f.state;uint64_t values[6];memcpy(values,&state,sizeof values);values[bad[i].field]^=bad[i].mask;memcpy(&state,values,sizeof values);
  FAIL(&f,ap_bind(f.context.data,f.space.data,&state,f.va,1,f.frame,2,flush_callback),E_CONTROLS);
 }
 const uint64_t va_bad[][2]={{UINT64_C(0xffffa00000001001),1},{UINT64_C(0x0000800000000000),1},{UINT64_C(0xffff7ffffffff000),1},{UINT64_C(0x00007ffffffff000),2},{UINT64_C(0xfffffffffffff000),2},{0,0},{0,UINT64_MAX}};
 for(size_t i=0;i<sizeof va_bad/sizeof va_bad[0];i++)FAIL(&f,ap_bind(f.context.data,f.space.data,&f.state,va_bad[i][0],va_bad[i][1],f.frame,2,flush_callback),E_INVALID);
 const uint64_t pa_bad[][2]={{UINT64_C(0x900000001),2},{0,0},{UINT64_C(1)<<52,1},{(UINT64_C(1)<<52)-PAGE,2},{UINT64_C(0xfffffffffffff000),2},{0,UINT64_MAX}};
 for(size_t i=0;i<sizeof pa_bad/sizeof pa_bad[0];i++)FAIL(&f,ap_bind(f.context.data,f.space.data,&f.state,f.va,1,pa_bad[i][0],pa_bad[i][1],flush_callback),E_INVALID);
 bind_fixture(&f);FAIL(&f,ap_bind(f.context.data,f.space.data,&f.state,f.va,1,f.frame,2,flush_callback),E_ALREADY_INIT);destroy(&f);
 /* A newly bound window must be empty, including pages after its first hole.
  * Reject UC, executable and outside-frame imported mappings with snapshots. */
 const uint64_t imported_flags[]={9,4,1};
 for(size_t i=0;i<sizeof imported_flags/sizeof imported_flags[0];i++){
  f=fixture(8);f.pages=2;CHECK(ap_map_live(f.space.data,f.va+PAGE,f.frame+8*PAGE,imported_flags[i])==0);
  FAIL(&f,ap_bind(f.context.data,f.space.data,&f.state,f.va,2,f.frame,2,flush_callback),E_INVALID);
  if(i==0){
   /* UC is intentionally outside the WB-only raw oracle. */
   uint64_t *pool=(uint64_t*)f.pool.data;size_t slot=0;
   for(unsigned level=0;level<3;level++)slot=(size_t)(((pool[slot*512+(((f.va+PAGE)>>(39-level*9))&511)]&ADDRESS)-f.physical)/PAGE);
   uint64_t *leaf=&pool[slot*512+(((f.va+PAGE)>>12)&511)];*leaf|=UINT64_C(0x80);
   FAIL(&f,ap_bind(f.context.data,f.space.data,&f.state,f.va,2,f.frame,2,flush_callback),E_MALFORMED);
  }
  destroy(&f);
 }
}
static void operation_failure_tests(void){
 phase="operation full snapshots";struct Fixture f=fixture(8);bind_fixture(&f);
 FAIL(&f,ap_unmap(f.context.data,&f.state,f.va),E_NOT_MAPPED);FAIL(&f,ap_protect(f.context.data,&f.state,f.va,0),E_NOT_MAPPED);FAIL(&f,ap_replace(f.context.data,&f.state,f.va,f.frame,1),E_NOT_MAPPED);
 const uint64_t badva[]={0,f.va-1,f.va+1,f.va+PAGE,UINT64_C(0x0000800000000000),UINT64_C(0xffff7ffffffff000)};
 for(size_t i=0;i<sizeof badva/sizeof badva[0];i++){
  FAIL(&f,ap_map(f.context.data,&f.state,badva[i],f.frame,1),E_INVALID);FAIL(&f,ap_protect(f.context.data,&f.state,badva[i],0),E_INVALID);
  FAIL(&f,ap_replace(f.context.data,&f.state,badva[i],f.frame,1),E_INVALID);FAIL(&f,ap_unmap(f.context.data,&f.state,badva[i]),E_INVALID);
 }
 const uint64_t badpa[]={f.frame-1,f.frame+1,f.frame-PAGE,f.frame+2*PAGE,UINT64_MAX};
 for(size_t i=0;i<sizeof badpa/sizeof badpa[0];i++){
  FAIL(&f,ap_map(f.context.data,&f.state,f.va,badpa[i],1),E_INVALID);FAIL(&f,ap_replace(f.context.data,&f.state,f.va,badpa[i],1),E_INVALID);
 }
 for(uint64_t flags=2;flags<32;flags++){
  FAIL(&f,ap_map(f.context.data,&f.state,f.va,f.frame,flags),E_INVALID);FAIL(&f,ap_protect(f.context.data,&f.state,f.va,flags),E_INVALID);FAIL(&f,ap_replace(f.context.data,&f.state,f.va,f.frame,flags),E_INVALID);
 }
 expect(&f,1,f.va,f.frame,1,4,0,0);CHECK(ap_map(f.context.data,&f.state,f.va,f.frame,1)==0);FAIL(&f,ap_map(f.context.data,&f.state,f.va,f.frame,0),E_MAPPED);
 struct State changed=f.state;changed.cr0^=8;FAIL(&f,ap_protect(f.context.data,&changed,f.va,0),E_CONTROLS);changed=f.state;changed.cr3+=PAGE;FAIL(&f,ap_unmap(f.context.data,&changed,f.va),E_CONTROLS);
 changed=f.state;changed.rflags|=UINT64_C(0x8d5);expect(&f,1,f.va,f.frame,0,4,0,0);CHECK(ap_protect(f.context.data,&changed,f.va,0)==0);mapping(&f,f.va,f.frame,0);
 changed=f.state;changed.rflags|=UINT64_C(1)<<18;FAIL(&f,ap_protect(f.context.data,&changed,f.va,1),E_CONTROLS);
 struct Mapping out={UINT64_C(0x1111222233334444),UINT64_C(0xaaaabbbbccccdddd)},saved=out;
 FAIL(&f,ap_query(f.context.data,f.va+PAGE,&out),E_INVALID);CHECK(!memcmp(&out,&saved,sizeof out));
 struct Mapping got={0};struct Path path;CHECK(raw_walk(&f,f.va,&got,&path));
 uint64_t original=*path.entries[0];*path.entries[0]|=NX;FAIL(&f,ap_protect(f.context.data,&f.state,f.va,1),E_MALFORMED);*path.entries[0]=original;
 original=*path.entries[3];*path.entries[3]|=UINT64_C(0x10);FAIL(&f,ap_replace(f.context.data,&f.state,f.va,f.frame+PAGE,1),E_MALFORMED);FAIL(&f,ap_unmap(f.context.data,&f.state,f.va),E_MALFORMED);*path.entries[3]=original;
 expect(&f,2,f.va,0,0,4,3,0);CHECK(ap_unmap(f.context.data,&f.state,f.va)==0);FAIL(&f,ap_query(f.context.data,f.va,&out),E_NOT_MAPPED);CHECK(!memcmp(&out,&saved,sizeof out));stats_equal(&f,2,1,3);destroy(&f);
 f=fixture(3);bind_fixture(&f);FAIL(&f,ap_map(f.context.data,&f.state,f.va,f.frame,1),E_OOM);CHECK(used(&f)==1);stats_equal(&f,0,0,0);destroy(&f);
}
static void receipt_unchanged(const struct Guard *r,const uint8_t *before){CHECK(!memcmp(r->data,before,r->size));guards(r);}
static void quarantine_tests(void){
 phase="quarantine forbids pre-flush reuse";struct Fixture f=fixture(7),other=fixture(4);struct Guard r=guarded((size_t)ap_retired_size(),(size_t)ap_retired_align());ap_retired_reset(r.data);
 uint8_t *initial=malloc(r.size);CHECK(initial!=NULL);memcpy(initial,r.data,r.size);
 FAIL(&f,ap_unmap_live(f.space.data,0x1001,r.data),E_INVALID);receipt_unchanged(&r,initial);
 FAIL(&f,ap_unmap_live(f.space.data,0x1000,r.data),E_NOT_MAPPED);receipt_unchanged(&r,initial);free(initial);
 CHECK(ap_map_live(f.space.data,0x1000,f.frame,1)==0);CHECK(used(&f)==4);CHECK(ap_unmap_live(f.space.data,0x1000,r.data)==0);CHECK(used(&f)==4);empty_quarantine(&f,3);
 uint8_t *receipt=malloc(r.size);CHECK(receipt!=NULL);memcpy(receipt,r.data,r.size);
 FAIL(&f,ap_unmap_live(f.space.data,0x1000,r.data),E_RECEIPT);receipt_unchanged(&r,receipt);
 FAIL(&other,ap_reclaim(other.space.data,r.data),E_RECEIPT);receipt_unchanged(&r,receipt);
 /* map_live must allocate 4,5,6, not touch detached slots 1,2,3. It has no
  * authority to free or repurpose old tables before the external barrier. */
 CHECK(ap_map_live(f.space.data,UINT64_C(0x8000000000),f.frame+PAGE,1)==0);CHECK(used(&f)==7);empty_quarantine(&f,3);
 struct Mapping got={0};struct Path path;CHECK(raw_walk(&f,UINT64_C(0x8000000000),&got,&path));CHECK(path.slots[1]==4&&path.slots[2]==5&&path.slots[3]==6);
 FAIL(&f,ap_map_live(f.space.data,0x1000,f.frame,1),E_OOM);receipt_unchanged(&r,receipt);
 /* Validate the whole receipt before freeing even one table. */
 f.meta.data[2]=1;FAIL(&f,ap_reclaim(f.space.data,r.data),E_RECEIPT);receipt_unchanged(&r,receipt);f.meta.data[2]=2;
 ((uint64_t*)f.pool.data)[3*512]=7;FAIL(&f,ap_reclaim(f.space.data,r.data),E_RECEIPT);receipt_unchanged(&r,receipt);((uint64_t*)f.pool.data)[3*512]=0;
 /* This native barrier is an oracle event, not an architectural TLB flush;
  * QEMU separately proves real INVLPG / MOV CR3 behavior. */
 empty_quarantine(&f,3);CHECK(ap_reclaim(f.space.data,r.data)==0);CHECK(used(&f)==4&&meta_count(&f,2)==0);
 uint8_t *empty=malloc(r.size);CHECK(empty!=NULL);memcpy(empty,r.data,r.size);FAIL(&f,ap_reclaim(f.space.data,r.data),E_RECEIPT);receipt_unchanged(&r,empty);
 CHECK(ap_map_live(f.space.data,0x1000,f.frame,1)==0);CHECK(raw_walk(&f,0x1000,&got,&path));CHECK(path.slots[1]==1&&path.slots[2]==2&&path.slots[3]==3);
 free(empty);free(receipt);guards(&r);free(r.raw);destroy(&f);destroy(&other);
}
static void partial_retirement_tests(void){
 phase="zero/one/two/three detached tables";
 const uint64_t neighbors[]={0x2000,0x200000,0x40000000,UINT64_C(0x8000000000)};
 for(size_t n=0;n<sizeof neighbors/sizeof neighbors[0];n++){
  struct Fixture f=fixture(8);struct Guard r=guarded((size_t)ap_retired_size(),(size_t)ap_retired_align());ap_retired_reset(r.data);
  CHECK(ap_map_live(f.space.data,0x1000,f.frame,1)==0);CHECK(ap_map_live(f.space.data,neighbors[n],f.frame+PAGE,1)==0);
  uint64_t before=used(&f);CHECK(ap_unmap_live(f.space.data,0x1000,r.data)==0);CHECK(used(&f)==before);empty_quarantine(&f,n);
  CHECK(ap_reclaim(f.space.data,r.data)==0);CHECK(used(&f)==before-n&&meta_count(&f,2)==0);
  struct Mapping got={0};CHECK(raw_walk(&f,neighbors[n],&got,NULL));CHECK(got.physical==f.frame+PAGE&&got.flags==1);
  CHECK(ap_unmap_live(f.space.data,neighbors[n],r.data)==0);empty_quarantine(&f,3);CHECK(ap_reclaim(f.space.data,r.data)==0);CHECK(used(&f)==1);
  guards(&r);free(r.raw);destroy(&f);
 }
}
static void independent_context_tests(void){
 phase="two disjoint contexts";struct Fixture a=fixture(8),b=fixture(8);bind_fixture(&a);bind_fixture(&b);
 expect(&a,1,a.va,a.frame,1,4,0,0);CHECK(ap_map(a.context.data,&a.state,a.va,a.frame,1)==0);struct Snapshot saved=snapshot(&b);
 expect(&a,2,a.va,0,0,4,3,0);CHECK(ap_unmap(a.context.data,&a.state,a.va)==0);unchanged(&b,saved);stats_equal(&a,1,1,3);stats_equal(&b,0,0,0);
 expect(&b,1,b.va,b.frame+PAGE,0,4,0,0);CHECK(ap_map(b.context.data,&b.state,b.va,b.frame+PAGE,0)==0);mapping(&b,b.va,b.frame+PAGE,0);stats_equal(&a,1,1,3);
 destroy(&a);destroy(&b);
}
/* A hardware-like writer sets A/D exactly once per epoch, racing the actual
 * generated protect CAS. It never changes PA/permissions or clears bits. The
 * next replace starts only after acknowledgement, so any lost A/D is visible
 * and cannot be hidden by a later repeated OR from the observer thread. */
struct AdRace {_Atomic uint64_t *entry;atomic_uint request,done,stop;};
#ifdef _WIN32
static DWORD WINAPI ad_writer(LPVOID argument){
#else
static void *ad_writer(void *argument){
#endif
 struct AdRace *race=argument;
 while(!atomic_load(&race->stop)){
  unsigned requested=atomic_load(&race->request);
  if(requested!=atomic_load(&race->done)){atomic_fetch_or(race->entry,AD);atomic_store(&race->done,requested);}
 }
#ifdef _WIN32
 return 0;
#else
 return NULL;
#endif
}
static void concurrent_ad_tests(void){
 phase="concurrent hardware A/D preservation";struct Fixture f=fixture(4);CHECK(ap_map_live(f.space.data,0x1000,f.frame,1)==0);
 struct Mapping got={0};struct Path path;CHECK(raw_walk(&f,0x1000,&got,&path));
 struct AdRace race={(_Atomic uint64_t*)path.entries[3],ATOMIC_VAR_INIT(0),ATOMIC_VAR_INIT(0),ATOMIC_VAR_INIT(0)};
#ifdef _WIN32
 HANDLE thread=CreateThread(NULL,0,ad_writer,&race,0,NULL);CHECK(thread!=NULL);
#else
 pthread_t thread;CHECK(pthread_create(&thread,NULL,ad_writer,&race)==0);
#endif
 for(unsigned epoch=1;epoch<=5000;epoch++){
  CHECK(ap_replace_live(f.space.data,0x1000,f.frame,1)==0);
  atomic_store(&race.request,epoch);
  CHECK(ap_protect_live(f.space.data,0x1000,0)==0);
  while(atomic_load(&race.done)!=epoch){}
  uint64_t entry=atomic_load(race.entry);CHECK((entry&AD)==AD);CHECK((entry&~AD)==(f.frame|NX|1));
 }
 atomic_store(&race.stop,1);
#ifdef _WIN32
 CHECK(WaitForSingleObject(thread,10000)==WAIT_OBJECT_0);CHECK(CloseHandle(thread));
#else
 CHECK(pthread_join(thread,NULL)==0);
#endif
 destroy(&f);
}
int main(void){basic_tests();bind_failure_tests();operation_failure_tests();quarantine_tests();partial_retirement_tests();independent_context_tests();concurrent_ad_tests();puts("live paging ordering/quarantine/reuse/atomicity checks passed");return 0;}
