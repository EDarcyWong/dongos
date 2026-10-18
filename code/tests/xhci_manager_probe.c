// Reuse independent ledger/IRQ regressions and the legacy no-xHCI launcher.
#define svc_call legacy_svc_call
#define main legacy_main
#include "device_manager_probe.c"
#undef main
#undef svc_call
typedef struct {U version,id,dependencies,restarts,timeout,flags,image,length;unsigned char name[32];U reserved[4];} Config;
typedef struct {U version,configuration,process,generation,state,status,sequence,argument;} Snapshot;
static Device usb_hardware[6];static U usb_boot[16],usb_binds,usb_revokes,usb_yields,usb_ready,usb_config,usb_spawn,usb_logs;
static int usb_spawn_failure,usb_bad_config,usb_bad_binding,usb_catalog_failure,usb_legacy;
static U usb_token=270;static int usb_bad_token;
ABI U svc_call(U number,U a,U b,U c,U d,U e,U f){
 if(usb_legacy)return legacy_svc_call(number,a,b,c,d,e,f);
 if(number==2)return (U)(uintptr_t)usb_boot;
 if(number==0x86){CK(a==0x101&&!b&&!c&&!d&&!e&&!f);return 3;}
 if(number==0x84){CK(a==0x101&&b==3&&!c&&!d&&!e&&!f&&usb_binds==4);usb_ready++;return 0;}
 if(number==0x70){CK(a&&b&&b<=4096&&!c&&!d&&!e&&!f);usb_logs++;return 0;}
 if(number==3){CK(!a&&!b&&!c&&!d&&!e&&!f);usb_yields++;if(usb_revokes){CK(usb_ready==1&&usb_binds==4);return 0x051200ff;}return 0;}
 if(number==0x80){CK(a==0x888&&b==13&&c&&d&&!e&&!f&&usb_ready==1);usb_config++;Config v={0};v.version=1;v.id=13;v.dependencies=1<<6;v.flags=4;*(Config*)(uintptr_t)c=v;Snapshot s={1,13,0,0,0,0,0,0};if(usb_bad_config)s.configuration=14;*(Snapshot*)(uintptr_t)d=s;return 0;}
 if(number==0x81){CK(a==0x888&&b==13&&!c&&!d&&e&&!f&&usb_ready==1&&usb_config==1);usb_spawn++;if(usb_spawn_failure)return DENIED;Snapshot s={1,13,usb_token,1,1,0,0,0};*(Snapshot*)(uintptr_t)e=s;return 0;}
 CK(a==0x999);
 if(number==0x90){CK(b<=6&&c&&!d&&!e&&!f);if(usb_catalog_failure&&usb_ready)return REMOVED;Device v={0};v.version=1;if(b<6){v=usb_hardware[b];v.next=b+1;if(usb_ready&&b==5)v.flags|=4;}*(Device*)(uintptr_t)c=v;return 0;}
 if(number==0x91){CK(b>=257&&b<=262&&d&&!e&&!f);Binding v={1,b,c,c==1?2:c==4?13:4,1,c==3?((1<<1)|(1<<12)):0,2,0};CK((c==1&&b==258)||(c==2&&b==259)||(c==3&&b==260)||(c==4&&b==262));if(usb_bad_binding&&c==4)v.config=14;*(Binding*)(uintptr_t)d=v;usb_binds++;return 0;}
 if(number==0x95){CK((b==262||(usb_catalog_failure&&(b==258||b==259||b==260)))&&c==1&&!d&&!e&&!f);usb_revokes++;return 0;}
 CK(0);return INVALID;
}
int main(int argc,char**argv){CK(argc==2);if(!strcmp(argv[1],"absent")){usb_legacy=1;return legacy_main(1,argv);}
 usb_spawn_failure=!strcmp(argv[1],"spawn-failure");usb_bad_config=!strcmp(argv[1],"bad-config");usb_bad_binding=!strcmp(argv[1],"bad-binding");usb_catalog_failure=!strcmp(argv[1],"catalog-failure");
 if(!strcmp(argv[1],"bare-pid")){usb_token=14;usb_bad_token=1;}
 if(!strcmp(argv[1],"wrong-pid")){usb_token=271;usb_bad_token=1;}
 if(!strcmp(argv[1],"incarnation-overflow")){usb_token=UINT64_C(0x100000000e);usb_bad_token=1;}
 if(!strcmp(argv[1],"later-incarnation"))usb_token=(7<<8)|14;
 catalog();ranks();interrupts();usb_boot[0]=1;usb_boot[1]=7;usb_boot[2]=0x101;usb_boot[8]=0x999;usb_boot[12]=0x888;
 usb_hardware[0]=pci(0xe0000000,0x8086,1,0x010601);usb_hardware[1]=pci(0xe0001000,0x8086,2,0x010802);usb_hardware[2]=pci(0xe0002000,0x1af4,0x1052,0);usb_hardware[3]=ps2();usb_hardware[4]=pci(0xe0004000,0x8086,3,0x020000);usb_hardware[5]=pci(0xe0005000,0x1b36,0xd,0x0c0330);for(unsigned i=0;i<6;i++){usb_hardware[i].token=257+i;usb_hardware[i].generation=1;}
 U result=service_main();if(usb_bad_binding){CK(result==INVALID&&!usb_ready&&!usb_spawn&&usb_binds==4);}
 else {CK(result==(usb_catalog_failure?0x05120009:0x051200ff));CK(usb_ready==1&&usb_binds==4&&usb_config==1&&usb_spawn==(usb_bad_config?0:1));CK(usb_revokes==(usb_catalog_failure?4:1));CK(usb_yields==((usb_spawn_failure||usb_bad_config||usb_bad_token)?1:usb_catalog_failure?1024:1025));}
 printf("xHCI manager native checks passed %lu; scenario=%s; bindings=%lu; spawns=%lu; revocations=%lu\n",(unsigned long)checks,argv[1],(unsigned long)usb_binds,(unsigned long)usb_spawn,(unsigned long)usb_revokes);return 0;
}
