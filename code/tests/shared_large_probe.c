/* Independent raw x86 PTE/PDE oracle. Context/Space stay opaque; only public
 * sizes and the caller-owned table pool/metadata are inspected. Counter-only
 * overflow seeding uses the compiler-verified final Stats field. No CPU
 * paging controls are touched by this host program. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
#define PAGE UINT64_C(4096)
#define LARGE UINT64_C(0x200000)
#define NX (UINT64_C(1)<<63)
#define ADDRESS UINT64_C(0x000ffffffffff000)
#define AD UINT64_C(0x60)
#define E_INVALID UINT64_C(0x02000003)
#define E_NOT_INIT UINT64_C(0x02000001)
#define E_OOM UINT64_C(0x02000007)
#define E_MAPPED UINT64_C(0x02030001)
#define E_NOT_MAPPED UINT64_C(0x02030002)
#define E_MALFORMED UINT64_C(0x02030003)
#define E_LARGE UINT64_C(0x02030006)
#define E_NOT_MERGEABLE UINT64_C(0x02030007)
#define E_CONTROLS UINT64_C(0x020a0002)
#define E_BUSY UINT64_C(0x020a0003)
#define E_CONTEXT UINT64_C(0x020a0001)
struct State{U cr0,cr3,cr4,efer,rflags,pat;};
struct Stats{U invlpg,full_flush,retired_tables;};
struct Mapping{U physical,flags;};
typedef void DG Flush(U,U);
extern DG U al_context_size(void),al_context_align(void),al_space_size(void),al_space_align(void);
extern DG void al_reset(void*,void*);
extern DG U al_init(void*,void*,U,U,void*),al_bind(void*,void*,const struct State*,U,U,U,U,Flush*);
extern DG U al_map_large(void*,const struct State*,U,U,U),al_split_large(void*,const struct State*,U),al_merge_large(void*,const struct State*,U);
extern DG U al_map(void*,const struct State*,U,U,U),al_replace(void*,const struct State*,U,U,U),al_protect(void*,const struct State*,U,U),al_unmap(void*,const struct State*,U);
extern DG U al_query(const void*,U,struct Mapping*),al_used(const void*),al_stats(const void*,struct Stats*);
static unsigned checks,callbacks,scenario,forbid_callback;
static const char *phase="initialization";
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"active large check failed scenario=%u phase=%s line=%d: %s\n",scenario,phase,__LINE__,#x);exit(1);}}while(0)
DG void __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const void *file,U length){(void)file;(void)length;fprintf(stderr,"unexpected panic %u/%u\n",kind,line);exit(2);}
struct Guard{uint8_t *allocation,*data;size_t size,guard;};
static struct Guard guarded(size_t size,size_t alignment){
 struct Guard g={0};g.size=size;g.guard=alignment<16?16:alignment;
 g.allocation=malloc(size+3*g.guard+alignment);CK(g.allocation!=NULL);
 g.data=(uint8_t*)(((uintptr_t)(g.allocation+g.guard)+alignment-1)&~(uintptr_t)(alignment-1));
 memset(g.data-g.guard,0xa5,g.guard);memset(g.data,0x6b,size);memset(g.data+size,0x5a,g.guard);return g;
}
static void guard(const struct Guard *g){for(size_t i=0;i<g->guard;i++){CK(g->data[-(ptrdiff_t)g->guard+(ptrdiff_t)i]==0xa5);CK(g->data[g->size+i]==0x5a);}}
struct Fixture{struct Guard context,space,pool,meta;size_t count;U pool_pa,va,pages,frame,frames;struct State state;};
static struct Fixture fixture(size_t count,U pages,U frames){
 scenario++;struct Fixture f={guarded((size_t)al_context_size(),(size_t)al_context_align()),guarded((size_t)al_space_size(),(size_t)al_space_align()),guarded(count*4096,4096),guarded(count+16,8),count,0x200000,UINT64_C(0xffffa20000000000),pages,UINT64_C(0x1000000000),frames,{0x80010033,0x200000,0x668,0xd00,2,UINT64_C(0x0007040600070406)}};
 al_reset(f.context.data,f.space.data);CK(al_init(f.space.data,f.pool.data,count,f.pool_pa,f.meta.data)==0);return f;
}
static void intact(const struct Fixture *f){guard(&f->context);guard(&f->space);guard(&f->pool);guard(&f->meta);for(size_t i=f->count;i<f->meta.size;i++)CK(f->meta.data[i]==0x6b);}
static void destroy(struct Fixture *f){intact(f);free(f->context.allocation);free(f->space.allocation);free(f->pool.allocation);free(f->meta.allocation);}
struct Snapshot{uint8_t *context,*space,*pool,*meta;struct State state;};
static struct Snapshot snapshot(const struct Fixture *f){
 struct Snapshot s={malloc(f->context.size),malloc(f->space.size),malloc(f->pool.size),malloc(f->meta.size),f->state};CK(s.context&&s.space&&s.pool&&s.meta);
 memcpy(s.context,f->context.data,f->context.size);memcpy(s.space,f->space.data,f->space.size);memcpy(s.pool,f->pool.data,f->pool.size);memcpy(s.meta,f->meta.data,f->meta.size);return s;
}
static void unchanged(const struct Fixture *f,struct Snapshot s){CK(!memcmp(s.context,f->context.data,f->context.size));CK(!memcmp(s.space,f->space.data,f->space.size));CK(!memcmp(s.pool,f->pool.data,f->pool.size));CK(!memcmp(s.meta,f->meta.data,f->meta.size));CK(!memcmp(&s.state,&f->state,sizeof s.state));intact(f);free(s.context);free(s.space);free(s.pool);free(s.meta);}
#define FAIL(f,call,code) do{struct Snapshot saved=snapshot(f);unsigned before=callbacks;forbid_callback++;U outcome=(call);forbid_callback--;CK(outcome==(code));CK(callbacks==before);unchanged(f,saved);}while(0)
struct Path{U *entry[4];size_t table[4];unsigned leaf_level;};
static int walk(const struct Fixture *f,U virtual,struct Mapping *out,struct Path *path){
 size_t table=0;U *pool=(U*)f->pool.data;
 for(unsigned level=0;level<4;level++){
  CK(table<f->count&&f->meta.data[table]==1);U *entry=&pool[table*512+((virtual>>(39-level*9))&511)],value=*entry;
  if(path){path->entry[level]=entry;path->table[level]=table;path->leaf_level=level;}
  if(!(value&1)){CK(value==0);return 0;}
  if(level==3||(level==2&&(value&0x80))){
   U offset=level==2?LARGE-1:PAGE-1,mask=ADDRESS&~offset;
   U permitted=mask|NX|AD|3|(level==2?0x80:0);CK((value&~permitted)==0);CK(value&NX);
   out->physical=(value&mask)+(virtual&offset);out->flags=(value&2)?1:0;return 1;
  }
  CK((value&~(ADDRESS|UINT64_C(0x27)))==0&&(value&7)==7);CK((value&ADDRESS)>=f->pool_pa);
  table=(size_t)(((value&ADDRESS)-f->pool_pa)/PAGE);
 }
 return 0;
}
static void mapping(const struct Fixture *f,U virtual,U physical,U flags,unsigned level){
 struct Mapping raw={0},out={UINT64_MAX,UINT64_MAX};struct Path path;
 CK(walk(f,virtual,&raw,&path));CK(raw.physical==physical&&raw.flags==flags&&path.leaf_level==level);
 CK(al_query(f->context.data,virtual,&out)==0&&out.physical==physical&&out.flags==flags);
}
static size_t metadata(const struct Fixture *f,unsigned value){size_t n=0;for(size_t i=0;i<f->count;i++){CK(f->meta.data[i]<=2);n+=f->meta.data[i]==value;}return n;}
struct Expect{struct Fixture *f;U kind,va,physical,flags,tables;unsigned level;size_t retired,retired_index;int full_check;};
static struct Expect expected;
static void DG flushed(U kind,U virtual){
 CK(!forbid_callback);struct Fixture *f=expected.f;callbacks++;CK(kind==expected.kind);CK(kind==1||kind==2);CK(virtual==expected.va);CK(al_used(f->space.data)==expected.tables);
 mapping(f,virtual,expected.physical,expected.flags,expected.level);
 CK(metadata(f,2)==expected.retired);
 if(expected.retired){
  CK(expected.retired==1&&expected.retired_index<f->count);CK(f->meta.data[expected.retired_index]==2);
  U *old=(U*)f->pool.data+expected.retired_index*512;
  CK(old[0]!=0&&old[511]!=0); /* The detached PT remains readable and owned. */
 }
 if(expected.full_check)for(U page=0;page<512;page++)mapping(f,f->va+page*PAGE,f->frame+page*PAGE,expected.flags,expected.level);
 FAIL(f,al_map_large(f->context.data,&f->state,virtual,f->frame,1),E_BUSY);
 FAIL(f,al_split_large(f->context.data,&f->state,virtual),E_BUSY);
 FAIL(f,al_merge_large(f->context.data,&f->state,virtual),E_BUSY);
 FAIL(f,al_map(f->context.data,&f->state,virtual,f->frame,1),E_BUSY);
 FAIL(f,al_replace(f->context.data,&f->state,virtual,f->frame,1),E_BUSY);
 FAIL(f,al_protect(f->context.data,&f->state,virtual,0),E_BUSY);
 FAIL(f,al_unmap(f->context.data,&f->state,virtual),E_BUSY);
}
static void bind_fixture(struct Fixture *f){unsigned before=callbacks;CK(al_bind(f->context.data,f->space.data,&f->state,f->va,f->pages,f->frame,f->frames,flushed)==0);CK(callbacks==before);}
static void expect(struct Fixture *f,unsigned level,U tables,size_t retired,size_t retired_index,int full){expected=(struct Expect){f,2,f->va,f->frame,1,tables,level,retired,retired_index,full};}
static void stats(const struct Fixture *f,U roots,U retired,U pages){struct Stats s={0};CK(al_stats(f->context.data,&s)==0);CK(s.invlpg==pages&&s.full_flush==roots&&s.retired_tables==retired);}
static void lifecycle(void){
 phase="full-root lifecycle";struct Fixture f=fixture(4,512,513);bind_fixture(&f);stats(&f,0,0,0);
 expect(&f,2,3,0,0,1);unsigned before=callbacks;
 CK(al_map_large(f.context.data,&f.state,f.va,f.frame,1)==0);CK(callbacks==before+1);stats(&f,1,0,0);
 struct Mapping m;struct Path path;CK(walk(&f,f.va,&m,&path));*path.entry[2]|=AD;
 expect(&f,3,4,0,0,1);before=callbacks;CK(al_split_large(f.context.data,&f.state,f.va)==0);CK(callbacks==before+1);stats(&f,2,0,0);
 CK(walk(&f,f.va,&m,&path));size_t detached=path.table[3];U *pt=(U*)f.pool.data+detached*512;
 for(size_t i=0;i<512;i++)CK((pt[i]&AD)==AD);
 expect(&f,3,4,0,0,0);expected.kind=1;expected.va=f.va+17*PAGE;expected.physical=f.frame+512*PAGE;
 CK(al_replace(f.context.data,&f.state,expected.va,expected.physical,1)==0);
 mapping(&f,f.va+17*PAGE,f.frame+512*PAGE,1,3);
 FAIL(&f,al_merge_large(f.context.data,&f.state,f.va),E_NOT_MERGEABLE);
 expected.physical=f.frame+17*PAGE;CK(al_replace(f.context.data,&f.state,expected.va,expected.physical,1)==0);
 expect(&f,2,4,1,detached,1);before=callbacks;CK(al_merge_large(f.context.data,&f.state,f.va)==0);CK(callbacks==before+1);stats(&f,3,1,2);
 CK(metadata(&f,2)==0&&al_used(f.space.data)==3&&f.meta.data[detached]==0);
 for(size_t i=0;i<512;i++)CK(pt[i]==0);
 CK(walk(&f,f.va,&m,&path)&&(*path.entry[2]&AD)==AD);
 /* Reuse is legal only after the callback; exact exhausted-pool split now
  * reacquires the same retired slot, rather than leaking another table. */
 expect(&f,3,4,0,0,1);CK(al_split_large(f.context.data,&f.state,f.va)==0);
 CK(walk(&f,f.va,&m,&path)&&path.table[3]==detached);stats(&f,4,1,2);
 pt=(U*)f.pool.data+detached*512;for(size_t i=0;i<512;i++)pt[i]&=~AD;pt[3]|=0x20;pt[500]|=0x40;
 expect(&f,2,4,1,detached,1);CK(al_merge_large(f.context.data,&f.state,f.va)==0);
 CK(walk(&f,f.va,&m,&path)&&(*path.entry[2]&AD)==AD);stats(&f,5,2,2);destroy(&f);
}
static void bounds(void){
 phase="whole 512-page owned bounds";
 const U lengths[]={1,511,512,513};
 for(size_t i=0;i<sizeof lengths/sizeof *lengths;i++){
  struct Fixture f=fixture(4,lengths[i],513);bind_fixture(&f);
  if(lengths[i]<512)FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,1),E_INVALID);
  else{expect(&f,2,3,0,0,1);CK(al_map_large(f.context.data,&f.state,f.va,f.frame,1)==0);}destroy(&f);
  f=fixture(4,512,lengths[i]);bind_fixture(&f);
  if(lengths[i]<512)FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,1),E_INVALID);
  else{expect(&f,2,3,0,0,1);CK(al_map_large(f.context.data,&f.state,f.va,f.frame,1)==0);}destroy(&f);
 }
 struct Fixture f=fixture(4,512,513);bind_fixture(&f);
 const U vas[]={f.va-PAGE,f.va+PAGE,f.va+LARGE,UINT64_C(0x0000800000000000),UINT64_MAX};
 for(size_t i=0;i<sizeof vas/sizeof *vas;i++){FAIL(&f,al_map_large(f.context.data,&f.state,vas[i],f.frame,1),E_INVALID);FAIL(&f,al_split_large(f.context.data,&f.state,vas[i]),E_INVALID);FAIL(&f,al_merge_large(f.context.data,&f.state,vas[i]),E_INVALID);}
 const U pas[]={f.frame-PAGE,f.frame+PAGE,f.frame+LARGE,UINT64_C(1)<<52,UINT64_MAX};
 for(size_t i=0;i<sizeof pas/sizeof *pas;i++)FAIL(&f,al_map_large(f.context.data,&f.state,f.va,pas[i],1),E_INVALID);
 for(U flag=2;flag<32;flag++)FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,flag),E_INVALID);
 struct State altered=f.state;altered.cr3+=PAGE;FAIL(&f,al_map_large(f.context.data,&altered,f.va,f.frame,1),E_CONTROLS);
 altered=f.state;altered.rflags|=0x200;FAIL(&f,al_map_large(f.context.data,&altered,f.va,f.frame,1),E_CONTROLS);
 FAIL(&f,al_split_large(f.context.data,&f.state,f.va),E_NOT_MAPPED);FAIL(&f,al_merge_large(f.context.data,&f.state,f.va),E_NOT_MAPPED);destroy(&f);
}
static void failure_atomicity(void){
 phase="error atomicity and OOM";struct Fixture f=fixture(2,512,513);bind_fixture(&f);FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,1),E_OOM);CK(al_used(f.space.data)==1);destroy(&f);
 f=fixture(3,512,513);bind_fixture(&f);expect(&f,2,3,0,0,1);CK(al_map_large(f.context.data,&f.state,f.va,f.frame,1)==0);
 FAIL(&f,al_split_large(f.context.data,&f.state,f.va),E_OOM);stats(&f,1,0,0);destroy(&f);
 f=fixture(4,512,513);bind_fixture(&f);expect(&f,2,3,0,0,1);CK(al_map_large(f.context.data,&f.state,f.va,f.frame,1)==0);
 FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,1),E_MAPPED);FAIL(&f,al_merge_large(f.context.data,&f.state,f.va),E_INVALID);
 FAIL(&f,al_protect(f.context.data,&f.state,f.va+17*PAGE,0),E_LARGE);FAIL(&f,al_replace(f.context.data,&f.state,f.va+17*PAGE,f.frame+512*PAGE,1),E_LARGE);FAIL(&f,al_unmap(f.context.data,&f.state,f.va+17*PAGE),E_LARGE);
 expect(&f,3,4,0,0,1);CK(al_split_large(f.context.data,&f.state,f.va)==0);FAIL(&f,al_split_large(f.context.data,&f.state,f.va),E_INVALID);
 struct Mapping m;struct Path p;CK(walk(&f,f.va+17*PAGE,&m,&p));U *entry=p.entry[3],original=*entry;
 const struct{U value,code;} bad[]={
  {((original&~ADDRESS)|(f.frame+513*PAGE)),E_INVALID},
  {original|4,E_MALFORMED}, /* USER is malformed in this kernel-half VA. */
  {original&~(NX|UINT64_C(2)),E_INVALID}, /* Valid RX; forbidden by this WB/NX Context. */
  {original|0x18,E_INVALID},{original|0x80,E_INVALID}};
 for(size_t i=0;i<sizeof bad/sizeof *bad;i++){*entry=bad[i].value;FAIL(&f,al_merge_large(f.context.data,&f.state,f.va),bad[i].code);*entry=original;}
 *entry=original&~2;FAIL(&f,al_merge_large(f.context.data,&f.state,f.va),E_NOT_MERGEABLE);*entry=original;
 /* A noncontiguous but still-owned last physical frame is refused. */
 *entry=(original&~ADDRESS)|(f.frame+512*PAGE);FAIL(&f,al_merge_large(f.context.data,&f.state,f.va),E_NOT_MERGEABLE);*entry=original;
 stats(&f,2,0,0);destroy(&f);
}
static void readonly_and_unbound(void){
 phase="readonly and unbound";struct Fixture f=fixture(4,512,512);
 FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,0),E_NOT_INIT);
 FAIL(&f,al_split_large(f.context.data,&f.state,f.va),E_NOT_INIT);
 FAIL(&f,al_merge_large(f.context.data,&f.state,f.va),E_NOT_INIT);
 bind_fixture(&f);expect(&f,2,3,0,0,1);expected.flags=0;
 CK(al_map_large(f.context.data,&f.state,f.va,f.frame,0)==0);
 struct Mapping m;struct Path p;CK(walk(&f,f.va,&m,&p));U original=*p.entry[2];*p.entry[2]|=UINT64_C(1)<<13;
 FAIL(&f,al_split_large(f.context.data,&f.state,f.va),E_MALFORMED);*p.entry[2]=original;
 expect(&f,3,4,0,0,1);expected.flags=0;CK(al_split_large(f.context.data,&f.state,f.va)==0);
 CK(walk(&f,f.va,&m,&p));expect(&f,2,4,1,p.table[3],1);expected.flags=0;
 CK(al_merge_large(f.context.data,&f.state,f.va)==0);stats(&f,3,1,0);destroy(&f);
}
extern DG void sl_domain_fault(U);
extern DG U sl_seal(void*);
static void domain_and_seal(void){
 phase="domain and sealed owner";
 for(U fault=1;fault<=6;fault++){struct Fixture f=fixture(4,512,512);bind_fixture(&f);sl_domain_fault(fault);FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,1),UINT64_C(0x060e0001));destroy(&f);}
 struct Fixture f=fixture(4,512,512);bind_fixture(&f);CK(sl_seal(f.context.data)==0);FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,1),UINT64_C(0x060e0002));destroy(&f);
}
static void counter_overflow(void){
 phase="counter overflow before mutation";
 for(unsigned operation=0;operation<3;operation++)for(unsigned field=0;field<3;field++){
  struct Fixture f=fixture(4,512,513);bind_fixture(&f);
  if(operation>=1){expect(&f,2,3,0,0,1);CK(al_map_large(f.context.data,&f.state,f.va,f.frame,1)==0);}
  if(operation>=2){expect(&f,3,4,0,0,1);CK(al_split_large(f.context.data,&f.state,f.va)==0);}
  struct Stats seeded={0,0,0};
  if(field==0)seeded.invlpg=UINT64_MAX;
  else if(field==1)seeded.full_flush=UINT64_MAX;
  else seeded.retired_tables=UINT64_MAX-2;
  /* The Python runner checks this exact field/type/offset in the real
   * compiler manifest. This changes only a formal production counter. */
  CK(f.context.size>=128);memcpy(f.context.data+104,&seeded,sizeof seeded);
  if(operation==0)FAIL(&f,al_map_large(f.context.data,&f.state,f.va,f.frame,1),E_CONTEXT);
  else if(operation==1)FAIL(&f,al_split_large(f.context.data,&f.state,f.va),E_CONTEXT);
  else FAIL(&f,al_merge_large(f.context.data,&f.state,f.va),E_CONTEXT);
  destroy(&f);
 }
}
int main(void){lifecycle();bounds();failure_atomicity();readonly_and_unbound();counter_overflow();domain_and_seal();printf("shared large native checks passed %u scenarios=%u callbacks=%u\n",checks,scenario,callbacks);return 0;}
