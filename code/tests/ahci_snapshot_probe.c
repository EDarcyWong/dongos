/* Real adapter with independent, non-atomic HBA publication steps. */
#define main ahci_legacy_main
#include "ahci_runtime_probe.c"
#undef main
enum {STEP_ORDERED=1,STEP_COPY_TFD,STEP_COPY_IS,STEP_NEVER_MARKER,
      STEP_EMPTY_FIS,STEP_ERROR_NO_MARKER,STEP_LATE_RFIS,STEP_CAPTURED_BUSY,STEP_STUCK_BUSY_EMPTY,
      STEP_CAPTURED_BUSY_VALID,STEP_STUCK_BUSY_VALID,STEP_DRQ_VALID,STEP_STUCK_DRQ_VALID,
      STEP_BUSY_DEVICE_ERR,STEP_BUSY_DEVICE_DF,STEP_BUSY_SERR};
static unsigned step_mode,step_issued,step_reads,step_acquires,step_changes;
static uint8_t step_fis[256];
static void publication(void){
 unsigned n=++step_reads;C(n<=12000);
 if(n==1){
  complete();memcpy(step_fis,dma+0x400,256);step_fis[0x42]=0x40;
  memset(dma+0x400,0,256);hba.p[2].ci=1;hba.p[2].tfd=0x80;
  hba.p[2].is=0;put(dma+4,0,4);dma[0x440]=0x34;
 }
 if(n==2){
  if(step_mode!=STEP_EMPTY_FIS&&step_mode!=STEP_LATE_RFIS&&step_mode!=STEP_CAPTURED_BUSY&&step_mode!=STEP_STUCK_BUSY_EMPTY)memcpy(dma+0x400,step_fis,256);
  else memset(dma+0x400,0,256);
 }
 if(n==3)hba.p[2].tfd=0x40;
 if(n==4){put(dma+4,512,4);hba.p[2].ci=0;if(step_mode==STEP_ERROR_NO_MARKER)hba.p[2].tfd=0x41;
  if(step_mode==STEP_CAPTURED_BUSY||step_mode==STEP_STUCK_BUSY_EMPTY){hba.p[2].is=1;hba.p[2].tfd=0xc0;}
  if(step_mode>=STEP_CAPTURED_BUSY_VALID){hba.p[2].is=1;hba.p[2].tfd=0xc0;}
  if(step_mode==STEP_DRQ_VALID||step_mode==STEP_STUCK_DRQ_VALID)hba.p[2].tfd=0x48;
  if(step_mode==STEP_BUSY_DEVICE_ERR)hba.p[2].tfd=0xc1;
  if(step_mode==STEP_BUSY_DEVICE_DF)hba.p[2].tfd=0xe0;
  if(step_mode==STEP_BUSY_SERR)hba.p[2].serr=1;
 }
 /* Preserve a whole legal software sampling window between ClearCI and
    SetIntr. The old adapter incorrectly poisons this CI0/IS0 observation. */
 if(n==6&&step_mode!=STEP_NEVER_MARKER&&step_mode!=STEP_ERROR_NO_MARKER&&step_mode!=STEP_STUCK_BUSY_EMPTY
    &&step_mode!=STEP_STUCK_BUSY_VALID&&step_mode!=STEP_STUCK_DRQ_VALID){
  if(step_mode==STEP_LATE_RFIS||step_mode==STEP_CAPTURED_BUSY){memcpy(dma+0x400,step_fis,256);hba.p[2].tfd=0x40;}
  if(step_mode==STEP_CAPTURED_BUSY_VALID||step_mode==STEP_DRQ_VALID)hba.p[2].tfd=0x40;
  hba.p[2].is=1;
 }
 /* The adapter's post-copy CI read is a deterministic interleaving point.
    Change status and RFIS together: the earlier copy must be discarded. */
 if(n==7&&step_mode==STEP_COPY_TFD){hba.p[2].tfd=0x50;dma[0x442]=0x50;step_changes++;}
 if(n==7&&step_mode==STEP_COPY_IS){hba.p[2].is=3;dma[0x44c]=0xa5;step_changes++;}
}
static ABI uint64_t phase_read(uint64_t context,uint64_t handle,uint64_t offset,uint64_t width,uint64_t*out){
 if(step_issued&&offset==0x238)publication();
 /* The independent phase machine, rather than complete-at-one-read, owns
    completion for this command. Keep the original MMIO validation intact. */
 uint64_t mode=hba.mode;hba.mode=HANG;
 uint64_t result=model_read(context,handle,offset,width,out);hba.mode=mode;return result;
}
static ABI uint64_t phase_write(uint64_t context,uint64_t handle,uint64_t offset,uint64_t width,uint64_t value){
 uint64_t result=model_write(context,handle,offset,width,value);
 if(offset==0x238){C(hba.issued_opcode==0x25);step_issued=1;hba.p[2].tfd=0x80;}
 return result;
}
static ABI uint64_t phase_fence(uint64_t context,uint64_t kind){if(kind==2)step_acquires++;return model_fence(context,kind);}
static const Ops phase_ops={phase_read,phase_write,phase_fence,model_acquire,model_release,model_enable,model_now};
static void phased(unsigned mode){
 GuardState g;C(init(&g,NORMAL)==0);State*s=&g.state;s->ops=&phase_ops;
 step_mode=mode;step_issued=step_reads=step_acquires=step_changes=0;
 uint64_t issued=commands,done=s->transfer.completed;uint8_t out[512];memset(out,0x8f,sizeof out);
 uint64_t lba=mode==STEP_CAPTURED_BUSY_VALID?0x7e4:23;
 if(mode==STEP_CAPTURED_BUSY_VALID)s->transfer.generation=0x78e;
 uint64_t result=ar_read(s,lba,1,out);
 C(commands==issued+1&&releases==0&&s->lease.token==0xabcdef&&s->info.held==1&&s->transfer.held==1);
 if(mode==STEP_NEVER_MARKER||mode==STEP_EMPTY_FIS||mode==STEP_ERROR_NO_MARKER||mode==STEP_STUCK_BUSY_EMPTY
    ||mode==STEP_STUCK_BUSY_VALID||mode==STEP_STUCK_DRQ_VALID||mode>=STEP_BUSY_DEVICE_ERR){
  uint64_t want=(mode==STEP_NEVER_MARKER||mode==STEP_STUCK_BUSY_EMPTY||mode==STEP_STUCK_BUSY_VALID||mode==STEP_STUCK_DRQ_VALID)?CORE_TIMEOUT:mode==STEP_EMPTY_FIS?CORE_BADCOMP:CORE_DEVICE;
  C(result==want&&s->transfer.completed==done&&s->info.faulted&&!s->info.ready&&s->transfer.faulted&&s->transfer.pending);
  for(unsigned i=0;i<sizeof out;i++)C(out[i]==0x8f);
  C(s->last_sample.ci==0&&s->last_sample.sact==0);
  if(mode==STEP_NEVER_MARKER){C(step_acquires==0&&s->last_sample.interrupts==0&&s->last_sample.prdbc==0);C(hba.time-s->transfer.start_ms>=5000);}
  if(mode==STEP_ERROR_NO_MARKER){C(step_acquires==0&&s->last_sample.tfd==0x41&&s->last_sample.interrupts==0);C(hba.time-s->transfer.start_ms<5000);}
  if(mode==STEP_STUCK_BUSY_EMPTY){C(step_acquires>0&&s->last_sample.interrupts==1&&s->last_sample.tfd==0xc0&&s->last_sample.prdbc==512);C(hba.time-s->transfer.start_ms>=5000);for(unsigned i=0;i<256;i++)C(!s->last_sample.fis[i]);}
  if(mode==STEP_STUCK_BUSY_VALID||mode==STEP_STUCK_DRQ_VALID){C(step_acquires>0&&s->last_sample.interrupts==1&&s->last_sample.prdbc==512);
   C(s->last_sample.tfd==(mode==STEP_STUCK_BUSY_VALID?0xc0:0x48)&&get(s->last_sample.fis+0x40,8)==0x404034);C(hba.time-s->transfer.start_ms>=5000);}
  if(mode>=STEP_BUSY_DEVICE_ERR){C(step_acquires==1&&hba.time-s->transfer.start_ms<5000&&get(s->last_sample.fis+0x40,8)==0x404034);}
  if(mode==STEP_EMPTY_FIS){C(step_acquires==1&&s->last_sample.interrupts==1&&s->last_sample.prdbc==512);for(unsigned i=0;i<256;i++)C(!s->last_sample.fis[i]);}
  State prior=*s;C(ar_read(s,23,1,out)==CLEANUP&&!memcmp(s,&prior,sizeof prior)&&commands==issued+1);
 }else{
  C(result==0&&s->transfer.completed==done+1&&!s->transfer.pending&&!s->info.faulted&&s->info.ready);
  C(!memcmp(out,cache+lba*512,512));exact_sample(s);
  C(step_acquires==((mode==STEP_COPY_TFD||mode==STEP_COPY_IS||mode==STEP_CAPTURED_BUSY||mode==STEP_CAPTURED_BUSY_VALID||mode==STEP_DRQ_VALID)?2u:1u));
  C(step_changes==((mode==STEP_COPY_TFD||mode==STEP_COPY_IS)?1u:0u));
  if(mode==STEP_CAPTURED_BUSY_VALID)C(s->last_sample.generation==0x78f&&get(s->last_sample.fis+0x40,8)==0x404034&&s->last_sample.tfd==0x40);
 }
 guards();printf("AHCI_PUBLICATION_CASE mode=%u rc=%" PRIx64 " ci_reads=%u acquires=%u changes=%u last_ci=%" PRIu64 " last_is=%" PRIu64 "\n",mode,result,step_reads,step_acquires,step_changes,s->last_sample.ci,s->last_sample.interrupts);
 step_issued=0;
}
int main(void){
 C(ahci_legacy_main()==0);
 for(unsigned mode=STEP_ORDERED;mode<=STEP_BUSY_SERR;mode++)phased(mode);
 printf("AHCI_SNAPSHOT_PHASE_PASS assertions=%" PRIu64 "; strict-core-unchanged ordered-publication resample-after-change missing-marker-timeout stable-empty-rejected no-extra-issue-or-free\n",assertions);return 0;
}
