// Independent physical controller consumes actual command and transfer DMA.
// Reuse bootstrap MMIO reset/NoOp model only; runtime commands/USB TDs below
// inspect wire bytes and maintain independent hardware dequeue/cycle state.
#include "xhci_transport_controller_model.h"
typedef struct {U usb,vendor,product,release,class_code,subclass,protocol,packet,configurations,manufacturer,product_string,serial;} XDevice;
typedef struct {U kind,interface_number,in_address,out_address,in_packet,out_packet,interval,report_bytes;} XBinding;
typedef struct {U value,attributes,power_ma,count;XBinding bindings[8];} XConfig;
typedef struct {U physical;unsigned char*pointer;U bytes;} XBuffer;
typedef struct {U region_physical,region_bytes,bits,physical;unsigned char*pointer;U dcbaa_physical;U*dcbaa;U context_bytes,port,epoch,hz,timeout;} XEnumSetup;
typedef struct {U held,ready,fault,busy,phase,slot,speed,packet,last_tsc;const void*ops;U context;XEnumSetup setup;XConfig configuration;XDevice device;Producer ep0,input,output;} XEnum;
typedef struct {U held,ready,fault,busy,epoch,token,physical;unsigned char*pointer;U bytes,last_tsc;CState*controller;U slots[9],ports[9],bases[9],stalled[9];Plan plan;U commands,transfers,shorts;} XTransport;
typedef struct {U connected,speed;} XPort;
typedef ABI U(*XReset)(U,U,U,XPort*);typedef ABI U(*XCommand)(U,const Command*,U,U*);typedef ABI U(*XControl)(U,U,Producer*,const ControlPlan*,const XBuffer*,U,U*);typedef ABI U(*XBulk)(U,U,U,Producer*,const XBuffer*,U,U*);typedef ABI U(*XRecover)(U,U,U,Producer*,U);typedef ABI U(*XNow)(U,U*);typedef ABI U(*XFence)(U);
typedef struct {XReset reset;XCommand command;XControl control;XBulk bulk;XRecover recover;XNow now;XFence fence;} XOps;
_Static_assert(sizeof(XTransport)==720&&sizeof(XEnum)==1784&&sizeof(XEnumSetup)==96,"runtime ABI");
extern ABI U xt_init(XTransport*,CState*),xt_ops(void),xt_enum(XEnum*,XTransport*,const XEnumSetup*),xt_control(XTransport*,U,Producer*,const Control*,const XBuffer*,U,U*);
extern ABI U xt_port(XTransport*,U,XPort*);
static U xchecks;
#undef CK
#define CK(x) do{xchecks++;if(!(x)){fprintf(stderr,"xHCI transport check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct {U physical,index,cycle,ready;} XEndpoint;
typedef struct {Hardware h;XTransport transport;XEnum enumeration;XEnumSetup setup;XEndpoint ep[9][32];U port,speed,packet,kind,slot,reset_polls,resets,commands,controls,evaluates,configured,protocol,idle,acks,doorbells,context_fences,report_reads;int resetting,short_once,missing_status,inject;const char*scenario;unsigned char descriptor[256];} XHardware;
static U xu64(const unsigned char*p){U value;memcpy(&value,p,8);return value;}
static uint32_t xu32(const unsigned char*p){uint32_t value;memcpy(&value,p,4);return value;}
static unsigned char*xpa(XHardware*x,U physical,U bytes){CK(physical>=x->h.setup.physical&&physical-x->h.setup.physical<=131072&&bytes<=131072-(physical-x->h.setup.physical));return x->h.dma+(physical-x->h.setup.physical);}
static U xport_offset(XHardware*x){return x->h.state.caps.op+0x400+(x->port-1)*16;}
static void xpost(XHardware*x,U parameter,U kind,U slot,U endpoint,U code,U residual){Hardware*h=&x->h;Trb t={parameter,(uint32_t)((code<<24)|residual),(uint32_t)((kind<<10)|(slot<<24)|(endpoint<<16)|h->event_cycle)};store(h->dma+8192,h->event_tail,t);h->event_tail++;if(h->event_tail==256){h->event_tail=0;h->event_cycle^=1;}h->registers[0x44/4]|=8;}
static unsigned xconfiguration(XHardware*x,unsigned char*p){unsigned char c[]={9,2,34,0,1,1,0,0xa0,50,9,4,0,0,1,3,1,1,0,9,33,0x11,1,0,1,34,63,0,7,5,0x81,3,8,0,10};memcpy(p,c,sizeof c);unsigned n=sizeof c;if(x->speed>=3)p[33]=7;if(x->speed==4){unsigned char s[]={6,48,0,0,8,0};memcpy(p+n,s,sizeof s);n+=sizeof s;p[2]=(unsigned char)n;}return n;}
static Trb xfetch(XHardware*x,XEndpoint*e,U*physical){for(unsigned n=0;n<2;n++){Trb t=load(xpa(x,e->physical,4096),e->index);CK((t.control&1)==e->cycle);if(((t.control>>10)&63)==6){CK(e->index==255&&t.parameter==e->physical&&(t.control&2));e->index=0;e->cycle^=1;continue;}*physical=e->physical+e->index*16;e->index++;return t;}CK(0);return (Trb){0};}
static void xcommand(XHardware*x){Hardware*h=&x->h;XEndpoint command={h->setup.physical+4096,h->hw_head,h->hw_cycle,1};U physical;Trb t=xfetch(x,&command,&physical);h->hw_head=command.index;h->hw_cycle=command.cycle;U kind=(t.control>>10)&63,slot=t.control>>24;x->commands++;CK(!t.status&&kind>=9&&kind<=23);
 if(kind==9){CK(!slot&&!t.parameter);slot=1;CK(!x->slot);x->slot=1;}
 else if(kind==23){CK(!slot&&!t.parameter);}
 else {CK(slot==1&&x->slot==1&&t.parameter==x->setup.physical);unsigned char*p=xpa(x,t.parameter,2112);U cb=h->state.caps.context_bytes,flags=xu32(p+4);CK(!xu32(p));if(kind==11){CK(flags==3&&x->setup.dcbaa[1]==x->setup.physical+4096);CK(xu32(p+cb)==((x->speed<<20)|(1u<<27))&&xu32(p+cb+4)==x->port<<16);CK(xu64(p+2*cb+8)==x->setup.physical+8193);memcpy(xpa(x,x->setup.physical+4096,2*cb),p+cb,2*cb);x->ep[1][1]=(XEndpoint){x->setup.physical+8192,0,1,1};}
  else if(kind==13){CK(flags==2&&x->speed==1&&(xu32(p+2*cb+4)>>16)==64);x->evaluates++;}
  else {CK(kind==12&&flags==9&&x->configured==1);CK(xu64(p+4*cb+8)==x->setup.physical+12289);CK((xu32(p+4*cb+4)>>16)==8);x->ep[1][3]=(XEndpoint){x->setup.physical+12288,0,1,1};}}
 if(!strcmp(x->scenario,"command-timeout")&&kind==9)return;
 if(!strcmp(x->scenario,"command-pointer")&&kind==9)physical+=16;
 if(!strcmp(x->scenario,"command-slot")&&kind==11)slot=2;
 xpost(x,physical,33,slot,0,1,0);
}
static void xtransfer(XHardware*x,U slot,U endpoint){CK(slot==1&&x->slot==1&&endpoint<32&&x->ep[slot][endpoint].ready);XEndpoint*r=&x->ep[slot][endpoint];U first,second=0,last;Trb setup=xfetch(x,r,&first),data={0},status={0};U kind=(setup.control>>10)&63;
 if(endpoint!=1){CK(endpoint==3&&kind==1&&(setup.control&32)&&(setup.control&4)&&setup.status==8);unsigned char report[]={2,0,4,0,0,0,0,0};memcpy(xpa(x,setup.parameter,8),report,8);x->report_reads++;xpost(x,first,32,slot,endpoint,1,0);return;}
 CK(kind==2&&setup.status==8&&(setup.control&64));U type=setup.parameter&255,request=(setup.parameter>>8)&255,value=(setup.parameter>>16)&65535,index=(setup.parameter>>32)&65535,length=setup.parameter>>48;
 if(length){data=xfetch(x,r,&second);CK(((data.control>>10)&63)==3&&data.status==length&&((data.control>>16)&1)==(type>>7));}
 status=xfetch(x,r,&last);CK(((status.control>>10)&63)==4&&status.parameter==0&&status.status==0&&(status.control&32));CK(((status.control>>16)&1)==(!length||!(type&128)));x->controls++;U actual=length;
 if(type==128&&request==6){CK(index==0);if(value==0x100){unsigned char d[]={18,1,0,2,0,0,0,64,0x27,6,1,0,0,1,1,2,3,1};CK(length==8||length==18);d[7]=(unsigned char)x->packet;if(x->speed==4){d[3]=3;d[7]=9;}memcpy(xpa(x,data.parameter,length),d,length);}else{CK(value==0x200);unsigned count=xconfiguration(x,x->descriptor);CK(length==9||length==count);memcpy(xpa(x,data.parameter,length),x->descriptor,length);}}
 else if(type==0&&request==9){CK(value==1&&index==0&&length==0);x->configured++;}
 else if(type==0x21&&request==11){CK(!value&&!index&&!length&&x->configured);x->protocol++;}
 else {CK(type==0x21&&request==10&&!value&&!index&&!length&&x->protocol);x->idle++;}
 if(x->short_once){CK(length==8);actual=4;x->short_once=0;xpost(x,second,32,slot,endpoint,13,length-actual);}
 if(!strcmp(x->scenario,"transfer-pointer")&&x->controls==1)last+=16;
 if(!x->missing_status)xpost(x,last,32,slot,endpoint,1,0);
}
static ABI U xread(U context,U handle,U offset,uint32_t*out){XHardware*x=(XHardware*)(uintptr_t)context;if(!x->transport.held)return read_register(context,handle,offset,out);CK(handle==0x123&&!(offset&3)&&offset<0x4000&&out);
 if(offset==xport_offset(x)&&x->resetting){x->reset_polls++;if(x->reset_polls>=3&&strcmp(x->scenario,"reset-timeout")){U completed=x->speed==4?1<<19:1<<21;x->h.registers[offset/4]=(uint32_t)((x->speed<<10)|0x203|completed);x->resetting=0;xpost(x,x->port<<24,34,0,0,1,0);}}
 *out=x->h.registers[offset/4];return 0;}
static ABI U xwrite(U context,U handle,U offset,uint32_t value){XHardware*x=(XHardware*)(uintptr_t)context;Hardware*h=&x->h;if(!x->transport.held)return write_register(context,handle,offset,value);CK(handle==0x123&&!(offset&3)&&offset<0x4000);
 if(offset>=0x2000&&offset<=0x2020){CK(h->fences[2]==x->doorbells+2);x->doorbells++;U slot=(offset-0x2000)/4;if(!slot){CK(!value);xcommand(x);}else xtransfer(x,slot,value);return 0;}
 if(offset==xport_offset(x)){CK(!(value&2)&&!(value&~0x8efec210u));if(value&(16u|0x80000000u)){CK((value&(16u|0x80000000u))==(x->speed==4?0x80000000u:16u));x->resetting=1;x->reset_polls=0;x->resets++;h->registers[offset/4]=(h->registers[offset/4]&~2u)|(value&(16u|0x80000000u));}else {h->registers[offset/4]&=~(value&0xfe0000u);h->registers[offset/4]=(h->registers[offset/4]&~0x0e00c200u)|(value&0x0e00c200u);}return 0;}
 if(offset==0x1038){CK((value&15)==8);CK((value&~15u)==h->setup.physical+8192+((x->acks+1)%256)*16);h->registers[offset/4]=value&~8u;h->last_low=offset;return 0;}
 if(offset==0x103c){CK(h->last_low==0x1038&&value==(h->setup.physical>>32));h->last_low=UINT64_MAX;h->registers[offset/4]=value;x->acks++;return 0;}
 if(offset==0x1020){CK(value==1&&x->acks==h->state.events.consumed);h->registers[offset/4]=0;return 0;}
 if(offset==0x44){CK(value==8);h->registers[offset/4]&=~8u;return 0;}
 CK(0);return 1;
}
static ABI U xfence(U context,U phase){XHardware*x=(XHardware*)(uintptr_t)context;if(!x->transport.held)return memory_fence(context,phase);CK(phase>=1&&phase<=4);x->h.fences[phase]++;if(phase==2)CK(x->h.fences[1]==x->h.fences[2]);if(phase==4)x->context_fences++;return 0;}
static XHardware*xhardware(const char*scenario){XHardware*x=calloc(1,sizeof *x);CK(x);initialize_hardware(&x->h,0);x->scenario=scenario;x->speed=!strcmp(scenario,"high-speed")?3:!strcmp(scenario,"superspeed")?4:1;x->packet=x->speed==1?64:x->speed==3?64:512;x->port=x->speed==4?5:3;x->kind=1;x->h.ops.read=xread;x->h.ops.write=xwrite;x->h.ops.fence=xfence;CK(xhc_initialize(&x->h.state,&x->h.ops,(U)(uintptr_t)x,&x->h.setup)==0);x->acks=1;x->h.registers[xport_offset(x)/4]=(uint32_t)((x->speed<<10)|0x201);CK(xt_init(&x->transport,&x->h.state)==0);CK(xhc_noop(&x->h.state)==0x08110007);x->setup=(XEnumSetup){x->h.setup.physical,131072,40,x->h.setup.physical+16384,x->h.dma+16384,x->h.setup.physical,(U*)x->h.dma,x->h.state.caps.context_bytes,x->port,x->h.setup.epoch,1000000,1000};return x;}
int main(int argc,char**argv){CK(argc==2);XHardware*x=xhardware(argv[1]);U result=xt_enum(&x->enumeration,&x->transport,&x->setup);int expected=!strcmp(argv[1],"reset-timeout")||!strcmp(argv[1],"command-timeout")||!strcmp(argv[1],"command-pointer")||!strcmp(argv[1],"command-slot")||!strcmp(argv[1],"transfer-pointer");
 if(expected){CK(result!=0&&!x->enumeration.ready&&x->enumeration.held&&x->transport.held&&x->transport.fault&&!x->transport.ready&&x->h.state.info.held);}
 else {if(result)fprintf(stderr,"transport enum error=%lx scenario=%s\n",(unsigned long)result,argv[1]);CK(result==0);CK(x->enumeration.ready&&x->enumeration.slot==1&&x->enumeration.packet==x->packet&&x->configured==1&&x->protocol==1&&x->idle==1&&x->transport.held&&!x->transport.fault);CK(x->evaluates==(x->speed==1));
  XPort port={9,9};CK(xt_port(&x->transport,x->port,&port)==0&&port.connected==1&&port.speed==x->speed);CK(xt_port(&x->transport,x->port==1?2:1,&port)==0&&!port.connected&&!port.speed);CK(xt_port(&x->transport,0,&port)!=0&&xt_port(&x->transport,9,&port)!=0&&!x->transport.fault);
  XBuffer b={x->setup.physical+20480,x->setup.pointer+20480,8};Control request={128,6,0x100,0,8,b.physical};U actual=UINT64_MAX;
  if(!strcmp(argv[1],"short-data")||!strcmp(argv[1],"missing-status")){x->short_once=1;x->missing_status=!strcmp(argv[1],"missing-status");result=xt_control(&x->transport,1,&x->enumeration.ep0,&request,&b,x->h.clock+100000,&actual);if(x->missing_status)CK(result!=0&&actual==UINT64_MAX&&x->transport.fault&&x->transport.held&&x->enumeration.ep0.pending==1);else CK(result==0&&actual==4&&!x->enumeration.ep0.pending&&x->transport.shorts==1);}
  else if(!strcmp(argv[1],"buffer-alias")){U before=x->controls;b.pointer++;CK(xt_control(&x->transport,1,&x->enumeration.ep0,&request,&b,x->h.clock+100000,&actual)!=0&&actual==UINT64_MAX&&x->controls==before&&!x->transport.fault);}
  else if(!strcmp(argv[1],"ring-alias")){U before=x->controls;x->enumeration.ep0.pointer++;CK(xt_control(&x->transport,1,&x->enumeration.ep0,&request,&b,x->h.clock+100000,&actual)!=0&&actual==UINT64_MAX&&x->controls==before&&!x->transport.fault);}
  else if(!strcmp(argv[1],"wrap")){for(unsigned n=0;n<300;n++){CK(xt_control(&x->transport,1,&x->enumeration.ep0,&request,&b,x->h.clock+100000,&actual)==0&&actual==8);}CK(x->h.event_tail<100&&x->h.state.events.cycle==0&&x->enumeration.ep0.generation>300);}
  else {XOps*ops=(XOps*)(uintptr_t)xt_ops();XBuffer report={x->setup.physical+28672,x->setup.pointer+28672,8};actual=UINT64_MAX;CK(ops->bulk((U)(uintptr_t)&x->transport,1,0x81,&x->enumeration.input,&report,x->h.clock+100000,&actual)==0&&actual==8&&report.pointer[0]==2&&report.pointer[2]==4);CK(x->report_reads==1);}
 }
 printf("xHCI transport native checks passed %lu; scenario=%s; commands=%lu; controls=%lu; events=%lu; held=%lu\n",(unsigned long)xchecks,argv[1],(unsigned long)x->commands,(unsigned long)x->controls,(unsigned long)x->h.state.events.consumed,(unsigned long)x->transport.held);return 0;
}
