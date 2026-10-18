#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
typedef struct{uint64_t context,capacity,max_transfer;uint64_t(SYSV*read)(uint64_t,uint64_t,uint64_t,uint8_t*);uint64_t(SYSV*write)(uint64_t,uint64_t,uint64_t,const uint8_t*);uint64_t(SYSV*flush)(uint64_t);} Device;
typedef struct{const Device*device;uint64_t ready,busy,failed,read_only,dirty,total,spc,reserved,fat_sectors,data_start,clusters,root,fsinfo,backup;} Volume;
#ifndef FAT32_SCRATCH_BYTES
#define FAT32_SCRATCH_BYTES 33835
#endif
typedef struct{uint8_t sector[512],fat[512],entry[32],name[11],seen[32768],directory_audit[FAT32_SCRATCH_BYTES-33835];} Scratch;
typedef struct{uint8_t name[11],attributes;uint64_t cluster,size,sector,offset;} Dir;
extern void SYSV fp_reset(Volume*);
extern uint64_t SYSV fp_mount(Volume*,const Device*,Scratch*),fp_list(Volume*,Scratch*,uint64_t,Dir*,uint64_t*);
extern uint64_t SYSV fp_create(Volume*,Scratch*,const char*,uint64_t),fp_remove(Volume*,Scratch*,const char*,uint64_t),fp_truncate(Volume*,Scratch*,const char*,uint64_t,uint64_t),fp_flush(Volume*,Scratch*);
extern uint64_t SYSV fp_read(Volume*,Scratch*,const char*,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*),fp_write(Volume*,Scratch*,const char*,uint64_t,uint64_t,const uint8_t*,uint64_t,uint64_t*);
static struct{uint8_t lo[32];Scratch value;uint8_t hi[32];} work;
static struct{uint8_t lo[32];Volume value;uint8_t hi[32];} volume;
static Device device;
typedef struct{FILE*disk,*log;uint64_t sectors,reads,writes,flushes,fail_read,fail_write;unsigned fail_flush,reenter,hit_reenter,io_bad;} Io;
static Io io;
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"FAT32 check failed line %u\n",__LINE__);return 1;}}while(0)
#define V (&volume.value)
#define W (&work.value)
#define CREATE(name) fp_create(V,W,name,sizeof(name)-1)
#define REMOVE(name) fp_remove(V,W,name,sizeof(name)-1)
#define READ(name,off,out,n,got) fp_read(V,W,name,sizeof(name)-1,off,out,n,got)
#define WRITE(name,off,data,n,got) fp_write(V,W,name,sizeof(name)-1,off,data,n,got)
void SYSV __dong_panic(uint64_t code,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"FAT32 unexpected panic %x\n",(unsigned)code);exit(9);}
static uint32_t SYSV get32(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void SYSV put32(uint8_t*p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(i*8));}
static unsigned SYSV all(const uint8_t*p,size_t n,uint8_t b){for(size_t i=0;i<n;i++)if(p[i]!=b)return 0;return 1;}
static int SYSV raw_read(uint64_t lba,uint8_t*out){return lba<io.sectors&&!fseek(io.disk,(long)(lba*512),SEEK_SET)&&fread(out,1,512,io.disk)==512;}
static uint64_t SYSV disk_read(uint64_t ctx,uint64_t lba,uint64_t count,uint8_t*out){
 Io*d=(Io*)(uintptr_t)ctx;uint8_t temp[512];d->reads++;
 if(count!=1||lba>=d->sectors){d->io_bad++;return 99;}
 if(d->reenter){Dir entry;uint64_t present=99;d->reenter=0;if(fp_list(V,W,0,&entry,&present)!=0x0504000bULL||present!=99)d->io_bad++;else d->hit_reenter++;}
 if(d->fail_read&&d->reads==d->fail_read)return 71;
 if(!raw_read(lba,temp))return 72;
 memcpy(out,temp,512);return 0;
}
static uint64_t SYSV disk_write(uint64_t ctx,uint64_t lba,uint64_t count,const uint8_t*input){
 Io*d=(Io*)(uintptr_t)ctx;uint8_t before[512];d->writes++;
 if(count!=1||lba>=d->sectors){d->io_bad++;return 99;}
 if(d->fail_write&&d->writes==d->fail_write)return 73;
 if(!raw_read(lba,before))return 74;
 /* Raw before/after byte journal survives every success and failure scenario. */
 if(fwrite(&lba,8,1,d->log)!=1||fwrite(before,512,1,d->log)!=1||fwrite(input,512,1,d->log)!=1)return 75;
 if(fseek(d->disk,(long)(lba*512),SEEK_SET)||fwrite(input,512,1,d->disk)!=1)return 76;
 return 0;
}
static uint64_t SYSV disk_flush(uint64_t ctx){Io*d=(Io*)(uintptr_t)ctx;d->flushes++;if(d->fail_flush)return 77;return fflush(d->disk)||fflush(d->log)?78:0;}
static int SYSV mount(void){fp_reset(V);return (int)fp_mount(V,&device,W);}
static int SYSV remount(const char*path){CHECK(!fclose(io.disk));io.disk=fopen(path,"r+b");CHECK(io.disk!=NULL);return mount();}
static int SYSV guards(void){CHECK(all(work.lo,32,0xa5)&&all(work.hi,32,0xa5)&&all(volume.lo,32,0xa5)&&all(volume.hi,32,0xa5)&&!io.io_bad);return 0;}
static int SYSV lifecycle(const char*path){
 uint8_t expected[2064],data[1500],tail[64],out[2128];uint64_t got=99,present=0;Dir entry;
 CHECK(mount()==0&&V->clusters>=65525&&V->read_only==0&&io.hit_reenter==1);
 memset(out,0xa5,sizeof out);CHECK(READ("README.TXT",0,out+32,2064,&got)==0&&got==34&&!memcmp(out+32,"DongOS FAT32 persistence fixture.\n",34));
 CHECK(all(out,32,0xa5)&&all(out+66,sizeof(out)-66,0xa5));
 CHECK(fp_list(V,W,0,&entry,&present)==0&&present==1&&!memcmp(entry.name,"README  TXT",11)&&entry.size==34);
 CHECK(CREATE("work.bin")==0&&CREATE("WORK.BIN")==0x05040007ULL&&CREATE("TOOLONGNAME.X")==0x05040001ULL);
 for(unsigned i=0;i<1500;i++){data[i]=(uint8_t)(i*7+3);expected[i]=data[i];}
 memset(expected+1500,0,564);for(unsigned i=0;i<64;i++){tail[i]=(uint8_t)(i*13+9);expected[2000+i]=tail[i];}
 CHECK(WRITE("WORK.BIN",0,data,1500,&got)==0&&got==1500);CHECK(WRITE("WORK.BIN",2000,tail,64,&got)==0&&got==64);
 memset(out,0xa5,sizeof out);CHECK(READ("WORK.BIN",0,out+32,2064,&got)==0&&got==2064&&!memcmp(out+32,expected,2064)&&all(out,32,0xa5)&&all(out+2096,32,0xa5));
 CHECK(fp_truncate(V,W,"WORK.BIN",8,700)==0);CHECK(fp_truncate(V,W,"WORK.BIN",8,1700)==0);memset(expected+700,0,1000);
 CHECK(WRITE("WORK.BIN",768,tail,64,&got)==0);memcpy(expected+768,tail,64);
 CHECK(CREATE("RESULT.BIN")==0&&WRITE("RESULT.BIN",0,expected,1700,&got)==0&&got==1700&&REMOVE("WORK.BIN")==0);
 for(unsigned i=0;i<20;i++){char name[13];sprintf(name,"F%02u.TXT",i);CHECK(fp_create(V,W,name,strlen(name))==0);}
 CHECK(fp_flush(V,W)==0&&V->dirty==0);CHECK(remount(path)==0&&V->read_only==0);
 memset(out,0xa5,sizeof out);CHECK(READ("RESULT.BIN",0,out+32,2064,&got)==0&&got==1700&&!memcmp(out+32,expected,1700)&&all(out+1732,sizeof(out)-1732,0xa5));
 CHECK(READ("WORK.BIN",0,out,1,&got)==0x05040006ULL);
 unsigned listed=0;for(uint64_t i=0;i<30;i++){present=99;CHECK(fp_list(V,W,i,&entry,&present)==0);if(!present)break;listed++;}CHECK(listed==22);
 CHECK(REMOVE("RESULT.BIN")==0);CHECK(fp_flush(V,W)==0);CHECK(remount(path)==0);CHECK(READ("RESULT.BIN",0,out,1,&got)==0x05040006ULL);
 /* Final persistent artifact contains a known nonempty file for the independent
    Python byte reader after this process and all Dong state have exited. */
 CHECK(CREATE("RESULT.BIN")==0&&WRITE("RESULT.BIN",0,expected,1700,&got)==0&&fp_flush(V,W)==0);
 return guards();
}
static int SYSV corrupt(const char*kind){
 uint8_t boot[512],fat[512],root[512];CHECK(raw_read(0,boot));uint64_t f=get32(boot+36),data=32+2*f;CHECK(raw_read(32,fat));
 if(!strcmp(kind,"bpb")){put32(boot+32,65536);CHECK(!disk_write((uint64_t)(uintptr_t)&io,0,1,boot)&&!disk_write((uint64_t)(uintptr_t)&io,6,1,boot));CHECK(mount()==0x05040002);}
 else if(!strcmp(kind,"mirror")){put32(fat+12,0x0ffffff7);CHECK(!disk_write((uint64_t)(uintptr_t)&io,32+f,1,fat));CHECK(mount()==0x05040005);}
 else if(!strcmp(kind,"cross")){CHECK(raw_read(data,root));root[26]=2;root[27]=0;CHECK(!disk_write((uint64_t)(uintptr_t)&io,data,1,root));CHECK(mount()==0x05040005);}
 else{put32(fat+12,!strcmp(kind,"cycle")?3:!strcmp(kind,"bad")?0x0ffffff7:0x00100000);CHECK(!disk_write((uint64_t)(uintptr_t)&io,32,1,fat)&&!disk_write((uint64_t)(uintptr_t)&io,32+f,1,fat));CHECK(mount()==0x05040005);}
 CHECK(V->ready==0&&V->busy==0);return guards();
}
static int SYSV failure(const char*path,const char*kind){
 uint64_t got=99;uint8_t out[128],data[1500];memset(data,0x5a,sizeof data);CHECK(mount()==0);
 if(!strcmp(kind,"read-failure")){memset(out,0xa5,sizeof out);io.fail_read=io.reads+1;CHECK(READ("README.TXT",0,out+32,34,&got)==0x05040004ULL&&got==99&&all(out,128,0xa5));io.fail_read=0;CHECK(READ("README.TXT",0,out+32,34,&got)==0&&got==34);}
 else if(!strcmp(kind,"flush-failure")){CHECK(CREATE("PENDING.TXT")==0);io.fail_flush=1;CHECK(fp_flush(V,W)==0x05040004ULL&&V->failed==1);CHECK(CREATE("NO.TXT")==0x0504000aULL);io.fail_flush=0;CHECK(remount(path)==0&&V->read_only==1);}
 else{CHECK(CREATE("FAILED.BIN")==0&&fp_flush(V,W)==0);uint64_t before=io.writes;io.fail_write=io.writes+9;
   CHECK(WRITE("FAILED.BIN",0,data,sizeof data,&got)==0x05040004ULL&&V->failed==1&&io.writes==before+9);CHECK(CREATE("NO.TXT")==0x0504000aULL&&fp_flush(V,W)==0x0504000aULL);
   io.fail_write=0;int result=remount(path);CHECK(result==0x05040005||(result==0&&V->read_only==1));
 }
 return guards();
}
static int SYSV end_marker(const char*path){
 uint8_t boot[512],root[512];CHECK(raw_read(0,boot));uint64_t data=32+2*(uint64_t)get32(boot+36);CHECK(raw_read(data,root));
 memcpy(root+64,"GHOST   TXT",11);root[75]=0x20;CHECK(!disk_write((uint64_t)(uintptr_t)&io,data,1,root));
 CHECK(mount()==0&&CREATE("NEW.TXT")==0&&fp_flush(V,W)==0&&remount(path)==0);Dir item;uint64_t present=1;
 CHECK(fp_list(V,W,2,&item,&present)==0&&present==0);return guards();
}
static int SYSV exhausted(void){
 uint8_t boot[512],fat[512],root[512],byte=7;uint64_t got=99;CHECK(raw_read(0,boot));uint64_t f=get32(boot+36),data=32+2*f,clusters=get32(boot+32)-data;
 for(uint64_t s=0;s<f;s++){CHECK(raw_read(32+s,fat));for(unsigned i=0;i<128;i++){uint64_t c=s*128+i;if(c>=4&&c<clusters+2)put32(fat+i*4,(uint32_t)(c==clusters+1?0x0fffffff:c+1));}CHECK(!disk_write((uint64_t)(uintptr_t)&io,32+s,1,fat)&&!disk_write((uint64_t)(uintptr_t)&io,32+f+s,1,fat));}
 CHECK(raw_read(data,root));memcpy(root+32,"FULL    BIN",11);root[43]=0x20;root[58]=4;put32(root+60,(uint32_t)((clusters-2)*512));CHECK(!disk_write((uint64_t)(uintptr_t)&io,data,1,root));
 CHECK(mount()==0&&CREATE("EMPTY.BIN")==0&&fp_flush(V,W)==0);uint64_t writes=io.writes;Volume saved=*V;
 CHECK(WRITE("EMPTY.BIN",0,&byte,1,&got)==0x05040008ULL&&got==99&&io.writes==writes&&!memcmp(V,&saved,sizeof saved));return guards();
}
int main(int argc,char**argv){
 if(argc!=4)return 2;
 memset(&work,0xa5,sizeof work);memset(&volume,0xa5,sizeof volume);memset(W,0,sizeof *W);memset(V,0,sizeof *V);
 io.disk=fopen(argv[1],"r+b");io.log=fopen(argv[3],"wb");if(!io.disk||!io.log)return 3;fseek(io.disk,0,SEEK_END);io.sectors=(uint64_t)ftell(io.disk)/512;
 device=(Device){(uint64_t)(uintptr_t)&io,io.sectors,128,disk_read,disk_write,disk_flush};io.reenter=1;int result;
 if(!strcmp(argv[2],"lifecycle"))result=lifecycle(argv[1]);else if(!strcmp(argv[2],"exhausted"))result=exhausted();else if(!strcmp(argv[2],"end-marker"))result=end_marker(argv[1]);
 else if(strstr(argv[2],"failure"))result=failure(argv[1],argv[2]);else result=corrupt(argv[2]);
 fflush(io.disk);fflush(io.log);fclose(io.disk);fclose(io.log);
 if(result)return result;
 printf("FAT32 native checks passed %u reads=%u writes=%u flushes=%u\n",checks,(unsigned)io.reads,(unsigned)io.writes,(unsigned)io.flushes);return 0;
}
