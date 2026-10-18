#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t U;
typedef struct { U cap,ghc,implemented,selected,bar_bytes,lease_physical,lease_bytes,pci_command,version,cap2,bohc; } Header;
typedef struct { U cmd,ci,sact,interrupts,clb,fb,ssts,signature; } Port;
extern U __attribute__((sysv_abi)) authority_permit(const Header*,const Port*,U,U*);
__attribute__((sysv_abi,noreturn)) void __dong_panic(U reason,U line) {
    fprintf(stderr,"unexpected Dong panic reason=%llu line=%llu\n",(unsigned long long)reason,(unsigned long long)line);abort();
}
static Header h;
static Port ports[32];
static unsigned checks;
static void reset(void) {
    h=(Header){31,0x80000000,0xffffffff,0,0x1100,0x100000,131072,0x402,0x10301,1,2};
    memset(ports,0,sizeof ports);
    ports[0].clb=h.lease_physical;ports[0].fb=h.lease_physical+0x400;
    ports[0].ssts=0x103;ports[0].signature=0x101;
}
static void run(U n,int accepted) {
    Header before=h;Port saved[32];memcpy(saved,ports,sizeof ports);
    U output=UINT64_C(0x1122334455667788);
    U status=authority_permit(&h,ports,n,&output);checks++;
    if ((status==0)!=accepted || (accepted ? output!=0x406 : output!=UINT64_C(0x1122334455667788))
        || memcmp(&before,&h,sizeof h) || memcmp(saved,ports,sizeof ports)) {
        fprintf(stderr,"authority case %u status=%llx output=%llx expected=%d\n",checks,(unsigned long long)status,(unsigned long long)output,accepted);
        exit(1);
    }
}
int main(int argc,char **argv) {
    (void)argv;reset();
    if(argc>1) {
        ports[31].cmd=1;U out=0;
        if(authority_permit(&h,ports,32,&out)==0) {puts("UNSAFE_OTHER_PORT_ACCEPTED");return 99;}
        puts("UNSAFE_OTHER_PORT_REJECTED");return 0;
    }
    run(32,1);
    /* All implemented engines, including ports other than the selected disk,
       must be idle before the controller-wide bus-master bit can change. */
    const U active[]={1,16,0x4000,0x8000,0xc011};
    for(unsigned i=0;i<32;i++) for(unsigned j=0;j<5;j++) {reset();ports[i].cmd=active[j];run(32,0);}
    for(unsigned i=0;i<32;i++) for(unsigned j=0;j<3;j++) {
        reset();if(j==0)ports[i].ci=1;else if(j==1)ports[i].sact=1;else ports[i].interrupts=1;run(32,0);
    }
    for(unsigned selected=0;selected<32;selected++) {
        reset();memset(ports,0,sizeof ports);h.selected=selected;
        ports[selected]=(Port){0,0,0,0,h.lease_physical,h.lease_physical+0x400,0x103,0x101};run(32,1);
        ports[selected].clb+=4096;run(32,0);ports[selected].clb-=4096;
        ports[selected].fb+=4096;run(32,0);ports[selected].fb-=4096;
        ports[selected].cmd=0x1000000;run(32,0);ports[selected].cmd=0x20000;run(32,0);
        ports[selected].cmd=0;ports[selected].signature=0xeb140101;run(32,0);
        ports[selected].signature=0x101;ports[selected].ssts=0x603;run(32,0);
    }
    for(U n=1;n<=32;n++) {
        reset();h.cap=n-1;h.implemented=(UINT64_C(1)<<n)-1;h.bar_bytes=0x100+n*128;run(n,1);
        h.bar_bytes--;run(n,0);h.bar_bytes++;
        h.implemented|=UINT64_C(1)<<n;run(n,0);
        reset();h.cap=n-1;h.implemented=1;run(n-1,0);run(n+1,0);
    }
    const U bad_pa[]={0,1,0xfffff000,UINT64_C(0x100000000),UINT64_MAX};
    for(unsigned i=0;i<sizeof bad_pa/sizeof bad_pa[0];i++) {reset();h.lease_physical=bad_pa[i];run(32,0);}
    for(U command=0;command<=65535;command++) {
        reset();h.pci_command=command;
        /* Grant deliberately clears IO decode and BME. Other PCI command
           bits are retained; the result adds memory/BME/INTx-disable only. */
        int valid=(command&7)==2;
        U out=0,rc=authority_permit(&h,ports,32,&out);checks++;
        if((rc==0)!=valid || (valid && out!=((command|0x406)&~UINT64_C(1))))return 2;
    }
    const U bad_ghc[]={0,1,2,0x80000001,0x80000002,UINT64_C(0x180000000)};
    for(unsigned i=0;i<sizeof bad_ghc/sizeof bad_ghc[0];i++){reset();h.ghc=bad_ghc[i];run(32,0);}
    for(U bohc=0;bohc<32;bohc++){reset();h.bohc=bohc;run(32,(bohc&0x13)==2);}
    reset();h.cap2=0;h.bohc=0;run(32,1);
    reset();h.version=0x10000;h.cap2=0;h.bohc=0;run(32,1);
    reset();h.lease_bytes=69632;run(32,0);
    reset();h.lease_physical=0xfffe0000;ports[0].clb=h.lease_physical;ports[0].fb=h.lease_physical+0x400;run(32,1);
    h.lease_physical+=4096;ports[0].clb=h.lease_physical;ports[0].fb=h.lease_physical+0x400;run(32,0);
    reset();h.implemented=UINT64_C(1)<<31;h.selected=31;
    memset(ports,0xff,sizeof ports);
    ports[31]=(Port){0,0,0,0,h.lease_physical,h.lease_physical+0x400,0x103,0x101};run(32,1);
    ports[31].clb|=UINT64_C(1)<<32;run(32,0);ports[31].clb=h.lease_physical;
    ports[31].fb|=UINT64_C(1)<<32;run(32,0);
    reset();h.cap=UINT64_C(0x10000001f);run(32,0);
    reset();h.selected=32;run(32,0);
    reset();h.implemented=0;run(32,0);
    U out=23;
    if(authority_permit(NULL,ports,32,&out)==0 || authority_permit(&h,NULL,32,&out)==0 || out!=23)return 3;
    printf("AHCI authority checks=%u all-ports/lease/BIOS-owner/PCI-readback verified\n",checks);
    return 0;
}
