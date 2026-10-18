#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif
typedef uint64_t U;
typedef struct {
    U cap,version,physical_bits,bar_bytes,lease_physical,lease_bytes,pci_command,cc;
    U csts,intms,aqa,asq,acq,msi_disabled,msix_disabled,lease_exclusive;
} Header;
typedef struct { U before[4];Header header;U after[4]; } GuardedHeader;
typedef struct { U before[4],value,after[4]; } GuardedOutput;
extern U __attribute__((sysv_abi)) nvme_authority_permit(const Header*,U*);
__attribute__((sysv_abi,noreturn)) void __dong_panic(U reason,U line) {
    fprintf(stderr,"unexpected Dong panic reason=%llu line=%llu\n",(unsigned long long)reason,(unsigned long long)line);abort();
}
static GuardedHeader input;
static U checks;
static U field(U value,unsigned shift,U mask) {return (value>>shift)&mask;}
static int oracle(const Header *h) {
    /* Decode the public subset as individual NVMe/PCI fields. Queue/data
       regions are independent half-open C intervals, not Dong outputs. */
    U major=h->version>>16,minor=field(h->version,8,255),tertiary=h->version&255;
    U css=field(h->cap,37,255),timeout=field(h->cap,24,255);
    U stride=UINT64_C(4)<<field(h->cap,32,15);
    if(major!=1 || minor>4 || tertiary || h->physical_bits<36 || h->physical_bits>52
       || !timeout || (css&1)==0 || (css&190)!=0 || field(h->cap,48,15)!=0
       || field(h->cap,59,3)!=0 || field(h->cap,62,3)!=0 || field(h->cap,19,31)!=0
       || field(h->cap,0,65535)<1)return 0;
    if(h->pci_command>65535 || (h->pci_command&1) || !(h->pci_command&2)
       || (h->pci_command&4) || !(h->pci_command&1024))return 0;
    if(h->cc!=0x460000 || h->csts!=0 || h->intms!=UINT64_C(0xffffffff)
       || h->aqa!=65537 || h->msi_disabled!=1 || h->msix_disabled!=1 || h->lease_exclusive!=1)return 0;
    if(h->bar_bytes<4096+3*stride+4 || !h->lease_physical || h->lease_physical%4096
       || h->lease_bytes!=131072 || h->lease_physical>UINT64_C(0xfffe0000)
       || h->asq!=h->lease_physical || h->acq!=h->lease_physical+4096)return 0;
    const U start[]={0,4096,8192,12288,16384,20480,24576};
    const U length[]={4096,4096,4096,4096,4096,4096,69632};
    for(unsigned i=0;i<7;i++) {
        if(start[i]+length[i]>h->lease_bytes || h->lease_physical+start[i]+length[i]>UINT64_C(0x100000000))return 0;
        for(unsigned j=0;j<i;j++)if(start[i]<start[j]+length[j] && start[j]<start[i]+length[i])return 0;
    }
    return 1;
}
static void reset(void) {
    memset(&input,0xa5,sizeof input);
    input.header=(Header){UINT64_C(0x2001000001),0x10400,48,0x4000,0x100000,131072,0x402,0x460000,
        0,UINT64_C(0xffffffff),65537,0x100000,0x101000,1,1,1};
}
static void run(void) {
    GuardedHeader before=input;GuardedOutput output,saved;
    memset(&output,0x5a,sizeof output);saved=output;
    int accepted=oracle(&input.header);U status=nvme_authority_permit(&input.header,&output.value);checks++;
    if(accepted)saved.value=input.header.pci_command|4;
    if((status==0)!=accepted || (!accepted && status!=UINT64_C(0x05220001))
       || memcmp(&input,&before,sizeof input) || memcmp(&output,&saved,sizeof output)) {
        fprintf(stderr,"NVMe authority case=%llu expected=%d status=%llx output=%llx\n",
            (unsigned long long)checks,accepted,(unsigned long long)status,(unsigned long long)output.value);exit(1);
    }
}
static U random_state=UINT64_C(0x84192837a54bc107);
static U random64(void) {random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return random_state;}
static unsigned char *guarded_page(void) {
#ifdef _WIN32
    DWORD old;unsigned char *p=VirtualAlloc(NULL,12288,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!p || !VirtualProtect(p,4096,PAGE_NOACCESS,&old) || !VirtualProtect(p+8192,4096,PAGE_NOACCESS,&old))exit(5);
#else
    unsigned char *p=mmap(NULL,12288,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(p==MAP_FAILED || mprotect(p,4096,PROT_NONE) || mprotect(p+8192,4096,PROT_NONE))exit(5);
#endif
    return p+4096;
}
static void guarded_snapshot(void) {
    unsigned char *a=guarded_page(),*b=guarded_page();
    reset();Header *h=(Header*)(a+4096-sizeof(Header));U *out=(U*)(b+4096-sizeof(U));
    memcpy(h,&input.header,sizeof *h);*out=UINT64_C(0x12345678);
    if(nvme_authority_permit(h,out)!=0 || *out!=0x406 || memcmp(h,&input.header,sizeof *h))exit(6);
    h->asq+=4096;*out=UINT64_C(0x87654321);
    if(nvme_authority_permit(h,out)!=UINT64_C(0x05220001) || *out!=UINT64_C(0x87654321))exit(7);
#ifdef _WIN32
    if(!VirtualFree(a-4096,0,MEM_RELEASE) || !VirtualFree(b-4096,0,MEM_RELEASE))exit(8);
#else
    if(munmap(a-4096,12288) || munmap(b-4096,12288))exit(8);
#endif
}
int main(int argc,char **argv) {
    if(sizeof(Header)!=128)return 2;
    reset();
    if(argc>1) {
        const char *label;
        if(!strcmp(argv[1],"interrupts")){input.header.intms=0;label="UNSAFE_INTERRUPT_MASK_ACCEPTED";}
        else if(!strcmp(argv[1],"admin-base")){input.header.asq+=131072;label="UNSAFE_ADMIN_BASE_ACCEPTED";}
        else if(!strcmp(argv[1],"doorbells")){input.header.bar_bytes=0x100c;label="UNSAFE_LAST_DOORBELL_ACCEPTED";}
        else return 3;
        U out=0;if(nvme_authority_permit(&input.header,&out)==0){puts(label);return 99;}return 0;
    }
    run();
    /* Every bit of every trusted field, including upper halves of dwords. */
    for(unsigned i=0;i<16;i++)for(unsigned bit=0;bit<64;bit++){reset();((U*)&input.header)[i]^=UINT64_C(1)<<bit;run();}
    for(U command=0;command<=65536;command++){reset();input.header.pci_command=command;run();}
    /* Exhaust both queue-size dwords independently. Only depth2 is granted. */
    for(U q=0;q<=65535;q++) {
        reset();input.header.aqa=(q<<16)|1;run();input.header.aqa=(UINT64_C(1)<<16)|q;run();
        reset();input.header.cap=(input.header.cap&~UINT64_C(65535))|q;run();
    }
    /* The entire minor/tertiary space includes exactly the five accepted VSs. */
    for(U v=0;v<65536;v++){reset();input.header.version=65536|v;run();}
    for(U major=0;major<65536;major++){reset();input.header.version=(major<<16)|0x400;run();}
    for(U timeout=0;timeout<=255;timeout++)for(U dstrd=0;dstrd<16;dstrd++) {
        reset();input.header.cap=(input.header.cap&~UINT64_C(0xffffffff000000))|(timeout<<24)|(dstrd<<32)|(UINT64_C(1)<<37);
        input.header.bar_bytes=4096+3*(UINT64_C(4)<<dstrd)+4;run();
        input.header.bar_bytes--;run();
    }
    for(U bits=0;bits<64;bits++){reset();input.header.physical_bits=bits;run();}
    for(U flags=0;flags<256;flags++){reset();input.header.cap=(input.header.cap&~(UINT64_C(255)<<37))|(flags<<37);run();}
    for(U value=0;value<65536;value++) {
        reset();input.header.cc=value;run();input.header.cc=0x460000|value;run();
        reset();input.header.csts=value;run();
    }
    const U physicals[]={0,1,4095,4096,0x100000,0xfffdf000,0xfffe0000,0xfffe1000,0xfffff000,
        UINT64_C(0x100000000),UINT64_MAX-131071,UINT64_MAX};
    for(unsigned i=0;i<sizeof physicals/sizeof physicals[0];i++) {
        reset();input.header.lease_physical=physicals[i];input.header.asq=physicals[i];input.header.acq=physicals[i]+4096;run();
    }
    for(U length=0;length<=131073;length++){reset();input.header.lease_bytes=length;run();}
    for(unsigned i=0;i<20000;i++) {
        reset();unsigned index=(unsigned)(random64()%16);((U*)&input.header)[index]=random64();run();
        reset();input.header.lease_physical=(random64()%UINT64_C(0xfffff))*4096;
        input.header.asq=input.header.lease_physical;input.header.acq=input.header.lease_physical+4096;
        input.header.pci_command=(random64()&65535&~UINT64_C(0x407))|0x402;run();
    }
    GuardedOutput output,saved;memset(&output,0x33,sizeof output);saved=output;
    if(nvme_authority_permit(NULL,&output.value)!=UINT64_C(0x05220001) || memcmp(&saved,&output,sizeof output))return 4;
    guarded_snapshot();
    printf("NVMe authority checks=%llu fields/lease/PCI/interrupts/admin/doorbells/guard-pages verified\n",(unsigned long long)checks);
    return 0;
}
