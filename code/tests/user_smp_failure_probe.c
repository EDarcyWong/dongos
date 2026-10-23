/* Appended to the unchanged current-entry native boundary fixture by the test.
 * The actual Dong Bridge/Domain/queue execute; CR3, clock, IPI and TLB inputs
 * below are explicitly synthetic host boundaries, never actual AP execution. */
typedef struct {
 U published,version,cpu,argument_cpu,entry,vector,stage,error_code,detail_code,clock;
 U domain_available,domain,sequence,owner,lock,mode,requested,acknowledged,barrier,completed;
 U published_kernel_root,raw_root_available,raw_root,normalized_root_available,normalized_root;
 U wait_started,deadline,acquired;
} Failure;
typedef struct {U entry,vector,stage,wait_started,deadline,acquired;} Progress;
typedef struct {U ready,failed;Domain*domain;void*pending;U*headers;U service_cpu,calls,deferred;} Bridge;
extern const Failure* ABI uf_failure(U);
extern const Progress* ABI uf_progress(U);
extern Bridge* ABI uf_bridge(void);
extern U ABI uf_size(U);
extern U ABI uf_version(void);
U diagnostic_legacy,diagnostic_project,diagnostic_nested;
static U diagnostic_wait_jump;
static U diagnostic_observe_enabled,diagnostic_observations;
_Static_assert(sizeof(Failure)==224,"independent failure ABI v2");
_Static_assert(sizeof(Progress)==48,"independent progress ABI v2");
_Static_assert(sizeof(Bridge)==64,"existing Bridge ABI");
_Static_assert(sizeof(Domain)==120&&sizeof(Cpu)==120&&sizeof(Header)==256,"unchanged ownership ABI");
void diagnostic_observe(void){
 if(!diagnostic_observe_enabled||cpu>=16)return;
 const Failure*f=uf_failure(cpu);
 if(!f->published&&diagnostic_wait_jump&&uf_progress(cpu)->stage==5){
  clock_tick+=diagnostic_wait_jump;diagnostic_wait_jump=0;
 }
 if(f->published){C(f->published==2);diagnostic_observations++;}
}
static void empty_slots_except(U selected){
 Failure zero={0};
 for(U id=0;id<16;id++)if(id!=selected)C(!memcmp(uf_failure(id),&zero,sizeof zero));
}
static void verify_failure(U id,U argument,U entry,U vector,U stage,U code,U detail){
 const Failure*f=uf_failure(id);
 C(f&&f->published==1&&f->version==2&&f->cpu==id&&f->argument_cpu==argument);
 C(f->entry==entry&&f->vector==vector&&f->stage==stage&&f->error_code==code&&f->detail_code==detail);
 C(f->clock>0&&f->domain_available==1&&f->domain==(U)(uintptr_t)d);
 C(f->sequence==d->sequence&&f->owner==d->owner&&f->lock==d->lock&&f->mode==d->cpus[id].mode);
 C(f->requested==d->cpus[id].requested&&f->acknowledged==d->cpus[id].ack);
 C(f->barrier==d->barrier&&f->completed==d->completed&&f->published_kernel_root==0x100000);
 C(f->raw_root_available==0&&f->raw_root==0&&f->normalized_root_available==0&&f->normalized_root==0);
 const Progress*p=uf_progress(id);
 C(f->wait_started==p->wait_started&&f->deadline==p->deadline&&f->acquired==p->acquired);
 if(stage==5){
  C(f->wait_started>0&&f->deadline>0&&f->deadline<=f->clock&&!f->acquired);
 }else if(stage==8){
  C(f->wait_started>0&&f->wait_started<f->acquired&&f->acquired<f->deadline&&f->acquired<f->clock);
 }else{
  C(!f->wait_started&&!f->deadline&&!f->acquired);
 }
 C(uf_bridge()->failed==1&&d->failed==1);
 empty_slots_except(id);
}
static void first_error_immutable(U id){
 Failure saved=*uf_failure(id);diagnostic_observe_enabled=0;cpu=id;
 C(dong_user_smp_return(id)==UINT64_MAX);
 C(!memcmp(&saved,uf_failure(id),sizeof saved));
}
int main(int argc,char**argv){
 C(argc==2&&uf_version()==2&&uf_size(0)==224&&uf_size(1)==48&&uf_size(2)==1536);
 C(!uf_failure(16)&&!uf_progress(16));
 if(!strcmp(argv[1],"no-active")){
  cpu=1;C(dong_user_smp_idle(1,257)==UINT64_MAX);empty_slots_except(UINT64_MAX);
 }else{
  setup();cpu=1;diagnostic_observe_enabled=1;
  if(!strcmp(argv[1],"timeout")){
   headers[1]->v[29]=8;d->lock=1;d->owner=0;
   C(dong_user_smp_idle(1,257)==UINT64_MAX);
   verify_failure(1,1,2,257,5,0x06090005,0);
   C(uf_failure(1)->wait_started<uf_failure(1)->deadline);
   C(diagnostic_observations==1&&d->lock==1&&d->owner==0&&d->sequence==0);
   for(U i=0;i<3;i++)C(!flushes[i]&&!d->cpus[i].requested&&!d->cpus[i].ack);
   first_error_immutable(1);
  }else if(!strcmp(argv[1],"expired-before-acquire")){
   U expected_deadline=clock_tick+8;
   headers[1]->v[29]=8;d->lock=1;d->owner=0;diagnostic_wait_jump=32;
   C(dong_user_smp_idle(1,257)==UINT64_MAX);
   verify_failure(1,1,2,257,5,0x06090005,0);
   C(uf_failure(1)->deadline==expected_deadline&&uf_failure(1)->wait_started>=expected_deadline);
   C(!diagnostic_wait_jump&&diagnostic_observations==1&&d->lock==1&&d->owner==0);
   for(U i=0;i<3;i++)C(!flushes[i]&&!d->cpus[i].requested&&!d->cpus[i].ack);
   first_error_immutable(1);
  }else if(!strcmp(argv[1],"hardware")){
   diagnostic_legacy=1;C(dong_user_smp_idle(1,257)==UINT64_MAX);
   verify_failure(1,1,2,257,4,0x06090003,0);C(diagnostic_observations==1&&!d->lock);
   first_error_immutable(1);
  }else if(!strcmp(argv[1],"checked-foreign")){
   C(dong_user_smp_idle(2,257)==UINT64_MAX);
   verify_failure(1,2,2,257,1,0x060b0011,0);
   C(!uf_progress(2)->stage&&diagnostic_observations==1);
   first_error_immutable(1);
  }else if(!strcmp(argv[1],"invalid-argument")){
   C(dong_user_smp_idle(16,257)==UINT64_MAX);
   verify_failure(1,16,2,257,1,0x060b0011,0);first_error_immutable(1);
  }else if(!strcmp(argv[1],"invalid-cpu")){
   cpu=16;C(dong_user_smp_idle(16,257)==UINT64_MAX);
   empty_slots_except(UINT64_MAX);C(!diagnostic_observations&&d->failed==1);
  }else if(!strcmp(argv[1],"pointer-guard")){
   d->cpus=(Cpu*)(uintptr_t)1;
   C(dong_user_smp_idle(2,257)==UINT64_MAX);
   const Failure*f=uf_failure(1);
   C(f->published==1&&f->cpu==1&&f->argument_cpu==2&&f->stage==1&&f->error_code==0x060b0011);
   C(!f->domain_available&&!f->domain&&!f->sequence&&!f->mode&&!f->published_kernel_root);
   C(!f->raw_root_available&&!f->raw_root&&!f->normalized_root_available&&!f->normalized_root);
   C(!f->wait_started&&!f->deadline&&!f->acquired);
   C(uf_bridge()->failed==1&&d->failed==1);empty_slots_except(1);first_error_immutable(1);
  }else if(!strcmp(argv[1],"commit")){
   C(dong_user_smp_return(1)==UINT64_MAX);
   verify_failure(1,1,3,0,15,0x06090002,0);first_error_immutable(1);
  }else if(!strcmp(argv[1],"acquired")){
   C(dong_user_smp_idle(1,257)==0);
   const Progress*p=uf_progress(1);
   C(p->entry==2&&p->vector==257&&p->stage==21);
   C(p->wait_started>0&&p->wait_started<p->acquired&&p->acquired<p->deadline);
   C(!d->failed&&!d->lock&&d->cpus[1].mode==1);
   empty_slots_except(UINT64_MAX);
   /* A new non-acquire entry clears the previous successful wait evidence. */
   C(dong_user_smp_return(1)==UINT64_MAX);
   verify_failure(1,1,3,0,15,0x06090002,0);first_error_immutable(1);
  }else if(!strcmp(argv[1],"capture-acquired")){
   cpu=0;C(!ue_lock(0));admit(0,2);C(!ue_unlock(0));start(1,0);
   C(event(1,0x73,256)==0&&!d->failed&&!d->lock&&d->cpus[1].mode==1);
   const Progress*p=uf_progress(1);
   C(p->entry==1&&p->vector==256&&p->stage==21);
   C(p->wait_started>0&&p->wait_started<p->acquired&&p->acquired<p->deadline);
   empty_slots_except(UINT64_MAX);
   C(dong_user_smp_return(1)==UINT64_MAX);
   verify_failure(1,1,3,0,15,0x06090002,0);first_error_immutable(1);
  }else{
   C(!strcmp(argv[1],"project")||!strcmp(argv[1],"nested-project"));cpu=0;diagnostic_project=0x050b4321;
   diagnostic_nested=!strcmp(argv[1],"nested-project");U expected_sequence=diagnostic_nested;
   C(dong_user_smp_idle(0,257)==UINT64_MAX);
   verify_failure(0,0,2,257,8,0x060b0011,diagnostic_project);
   C(d->lock==1&&d->owner==0&&!service_calls&&d->sequence==expected_sequence);
   first_error_immutable(0);
  }
 }
 C(checks<=UINT32_MAX);
 printf("USER_SMP_FAILURE_NATIVE_PASS synthetic_hardware=true actual_ap_cpl3_executed=false scenario=%s checks=%u\n",argv[1],(unsigned)checks);
 return 0;
}
