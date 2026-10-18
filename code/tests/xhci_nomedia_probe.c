// Actual entry start_proxy/serve_block with only the syscall edge mocked.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"entry NoMedia native failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static U checks,peer=3,epochs=(7ull<<32)|1,receives,replies,logs,unexpected;static int idle;static U op=1,response[8];
extern ABI U entry_nomedia_setup(const void*),entry_nomedia_serve(void),entry_hid_preserved(void);
ABI U svc_call(U code,U a,U b,U c,U d,U e,U f){CK(!d&&!e&&!f);if(code==0x70){CK(a&&b&&b<128);logs++;return 0;}if(code==0x25){CK(a==0x123&&b&&c);receives++;if(idle)return 0x05110005;U*q=(U*)(uintptr_t)b;memset(q,0,64);q[0]=op;if(op==2||op==3){q[1]=8;q[2]=1;}*(U*)(uintptr_t)c=17;return 0;}if(code==0x29){CK(a==0x123&&b==17&&!c);return peer;}if(code==0x2a){CK(a==0x123&&b==17&&!c);return epochs;}if(code==0x24){CK(a==0x123&&b==17&&c);memcpy(response,(void*)(uintptr_t)c,64);replies++;return 0;}unexpected++;CK(0);return 1;}
ABI void svc_fence(void){}
ABI void __dong_panic(U kind,U line,const unsigned char*file,U len){(void)kind;(void)line;(void)file;(void)len;CK(0);abort();}
int main(int argc,char**argv){CK(argc==2);U boot[16]={1,14,0x123,0,0,0x234,0x51000000,65536,0,0,0x345,14,0,0,0,1000000};CK(entry_nomedia_setup(boot)==0&&logs==1&&entry_hid_preserved()==1);const char*s=argv[1];
 if(!strcmp(s,"hid-only")){for(op=1;op<=4;op++){memset(response,0xa5,sizeof response);CK(entry_nomedia_serve()==0&&response[0]==0x081a0005&&response[1]==0&&response[2]==0&&response[3]==1&&response[4]==0);for(unsigned i=5;i<8;i++)CK(response[i]==0);}CK(receives==4&&replies==4);}
 else if(!strcmp(s,"peer")){peer=14;CK(entry_nomedia_serve()==0&&replies==1&&response[0]==0x081a0002);for(unsigned i=1;i<8;i++)CK(!response[i]);}
 else if(!strcmp(s,"epochs")){U bad[]={6ull<<32|1,7ull<<32,7ull<<32|0x10000000,1};for(unsigned i=0;i<4;i++){epochs=bad[i];CK(entry_nomedia_serve()==0&&response[0]==0x081a0002);for(unsigned j=1;j<8;j++)CK(!response[j]);}CK(replies==4);}
 else if(!strcmp(s,"idle")){idle=1;for(unsigned i=0;i<100;i++)CK(entry_nomedia_serve()==0);CK(receives==100&&!replies);}
 else {CK(0);}CK(!unexpected&&entry_hid_preserved()==1);printf("entry NoMedia native checks passed %u; scenario=%s; receives=%u; replies=%u; no DMA/MMIO\n",(unsigned)checks,s,(unsigned)receives,(unsigned)replies);return 0;}
