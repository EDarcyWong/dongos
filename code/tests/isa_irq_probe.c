// Reuse the established initialization hardware model, then independently
// model runtime redirection writes, ISO polarity/trigger and failed readbacks.
#define main fixture_original_main
#define irq_hw_read32 fixture_read32
#define irq_hw_write32 fixture_write32
#include "irq_platform_probe.c"
#undef main
#undef irq_hw_read32
#undef irq_hw_write32
typedef struct {uint64_t version,irq,gsi,controller,pin,vector,polarity,trigger,destination,masked;} Route;
extern ABI uint64_t isa_route(uint64_t,uint64_t,Route*),isa_mask(uint64_t,uint64_t),isa_describe(uint64_t,Route*),isa_eoi(void);
static uint64_t topology_runtime[307];
static unsigned runtime_mode,route_case,runtime_writes,high_writes,low_writes,unmasks,eois,initial_mask_readbacks;
static unsigned preflight_mask,high_verified,low_verified;
static uint32_t last_high,last_low;
ABI uint32_t irq_hw_read32(uint64_t address){
    if(!runtime_mode)return fixture_read32(address);
    if(address>=BASE+4096&&address<BASE+9*4096){unsigned index=(unsigned)((address-BASE)/4096)-1;CHECK(index<controllers&&(address&4095)==16);unsigned reg=selector[index];uint32_t value=io[index][reg];if(reg&1){if(high_writes&&value==last_high)high_verified=1;}else if(reg>=0x10){if(preflight_mask&&(value&0x10000))initial_mask_readbacks++;if(low_writes&&(value&0x1afff)==(last_low&0x1afff))low_verified=1;}return value;}
    return fixture_read32(address);
}
ABI void irq_hw_write32(uint64_t address,uint32_t value){
    if(!runtime_mode){fixture_write32(address,value);return;}
    runtime_writes++;
    if(address==BASE+0xb0){CHECK(value==0);eois++;return;}
    CHECK(address>=BASE+4096&&address<BASE+9*4096);unsigned index=(unsigned)((address-BASE)/4096)-1,off=(unsigned)(address&4095);CHECK(index<controllers);
    if(off==0){CHECK(value<256);selector[index]=value;return;}
    CHECK(off==16);unsigned reg=selector[index];CHECK(reg>=0x10);
    if(reg&1){CHECK(initial_mask_readbacks>0);CHECK((io[index][reg-1]&0x10000)!=0);high_writes++;last_high=value;io[index][reg]=value^(route_case==7?0x01000000:0);return;}
    low_writes++;last_low=value;
    if((value&0xff)==0x51||(value&0xff)==0x5c){
        if((value&0x10000)==0){CHECK(high_verified&&low_verified);unmasks++;if(route_case==9){io[index][reg]=value|0x10000;return;}}
        else if((io[index][reg]&0x10000)!=0&&high_writes)CHECK(high_verified||route_case==7);
    }else{CHECK(value==(io[index][reg]|0x10000));preflight_mask=1;}
    uint32_t read_only=io[index][reg]&0x5000;io[index][reg]=(value&~0x5000)|read_only;
    if(route_case==8&&high_writes&&(value&0xff)==0x51)io[index][reg]^=1;
    if(route_case==13&&(value&0x10000)==0)io[index][reg]^=1;
}
static void setup(void){scenario=0;controllers=2;topology_runtime[8]=0xfee00000;topology_runtime[10]=1;topology_runtime[11]=2;topology_runtime[46]=1;Views views={0};Report out;views.lapic=BASE;
    for(unsigned i=0;i<controllers;i++){topology_runtime[107+3*i]=i;topology_runtime[108+3*i]=0xfec00000+i*4096;topology_runtime[109+3*i]=i*24;views.ioapics[i]=BASE+(i+1)*4096;io[i][0]=i<<24;io[i][1]=23u<<16|0x11;wanted_ids[i]=i;initial_ids[i]=io[i][0];for(unsigned pin=0;pin<24;pin++)io[i][0x10+pin*2]=0x20+pin;}
    lapic[0x30/4]=max_lvt()<<16|0x14;CHECK(irq_model_init(topology_runtime,&views,&out)==0);runtime_mode=1;
}
int main(int argc,char**argv){CHECK(argc==2);route_case=(unsigned)atoi(argv[1]);CHECK(route_case<=14);setup();Route out,before;memset(&out,0xa5,sizeof out);before=out;uint64_t error=0;
    if(route_case>=1&&route_case<=5){topology_runtime[12]=1;topology_runtime[131]=0;topology_runtime[132]=1;topology_runtime[133]=30;topology_runtime[134]=15;}
    if(route_case==2)topology_runtime[134]=2;
    if(route_case==3)topology_runtime[133]=128;
    if(route_case==4){topology_runtime[12]=2;for(unsigned i=0;i<4;i++)topology_runtime[135+i]=topology_runtime[131+i];}
    if(route_case==5)topology_runtime[133]=12;
    if(route_case==6){topology_runtime[13]=1;topology_runtime[195]=3;topology_runtime[199]=1;}
    if(route_case==14){topology_runtime[12]=1;topology_runtime[132]=1;topology_runtime[133]=30;topology_runtime[134]=13;}
    if(route_case==12){unsigned writes=runtime_writes;CHECK(isa_route(2,0,&out)==0x03050008&&runtime_writes==writes);CHECK(!memcmp(&out,&before,sizeof out));puts("ISA route native scenario=12 passed");return 0;}
    error=isa_route(1,route_case==11||route_case==10,&out);
    if(route_case==2||route_case==3||route_case==4||route_case==6){CHECK(error==0x03050003&&low_writes==0&&high_writes==0&&!memcmp(&out,&before,sizeof out));}
    else if(route_case==7||route_case==8||route_case==9||route_case==13){CHECK(error==0x0305000a&&!memcmp(&out,&before,sizeof out));unsigned controller=route_case==7||route_case==8||route_case==9||route_case==13?0:1;CHECK((io[controller][0x10+2]&0x10000)!=0);}
    else{
        CHECK(error==0&&out.version==1&&out.irq==1&&out.vector==0x51&&out.destination==0);CHECK(out.masked==(route_case==11||route_case==10));
        CHECK(out.gsi==(route_case==1||route_case==14?30:route_case==5?12:1));
        CHECK(out.controller==(route_case==1||route_case==14?1:0));
        CHECK(out.polarity==(route_case==1||route_case==5));CHECK(out.trigger==(route_case==1||route_case==5||route_case==14));
        if(route_case==10){io[out.controller][0x11+out.pin*2]^=0x01000000;CHECK(isa_mask(1,0)==0x0305000a);CHECK(io[out.controller][0x10+out.pin*2]&0x10000);}
        else{
            if(route_case==11)io[out.controller][0x10+out.pin*2]|=0x5000;
            CHECK(isa_mask(1,1)==0);CHECK(isa_describe(1,&out)==0&&out.masked==1);CHECK(isa_mask(1,0)==0);CHECK(isa_describe(1,&out)==0&&out.masked==0);
            Route second;uint64_t got=isa_route(12,1,&second);CHECK(got==(route_case==5?0x03050009:0));if(!got)CHECK(second.vector==0x5c&&second.gsi==12&&second.masked==1);
            CHECK(isa_eoi()==0&&eois==1);
        }
    }
    printf("ISA route native scenario=%u passed; writes=%u; high=%u; low=%u; unmasks=%u; EOI=%u\n",route_case,runtime_writes,high_writes,low_writes,unmasks,eois);return 0;
}
