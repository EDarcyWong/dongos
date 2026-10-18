#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct {U r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rdx,rcx,rbx,rax,rip,flags,rsp,root,fs,gs,status,calls,exit_code,reserved;} Frame;
typedef struct {U version,lease,owner,epoch,client,server,bytes,width,height,stride;} Lease;
typedef struct {U version,owner,epoch,role;} Peer;
typedef struct {U version,owner,epoch,client,server,bytes,pixels,scale,glyphs;} Font;
extern U ABI gui_setup(void),gui_cap(U,U),gui_invoke(U,Frame*,U*),gui_get(U,U),gui_request(U,U),gui_accept(U),gui_finish(U),gui_retire(U),gui_launch(U,U),gui_change(U,U,U),gui_scope(U,U,U),gui_fatal(U);
static unsigned checks,recording,fault_boot,fault_unshare,allocations,withdrawals,destroys,font_calls,attaches;
typedef struct {U kind,a,b,c,d;} Event;
static Event events[2048];static unsigned event_count;
typedef struct {U actor,base,size,write;} Span;
static Span spans[64];static unsigned span_count;
typedef struct {U source,client,server,pages;unsigned source_live,server_live;} Mapping;
static Mapping mappings[32];static unsigned mapping_count;
static void die(const char*why){fprintf(stderr,"GUI wiring ordering failed: %s\n",why);exit(1);}
#define C(x) do{++checks;if(!(x)){fprintf(stderr,"GUI wiring oracle line %u: %s\n",__LINE__,#x);exit(1);}}while(0)
void ABI __dong_panic(void){die("unexpected Dong panic");}
void ABI runtime_copy_bytes(void*out,const void*in,U bytes){memcpy(out,in,(size_t)bytes);}
static void allow(U actor,void*p,size_t bytes,unsigned write){C(span_count<64);spans[span_count++]=(Span){actor,(U)(uintptr_t)p,bytes,write};}
U ABI gui_validate(U actor,U address,U bytes,U write){
 if(address==0x70000000&&bytes==128)return 0;
 for(unsigned i=0;i<span_count;i++){Span*s=&spans[i];if(s->actor==actor&&(!write||s->write)&&address>=s->base&&bytes<=s->size&&address-s->base<=s->size-bytes)return 0;}
 return 1;
}
U ABI gui_event(U kind,U a,U b,U c,U d){
 if(!recording)return 0;
 C(event_count<2048);events[event_count++]=(Event){kind,a,b,c,d};
 if(kind==10&&a==13&&b==0x70000000&&fault_boot)return 1;
 if(kind==20){C(a>=7&&a<16&&a!=13&&b==3&&c>=0x74000000&&d>0&&d<=768);C(mapping_count<32);
  U server=0x78000000+(c-0x74000000);mappings[mapping_count++]=(Mapping){a,c,server,d,1,1};allocations++;
 }
 if(kind==21){withdrawals++;if(fault_unshare&&withdrawals==fault_unshare)return 1;
  unsigned found=0;for(unsigned i=0;i<mapping_count;i++){Mapping*m=&mappings[i];
   if(m->source==a&&m->client==b&&m->pages==c&&m->source_live){m->source_live=0;found=1;break;}
   if(a==3&&m->server==b&&m->pages==c&&m->server_live){m->server_live=0;found=1;break;}
  }if(!found)die("withdrawal did not use recorded exact aperture");
 }
 if(kind==22){for(unsigned i=0;i<mapping_count;i++){Mapping*m=&mappings[i];if((m->source==a||a==3)&&(m->source_live||m->server_live))die("destroy before both aliases withdrawn");}destroys++;}
 if(kind==23){C(a==7&&b==((UINT64_C(8)<<32)|1)&&c==1&&d==16);font_calls++;}
 if(kind==40){C(a==13&&b==((UINT64_C(14)<<32)|1)&&c==1);attaches++;}
 if(kind==41){C(a==13&&b==((UINT64_C(14)<<32)|1)&&c==1);}
 return 0;
}
U ABI gui_catalog_event(U kind,U a,U b){return gui_event(kind,a,b,0,0);}
static U invoke(unsigned actor,Frame*f){U next=99;return gui_invoke(actor,f,&next);}
static Frame frame(unsigned actor,U code){Frame f={0};f.rax=code;f.rdi=gui_cap(actor,0);return f;}
static void setup(void){C(gui_setup()==0);recording=1;}
static U request(unsigned caller,unsigned server){U ticket=gui_request(caller,server);C(ticket>UINT32_MAX);C(gui_accept(server)==ticket);return ticket;}
static int nonblock(void){
 setup();unsigned char output[80];memset(output,0xa5,sizeof output);allow(3,output,sizeof output,1);
 Frame f=frame(3,0x25);f.rsi=(U)(uintptr_t)output;f.rdx=(U)(uintptr_t)(output+64);
 C(invoke(3,&f)==0x05110005&&gui_get(0,3)==0);for(unsigned i=0;i<80;i++)C(output[i]==0xa5);
 U ticket=gui_request(7,3);C(ticket>UINT32_MAX);f=frame(3,0x25);f.rsi=(U)(uintptr_t)output;f.rdx=(U)(uintptr_t)(output+60);
 C(invoke(3,&f)!=0&&gui_get(0,3)==1);for(unsigned i=0;i<80;i++)C(output[i]==0xa5);
 f.rdx=(U)(uintptr_t)(output+78);C(invoke(3,&f)!=0&&gui_get(0,3)==1);for(unsigned i=0;i<80;i++)C(output[i]==0xa5);
 f.rdx=(U)(uintptr_t)(output+64);C(!invoke(3,&f)&&output[0]==0x51&&gui_get(0,3)==2);
 U copied;memcpy(&copied,output+64,8);C(copied==ticket);C(gui_finish(3)==0);return 0;
}
static U allocate(unsigned caller,Lease*out){
 U ticket=request(caller,3);Frame f=frame(3,0xa0);f.rsi=ticket;f.rdx=(UINT64_C(1)<<32)|0x100|(caller-6);
 f.r10=64|(UINT64_C(32)<<32);f.r8=256;f.r9=(U)(uintptr_t)out;C(!invoke(3,&f));C(gui_finish(3)==0);return out->lease;
}
static int windows_case(void){
 setup();Lease lease;memset(&lease,0xa5,sizeof lease);allow(3,&lease,sizeof lease,1);Peer peer;memset(&peer,0xa5,sizeof peer);allow(3,&peer,sizeof peer,1);Font font;allow(3,&font,sizeof font,1);
 U ticket=request(7,3);Frame f=frame(3,0xa0);f.rsi=ticket;f.rdx=(UINT64_C(1)<<32)|0x101;f.r10=64|(UINT64_C(32)<<32);f.r8=256;f.r9=1;
 C(invoke(3,&f)!=0&&!allocations&&!gui_get(3,0));
 f.r9=(U)(uintptr_t)&lease;f.rsi=ticket+1;C(invoke(3,&f)!=0&&!allocations);f.rsi=ticket;
 C(gui_change(1,7,2)==0);C(invoke(3,&f)!=0&&!allocations);C(gui_change(1,7,1)==0);
 C(gui_change(3,0,2)==0);C(invoke(3,&f)!=0&&!allocations);C(gui_change(3,0,1)==0);
 C(!invoke(3,&f)&&allocations==1&&lease.owner==((UINT64_C(8)<<32)|1)&&lease.epoch==1&&lease.bytes==8192);
 C(lease.client==0x74000000&&lease.server==0x78000000&&gui_get(3,0)==8192);
 f=frame(3,0xa3);f.rsi=ticket;f.rdx=(U)(uintptr_t)&peer;C(!invoke(3,&f)&&peer.owner==lease.owner&&peer.role==1&&peer.epoch==1);
 f=frame(3,0xa2);f.rsi=ticket;f.rdx=16;f.r10=1;C(invoke(3,&f)!=0&&!font_calls);f.r10=(U)(uintptr_t)&font;
 C(!invoke(3,&f)&&font_calls==1&&font.owner==lease.owner&&font.pixels==16);C(!gui_finish(3));
 f=frame(3,0xa1);f.rdx=lease.lease;C(!invoke(3,&f)&&withdrawals==2&&!gui_get(3,0));f.rax=0xa1;C(!invoke(3,&f)&&withdrawals==2);
 C(gui_change(2,7,1)==0);f=frame(3,0xa3);f.rdx=1;C(invoke(3,&f)!=0&&gui_get(4,7)==1);f.rdx=(U)(uintptr_t)&peer;
 C(!invoke(3,&f)&&peer.owner==lease.owner&&peer.role==0&&!gui_get(4,7));return 0;
}
static int roles(void){
 setup();for(unsigned caller=7;caller<=11;caller++){U ticket=request(caller,1);Frame f=frame(1,0x2d);f.rsi=ticket;C(!invoke(1,&f));
  U role=caller<=10?caller-6:0,scope=(role==2||role==3)?1:role==4?2:0;C(f.rax==((scope<<32)|role));C(!gui_finish(1));}
 C(gui_scope(7,1,0)==0&&gui_scope(7,1,1)!=0&&gui_scope(7,16,1)==0);
 C(gui_scope(3,13,0)==0&&gui_scope(3,13,1)!=0&&gui_scope(3,16,1)==0);
 C(!gui_change(5,14,0));C(gui_scope(14,16,1)!=0);
 C(gui_retire(7)==0);C(gui_launch(0,8)==0x208);C(gui_get(6,7)==8&&gui_get(7,7)==2);
 U ticket=request(7,1);Frame f=frame(1,0x2d);f.rsi=ticket;C(!invoke(1,&f)&&f.rax==0);C(gui_scope(7,16,1)!=0);C(!gui_finish(1));return 0;
}
static int teardown(unsigned failure){
 setup();Lease a,b;allow(3,&a,sizeof a,1);allow(3,&b,sizeof b,1);allocate(7,&a);
 if(!failure){allocate(8,&b);C(gui_retire(3)==0);C(withdrawals==4&&!gui_get(3,0)&&destroys>=3&&gui_get(5,3)==0&&gui_get(5,7)==0&&gui_get(5,8)==0);}
 else{fault_unshare=1;C(gui_retire(7)!=0&&withdrawals==1&&!destroys&&gui_get(8,0)&&gui_get(9,0));C(gui_get(5,7)==1&&gui_get(6,7)==14&&gui_get(3,0)==8192);C(gui_fatal(0x07430004)==16);}
 return 0;
}
static int teardown_server_fail(void){
 setup();Lease a;allow(3,&a,sizeof a,1);allocate(7,&a);fault_unshare=2;
 Frame f=frame(3,0xa1);f.rdx=a.lease;
 C(invoke(3,&f)==0x07430004&&withdrawals==2&&!destroys&&gui_get(8,0)&&gui_get(9,0));
 C(gui_get(3,0)==8192&&gui_get(5,7)==1&&gui_get(5,3)==1);
 C(!mappings[0].source_live&&mappings[0].server_live&&gui_fatal(0x07430004)==16);
 return 0;
}
static int launch_case(void){
 setup();fault_boot=1;C(gui_launch(6,13)==0x04060004);C(!gui_get(13,0)&&!attaches&&gui_get(5,13)==0&&gui_get(10,13)==0&&gui_get(12,13)==0);
 fault_boot=0;C(!gui_change(4,12,1));C(gui_launch(0,8)==0x10f);C(gui_get(6,14)==8&&gui_get(6,13)==UINT64_MAX&&gui_cap(14,4)==0);U token=gui_launch(6,13);C(token==0x10e&&gui_get(6,13)==13&&gui_get(13,0)==((UINT64_C(14)<<32)|1));
 unsigned seen_boot=0,seen_ro=0,seen_attach=0,seen_start=0,seen_commit=0;
 for(unsigned i=0;i<event_count;i++){Event*e=&events[i];if(e->a!=13)continue;if(e->kind==10)seen_boot=i+1;if(e->kind==11)seen_ro=i+1;if(e->kind==40)seen_attach=i+1;if(e->kind==33)seen_start=i+1;if(e->kind==32)seen_commit=i+1;}
 C(seen_boot<seen_ro&&seen_ro<seen_attach&&seen_attach<seen_start&&seen_start<seen_commit);
 Frame f=frame(13,0x67);f.rdi=gui_cap(13,4);C(!invoke(13,&f));f=frame(7,0x67);f.rdi=gui_cap(7,4);C(invoke(7,&f)!=0);
 return 0;
}
int main(int argc,char**argv){C(argc==2);if(!strcmp(argv[1],"nonblock"))nonblock();else if(!strcmp(argv[1],"windows"))windows_case();else if(!strcmp(argv[1],"roles"))roles();else if(!strcmp(argv[1],"teardown"))teardown(0);else if(!strcmp(argv[1],"teardown-fail"))teardown(1);else if(!strcmp(argv[1],"teardown-server-fail"))teardown_server_fail();else if(!strcmp(argv[1],"launch"))launch_case();else C(0);
 printf("GUI wiring checks passed %u; scenario=%s actual-service-fragments real-catalog-caps-ipc-broker\n",checks,argv[1]);return 0;}

void ABI fixture_boundary_fail(uint64_t code){fprintf(stderr,"unexpected unsupported fixture boundary %x\n",(unsigned)code);exit(3);}
