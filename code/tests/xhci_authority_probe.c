#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#define ABI __attribute__((sysv_abi))
#else
#define ABI
#endif
typedef uint64_t U;
typedef struct{U owner,incarnation,binding_owner,binding_incarnation,binding_token,binding_role,lease_owner,lease_incarnation,lease_token,lease_exclusive,bar_exclusive,bar_uncached,lease_private_nx,attempted,physical_bits,bar_physical,bar_bytes,lease_physical,lease_bytes,pci_command,class_code,header_type,msi_disabled,msix_disabled,cap0,hcs1,hcs2,hcc1,dboff,rtsoff,pagesize;} Header;
typedef struct{U operational,runtime,doorbells,ports,interrupters,slots,extended_first,context_bytes;} Bounds;
typedef struct{U usbcmd,usbsts,dnctrl,dcbaap,crcr,config;} Registers;
typedef struct{U iman,imod,erstsz,erstba,erdp;} Interrupter;
typedef struct{U offset,header,name,range,slot,legacy_control;} Extension;
extern ABI U xa_shape(const Header*,Bounds*),xa_permit(const Header*,const Registers*,const Interrupter*,U,const Extension*,U,const unsigned char*,U,U*);
static U checks;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"xHCI authority check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static const U DENIED=0x08180001;
static Header h;static Registers r;static Interrupter interrupts[16];static Extension ext[3];static U dma[16384];
static void setup(void){h=(Header){13,7,13,7,91,4,13,7,44,1,1,1,1,0,40,0xf0000000,16384,0x20000000,131072,0x402,0x0c0330,0,1,1,0x01000040,(8u<<24)|(16u<<8)|64,15,0x80001,0x2000,0x1000,1};r=(Registers){0,1,0,h.lease_physical,h.lease_physical+4097,8};memset(interrupts,0,sizeof interrupts);interrupts[0]=(Interrupter){0,0,1,0,h.lease_physical+8192};ext[0]=(Extension){32,0x02000402,0x20425355,(4u<<8)|5,0,0};ext[1]=(Extension){48,0x03000002,0x20425355,(4u<<8)|1,0,0};memset(dma,0,sizeof dma);dma[8176/8]=h.lease_physical+4096;dma[8184/8]=(U)((6<<10)|2)<<32;dma[12288/8]=h.lease_physical+8192;dma[12296/8]=256;}
static U permit(U n,U en,U bytes,U*out){return xa_permit(&h,&r,interrupts,n,ext,en,(unsigned char*)dma,bytes,out);}
static void denied(void){U output=0xa55a;U result=permit(16,2,131072,&output);if(result!=DENIED){fprintf(stderr,"accepted invalid snapshot checks=%lu\n",(unsigned long)checks);for(unsigned i=0;i<31;i++)fprintf(stderr,"h%u=%lx ",i,(unsigned long)((U*)&h)[i]);for(unsigned i=0;i<6;i++)fprintf(stderr,"r%u=%lx ",i,(unsigned long)((U*)&r)[i]);}CK(result==DENIED&&output==0xa55a);}
static void normal(void){setup();U out=0;Bounds b;CK(xa_shape(&h,&b)==0&&b.operational==64&&b.runtime==4096&&b.doorbells==8192&&b.interrupters==16&&b.slots==8&&b.ports==8);CK(permit(16,2,131072,&out)==0&&out==0x406);r.usbsts=0x11;interrupts[0].iman=1;CK(permit(16,2,131072,&out)==0);setup();h.hcc1|=4;CK(xa_shape(&h,&b)==0&&b.context_bytes==64&&permit(16,2,131072,&out)==0);setup();h.physical_bits=32;h.hcc1&=~1u;CK(permit(16,2,131072,&out)==0);setup();h.hcs1=(h.hcs1&~255u)|4;r.config=4;CK(xa_shape(&h,&b)==0&&b.slots==4&&permit(16,2,131072,&out)==0);setup();h.hcc1=0x80001;ext[2]=ext[1];ext[1]=ext[0];ext[1].offset=40;ext[1].header=0x02000402;ext[2].offset=56;ext[0]=(Extension){32,0x01000201,0,0,0,0};CK(permit(16,3,131072,&out)==0);}
static void controls(void){const U fields[]={0,1,2,3,5,6,7,9,10,11,12,13,18,20,22,23};for(unsigned i=0;i<sizeof fields/sizeof fields[0];i++)for(unsigned bit=0;bit<64;bit++){setup();((U*)&h)[fields[i]]^=(U)1<<bit;denied();}for(unsigned i=0;i<6;i++)for(unsigned bit=0;bit<64;bit++){if(i==1&&bit==4)continue;setup();((U*)&r)[i]^=(U)1<<bit;denied();}for(unsigned index=0;index<16;index++)for(unsigned field=0;field<5;field++)for(unsigned bit=0;bit<64;bit++){if(index==0&&field==0&&bit==0)continue;setup();((U*)&interrupts[index])[field]^=(U)1<<bit;denied();}for(unsigned i=0;i<2048;i++){setup();dma[i]^=(U)1<<((i*13)&63);denied();}setup();h.binding_token=0;denied();setup();h.lease_token=0;denied();setup();h.lease_physical=UINT64_C(0x100000000);h.hcc1&=~1u;denied();setup();h.physical_bits=31;denied();setup();h.bar_bytes=8192;denied();setup();h.rtsoff=0x3c0;denied();setup();h.hcs2|=1u<<27;denied();setup();h.hcc1=0;denied();setup();h.hcc1=0x10001;denied();setup();h.cap0=0x00960040;denied();setup();ext[1].range=0x404;denied();setup();ext[0].header=1;denied();setup();ext[0].header=0x01010401;ext[0].name=ext[0].range=0;denied();setup();ext[1].slot=1;denied();setup();ext[1].range|=1u<<28;denied();setup();U out=0;CK(permit(15,2,131072,&out)==DENIED);CK(permit(16,1,131072,&out)==DENIED);CK(permit(16,2,131071,&out)==DENIED);Bounds b,before;memset(&b,0xa5,sizeof b);before=b;h.bar_bytes=8192;CK(xa_shape(&h,&b)==DENIED&&!memcmp(&b,&before,sizeof b));}
static void empty_protocols(void){
 /* Exact QEMU capability/extension words captured before the BME denial. */
 setup();h.hcs1=0x04001040;h.hcc1=0x00087001;
 ext[0]=(Extension){0x20,0x02000402,0x20425355,0x401,0,0};
 ext[1]=(Extension){0x30,0x03000002,0x20425355,1,0,0};
 U out=0;CK(permit(16,2,131072,&out)==0&&out==0x406);
 ext[1].range=5;CK(permit(16,2,131072,&out)==0);
 ext[1].range=0;denied();ext[1].range=6;denied();
 ext[1].range=0x105;denied();ext[1].range=0x101;denied();
 ext[1].range=1;ext[0].range=0x301;denied();
 ext[0].range=0x401;ext[1].name=0;denied();
 ext[1].name=0x20425355;ext[1].slot=1;denied();
 ext[1].slot=0;ext[1].range=0x10000001;denied();
 /* A 32-port controller admits the empty one-past-end sentinel only. */
 setup();h.hcs1=(h.hcs1&0x00ffffff)|(32u<<24);
 ext[0].range=0x2001;ext[1].range=33;
 CK(permit(16,2,131072,&out)==0);ext[1].range=34;denied();
}
int main(void){normal();empty_protocols();controls();printf("xHCI authority native checks passed %lu; poisoned_DMA_words=2048; interrupters=16; empty_protocol_boundaries=12\n",(unsigned long)checks);return 0;}
ABI void __dong_panic(void){fprintf(stderr,"unexpected xHCI authority Dong panic\n");exit(2);}
