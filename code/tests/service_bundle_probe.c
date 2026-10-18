#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"BUNDLE_MODEL_ASSERT line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
typedef struct { uint8_t name[32];uint64_t offset,length,kind;uint8_t digest[32]; } Entry;
typedef struct { uint64_t count,total;Entry entries[31]; } Inventory;
extern ABI size_t bundle_inventory_size(void);
extern ABI uint64_t bundle_validate(const uint8_t *,size_t,Inventory *);
extern ABI uint64_t bundle_sha256(const uint8_t *,size_t,uint8_t *);
extern ABI uint64_t bundle_contents(const uint8_t *,size_t,const Inventory *,size_t,const uint8_t **,size_t *);
ABI void __dong_panic(uint64_t code) { fprintf(stderr,"unexpected Dong panic %llu\n",(unsigned long long)code);exit(99); }
ABI void bundle_negative_hit(uint64_t kind) { fprintf(stderr,"BUNDLE_NEGATIVE_HIT %llu\n",(unsigned long long)kind); }
static uint8_t *read_file(const char *name,size_t *length) {
    FILE *f=fopen(name,"rb");CHECK(f);CHECK(fseek(f,0,SEEK_END)==0);long size=ftell(f);CHECK(size>=0&&size<=64*1024*1024);
    CHECK(fseek(f,0,SEEK_SET)==0);*length=(size_t)size;uint8_t *raw=malloc(*length+1);CHECK(raw);CHECK(fread(raw,1,*length,f)==*length);CHECK(fclose(f)==0);return raw;
}
int main(int argc,char **argv) {
    CHECK(argc>=4);size_t length=0;uint8_t *raw=read_file(argv[2],&length);
    if(strcmp(argv[1],"hash")==0) {
        CHECK(strlen(argv[3])==64);struct { uint8_t a[16],digest[32],z[16]; } out;memset(&out,0xa7,sizeof out);
        CHECK(bundle_sha256(raw,length,out.digest)==0);
        for(unsigned i=0;i<32;i++) { unsigned value=0;CHECK(sscanf(argv[3]+i*2,"%2x",&value)==1);CHECK(out.digest[i]==value); }
        for(unsigned i=0;i<16;i++) CHECK(out.a[i]==0xa7&&out.z[i]==0xa7);
        printf("bundle SHA256 passed length=%llu\n",(unsigned long long)length);free(raw);return 0;
    }
    CHECK(strcmp(argv[1],"bundle")==0);CHECK(sizeof(Entry)==88&&sizeof(Inventory)==2744&&bundle_inventory_size()==2744);
    uint64_t expected=strtoull(argv[3],NULL,0);uint8_t *snapshot=malloc(length+1);CHECK(snapshot);memcpy(snapshot,raw,length);
    struct { uint64_t a[2];Inventory value;uint64_t z[2]; } out;memset(&out,0xa7,sizeof out);Inventory before=out.value;
    uint64_t error=bundle_validate(raw,length,&out.value);
    if(error!=expected) fprintf(stderr,"got 0x%llx expected 0x%llx\n",(unsigned long long)error,(unsigned long long)expected);
    CHECK(error==expected);CHECK(memcmp(raw,snapshot,length)==0);
    CHECK(out.a[0]==UINT64_C(0xa7a7a7a7a7a7a7a7)&&out.a[1]==out.a[0]&&out.z[0]==out.a[0]&&out.z[1]==out.a[0]);
    if(error) CHECK(memcmp(&before,&out.value,sizeof before)==0);
    else {
        CHECK(argc==5);size_t expected_length;uint8_t *expected_bytes=read_file(argv[4],&expected_length);CHECK(expected_length==sizeof(Inventory));CHECK(memcmp(&out.value,expected_bytes,sizeof(Inventory))==0);free(expected_bytes);
        for(size_t i=0;i<out.value.count;i++) { const uint8_t *pointer=NULL;size_t bytes=0;
            CHECK(bundle_contents(raw,length,&out.value,i,&pointer,&bytes)==0);CHECK(pointer==raw+out.value.entries[i].offset&&bytes==out.value.entries[i].length); }
        const uint8_t *pointer=(const uint8_t *)(uintptr_t)0x1234;size_t bytes=0x5678;
        CHECK(bundle_contents(raw,length,&out.value,(size_t)out.value.count,&pointer,&bytes)==0x04040004);
        CHECK(pointer==(const uint8_t *)(uintptr_t)0x1234&&bytes==0x5678);
    }
    printf("bundle independent inventory passed error=0x%llx bytes=%llu\n",(unsigned long long)error,(unsigned long long)length);free(snapshot);free(raw);return 0;
}
