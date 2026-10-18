/* Independent slot/payload model and raw page-table/physical-ownership oracle.
 * Host VA is real native storage; PA is a distinct >4GiB numeric buddy arena.
 * The callback observes order, never claims to execute a hardware TLB flush. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define PAGE UINT64_C(4096)
#define ARENA UINT64_C(0x900000000)
#define POOL_PA UINT64_C(0x200000)
#define ADDRESS UINT64_C(0x000ffffffffff000)
#define NX (UINT64_C(1)<<63)
#define CAP 128
#define STRIDE 32
#define OBJECT 24
#define E_NOT_INIT UINT64_C(0x02000001)
#define E_ALREADY UINT64_C(0x02000002)
#define E_INVALID UINT64_C(0x02000003)
#define E_META UINT64_C(0x02000004)
#define E_OOM UINT64_C(0x02000007)
#define E_FREE UINT64_C(0x02000008)
#define E_CONTROLS UINT64_C(0x020a0002)
#define E_BUSY UINT64_C(0x020a0003)
#define E_IN_USE UINT64_C(0x020d0001)
#define E_CLEANUP UINT64_C(0x020d0002)
struct State {uint64_t cr0,cr3,cr4,efer,rflags,pat;};
struct Info {uint64_t physical,virtual,capacity,free_objects,mapped,ready;};
struct Mapping {uint64_t physical,flags;};
typedef void DG Flush(uint64_t,uint64_t);
extern uint64_t DG pc_owner_size(void),pc_owner_align(void),pc_info_size(void),pc_info_align(void);
extern uint64_t DG pc_buddy_size(void),pc_buddy_align(void),pc_page_meta_size(void),pc_page_meta_align(void);
extern uint64_t DG pc_slot_size(void),pc_slot_align(void),pc_space_size(void),pc_space_align(void);
extern void DG pc_owner_reset(void*),pc_buddy_reset(void*),pc_space_reset(void*);
extern uint64_t DG pc_buddy_init(void*,uint64_t,uint64_t,void*,uint64_t),pc_buddy_add(void*,uint64_t,uint64_t),pc_buddy_count(const void*,uint64_t*);
extern uint64_t DG pc_paging_init(void*,void*,uint64_t,uint64_t,void*),pc_paging_used(const void*,uint64_t*);
extern uint64_t DG pc_paging_query(const void*,uint64_t,struct Mapping*),pc_paging_map(void*,uint64_t,uint64_t);
extern uint64_t DG pc_create(void*,void*,void*,const struct State*,uint64_t,uint64_t,uint64_t,void*,uint64_t,Flush*);
extern uint64_t DG pc_alloc(void*,uint64_t*),pc_free(void*,void*),pc_describe(void*,struct Info*),pc_destroy(void*,const struct State*);
static const char *phase="init";
static unsigned negative_hits;
static unsigned negative_armed;
static unsigned cleanup_armed,cleanup_hits[3];
#define CHECK(X) do{if(!(X)){fprintf(stderr,"page cache failure phase=%s line=%d: %s\n",phase,__LINE__,#X);exit(1);}}while(0)
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
 fprintf(stderr,"unexpected page cache panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char*)file);exit(99);
}
void DG pc_negative_hit(uint64_t kind){fprintf(stderr,"PC_NEGATIVE_HIT=%u kind=%u\n",++negative_hits,(unsigned)kind);}
uint64_t DG pc_negative_armed(void){return negative_armed;}
uint64_t DG pc_cleanup_fault(uint64_t stage){
 CHECK(stage==1||stage==2);
 if(cleanup_armed&&!cleanup_hits[stage]){cleanup_hits[stage]++;fprintf(stderr,"PC_CLEANUP_HIT stage=%u count=1\n",(unsigned)stage);return 1;}
 return 0;
}
struct Guard {uint8_t *raw,*data;size_t size;};
static struct Guard guarded(size_t size,size_t alignment){
 struct Guard g={0};CHECK(alignment&&!(alignment&(alignment-1)));g.size=size;
 g.raw=malloc(size+alignment+48);CHECK(g.raw!=NULL);
 g.data=(uint8_t*)(((uintptr_t)(g.raw+16)+alignment-1)&~(uintptr_t)(alignment-1));
 memset(g.data-16,0xa5,16);memset(g.data,0x6b,size);memset(g.data+size,0x5a,16);return g;
}
static void guard(const struct Guard *g){for(size_t i=0;i<16;i++){CHECK(g->data[-16+(ptrdiff_t)i]==0xa5);CHECK(g->data[g->size+i]==0x5a);}}
struct Fixture {
 struct Guard owner[2],slots[2],buffer[2],buddy,physical_meta,space,pool,table_meta;
 struct State state;size_t tables,slot_size;
 uint8_t expected[2][4096];uint8_t *empty_owner;
 uint64_t physical[2];unsigned callbacks,maps,flushes;
};
static struct Guard *all_guards(struct Fixture *f,size_t n){
 switch(n){case 0:return &f->owner[0];case 1:return &f->owner[1];case 2:return &f->slots[0];case 3:return &f->slots[1];
 case 4:return &f->buffer[0];case 5:return &f->buffer[1];case 6:return &f->buddy;case 7:return &f->physical_meta;
 case 8:return &f->space;case 9:return &f->pool;default:CHECK(n==10);return &f->table_meta;}
}
static uint64_t pages(const struct Fixture *f){uint64_t out=UINT64_MAX;CHECK(pc_buddy_count(f->buddy.data,&out)==0);return out;}
static uint64_t tables(const struct Fixture *f){uint64_t out=UINT64_MAX;CHECK(pc_paging_used(f->space.data,&out)==0);return out;}
static void intact(struct Fixture *f){
 for(size_t n=0;n<11;n++)guard(all_guards(f,n));
 for(unsigned i=0;i<2;i++){
  CHECK(!memcmp(f->buffer[i].data,f->expected[i],4096));
  for(size_t n=CAP*f->slot_size;n<f->slots[i].size;n++)CHECK(f->slots[i].data[n]==0x6b);
 }
 for(size_t n=f->tables;n<f->table_meta.size;n++)CHECK(f->table_meta.data[n]==0x6b);
}
static struct Fixture fixture(size_t table_count,unsigned usable){
 struct Fixture f={0};f.tables=table_count;f.slot_size=(size_t)pc_slot_size();
 for(unsigned i=0;i<2;i++){
  f.owner[i]=guarded((size_t)pc_owner_size(),(size_t)pc_owner_align());pc_owner_reset(f.owner[i].data);
  f.slots[i]=guarded((CAP+2)*f.slot_size,(size_t)pc_slot_align());
  f.buffer[i]=guarded(4096,4096);memset(f.buffer[i].data,0x7b,4096);memset(f.expected[i],0x7b,4096);
 }
 f.buddy=guarded((size_t)pc_buddy_size(),(size_t)pc_buddy_align());pc_buddy_reset(f.buddy.data);
 f.physical_meta=guarded(16*(size_t)pc_page_meta_size(),(size_t)pc_page_meta_align());
 CHECK(pc_buddy_init(f.buddy.data,ARENA,16,f.physical_meta.data,16)==0);
 if(usable>0)CHECK(pc_buddy_add(f.buddy.data,1,1)==0);
 if(usable>1)CHECK(pc_buddy_add(f.buddy.data,6,1)==0);
 f.space=guarded((size_t)pc_space_size(),(size_t)pc_space_align());pc_space_reset(f.space.data);
 f.pool=guarded(table_count*4096,4096);f.table_meta=guarded(table_count+16,8);
 CHECK(pc_paging_init(f.space.data,f.pool.data,table_count,POOL_PA,f.table_meta.data)==0);
 f.state=(struct State){0x80010033,POOL_PA,0x300e20,0xd00,2,UINT64_C(0x0007040600070406)};
 f.empty_owner=malloc(f.owner[0].size);CHECK(f.empty_owner!=NULL);memcpy(f.empty_owner,f.owner[0].data,f.owner[0].size);
 CHECK(pages(&f)==usable&&tables(&f)==1);intact(&f);return f;
}
static void dispose(struct Fixture *f){intact(f);for(size_t n=0;n<11;n++)free(all_guards(f,n)->raw);free(f->empty_owner);}
struct Snapshot {uint8_t *bytes[11];unsigned callbacks,maps,flushes;};
static struct Snapshot snapshot(struct Fixture *f){
 struct Snapshot s={0};s.callbacks=f->callbacks;s.maps=f->maps;s.flushes=f->flushes;
 for(size_t n=0;n<11;n++){struct Guard *g=all_guards(f,n);s.bytes[n]=malloc(g->size);CHECK(s.bytes[n]!=NULL);memcpy(s.bytes[n],g->data,g->size);}return s;
}
static void unchanged(struct Fixture *f,struct Snapshot *s){
 CHECK(f->callbacks==s->callbacks&&f->maps==s->maps&&f->flushes==s->flushes);
 for(size_t n=0;n<11;n++){struct Guard *g=all_guards(f,n);CHECK(!memcmp(g->data,s->bytes[n],g->size));free(s->bytes[n]);}intact(f);
}
#define FAIL(F,CALL,CODE) do{struct Snapshot _s=snapshot(F);CHECK((CALL)==(CODE));unchanged(F,&_s);}while(0)
static int raw_walk(const struct Fixture *f,uint64_t va,struct Mapping *out){
 size_t slot=0;uint64_t *pool=(uint64_t*)f->pool.data;
 for(unsigned level=0;level<4;level++){
  CHECK(slot<f->tables&&f->table_meta.data[slot]==1);
  uint64_t entry=pool[slot*512+((va>>(39-9*level))&511)];
  if(!(entry&1)){CHECK(entry==0);return 0;}
  if(level==3){CHECK(!(entry&~(ADDRESS|UINT64_C(0x67)|NX)));CHECK((entry&NX)&&!(entry&UINT64_C(0x1c)));
   out->physical=(entry&ADDRESS)|(va&4095);out->flags=(entry&2)?1:0;return 1;}
  CHECK((entry&7)==7&&!(entry&~(ADDRESS|UINT64_C(0x27))));
  CHECK((entry&ADDRESS)>=POOL_PA&&((entry&ADDRESS)-POOL_PA)%4096==0);slot=(size_t)(((entry&ADDRESS)-POOL_PA)/4096);
 }return 0;
}
static unsigned quarantine(const struct Fixture *f){
 unsigned held=0,retired=0;for(size_t i=0;i<f->tables;i++){
  unsigned value=f->table_meta.data[i];CHECK(value<=2);held+=value!=0;
  if(value==2){retired++;for(size_t j=0;j<4096;j++)CHECK(f->pool.data[i*4096+j]==0);}
 }CHECK(held==tables(f));return retired;
}
struct Expected {struct Fixture *fixture;unsigned owner;uint64_t kind,free_pages,held_tables;};
static struct Expected expected;
static void DG flush_callback(uint64_t kind,uint64_t va){
 struct Fixture *f=expected.fixture;CHECK(f!=NULL);CHECK(kind==expected.kind&&va==(uintptr_t)f->buffer[expected.owner].data);
 f->callbacks++;CHECK(pages(f)==expected.free_pages);
 struct Mapping raw={0},query={UINT64_MAX,UINT64_MAX};
 if(kind==1){
  CHECK(raw_walk(f,va,&raw));CHECK(pc_paging_query(f->space.data,va,&query)==0);
  CHECK(raw.physical==query.physical&&raw.flags==query.flags&&raw.flags==1);
  CHECK(raw.physical==ARENA+PAGE||raw.physical==ARENA+6*PAGE);
  CHECK(raw.physical!=f->physical[expected.owner^1]);f->physical[expected.owner]=raw.physical;
  CHECK(quarantine(f)==0);f->maps++;
 }else{
  CHECK(kind==2);CHECK(!raw_walk(f,va,&raw));CHECK(pc_paging_query(f->space.data,va,&query)==UINT64_C(0x02030002));
  CHECK(tables(f)==expected.held_tables);(void)quarantine(f);f->flushes++;
  /* The same owner is closing. No nested operation may resurrect a live
   * object after the outer destroy already established that the cache is empty. */
  unsigned owner=expected.owner;uint64_t output=UINT64_C(0x1122334455667788);
  FAIL(f,pc_alloc(f->owner[owner].data,&output),E_BUSY);CHECK(output==UINT64_C(0x1122334455667788));
  FAIL(f,pc_free(f->owner[owner].data,f->buffer[owner].data),E_BUSY);
  FAIL(f,pc_destroy(f->owner[owner].data,&f->state),E_BUSY);
  FAIL(f,pc_create(f->owner[owner].data,f->buddy.data,f->space.data,&f->state,va,OBJECT,16,f->slots[owner].data,CAP,flush_callback),E_BUSY);
 }
 intact(f);
}
static void expect_create(struct Fixture *f,unsigned owner,uint64_t free_pages){expected=(struct Expected){f,owner,1,free_pages,0};}
static uint64_t create(struct Fixture *f,unsigned owner){return pc_create(f->owner[owner].data,f->buddy.data,f->space.data,&f->state,(uintptr_t)f->buffer[owner].data,OBJECT,16,f->slots[owner].data,CAP,flush_callback);}
static struct Info info(struct Fixture *f,unsigned owner,uint64_t free_objects){
 struct {uint64_t before;struct Info value;uint64_t after;} g={UINT64_C(0x123456789abcdef0),{0},UINT64_C(0xfedcba9876543210)};
 CHECK(pc_describe(f->owner[owner].data,&g.value)==0);CHECK(g.before==UINT64_C(0x123456789abcdef0)&&g.after==UINT64_C(0xfedcba9876543210));
 CHECK(g.value.physical==f->physical[owner]&&g.value.virtual==(uintptr_t)f->buffer[owner].data);
 CHECK(g.value.capacity==CAP&&g.value.free_objects==free_objects&&g.value.mapped==1&&g.value.ready==1);intact(f);return g.value;
}
static uint64_t allocate(struct Fixture *f,unsigned owner){
 uint64_t out=UINT64_MAX;CHECK(pc_alloc(f->owner[owner].data,&out)==0);
 uint64_t va=(uintptr_t)f->buffer[owner].data;CHECK(out>=va&&out<va+PAGE);CHECK((out-va)%STRIDE==0);CHECK(out%16==0);intact(f);return out;
}
static void destroy(struct Fixture *f,unsigned owner,uint64_t free_before){
 expected=(struct Expected){f,owner,2,free_before,tables(f)};
 CHECK(pc_destroy(f->owner[owner].data,&f->state)==0);CHECK(pages(f)==free_before+1);
 CHECK(!memcmp(f->owner[owner].data,f->empty_owner,f->owner[owner].size));CHECK(quarantine(f)==0);f->physical[owner]=0;intact(f);
}
static void lifecycle(void){
 phase="two physical leases and payload/padding lifecycle";struct Fixture f=fixture(16,2);
 expect_create(&f,0,1);CHECK(create(&f,0)==0);CHECK(pages(&f)==1);info(&f,0,CAP);
 expect_create(&f,1,0);CHECK(create(&f,1)==0);CHECK(pages(&f)==0);info(&f,1,CAP);
 CHECK(f.physical[0]!=f.physical[1]);
 FAIL(&f,create(&f,0),E_ALREADY);
 uint64_t held[CAP];uint8_t occupied[CAP]={0};
 for(unsigned i=0;i<CAP;i++){
  held[i]=allocate(&f,0);size_t slot=(size_t)((held[i]-(uintptr_t)f.buffer[0].data)/STRIDE);CHECK(!occupied[slot]);occupied[slot]=1;
  for(unsigned j=0;j<OBJECT;j++){uint8_t v=(uint8_t)(3+slot*7+j);((uint8_t*)(uintptr_t)held[i])[j]=v;f.expected[0][slot*STRIDE+j]=v;}intact(&f);
 }
 info(&f,0,0);uint64_t unchanged_output=UINT64_C(0x1122334455667788);
 FAIL(&f,pc_alloc(f.owner[0].data,&unchanged_output),E_OOM);CHECK(unchanged_output==UINT64_C(0x1122334455667788));
 FAIL(&f,pc_destroy(f.owner[0].data,&f.state),E_IN_USE);
 uint64_t b=allocate(&f,1);info(&f,1,CAP-1);
 FAIL(&f,pc_free(f.owner[0].data,(void*)(uintptr_t)b),E_FREE);
 FAIL(&f,pc_free(f.owner[0].data,NULL),E_FREE);
 FAIL(&f,pc_free(f.owner[0].data,(void*)(uintptr_t)(held[0]+1)),E_FREE);
 CHECK(pc_free(f.owner[0].data,(void*)(uintptr_t)held[17])==0);intact(&f);info(&f,0,1);
 CHECK(allocate(&f,0)==held[17]);info(&f,0,0);
 for(unsigned i=0;i<CAP;i++){CHECK(pc_free(f.owner[0].data,(void*)(uintptr_t)held[i])==0);intact(&f);}
 info(&f,0,CAP);FAIL(&f,pc_free(f.owner[0].data,(void*)(uintptr_t)held[0]),E_FREE);
 FAIL(&f,pc_destroy(f.owner[1].data,&f.state),E_IN_USE);
 CHECK(pc_free(f.owner[1].data,(void*)(uintptr_t)b)==0);intact(&f);info(&f,1,CAP);
 phase="unmap flush completes before physical page release";negative_armed=1;destroy(&f,0,0);destroy(&f,1,1);CHECK(tables(&f)==1&&pages(&f)==2);
 phase="empty owner can be reused";expect_create(&f,0,1);CHECK(create(&f,0)==0);info(&f,0,CAP);
 uint64_t p=allocate(&f,0);CHECK(pc_free(f.owner[0].data,(void*)(uintptr_t)p)==0);intact(&f);destroy(&f,0,1);
 CHECK(f.maps==3&&f.flushes==3&&f.callbacks==6&&pages(&f)==2&&tables(&f)==1);dispose(&f);
}
static void preconditions(void){
 phase="precondition failures preserve every owned byte";struct Fixture f=fixture(16,2);uint64_t out=0x87654321;
 FAIL(&f,pc_alloc(f.owner[0].data,&out),E_NOT_INIT);CHECK(out==0x87654321);
 struct Info empty_info,saved_info;memset(&empty_info,0x6b,sizeof empty_info);saved_info=empty_info;
 FAIL(&f,pc_describe(f.owner[0].data,&empty_info),E_NOT_INIT);CHECK(!memcmp(&empty_info,&saved_info,sizeof empty_info));
 FAIL(&f,pc_free(f.owner[0].data,f.buffer[0].data),E_NOT_INIT);
 FAIL(&f,pc_destroy(f.owner[0].data,&f.state),E_NOT_INIT);
 FAIL(&f,pc_create(f.owner[0].data,f.buddy.data,f.space.data,&f.state,(uintptr_t)f.buffer[0].data,0,16,f.slots[0].data,CAP,flush_callback),E_INVALID);
 FAIL(&f,pc_create(f.owner[0].data,f.buddy.data,f.space.data,&f.state,(uintptr_t)f.buffer[0].data,OBJECT,3,f.slots[0].data,CAP,flush_callback),E_INVALID);
 FAIL(&f,pc_create(f.owner[0].data,f.buddy.data,f.space.data,&f.state,(uintptr_t)f.buffer[0].data+1,OBJECT,16,f.slots[0].data,CAP,flush_callback),E_INVALID);
 FAIL(&f,pc_create(f.owner[0].data,f.buddy.data,f.space.data,&f.state,(uintptr_t)f.buffer[0].data,OBJECT,16,f.slots[0].data,CAP-1,flush_callback),E_META);
 struct State bad=f.state;bad.cr3+=PAGE;
 FAIL(&f,pc_create(f.owner[0].data,f.buddy.data,f.space.data,&bad,(uintptr_t)f.buffer[0].data,OBJECT,16,f.slots[0].data,CAP,flush_callback),E_CONTROLS);
 expect_create(&f,0,1);CHECK(create(&f,0)==0);info(&f,0,CAP);
 FAIL(&f,pc_destroy(f.owner[0].data,&bad),E_CONTROLS);info(&f,0,CAP);destroy(&f,0,1);dispose(&f);
 phase="physical OOM is unchanged";struct Fixture empty=fixture(16,0);FAIL(&empty,create(&empty,0),E_OOM);dispose(&empty);
}
static void rollback(void){
 phase="failed map returns the physical lease without publishing owner";struct Fixture f=fixture(3,2);
 uint8_t *owner=malloc(f.owner[0].size);CHECK(owner!=NULL);memcpy(owner,f.owner[0].data,f.owner[0].size);
 uint8_t *slots=malloc(f.slots[0].size);CHECK(slots!=NULL);memcpy(slots,f.slots[0].data,f.slots[0].size);
 CHECK(create(&f,0)==E_OOM);CHECK(f.callbacks==0&&pages(&f)==2&&tables(&f)==1);
 CHECK(!memcmp(owner,f.owner[0].data,f.owner[0].size));struct Mapping got={0};CHECK(!raw_walk(&f,(uintptr_t)f.buffer[0].data,&got));
 CHECK(quarantine(&f)==0);CHECK(!memcmp(slots,f.slots[0].data,f.slots[0].size));intact(&f);free(owner);free(slots);dispose(&f);
}
static void cleanup_recovery(void){
 phase="post-map init failure plus precommit cleanup failure";struct Fixture f=fixture(16,1);
 cleanup_armed=1;expect_create(&f,0,0);CHECK(create(&f,0)==E_CLEANUP);
 CHECK(cleanup_hits[1]==1&&cleanup_hits[2]==1);CHECK(f.callbacks==1&&f.maps==1&&f.flushes==0);
 CHECK(pages(&f)==0&&tables(&f)==4);CHECK(memcmp(f.owner[0].data,f.empty_owner,f.owner[0].size)!=0);
 struct Mapping mapping={0};CHECK(raw_walk(&f,(uintptr_t)f.buffer[0].data,&mapping));
 CHECK(mapping.physical==ARENA+PAGE&&mapping.flags==1);CHECK(quarantine(&f)==0);intact(&f);
 uint64_t output=UINT64_C(0x1122334455667788);
 FAIL(&f,pc_alloc(f.owner[0].data,&output),E_NOT_INIT);CHECK(output==UINT64_C(0x1122334455667788));
 FAIL(&f,pc_free(f.owner[0].data,f.buffer[0].data),E_NOT_INIT);
 struct Info value,saved;memset(&value,0x6b,sizeof value);saved=value;
 FAIL(&f,pc_describe(f.owner[0].data,&value),E_NOT_INIT);CHECK(!memcmp(&value,&saved,sizeof value));
 FAIL(&f,create(&f,0),E_ALREADY);
 phase="retry cleanup flushes and then returns still-owned physical page";destroy(&f,0,0);
 CHECK(cleanup_hits[1]==1&&cleanup_hits[2]==1);CHECK(f.callbacks==2&&f.maps==1&&f.flushes==1);
 CHECK(pages(&f)==1&&tables(&f)==1);dispose(&f);puts("page cache cleanup failure/retry passed");
}
int main(int argc,char **argv){
 CHECK(pc_info_size()==sizeof(struct Info)&&pc_info_align()==_Alignof(struct Info));
 if(argc==2&&!strcmp(argv[1],"--cleanup-recovery")){cleanup_recovery();return 0;}
 CHECK(argc==1);
 preconditions();lifecycle();rollback();puts("page cache ownership/ordering/payload model passed");return 0;
}
