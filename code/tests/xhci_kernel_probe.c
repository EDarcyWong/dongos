#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#define ABI __attribute__((sysv_abi))
#else
#define ABI
#endif
typedef uint64_t U;
typedef struct {U version,token,next,kind,ecam,segment,bus,device,function,vendor,id,class_code,header,flags,generation,reserved;} Device;
typedef struct {U version,device,role,configuration,generation,irqmask,flags,reserved;} Binding;
typedef struct {U physical,bytes,handle;} Bar;
typedef struct {U token,physical,pointer,length;} Lease;
typedef struct {U generation,kind,object,rights,live;} Handle;
typedef struct {U ready,used;Handle entries[32];} Handles;
typedef struct {U physical,virtual,writable;} Frame;
extern ABI void xk_native_start(void);
extern ABI U xk_host_init(void),xk_enum(U,Device*),xk_bind(U,U,Binding*),xk_attach(U,U,U),xk_grant(U,Handles*,U),xk_dma(U,U,U),xk_bars(U),xk_lease(U),xk_mapped(U,U),xk_enable(U,U,U),xk_quarantine(U),xk_revoke_owner(U),xk_revoke(U,U);
static U checks;
#define CK(x) do{++checks;if(!(x)){fprintf(stderr,"xHCI kernel check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static const U ECAM=0xe0000000,XHCI=0xe0018000,OWNER=0x10000000e,INCARNATION=1;
static const U DENIED=0x050a0002,HOST_DENIED=0x05120002,REMOVED=0x05120008;
static uint32_t pci[3][64],mmio[4096];static U bars[3]={0xf1000000,0xf2000000,0xf3000000};
static unsigned char dma[131072],table[8192],snapshot_storage[43*4096+4095];static Frame frames[32];
static U table_allocations,snapshot_allocations;
typedef struct {U physical,virtual,pages;} ResourceBlock;
static U mapped[16],allocations[16],bme_writes,alias_calls,mmio_reads,range_calls,quarantine_writes;
static int probes[3],partial_grant,readback_failure,readback_pending,bad_alias;
static Device catalog[4];static Binding binding[4];static Handles handles[16];
static unsigned device_at(U p){CK(p>=ECAM&&p<ECAM+0x100000);return (unsigned)((p-ECAM)>>15);}
ABI U native_read(U p,uint32_t*out){unsigned n=device_at(p);CK(!(p&3)&&out);unsigned r=(unsigned)((p&4095)/4);CK(r<64);if(n<1||n>3){*out=0xffffffff;return 0;}n--;if(r==4&&probes[n]){*out=n==2?0xffffc000:0xfffff000;return 0;}if(r>=5&&r<=9&&pci[n][r]==0xffffffff){*out=0;return 0;}*out=pci[n][r];if(n==2&&r==1&&readback_pending){*out&=~4U;readback_pending=0;}return 0;}
ABI U native_write(U p,uint32_t value){unsigned n=device_at(p);CK(n>=1&&n<=3&&!(p&3));unsigned r=(unsigned)((p&4095)/4);CK(r>=4&&r<=9);n--;pci[n][r]=value;if(r==4)probes[n]=value==0xffffffff;return 0;}
ABI U native_command(U p,uint16_t value){unsigned n=device_at(p);CK(n>=1&&n<=3&&!(p&4095));n--;pci[n][1]=(pci[n][1]&0xffff0000)|value;if(n==2){if(value&4){bme_writes++;if(readback_failure)readback_pending=1;}else if(value&0x400)quarantine_writes++;}return 0;}
ABI U native_write16(U p,uint16_t value){unsigned n=device_at(p);CK(n>=1&&n<=3&&!(p&1));n--;unsigned r=(unsigned)((p&4095)/4),shift=(unsigned)((p&2)*8);CK(r<64);pci[n][r]=(pci[n][r]&~(0xffffU<<shift))|((uint32_t)value<<shift);return 0;}
ABI U native_range(U physical,U bytes,U ecam){range_calls++;CK(!ecam&&physical&&bytes&&!(physical&4095)&&!(bytes&4095));for(unsigned n=0;n<3;n++){U length=n==2?16384:4096;if(physical>=bars[n]&&physical-bars[n]<=length&&bytes<=length-(physical-bars[n]))return 0;}return 1;}
ABI U native_mmio(U p,uint32_t*out){CK(out&&p>=bars[2]&&p-bars[2]<16384&&!(p&3));mmio_reads++;*out=mmio[(p-bars[2])/4];return 0;}
ABI U native_map(U id,U virtual,U physical,U bytes){CK(id==2||id==4||id==13);CK(virtual==0x60000000&&physical==bars[id==2?0:id==4?1:2]&&bytes==(id==13?16384:4096));mapped[id]++;return id==13&&partial_grant;}
ABI U native_alloc(U id,U virtual,U requested,U*out){CK(out&&virtual==0x68000000&&(id==2||id==4||id==13));CK(requested==(id==13?32:id==2?17:4));CK(!allocations[id]);allocations[id]++;*out=id==13?0x20000000:id==2?0x21000000:0x22000000;return 0;}
ABI U native_alias(U id,U virtual,U*out){CK(id==13&&virtual>=0x68000000&&virtual<0x68020000&&!(virtual&4095)&&out);alias_calls++;*out=(U)(uintptr_t)(dma+virtual-0x68000000);if(bad_alias&&virtual==0x6801f000)*out+=8;return 0;}
ABI U native_copy(U id,U virtual,unsigned char*out,U bytes){CK(id==13&&virtual==0x68000000&&out&&bytes==sizeof dma);memcpy(out,dma,sizeof dma);return 0;}
ABI const Frame* native_frames(void){return frames;}
ABI U native_arena(void){return ((U)(uintptr_t)snapshot_storage+4095)&~(U)4095;}
ABI U native_resources(U pages,U alignment,ResourceBlock*out){
 CK(out&&alignment==1);
 if(pages==2){CK(!table_allocations&&!snapshot_allocations);table_allocations++;out->physical=0x2fffe000;out->virtual=(U)(uintptr_t)table;}
 else{CK(pages==43&&table_allocations==1&&!snapshot_allocations);snapshot_allocations++;out->physical=0x30000000;out->virtual=native_arena();
  CK(!(out->virtual&4095)&&out->virtual>=(U)(uintptr_t)snapshot_storage&&out->virtual+43*4096<=(U)(uintptr_t)snapshot_storage+sizeof snapshot_storage);
  CK(out->virtual+43*4096<=(U)(uintptr_t)dma||out->virtual>=(U)(uintptr_t)dma+sizeof dma);
  for(U i=0;i<43*4096;i++)CK(!((unsigned char*)(uintptr_t)out->virtual)[i]);
 }
 out->pages=pages;return 0;
}
ABI void __dong_panic(void){fprintf(stderr,"unexpected Dong panic\n");exit(2);}
static Bar* bar(U id){return (Bar*)(uintptr_t)xk_bars(id);}
static Lease* lease(U id){return (Lease*)(uintptr_t)xk_lease(id);}
static void qword(U offset,U value){CK(!(offset&7)&&offset+8<=sizeof dma);memcpy(dma+offset,&value,8);}
static void registers(void){memset(mmio,0,sizeof mmio);mmio[0]=0x01000020;mmio[1]=(4U<<24)|(16<<8)|8;mmio[4]=(0x400U<<16)|1;mmio[5]=0x3000;mmio[6]=0x2000;mmio[(0x20+4)/4]=0x11;mmio[(0x20+8)/4]=1;mmio[(0x20+0x18)/4]=0x20001001;mmio[(0x20+0x30)/4]=0x20000000;mmio[(0x20+0x38)/4]=8;mmio[(0x2000+0x20+8)/4]=1;mmio[(0x2000+0x20+24)/4]=0x20002000;mmio[0x1000/4]=0x02000402;mmio[0x1004/4]=0x20425355;mmio[0x1008/4]=0x0201;mmio[0x1010/4]=0x03000002;mmio[0x1014/4]=0x20425355;mmio[0x1018/4]=0x0203;qword(8176,0x20001000);qword(8184,(U)((6<<10)|2)<<32);qword(12288,0x20002000);qword(12296,256);}
static void setup(int attach){for(unsigned n=0;n<3;n++){pci[n][0]=n==0?0x10421af4:n==1?0x10521af4:0x000d1b36;pci[n][1]=6;pci[n][2]=n==2?0x0c033000:0;pci[n][4]=(uint32_t)bars[n];}for(unsigned n=0;n<16;n++){handles[n].ready=1;for(unsigned h=0;h<32;h++)handles[n].entries[h].generation=1;}for(unsigned n=0;n<32;n++){frames[n].physical=0x20000000+n*4096;frames[n].virtual=(U)(uintptr_t)(dma+n*4096);frames[n].writable=1;}xk_native_start();CK(xk_host_init()==0);for(U n=0;n<4;n++){CK(xk_enum(n,&catalog[n])==0&&catalog[n].version==1&&catalog[n].token==257+n);}Device end;CK(xk_enum(4,&end)==0&&end.kind==0);CK(xk_bind(catalog[0].token,1,&binding[0])==0);CK(xk_bind(catalog[1].token,2,&binding[1])==0);CK(xk_bind(catalog[2].token,4,&binding[3])==0&&binding[3].configuration==13);if(attach)CK(xk_attach(13,OWNER,INCARNATION)==0);registers();}
static void grant(void){CK(xk_grant(13,&handles[13],XHCI)==0);CK(pci[2][4]==bars[2]&&(pci[2][1]&0x407)==0x402&&mapped[13]==1);CK(bar(13)[0].physical==bars[2]&&bar(13)[0].bytes==16384&&bar(13)[0].handle);for(unsigned i=1;i<6;i++)CK(!bar(13)[i].physical&&!bar(13)[i].bytes&&!bar(13)[i].handle);CK(xk_mapped(13,100)==0x60000000&&xk_mapped(13,101)==DENIED);CK(xk_dma(13,131072,4096)==0&&allocations[13]==1);CK(lease(13)->token==3&&lease(13)->physical==0x20000000&&lease(13)->pointer==0x68000000&&lease(13)->length==131072);CK(xk_dma(13,131072,4096)==DENIED);}
int main(int argc,char**argv){CK(argc==2);const char*s=argv[1];int before=!strcmp(s,"removed-before-attach")||!strcmp(s,"wrong-slot");setup(!before);
 if(!strcmp(s,"removed-before-attach")){pci[2][0]^=1U<<16;CK(xk_attach(13,OWNER,INCARNATION)==REMOVED);CK(!mapped[13]&&!bme_writes);}
 else if(!strcmp(s,"wrong-slot")){CK(xk_attach(2,OWNER,INCARNATION)==HOST_DENIED);CK(xk_attach(13,OWNER,INCARNATION)==0);CK(xk_attach(13,OWNER,INCARNATION)==HOST_DENIED);}
 else if(!strcmp(s,"partial-grant")){partial_grant=1;CK(xk_grant(13,&handles[13],XHCI)!=0);CK(xk_grant(13,&handles[13],XHCI)==DENIED);CK(xk_quarantine(13)==0&&(pci[2][1]&0x404)==0x400);CK(xk_dma(13,131072,4096)==DENIED&&!allocations[13]);}
 else if(!strcmp(s,"bar-overlap")){CK(xk_grant(2,&handles[2],catalog[0].ecam)==0);Bar saved=bar(2)[0];pci[2][4]=(uint32_t)bars[0];bars[2]=bars[0];CK(xk_grant(13,&handles[13],XHCI)==DENIED);CK(!memcmp(&saved,bar(2),sizeof saved)&&!mapped[13]&&!bme_writes);}
 else {if(!strcmp(s,"msi")){pci[2][1]|=0x100000;pci[2][0x34/4]=0x50;pci[2][0x50/4]=0x00016005;pci[2][0x60/4]=0x80000011;}
  Bar old_bars[12];Lease old_leases[2];U old_commands[2]={0};
  if(!strcmp(s,"legacy-isolation")){CK(xk_grant(2,&handles[2],catalog[0].ecam)==0);CK(xk_grant(4,&handles[4],catalog[1].ecam)==0);CK(xk_dma(2,69632,4096)==0&&xk_dma(4,16384,4096)==0);memcpy(old_bars,bar(2),6*sizeof(Bar));memcpy(old_bars+6,bar(4),6*sizeof(Bar));old_leases[0]=*lease(2);old_leases[1]=*lease(4);old_commands[0]=pci[0][1];old_commands[1]=pci[1][1];}
  grant();CK(xk_enable(2,OWNER,INCARNATION)==DENIED&&!bme_writes);
  if(!strcmp(s,"removed-identity")){pci[2][0]^=1U<<16;CK(xk_enable(13,OWNER,INCARNATION)==DENIED&&!bme_writes);}
  else if(!strcmp(s,"owner")){CK(xk_enable(13,OWNER+1,INCARNATION)==DENIED&&!bme_writes);CK(xk_enable(13,OWNER,INCARNATION+1)==DENIED&&!bme_writes);CK(xk_enable(13,OWNER,INCARNATION)==0&&bme_writes==1);}
  else if(!strcmp(s,"late-interrupter")){mmio[(0x2000+0x20+15*32)/4]=2;CK(xk_enable(13,OWNER,INCARNATION)!=0&&!bme_writes);}
  else if(!strcmp(s,"quarantine")){Lease saved=*lease(13);CK(xk_quarantine(13)==0);CK(xk_enable(13,OWNER,INCARNATION)==DENIED&&!bme_writes);CK(xk_mapped(13,100)==DENIED&&!memcmp(&saved,lease(13),sizeof saved));}
  else if(!strcmp(s,"readback")){readback_failure=1;CK(xk_enable(13,OWNER,INCARNATION)!=0&&bme_writes==1);CK((pci[2][1]&0x404)==0x400&&xk_enable(13,OWNER,INCARNATION)==DENIED&&allocations[13]==1);}
  else if(!strcmp(s,"dma-page")){bad_alias=1;CK(xk_enable(13,OWNER,INCARNATION)!=0&&!bme_writes&&alias_calls==32);}
  else if(!strcmp(s,"old-erstba")){mmio[(0x2000+0x20+16)/4]=0x20003000;CK(xk_enable(13,OWNER,INCARNATION)!=0&&!bme_writes);}
  else if(!strcmp(s,"cap-boundary")){mmio[6]=0x3fe0;CK(xk_enable(13,OWNER,INCARNATION)!=0&&!bme_writes&&mmio_reads==7);}
  else if(!strcmp(s,"extension-boundary")){mmio[4]=(0xfffU<<16)|1;mmio[0x3ffc/4]=2;CK(xk_enable(13,OWNER,INCARNATION)!=0&&!bme_writes);}
  else {CK(xk_enable(13,OWNER,INCARNATION)==0&&bme_writes==1&&alias_calls==32&&mmio_reads>=8+16*7);CK((pci[2][1]&0x407)==0x406);CK(xk_enable(13,OWNER,INCARNATION)==DENIED&&bme_writes==1);Lease saved=*lease(13);Bar savedbar=bar(13)[0];CK(xk_revoke_owner(OWNER)==0);CK((pci[2][1]&0x404)==0x400);CK(!memcmp(&saved,lease(13),sizeof saved)&&!memcmp(&savedbar,bar(13),sizeof savedbar)&&xk_mapped(13,100)==DENIED);CK(xk_enable(13,OWNER,INCARNATION)==DENIED&&xk_attach(13,OWNER,INCARNATION+1)==HOST_DENIED);CK(xk_grant(13,&handles[13],XHCI)==DENIED&&xk_dma(13,131072,4096)==DENIED);if(!strcmp(s,"msi")){CK(!(pci[2][0x50/4]&(1U<<16))&&!(pci[2][0x60/4]&(1U<<31))&&(pci[2][0x60/4]&(1U<<30)));}if(!strcmp(s,"legacy-isolation")){CK(!memcmp(old_bars,bar(2),6*sizeof(Bar))&&!memcmp(old_bars+6,bar(4),6*sizeof(Bar)));CK(!memcmp(old_leases,lease(2),sizeof(Lease))&&!memcmp(old_leases+1,lease(4),sizeof(Lease)));CK(pci[0][1]==old_commands[0]&&pci[1][1]==old_commands[1]);}}
 }
 printf("xHCI kernel native checks passed %lu; scenario=%s; mmio_reads=%lu; dma_allocations=%lu; bme_writes=%lu\n",(unsigned long)checks,s,(unsigned long)mmio_reads,(unsigned long)allocations[13],(unsigned long)bme_writes);return 0;
}
