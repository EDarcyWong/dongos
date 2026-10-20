#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
#define IO_ERROR 0x05040004ULL
#define NO_SPACE 0x05040008ULL
#define MASK 0x0fffffffU
typedef struct {uint64_t context,capacity,max_transfer;uint64_t(SYSV*read)(uint64_t,uint64_t,uint64_t,uint8_t*);uint64_t(SYSV*write)(uint64_t,uint64_t,uint64_t,const uint8_t*);uint64_t(SYSV*flush)(uint64_t);} Device;
typedef struct {const Device*device;uint64_t ready,busy,failed,read_only,dirty,total,spc,reserved,fat_sectors,data_start,clusters,root,fsinfo,backup;} Volume;
typedef struct {uint8_t name[11],attributes;uint64_t cluster,size,sector,offset;} Dir;
typedef struct {uint8_t*bytes;uint64_t sectors,reads,writes,flushes,budget,fail_read,fail_write,fail_flush,budget_hit,bad_io;} Io;
extern uint64_t SYSV fa_grow(Volume*,void*,Dir*,uint64_t,uint64_t);
extern uint64_t SYSV fa_allocate(Volume*,void*,uint64_t*);
extern uint64_t SYSV fa_enough(const Volume*,void*,uint64_t);
static Io io;
static Device device;
static Volume volume;
static uint8_t *scratch_storage,*scratch;
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"allocation check failed line %u: %s (reads=%u writes=%u budget_hit=%u)\n",__LINE__,#x,(unsigned)io.reads,(unsigned)io.writes,(unsigned)io.budget_hit);return 1;}}while(0)
void SYSV __dong_panic(uint64_t code,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"allocation unexpected panic %x\n",(unsigned)code);exit(9);}
static uint32_t get32(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put32(uint8_t*p,uint32_t value){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(value>>(8*i));}
static uint64_t SYSV disk_read(uint64_t context,uint64_t lba,uint64_t count,uint8_t*out){
    Io*d=(Io*)(uintptr_t)context;d->reads++;
    if(count!=1||lba>=d->sectors){d->bad_io++;return 99;}
    if(d->budget&&d->reads>d->budget){d->budget_hit++;return 71;}
    if(d->fail_read&&d->reads==d->fail_read)return 72;
    memcpy(out,d->bytes+lba*512,512);return 0;
}
static uint64_t SYSV disk_write(uint64_t context,uint64_t lba,uint64_t count,const uint8_t*input){
    Io*d=(Io*)(uintptr_t)context;d->writes++;
    if(count!=1||lba>=d->sectors){d->bad_io++;return 99;}
    if(d->fail_write&&d->writes==d->fail_write)return 73;
    memcpy(d->bytes+lba*512,input,512);return 0;
}
static uint64_t SYSV disk_flush(uint64_t context){Io*d=(Io*)(uintptr_t)context;d->flushes++;return d->fail_flush?74:0;}
static void set_fat(uint64_t cluster,uint32_t value){
    for(unsigned copy=0;copy<2;copy++)put32(io.bytes+(volume.reserved+copy*volume.fat_sectors)*512+cluster*4,value);
}
static uint32_t fat(uint64_t cluster){return get32(io.bytes+volume.reserved*512+cluster*4);}
static int setup(uint64_t clusters){
    free(io.bytes);memset(&io,0,sizeof io);memset(&volume,0,sizeof volume);
    volume.ready=1;volume.reserved=8;volume.fat_sectors=(clusters+2+127)/128;volume.spc=1;
    volume.data_start=volume.reserved+2*volume.fat_sectors;volume.clusters=clusters;volume.total=volume.data_start+clusters;
    volume.root=2;volume.fsinfo=1;volume.backup=6;io.sectors=volume.total;io.bytes=calloc((size_t)io.sectors,512);
    CHECK(io.bytes!=NULL);memset(io.bytes+volume.data_start*512,0xa5,(size_t)clusters*512);
    device=(Device){(uint64_t)(uintptr_t)&io,io.sectors,1,disk_read,disk_write,disk_flush};volume.device=&device;
    memset(scratch_storage,0xa5,FAT32_SCRATCH_BYTES+64);memset(scratch,0,FAT32_SCRATCH_BYTES);
    set_fat(0,0x0ffffff8);set_fat(1,0x0fffffff);return 0;
}
static int guards(void){
    for(unsigned i=0;i<32;i++)CHECK(scratch_storage[i]==0xa5&&scratch[FAT32_SCRATCH_BYTES+i]==0xa5);
    CHECK(!io.bad_io);return 0;
}
static int mirrored(void){CHECK(!memcmp(io.bytes+volume.reserved*512,io.bytes+(volume.reserved+volume.fat_sectors)*512,(size_t)volume.fat_sectors*512));return guards();}
static int zero_cluster(uint64_t cluster){
    const uint8_t*p=io.bytes+(volume.data_start+cluster-2)*512;
    for(unsigned i=0;i<512;i++){CHECK(p[i]==0);}
    return 0;
}
static int large(void){
    CHECK(setup(128992)==0);for(uint64_t c=2;c<4563;c++)set_fat(c,MASK);
    Dir item={0};io.budget=24000;
    uint64_t result=fa_grow(&volume,scratch,&item,0,2*1024*1024);
    if(io.budget_hit){fprintf(stderr,"allocation read budget rejected production body: reads=%u result=%x\n",(unsigned)io.reads,(unsigned)result);return 2;}
    CHECK(result==0&&item.cluster==4563&&io.reads<=io.budget);
    for(uint64_t i=0;i<4096;i++){uint64_t c=item.cluster+i;CHECK((fat(c)&MASK)==(i==4095?MASK:c+1));CHECK(zero_cluster(c)==0);}
    CHECK(fat(4562)==MASK&&fat(8659)==0&&volume.dirty==1&&volume.failed==0);
    CHECK(io.flushes==1&&(fat(1)&0x08000000)==0);CHECK(mirrored()==0);
    printf("allocation large 2MiB passed: reads=%u budget=%u writes=%u flushes=%u\n",(unsigned)io.reads,(unsigned)io.budget,(unsigned)io.writes,(unsigned)io.flushes);return 0;
}
static int fragmented(void){
    CHECK(setup(260)==0);for(uint64_t c=2;c<262;c++)set_fat(c,MASK);
    const uint64_t holes[]={3,127,128,255,261};for(unsigned i=0;i<5;i++)set_fat(holes[i],i==2?0xf0000000U:0);
    Dir item={0};item.cluster=200;CHECK(fa_grow(&volume,scratch,&item,1,6*512)==0&&item.cluster==200);
    uint64_t previous=200;for(unsigned i=0;i<5;i++){CHECK((fat(previous)&MASK)==holes[i]);CHECK(zero_cluster(holes[i])==0);previous=holes[i];}
    CHECK((fat(previous)&MASK)==MASK&&(fat(128)&0xf0000000U)==0xf0000000U);
    /* Another allocation and another grow must rediscover a newly freed low
       cluster, even though the old chain tail and previous cursor were high. */
    set_fat(2,0);uint64_t selected=99;CHECK(fa_allocate(&volume,scratch,&selected)==0&&selected==2);
    set_fat(7,0);CHECK(fa_grow(&volume,scratch,&item,6,7*512)==0&&(fat(261)&MASK)==7&&(fat(7)&MASK)==MASK);
    CHECK(mirrored()==0);puts("allocation fragmented and operation-local cursor passed");return 0;
}
static int boundaries(void){
    CHECK(setup(129)==0);for(uint64_t c=2;c<131;c++)set_fat(c,MASK);
    /* Entries 131..255 are zero padding, never allocatable clusters. */
    CHECK(fa_enough(&volume,scratch,0)==0&&io.reads==0);
    CHECK(fa_enough(&volume,scratch,1)==NO_SPACE&&io.reads==2&&io.writes==0);
    uint64_t selected=99;CHECK(fa_allocate(&volume,scratch,&selected)==NO_SPACE&&selected==99&&io.reads==4);
    Dir item={0};CHECK(fa_grow(&volume,scratch,&item,0,512)==NO_SPACE&&volume.dirty==0&&io.writes==0&&io.flushes==0);
    set_fat(127,0);set_fat(128,0);set_fat(130,0xf0000000U);
    uint64_t before=io.reads;CHECK(fa_enough(&volume,scratch,3)==0&&io.reads-before==2);
    CHECK(fa_enough(&volume,scratch,4)==NO_SPACE);
    const uint64_t expected[]={127,128,130};for(unsigned i=0;i<3;i++)CHECK(fa_allocate(&volume,scratch,&selected)==0&&selected==expected[i]);
    CHECK(fat(130)==0xffffffffU&&fa_allocate(&volume,scratch,&selected)==NO_SPACE);
    CHECK(mirrored()==0);puts("allocation sector boundaries, padding, high bits and NoSpace passed");return 0;
}
static int failures(void){
    CHECK(setup(129)==0);set_fat(2,MASK);io.fail_read=1;
    CHECK(fa_enough(&volume,scratch,1)==IO_ERROR&&io.writes==0&&volume.dirty==0);
    io.fail_read=2;uint64_t selected=99;CHECK(fa_allocate(&volume,scratch,&selected)==IO_ERROR&&selected==99&&io.writes==0);
    io.fail_read=3;Dir item={0};CHECK(fa_grow(&volume,scratch,&item,0,512)==IO_ERROR&&io.writes==0&&volume.dirty==0&&item.cluster==0);
    /* The second scanned FAT sector must also propagate an actual read error. */
    CHECK(setup(129)==0);for(uint64_t c=2;c<128;c++)set_fat(c,MASK);io.fail_read=2;
    CHECK(fa_enough(&volume,scratch,1)==IO_ERROR&&io.writes==0);
    io.fail_read=io.reads+2;CHECK(fa_allocate(&volume,scratch,&selected)==IO_ERROR&&io.writes==0);
    /* FAT mirror write and data-clear errors retain the existing failed flag. */
    CHECK(setup(129)==0);io.fail_write=2;
    CHECK(fa_allocate(&volume,scratch,&selected)==IO_ERROR&&volume.failed==1&&selected==99&&io.writes==2);
    CHECK(setup(129)==0);io.fail_write=3;
    CHECK(fa_allocate(&volume,scratch,&selected)==IO_ERROR&&volume.failed==1&&selected==99&&io.writes==3);
    CHECK(setup(129)==0);io.fail_flush=1;
    CHECK(fa_grow(&volume,scratch,&item,0,512)==IO_ERROR&&volume.dirty==1&&volume.failed==1&&io.flushes==1&&io.writes==2&&item.cluster==0);
    CHECK(guards()==0);puts("allocation callback I/O and flush failures passed");return 0;
}
int main(int argc,char**argv){
    if(argc!=2){return 3;}
    scratch_storage=malloc(FAT32_SCRATCH_BYTES+64);if(!scratch_storage){return 4;}scratch=scratch_storage+32;
    int result=!strcmp(argv[1],"large")?large():!strcmp(argv[1],"fragmented")?fragmented():!strcmp(argv[1],"boundaries")?boundaries():!strcmp(argv[1],"failures")?failures():3;
    if(!result){printf("allocation native checks passed: %u\n",checks);}
    free(io.bytes);free(scratch_storage);return result;
}
