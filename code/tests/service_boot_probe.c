/* Execute the real Win64 UEFI helper against bounded firmware protocols. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#include <windows.h>
#else
#include <sys/mman.h>
#endif
#define EFI __attribute__((ms_abi))
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"SERVICE_BOOT_ASSERT line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
#define E(n) (UINT64_C(0x8000000000000000)+(n))
typedef struct { uint64_t magic,version,size,flags,bundle,bundle_bytes,bundle_pages,arena,arena_bytes,arena_pages,self,checksum; } Handoff;
extern EFI uint64_t service_bundle_load(void *,void *,uint64_t *);
extern EFI uint64_t service_handoff_validate(const Handoff *,uint64_t);
static uint8_t bs[400],root[88],file[88];
static unsigned scenario,alloc_calls,free_calls,close_calls,read_calls,opened;
static uint8_t *source;static size_t source_size,position;
typedef struct { uint64_t reported,bytes;void *actual;int alive; } Allocation;
static Allocation allocations[3];
static void put64(uint8_t *p,uint64_t value) { memcpy(p,&value,8); }
static void *low_memory(uintptr_t base,size_t size) {
#if defined(_WIN32)
    return VirtualAlloc((void *)base,size,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
#else
    void *p=mmap((void *)base,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    return p==MAP_FAILED?NULL:p;
#endif
}
static void drop(Allocation *a) {
    if(a->actual) {
#if defined(_WIN32)
        CHECK(VirtualFree(a->actual,0,MEM_RELEASE));
#else
        CHECK(munmap(a->actual,(size_t)a->bytes)==0);
#endif
    }
    a->alive=0;
}
static EFI uint64_t allocate_pages(uint32_t type,uint32_t memory_type,size_t pages,uint64_t *address) {
    CHECK(type==1&&memory_type==2&&*address==UINT32_MAX);alloc_calls++;CHECK(alloc_calls<=3);
    CHECK(pages==(alloc_calls==1?(source_size/4096):alloc_calls==2?32768:1));
    if((scenario==9&&alloc_calls==1)||(scenario==15&&alloc_calls==2)||(scenario==16&&alloc_calls==3))return E(9);
    Allocation *a=&allocations[alloc_calls-1];a->bytes=(uint64_t)pages*4096;a->alive=1;
    if(scenario==17&&alloc_calls==1) { a->reported=UINT64_C(0xfffff000);*address=a->reported;return 0; }
    if(scenario==23&&alloc_calls==1) { a->reported=0;*address=0;return 0; }
    uintptr_t base=UINT64_C(0x10000000)+(alloc_calls-1)*UINT64_C(0x10000000);
    a->actual=low_memory(base,(size_t)a->bytes);CHECK(a->actual==(void *)base);memset(a->actual,0xa7,(size_t)a->bytes);
    a->reported=base+(scenario==18&&alloc_calls==1?1:0);*address=a->reported;return 0;
}
static EFI uint64_t free_pages(uint64_t address,size_t pages) {
    free_calls++;
    for(unsigned i=0;i<3;i++)if(allocations[i].alive&&allocations[i].reported==address) {
        CHECK(allocations[i].bytes==(uint64_t)pages*4096);
        if(scenario==19)return E(7);
        drop(&allocations[i]);return 0;
    }
    CHECK(0);return E(2);
}
static EFI uint64_t open_file(void *self,void **out,const uint16_t *path,uint64_t mode,uint64_t attrs) {
    static const uint16_t name[]={92,'S','E','R','V','I','C','E','S','.','B','I','N',0};
    CHECK(self==root&&mode==1&&attrs==0&&memcmp(path,name,sizeof name)==0);CHECK(!opened);
    if(scenario==3)return E(14);
    opened=1;*out=file;return 0;
}
static EFI uint64_t close_file(void *self) { CHECK(self==file&&opened);opened=0;close_calls++;return scenario==14?E(7):0; }
static EFI uint64_t get_info(void *self,const uint8_t *guid,size_t *size,void *buffer) {
    static const uint8_t expected[]={0x92,0x6e,0x57,0x09,0x3f,0x6d,0xd2,0x11,0x8e,0x39,0,0xa0,0xc9,0x69,0x72,0x3b};
    CHECK(self==file&&opened&&memcmp(guid,expected,16)==0&&*size==512);
    if(scenario==4)return E(7);
    if(scenario==22) { *size=1024;return E(5); }
    memset(buffer,0,512);put64(buffer,scenario==20?513:104);uint64_t length=source_size;
    if(scenario==6)length=0;
    if(scenario==7)length=64*1024*1024+4096;
    if(scenario==8)length++;
    put64((uint8_t *)buffer+8,length);put64((uint8_t *)buffer+72,scenario==5?16:0);*size=104;return 0;
}
static EFI uint64_t read_file(void *self,size_t *size,void *buffer) {
    CHECK(self==file&&opened&&*size>=1&&*size<=1024*1024);read_calls++;
    if(scenario==10)return E(7);
    if(scenario==11&&position>=4096) { *size=0;return 0; }
    if(position==source_size) { if(scenario==12) { *(uint8_t *)buffer=1;*size=1;return 0; } *size=0;return 0; }
    size_t bytes=*size;if(bytes>source_size-position)bytes=source_size-position;
    if(scenario==2&&bytes>1024)bytes=1024;
    if(scenario==11&&bytes>4096)bytes=4096;
    memcpy(buffer,source+position,bytes);position+=bytes;
    *size=bytes+(scenario==21?1:0);return 0;
}
static void checksum(Handoff *h) { uint64_t *words=(uint64_t *)h,total=0;h->checksum=0;for(unsigned i=0;i<12;i++)total+=words[i];h->checksum=0-total; }
static void handoff_cases(Handoff *original) {
    Handoff h=*original;CHECK(service_handoff_validate(&h,h.self)==0);
    uint64_t *words=(uint64_t *)&h;
    for(unsigned i=0;i<12;i++) { h=*original;words[i]^=1;if(i!=11)checksum(&h);CHECK(service_handoff_validate(&h,original->self)!=0); }
    h=*original;h.bundle=UINT64_C(0x100000000)-h.bundle_bytes;checksum(&h);CHECK(service_handoff_validate(&h,h.self)==0);
    h.bundle+=4096;checksum(&h);CHECK(service_handoff_validate(&h,h.self)!=0);
    h=*original;h.arena=UINT64_C(0xf8000000);checksum(&h);CHECK(service_handoff_validate(&h,h.self)==0);
    h.arena+=4096;checksum(&h);CHECK(service_handoff_validate(&h,h.self)!=0);
    h=*original;h.bundle=h.self;checksum(&h);CHECK(service_handoff_validate(&h,h.self)!=0);
    h=*original;h.arena=h.bundle;checksum(&h);CHECK(service_handoff_validate(&h,h.self)!=0);
    CHECK(service_handoff_validate(original,original->self+4096)!=0);
}
int main(int argc,char **argv) {
    CHECK(argc==3);scenario=(unsigned)strtoul(argv[1],NULL,0);CHECK(scenario<=23);
    FILE *input=fopen(argv[2],"rb");CHECK(input);CHECK(fseek(input,0,SEEK_END)==0);long length=ftell(input);CHECK(length>=8192&&length<=64*1024*1024&&length%4096==0);
    source_size=(size_t)length;source=malloc(source_size);CHECK(source);CHECK(fseek(input,0,SEEK_SET)==0&&fread(source,1,source_size,input)==source_size);CHECK(fclose(input)==0);
    if(scenario==13||scenario==19)source[0]^=1;
    /* EFI_TABLE_HEADER=24; RaiseTPL/RestoreTPL precede AllocatePages. */
    put64(bs+40,(uint64_t)(uintptr_t)allocate_pages);put64(bs+48,(uint64_t)(uintptr_t)free_pages);
    put64(root+8,(uint64_t)(uintptr_t)open_file);put64(file+16,(uint64_t)(uintptr_t)close_file);
    put64(file+32,(uint64_t)(uintptr_t)read_file);put64(file+64,(uint64_t)(uintptr_t)get_info);
    uint64_t out=UINT64_C(0x123456789abcdef0);uint64_t status=service_bundle_load(bs,root,&out);
    if(scenario<=2) {
        CHECK(status==0&&alloc_calls==3&&free_calls==0&&close_calls==1&&!opened);
        Handoff *h=(Handoff *)(uintptr_t)out;CHECK(out==allocations[2].reported&&h->magic==UINT64_C(0x31444e4148565344)&&h->version==1&&h->size==96&&h->flags==1);
        CHECK(h->bundle==allocations[0].reported&&h->bundle_bytes==source_size&&h->bundle_pages==source_size/4096);
        CHECK(memcmp((void *)(uintptr_t)h->bundle,source,source_size)==0);
        CHECK(h->arena==allocations[1].reported&&h->arena_bytes==128*1024*1024&&h->arena_pages==32768&&h->self==out);
        uint64_t *arena=(uint64_t *)(uintptr_t)h->arena;for(size_t i=0;i<h->arena_bytes/8;i++)CHECK(arena[i]==0);
        for(unsigned i=96;i<4096;i++)CHECK(*((uint8_t *)h+i)==0);
        handoff_cases(h);if(scenario==2)CHECK(read_calls==source_size/1024+1);
        for(unsigned i=0;i<3;i++) { CHECK(allocations[i].alive);drop(&allocations[i]); }
        printf("service boot actual UEFI helper passed scenario=%u bytes=%llu handoff=96 arena=134217728\n",scenario,(unsigned long long)source_size);
    } else {
        CHECK(status!=0&&out==UINT64_C(0x123456789abcdef0)&&!opened);
        if(scenario==19)CHECK(status==E(7));
        if(scenario==17||scenario==18||scenario==23)CHECK(status==E(3));
        for(unsigned i=0;i<3;i++) { if(scenario!=19)CHECK(!allocations[i].alive);else if(allocations[i].alive)drop(&allocations[i]); }
        CHECK(close_calls==(scenario==3?0:1));
        printf("service boot failure retained output and cleaned resources scenario=%u status=%llx\n",scenario,(unsigned long long)status);
    }
    free(source);return 0;
}
