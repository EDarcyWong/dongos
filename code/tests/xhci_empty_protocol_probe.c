#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{U bar,bar_bytes,token,physical;unsigned char*pointer;U bytes,bits,epoch,hz,timeout,device,exclusive,interrupts_off,pci_command;} Setup;
typedef struct{U version,op,runtime,doorbells,ports,max_slots,slots,context_bytes,ac64,protocols[32];} Caps;
typedef ABI U(*Read)(U,U,U,uint32_t*);
typedef ABI U(*Write)(U,U,U,uint32_t);
typedef ABI U(*Fence)(U,U);
typedef ABI U(*Now)(U,U*);
typedef ABI U(*Enable)(U);
typedef struct{Read read;Write write;Fence fence;Now now;Enable enable;} Ops;
static unsigned checks,reads;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"XHCI_EMPTY_PROTOCOL_ASSERT line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
extern ABI U xhp_check(const Ops*,U,const Setup*,Caps*);
static uint32_t registers[4096];static unsigned char memory[131072+4095];
static ABI U read_reg(U context,U bar,U offset,uint32_t*out){CK(context==0x1234&&bar==0xaaaa&&out&&(offset&3)==0&&offset<sizeof(registers));reads++;*out=registers[offset/4];return 0;}
static ABI U write_reg(U context,U bar,U offset,uint32_t value){(void)context;(void)bar;(void)offset;(void)value;CK(0);return 1;}
static ABI U no_fence(U context,U phase){(void)context;(void)phase;CK(0);return 1;}
static ABI U no_time(U context,U*out){(void)context;(void)out;CK(0);return 1;}
static ABI U no_enable(U context){(void)context;CK(0);return 1;}
ABI void __dong_panic(void){CK(0);abort();}
static void fixture(unsigned p2,unsigned p3){memset(registers,0,sizeof(registers));
 const uint32_t captured[]={0x01000040,0x04001040,0x0000000f,0,0x00087001,0x00002000,0x00001000,0,0x02000402,0x20425355,0x00000401,0,0x03000002,0x20425355,0x00000001,0};
 memcpy(registers,captured,sizeof(captured));registers[1]=((p2+p3)<<24)|0x1040;registers[0x28/4]=(p2<<8)|(p3+1);registers[0x38/4]=(p3<<8)|1;registers[0x48/4]=1;}
int main(int argc,char**argv){CK(argc==2);unsigned scenario=(unsigned)atoi(argv[1]);CK(scenario<=19);unsigned p2=4,p3=0;if(scenario==1){p2=0;p3=4;}if(scenario==2){p2=4;p3=4;}if(scenario==3){p2=0;p3=0;}fixture(p2,p3);
 U expected=0;
 switch(scenario){
 case 3:expected=0x08110002;break;
 case 4:registers[0x30/4]=0x04000002;expected=0x08110002;break;
 case 5:registers[0x34/4]^=1;expected=0x08110002;break;
 case 6:registers[0x38/4]|=0x10000000;expected=0x08110002;break;
 case 7:registers[0x3c/4]=1;expected=0x08110002;break;
 case 8:registers[0x38/4]=0;expected=0x08110002;break;
 case 9:registers[0x38/4]=6;expected=0x08110002;break;
 case 10:registers[0x38/4]=5;break;
 case 11:registers[0x38/4]=0x105;expected=0x08110002;break;
 case 12:registers[0x38/4]=0x104;expected=0x08110001;break;
 case 13:registers[0x30/4]=0x03000102;registers[0x34/4]=0x20425355;expected=0x08110002;break;
 case 14:registers[0x3c/4]=0x80000000;expected=0x08110002;break;
 case 15:registers[0x30/4]=0x03000003;expected=0x08110002;break;
 case 16:registers[0x38/4]=0x5001;expected=0x08110002;break;
 case 17:registers[0x30/4]=0x0300ff02;expected=0x08110002;break;
 case 18:registers[0x38/4]=0x1001;expected=0x08110002;break;
 case 19:registers[0x28/4]=0x501;expected=0x08110002;break;
 default:break;
 }
 Setup s={0xaaaa,sizeof(registers),0xbbbb,0x200000,(unsigned char*)(((uintptr_t)memory+4095)&~(uintptr_t)4095),131072,48,7,1000000000,100,0xcccc,1,3,0x402};
 Ops ops={read_reg,write_reg,no_fence,no_time,no_enable};Caps out,before;memset(&out,0xa5,sizeof(out));before=out;
 U result=xhp_check(&ops,0x1234,&s,&out);CK(result==expected);
 if(expected)CK(!memcmp(&out,&before,sizeof(out)));
 else{CK(out.version==0x100&&out.op==0x40&&out.runtime==0x1000&&out.doorbells==0x2000&&out.ports==p2+p3&&out.max_slots==64&&out.slots==8&&out.context_bytes==32&&out.ac64==1);
  for(unsigned i=0;i<32;i++)CK(out.protocols[i]==(i<p3?3:i<p3+p2?2:0));
 }
 for(unsigned i=0;i<131072;i++)CK(s.pointer[i]==0);
 printf("XHCI_EMPTY_PROTOCOL_NATIVE_PASS checks=%u scenario=%u reads=%u\n",checks,scenario,reads);return 0;
}
