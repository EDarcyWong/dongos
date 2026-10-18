#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"SMP_MODEL_ASSERT %d: %s\n",__LINE__,#x);return 1;}}while(0)
#define P(n) (UINT64_C(0x06010000)+(n))
#define T(n) (UINT64_C(0x06030000)+(n))
typedef struct {uint64_t v[32];} Context;
typedef struct {uint64_t count,bsp,lapic,cpus[16][4];} Topology;
typedef struct {uint64_t scalar[28],gas[15],cpus[16][4],io[8][3],iso[16][4],nmi[16][5],mcfg[8][4];} Inventory;
typedef ABI uint64_t (*Send)(uint64_t,uint64_t,uint64_t);
typedef ABI uint64_t (*Clock)(uint64_t);
typedef ABI void (*Pause)(uint64_t);
typedef ABI uint64_t (*Delay)(uint64_t,uint64_t);
typedef struct {uint64_t context;Send send;Delay delay;} StartupOps;
typedef struct {uint64_t sequence,virtual,scope,ack,expected,observed,fault,reserved;} Mailbox;
typedef struct {uint64_t context;Send send;Clock clock;Pause pause;uint64_t timeout;} Ops;
typedef struct {uint64_t ready,pending;Context *cpus;size_t count;Mailbox *boxes;const Ops *ops;
 uint64_t epoch,broadcasts,sent,acknowledgements,invalidations,full,probes,failures;} Domain;
extern ABI void sp_sizes(uint64_t *);
extern ABI uint64_t sp_topology(const Inventory*,uint64_t,Topology*),sp_prepare(const Context*,Context*);
extern ABI uint64_t sp_transition(Context*,uint64_t,uint64_t),sp_startup(const StartupOps*,uint64_t,uint64_t);
extern ABI uint64_t sp_tlb_init(Domain*,Context*,size_t,Mailbox*,const Ops*),sp_broadcast(Domain*,uint64_t,uint64_t,uint64_t);
extern ABI uint64_t smp_prepare_trampoline(void*,uint64_t,uint64_t,uint64_t),smp_send_ipi(void*,uint64_t,uint64_t,uint64_t);
extern char smp_trampoline_start[],smp_trampoline_end[],smp_trampoline_cr3[],smp_trampoline_context[],smp_trampoline_pm_pointer[],smp_trampoline_lm_pointer[],smp_trampoline_gdtr[];
extern char smp_trampoline_pm[],smp_trampoline_long[],smp_ap_entry[];
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected DG panic %llu\n",(unsigned long long)code);exit(99);}
ABI void kernel_exception_panic(void *frame){(void)frame;abort();}
static unsigned checks;
static Context valid_context(void){
 Context c={{0}};uint64_t h=UINT64_C(0xffffd40000000000);
 c.v[0]=h;c.v[1]=1;c.v[2]=1;c.v[4]=1;c.v[5]=0x400000;c.v[6]=0x80010033;c.v[7]=0x340e68;c.v[8]=0xd00;
 c.v[9]=UINT64_C(0x0007040600070406);c.v[10]=3;
 c.v[11]=h+0x11000;c.v[12]=h+0x15000;c.v[13]=h+0x50000;c.v[14]=h+0x50040;c.v[15]=h+0x51000;
 c.v[16]=h+0x21000;c.v[17]=h+0x25000;c.v[18]=h+0x31000;c.v[19]=h+0x35000;
 c.v[20]=h+0x41000;c.v[21]=h+0x45000;c.v[22]=0xfee00000;c.v[23]=UINT64_C(0xffffc00000000000);c.v[24]=UINT64_C(0xffffffff80010000);return c;
}
static int policies(void){
 uint64_t sizes[4];sp_sizes(sizes);CHECK(sizes[0]==256&&sizes[1]==536&&sizes[2]==64&&sizes[3]==112&&sizeof(Inventory)==2456);
 Inventory inv={0};inv.scalar[8]=0xfee00000;inv.scalar[10]=4;
 for(unsigned i=0;i<4;i++){inv.cpus[i][1]=10+i;inv.cpus[i][2]=i;inv.cpus[i][3]=1;}
 Topology out,before;memset(&out,0xa7,sizeof out);CHECK(sp_topology(&inv,2,&out)==0&&out.count==4&&out.cpus[0][1]==2);
 const unsigned bads[]={0,17};for(unsigned i=0;i<2;i++){Inventory bad=inv;bad.scalar[10]=bads[i];before=out;CHECK(sp_topology(&bad,0,&out)==P(2)&&!memcmp(&before,&out,sizeof out));}
 Inventory bad=inv;bad.cpus[1][2]=0;before=out;CHECK(sp_topology(&bad,0,&out)==P(2)&&!memcmp(&before,&out,sizeof out));
 bad=inv;bad.cpus[1][1]=10;CHECK(sp_topology(&bad,0,&out)==P(2));bad=inv;bad.cpus[3][2]=256;CHECK(sp_topology(&bad,0,&out)==P(3));
 bad=inv;bad.cpus[1][3]=0;CHECK(sp_topology(&bad,0,&out)==0&&out.count==3);CHECK(sp_topology(&bad,1,&out)==P(2));
 Context c=valid_context(),prepared;memset(&prepared,0x5a,sizeof prepared);CHECK(sp_prepare(&c,&prepared)==0&&prepared.v[3]==2);
 for(unsigned field=0;field<32;field++){
  Context broken=c,old=prepared;broken.v[field]=(field==4||field==24)?0:UINT64_MAX;
  CHECK(sp_prepare(&broken,&prepared)==P(1)&&!memcmp(&old,&prepared,sizeof old));
 }
 Context reserved=c,unchanged=prepared;reserved.v[6]|=UINT64_C(1)<<40;
 CHECK(sp_prepare(&reserved,&prepared)==P(1)&&!memcmp(&unchanged,&prepared,sizeof unchanged));
 reserved=c;reserved.v[9]=(reserved.v[9]&~(UINT64_C(255)<<32))|(UINT64_C(2)<<32);
 CHECK(sp_prepare(&reserved,&prepared)==P(1)&&!memcmp(&unchanged,&prepared,sizeof unchanged));
 CHECK(sp_prepare(&c,&prepared)==0&&sp_transition(&prepared,0,1)==0&&prepared.v[3]==3);
 Context old=prepared;CHECK(sp_transition(&prepared,1,2)==P(4)&&!memcmp(&old,&prepared,sizeof old));
 CHECK(sp_transition(&prepared,1,1)==0&&prepared.v[3]==4&&prepared.v[25]==1);
 CHECK(sp_transition(&prepared,2,1)==0&&sp_transition(&prepared,3,1)==0&&prepared.v[27]==1);
 old=prepared;CHECK(sp_transition(&prepared,2,1)==P(4)&&!memcmp(&old,&prepared,sizeof old));
 CHECK(sp_transition(&prepared,4,1)==0&&prepared.v[3]==5&&sp_transition(&prepared,5,1)==0&&prepared.v[3]==6);
 CHECK(sp_prepare(&c,&prepared)==0&&sp_transition(&prepared,0,1)==0&&sp_transition(&prepared,6,0)==0&&prepared.v[3]==8);
 return 0;
}
static uint64_t startup_trace[16];static unsigned trace_count;static unsigned fail_call;
static ABI uint64_t startup_send(uint64_t ctx,uint64_t apic,uint64_t command){(void)ctx;if(apic!=3)return 1;startup_trace[trace_count++]=command;return trace_count==fail_call;}
static ABI uint64_t startup_delay(uint64_t ctx,uint64_t us){(void)ctx;startup_trace[trace_count++]=UINT64_C(0x10000000)|us;return trace_count==fail_call;}
static int startup_policy(void){
 StartupOps ops={0,startup_send,startup_delay};CHECK(sp_startup(&ops,3,0x8000)==0&&trace_count==7);
 const uint64_t expected[]={0xc500,0x10002710,0x8500,0x608,0x100000c8,0x608,0x100000c8};CHECK(!memcmp(startup_trace,expected,sizeof expected));
 for(unsigned i=1;i<=7;i++){trace_count=0;fail_call=i;CHECK(sp_startup(&ops,3,0x8000)==P(i==2||i==5||i==7?6:5)&&trace_count==i);}
 trace_count=0;fail_call=0;CHECK(sp_startup(&ops,3,0)==P(1)&&trace_count==0);return 0;
}
static Mailbox boxes[4];static uint64_t now;static unsigned mode,send_count;static unsigned pause_count;
static ABI uint64_t send_tlb(uint64_t context,uint64_t apic,uint64_t vector){
 (void)context;send_count++;if(apic==0||apic>=4||vector!=0xf2)return 1;
 if(mode==1&&apic==2)return 1;
 if(mode!=2){boxes[apic].ack=boxes[apic].sequence;if(boxes[apic].scope==2)boxes[apic].observed=boxes[apic].expected+(mode==3?1:0);}
 return 0;
}
static ABI uint64_t clock_tlb(uint64_t ctx){(void)ctx;return now++;}
static ABI void pause_tlb(uint64_t ctx){(void)ctx;pause_count++;}
static int tlb_policy(void){
 Context cpus[4];for(unsigned i=0;i<4;i++){cpus[i]=valid_context();cpus[i].v[1]=i;cpus[i].v[2]=i;cpus[i].v[3]=4;cpus[i].v[25]=1;}
 Ops ops={0,send_tlb,clock_tlb,pause_tlb,10};Domain d={0};CHECK(sp_tlb_init(&d,cpus,4,boxes,&ops)==0&&d.ready==1);
 CHECK(sp_broadcast(&d,0xffffc80000000000ULL,0,0)==0&&d.sent==3&&d.acknowledgements==3&&d.invalidations==1&&!d.pending);
 CHECK(sp_broadcast(&d,0,1,0)==0&&d.full==1);
 CHECK(sp_broadcast(&d,0xffffc80000000000ULL,2,0x1234)==0&&d.probes==1&&boxes[3].observed==0x1234);
 Domain previous=d;CHECK(sp_broadcast(&d,0x800000000000ULL,0,0)==T(1)&&!memcmp(&previous,&d,sizeof d));
 boxes[1].sequence++;previous=d;CHECK(sp_broadcast(&d,0,1,0)==T(2)&&!memcmp(&previous,&d,sizeof d));boxes[1].sequence--;
 for(unsigned broken=1;broken<=3;broken++){
  memset(&d,0,sizeof d);mode=broken;now=0;send_count=pause_count=0;CHECK(sp_tlb_init(&d,cpus,4,boxes,&ops)==0);
  uint64_t expected=broken==1?T(3):broken==2?T(4):T(6);
  CHECK(sp_broadcast(&d,0xffffc80000000000ULL,2,17)==expected&&d.pending==1&&d.failures==1&&d.broadcasts==0);
  CHECK(sp_broadcast(&d,0,1,0)==T(2));
  if(broken==2)CHECK(pause_count>0);
 }
 mode=0;return 0;
}
static uint8_t destination[4128];static uint8_t before[4128];static uint32_t lapic[1024] __attribute__((aligned(4096)));
static int assembly_contract(void){
 memset(destination,0xa7,sizeof destination);uint8_t *page=destination+16;
 CHECK(smp_trampoline_end-smp_trampoline_start==4096);
 CHECK(smp_prepare_trampoline(page,0x8000,0x400000,0xffffd40000000000ULL)==0);
 for(unsigned i=0;i<16;i++)CHECK(destination[i]==0xa7&&destination[4112+i]==0xa7);
 uint32_t cr3,pm,lm,gdt;uint64_t ctx;
 memcpy(&cr3,page+(smp_trampoline_cr3-smp_trampoline_start),4);memcpy(&ctx,page+(smp_trampoline_context-smp_trampoline_start),8);
 memcpy(&pm,page+(smp_trampoline_pm_pointer-smp_trampoline_start),4);memcpy(&lm,page+(smp_trampoline_lm_pointer-smp_trampoline_start),4);
 memcpy(&gdt,page+(smp_trampoline_gdtr-smp_trampoline_start)+2,4);
 CHECK(cr3==0x400000&&ctx==0xffffd40000000000ULL&&pm==0x8000+smp_trampoline_pm-smp_trampoline_start&&lm==0x8000+smp_trampoline_long-smp_trampoline_start&&gdt>=0x8000&&gdt<0x9000);
 const uint64_t lows[]={0,4095,0x8001,0xa0000};
 for(unsigned i=0;i<4;i++){memcpy(before,destination,sizeof before);CHECK(smp_prepare_trampoline(page,lows[i],0x400000,ctx)==0x06020001&&!memcmp(before,destination,sizeof before));}
 memset(lapic,0,sizeof lapic);CHECK(smp_send_ipi(lapic,3,0xf2,100)==0&&lapic[0x310/4]==3u<<24&&lapic[0x300/4]==0xf2);
 lapic[0x300/4]=1u<<12;uint32_t saved[1024];memcpy(saved,lapic,sizeof saved);CHECK(smp_send_ipi(lapic,3,0xf1,2)==0x06020004&&!memcmp(saved,lapic,sizeof saved));
 CHECK(smp_send_ipi(lapic,256,0xf1,2)==0x06020001);return 0;
}
int main(void){if(policies()||startup_policy()||tlb_policy()||assembly_contract())return 1;printf("SMP independent policy/real trampoline/ICR/TLB failure retention checks=%u\n",checks);return 0;}
