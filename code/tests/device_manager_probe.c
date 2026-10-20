#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#define ABI __attribute__((sysv_abi))
#else
#define ABI
#endif
typedef uint64_t U;
typedef struct {U version,token,next,kind,ecam,segment,bus,device,function,vendor,id,class_code,header,flags,generation,reserved;} Device;
typedef struct {U version,device,role,config,generation,irqmask,flags,reserved;} Binding;
typedef struct {U version,token,irq,gsi,vector,generation,sequence,flags;} Irq;
typedef struct {Irq view;U owner,device,live,serial;} IrqState;
typedef struct {U ready,count;Device devices[32];Binding bindings[4];IrqState interrupts[2];} Table;
_Static_assert(sizeof(Device)==128,"Device");_Static_assert(sizeof(Binding)==64,"Binding");_Static_assert(sizeof(Irq)==64,"Irq");_Static_assert(sizeof(Table)==4560,"Table");
extern ABI U dm_init(Table*),dm_register(Table*,const Device*,Device*),dm_enum(const Table*,U,Device*),dm_bind(Table*,U,const Device*,U,Binding*),dm_binding(const Table*,U,Binding*),dm_revoke(Table*,U,U),dm_rank(const Device*,U);
extern ABI U dm_irq_bind(Table*,U,U,U,U,Irq*),dm_signal(Table*,U,Irq*,U*),dm_poll(const Table*,U,U,U,Irq*),dm_ack(Table*,U,U,U),dm_ack_valid(const Table*,U,U,U),dm_irq_revoke(Table*,U);
extern ABI U service_main(void);
static U checks;
#define CK(x) do{++checks;if(!(x)){fprintf(stderr,"device manager check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static const U INVALID=0x05120001,DENIED=0x05120002,BUSY=0x05120003,STALE=0x05120004,CAPACITY=0x05120005,BLOCKED=0x05120006,REMOVED=0x05120008;
static Device pci(U ecam,U vendor,U id,U class_code){Device d={0};d.version=1;d.kind=1;d.ecam=ecam;d.vendor=vendor;d.id=id;d.class_code=class_code;return d;}
static Device ps2(void){Device d={0};d.version=1;d.kind=2;return d;}
static void catalog(void){Table t={0},before;Device out,old,d=pci(0xe0000000,0x8086,1,0x010802);Binding b,poison;memset(&out,0xa7,sizeof out);old=out;CK(dm_register(&t,&d,&out)==INVALID&&!memcmp(&out,&old,sizeof out));CK(dm_init(&t)==0);CK(dm_init(&t)==INVALID);for(unsigned i=0;i<32;i++){Device v=d;v.ecam+=i*4096;CK(dm_register(&t,&v,&out)==0&&out.token==257+i&&out.generation==1);CK(dm_register(&t,&v,&out)==0&&out.token==257+i);}before=t;Device v=d;v.ecam+=32*4096;CK(dm_register(&t,&v,&out)==CAPACITY&&!memcmp(&before,&t,sizeof t));for(U i=0;i<32;i++){CK(dm_enum(&t,i,&out)==0&&out.token==257+i&&out.next==i+1);}CK(dm_enum(&t,32,&out)==0&&out.kind==0&&out.token==0);memset(&out,0x5a,sizeof out);old=out;CK(dm_enum(&t,33,&out)==INVALID&&!memcmp(&old,&out,sizeof out));memset(&b,0xa5,sizeof b);poison=b;for(unsigned bit=0;bit<64;bit++){v=d;v.vendor^=UINT64_C(1)<<bit;before=t;U result=dm_bind(&t,257,&v,1,&b);CK(result==(v.vendor==0||v.vendor>=65535?INVALID:REMOVED));CK(!memcmp(&before,&t,sizeof t)&&!memcmp(&b,&poison,sizeof b));}v=d;v.class_code=0x010601;CK(dm_bind(&t,257,&v,1,&b)==REMOVED);CK(dm_bind(&t,257,&d,2,&b)==DENIED);CK(dm_bind(&t,257,&d,1,&b)==0&&b.config==2&&b.flags==2);before=t;CK(dm_bind(&t,258,&d,1,&b)==REMOVED);d.ecam+=4096;CK(dm_bind(&t,258,&d,1,&b)==BUSY&&!memcmp(&t,&before,sizeof t));CK(dm_revoke(&t,257,2)==STALE);CK(dm_revoke(&t,257,1)==0);CK(dm_binding(&t,1,&b)==STALE);CK(dm_revoke(&t,257,1)==STALE);d.ecam-=4096;CK(dm_register(&t,&d,&out)==REMOVED);}
static void ranks(void){Device d=pci(0xe0000000,0x1af4,0x1042,0);CK(dm_rank(&d,1)==3);d.id=0x1052;CK(dm_rank(&d,2)==1&&dm_rank(&d,1)==0);d.vendor=0x8086;d.id=1;for(U cl=0;cl<0x1000000;cl+=257){d.class_code=cl;U expected=cl==0x010802?2:cl==0x010601?1:0;CK(dm_rank(&d,1)==expected);}d.class_code=0x010802;for(U h=0;h<256;h++){d.header=h;CK(dm_rank(&d,1)==((h&127)?0:2));}d=ps2();CK(dm_rank(&d,3)==1&&dm_rank(&d,1)==0);}
static void interrupts(void){Table t={0};Device d=ps2(),view;Binding b;Irq q,out,poison;U owner=0;CK(dm_init(&t)==0);CK(dm_register(&t,&d,&view)==0);CK(dm_bind(&t,view.token,&d,3,&b)==0&&b.irqmask==((1<<1)|(1<<12)));CK(dm_irq_bind(&t,5,7,1,1,&q)==0&&q.token==257&&q.vector==0x51&&q.generation==7);CK(dm_irq_bind(&t,5,7,1,1,&q)==BUSY);memset(&out,0xa5,sizeof out);poison=out;CK(dm_poll(&t,257,5,0,&out)==BLOCKED&&!memcmp(&out,&poison,sizeof out));for(U n=1;n<=1024;n++){CK(dm_signal(&t,0x51,&out,&owner)==0&&owner==5&&out.sequence==n&&out.flags==3);CK(dm_signal(&t,0x51,&out,&owner)==BUSY);CK(dm_poll(&t,257,4,n-1,&out)==STALE);CK(dm_poll(&t,257,5,n-1,&out)==0&&out.sequence==n);Table before=t;CK(dm_ack(&t,257,5,n+1)==STALE&&!memcmp(&t,&before,sizeof t));CK(dm_ack_valid(&t,257,5,n)==0);CK(dm_ack(&t,257,5,n)==0);CK(dm_ack(&t,257,5,n)==STALE);}CK(dm_irq_revoke(&t,5)==0);CK(dm_poll(&t,257,5,1024,&out)==STALE);CK(dm_irq_bind(&t,5,8,1,1,&q)==0&&q.token==513&&q.generation==8);CK(dm_signal(&t,0x51,&out,&owner)==0&&out.sequence==1);CK(dm_ack(&t,257,5,1)==STALE);CK(dm_irq_bind(&t,5,8,12,12,&q)==0&&q.token==258&&q.vector==0x5c);CK(dm_revoke(&t,view.token,1)==0);CK(dm_poll(&t,513,5,0,&out)==STALE&&dm_signal(&t,0x5c,&out,&owner)==STALE);}
typedef U (ABI *RecoveryStep)(U,U,U);
typedef U (ABI *RecoveryRead)(U,Device*);
typedef struct {RecoveryStep stop,quiesce,retire,reclaim;RecoveryRead read;} RecoveryOps;
extern ABI U dm_recover(Table*,U,U,const RecoveryOps*,U,Device*);
static Table *recovery_table;
static Device recovery_hardware;
static U recovery_token,recovery_generation,recovery_calls,recovery_fail,recovery_reentry,recovery_stops;
static RecoveryOps recovery_ops;
static ABI U recovery_step(U context,U token,U generation,U stage){
    CK(context==0xcafe&&token==recovery_token&&generation==recovery_generation);
    CK(recovery_stops==1&&++recovery_calls==stage);
    CK(recovery_table->devices[(token&255)-1].flags&8);
    if(recovery_reentry){Device ignored;CK(dm_recover(recovery_table,token,generation,&recovery_ops,context,&ignored)==BUSY);}
    return recovery_fail==stage?1:0;
}
static ABI U stop_owner(U c,U t,U g){
    CK(c==0xcafe&&t==recovery_token&&g==recovery_generation&&recovery_calls==0);
    CK(++recovery_stops==1&&(recovery_table->devices[(t&255)-1].flags&8));
    Device ignored;CK(dm_recover(recovery_table,t,g,&recovery_ops,c,&ignored)==BUSY);
    return recovery_fail==7?1:0;
}
static ABI U quiesce(U c,U t,U g){return recovery_step(c,t,g,1);}
static ABI U retire(U c,U t,U g){return recovery_step(c,t,g,2);}
static ABI U reclaim(U c,U t,U g){return recovery_step(c,t,g,3);}
static ABI U recovery_read(U c,Device *out){
    CK(c==0xcafe&&++recovery_calls==4);
    CK(recovery_table->devices[(recovery_token&255)-1].flags&8);
    if(recovery_reentry){Device ignored;CK(dm_recover(recovery_table,recovery_token,recovery_generation,&recovery_ops,c,&ignored)==BUSY);}
    *out=recovery_hardware;return recovery_fail==4?1:0;
}
static void recovery(void){
    recovery_ops=(RecoveryOps){stop_owner,quiesce,retire,reclaim,recovery_read};
    for(U fail=0;fail<=7;fail++){
        Table t={0},before;Device d=ps2(),v,out,poison;Binding b;Irq irq;
        recovery_table=&t;recovery_hardware=d;recovery_calls=0;recovery_stops=0;recovery_fail=fail;recovery_reentry=1;
        CK(dm_init(&t)==0&&dm_register(&t,&d,&v)==0&&dm_bind(&t,v.token,&d,3,&b)==0);
        CK(dm_irq_bind(&t,5,1,1,1,&irq)==0&&irq.token==257);
        recovery_token=v.token;recovery_generation=2;
        memset(&out,0xa5,sizeof out);poison=out;before=t;
        CK(dm_recover(&t,v.token,2,&recovery_ops,0xcafe,&out)==STALE&&!memcmp(&t,&before,sizeof t));
        CK(dm_revoke(&t,v.token,1)==0);before=t;
        CK(dm_recover(&t,v.token,1,&recovery_ops,0xcafe,&out)==STALE&&!memcmp(&t,&before,sizeof t));
        CK(dm_recover(&t,v.token,2,NULL,0xcafe,&out)==INVALID&&!memcmp(&t,&before,sizeof t));
        CK(dm_recover(&t,v.token,2,&recovery_ops,0xcafe,NULL)==INVALID&&!memcmp(&t,&before,sizeof t));
        CK(recovery_calls==0&&!memcmp(&out,&poison,sizeof out));
        if(fail==5)recovery_hardware= pci(0xe0000000,0x8086,1,0x010802);
        if(fail==6)recovery_hardware.token=257;
        U result=dm_recover(&t,v.token,2,&recovery_ops,0xcafe,&out);
        if(fail){
            CK(result==(fail<=4||fail==7?UINT64_C(0x05120009):fail==5?REMOVED:INVALID));
            CK(recovery_calls==(fail==7?0:fail<=4?fail:4));
            CK(!memcmp(&out,&poison,sizeof out)&&t.devices[0].token==257&&t.devices[0].generation==2);
            CK(t.devices[0].flags==(before.devices[0].flags|8));
            before.devices[0].flags|=8;CK(!memcmp(&t,&before,sizeof t));
            U calls=recovery_calls;CK(dm_recover(&t,257,2,&recovery_ops,0xcafe,&out)==BUSY&&recovery_calls==calls);
            CK(dm_bind(&t,257,&d,3,&b)==STALE&&dm_bind(&t,513,&d,3,&b)==STALE);
        }else{
            CK(result==0&&recovery_calls==4&&out.token==513&&out.generation==2&&out.flags==1);
            CK(dm_bind(&t,257,&d,3,&b)==STALE&&dm_ack(&t,257,5,1)==STALE);
            CK(dm_bind(&t,513,&d,3,&b)==0&&dm_irq_bind(&t,6,2,1,1,&irq)==0&&irq.token==513);
            CK(dm_irq_bind(&t,6,2,1,1,&irq)==BUSY);
            for(U generation=3;generation<66;generation++){
                U old=t.devices[0].token;CK(dm_revoke(&t,old,generation-1)==0);
                recovery_token=old;recovery_generation=generation;recovery_calls=0;recovery_stops=0;
                CK(dm_recover(&t,old,generation,&recovery_ops,0xcafe,&out)==0&&out.token==(generation<<8|1));
                CK(dm_bind(&t,old,&d,3,&b)==STALE&&dm_bind(&t,out.token,&d,3,&b)==0);
            }
        }
    }
    // PCI block recovery uses the same transaction, never auto-binds a role.
    for(U fail=0;fail<=4;fail++){
        Table p={0};Device d=pci(0xe0000000,0x8086,1,0x010802),v,out;Binding b;
        recovery_table=&p;recovery_hardware=d;recovery_calls=0;recovery_stops=0;recovery_fail=fail;recovery_reentry=1;
        CK(dm_init(&p)==0&&dm_register(&p,&d,&v)==0&&dm_bind(&p,v.token,&d,1,&b)==0);
        recovery_token=v.token;recovery_generation=2;CK(dm_revoke(&p,v.token,1)==0);
        U result=dm_recover(&p,v.token,2,&recovery_ops,0xcafe,&out);
        if(fail){CK(result==UINT64_C(0x05120009)&&recovery_calls==fail&&p.bindings[0].device==257);}
        else{CK(result==0&&out.token==513&&out.flags==1&&p.bindings[0].device==0);CK(dm_bind(&p,out.token,&d,1,&b)==0);}
    }
    // Recover a non-first slot without touching another device/role/IRQ.
    {
        Table p={0},before;Device a=ps2(),d=pci(0xe0000000,0x8086,1,0x010802),v,out;Binding b;Irq irq;
        CK(dm_init(&p)==0&&dm_register(&p,&a,&v)==0&&dm_bind(&p,v.token,&a,3,&b)==0);
        CK(dm_irq_bind(&p,5,1,1,1,&irq)==0);
        CK(dm_register(&p,&d,&v)==0&&v.token==258&&dm_bind(&p,v.token,&d,1,&b)==0);
        CK(dm_revoke(&p,v.token,1)==0);before=p;
        recovery_table=&p;recovery_hardware=d;recovery_token=v.token;recovery_generation=2;
        recovery_calls=0;recovery_stops=0;recovery_fail=0;recovery_reentry=1;
        CK(dm_recover(&p,v.token,2,&recovery_ops,0xcafe,&out)==0&&out.token==514&&recovery_calls==4);
        CK(!memcmp(&p.devices[0],&before.devices[0],sizeof(Device)));
        CK(!memcmp(&p.bindings[2],&before.bindings[2],sizeof(Binding)));
        CK(!memcmp(p.interrupts,before.interrupts,sizeof p.interrupts));
        CK(p.bindings[0].device==0&&dm_bind(&p,out.token,&d,1,&b)==0);
    }
    Table t={0},before;Device d=ps2(),v,out;Binding b;
    CK(dm_init(&t)==0&&dm_register(&t,&d,&v)==0&&dm_bind(&t,v.token,&d,3,&b)==0);
    const U max=UINT64_C(0x00ffffffffffffff);
    t.devices[0].generation=max-1;t.devices[0].token=((max-1)<<8)|1;
    CK(dm_revoke(&t,t.devices[0].token,max-1)==0);before=t;recovery_calls=0;recovery_stops=0;
    CK(dm_recover(&t,t.devices[0].token,max,&recovery_ops,0xcafe,&out)==CAPACITY&&!memcmp(&t,&before,sizeof t)&&!recovery_calls);
}

// Actual CPL3 manager program against a syscall model: kernel catalog has an
// AHCI+NVMe pair, a tablet, i8042 and an unsupported NIC. After READY the NVMe
// disappears; only its original bound token may be revoked.
static int main_mode,catalog_failure;static U boot[16],enum_calls,binds,revokes,yields,ready,logs;static Device hardware[5];
ABI U svc_call(U number,U a,U b,U c,U d,U e,U f){CK(main_mode);if(number==2)return (U)(uintptr_t)boot;if(number==0x86){CK(a==0x101&&!b&&!c&&!d&&!e&&!f);return 3;}if(number==0x84){CK(a==0x101&&b==3&&!c&&!d&&!e&&!f);ready++;return 0;}if(number==0x70){CK(b&&b<=4096);logs++;return 0;}if(number==3){CK(!a&&!b&&!c&&!d&&!e&&!f);yields++;if(revokes){CK(ready==1&&binds==3&&logs==2);return 0x051200ff;}return 0;}CK(a==0x999);if(number==0x90){CK(b<=5&&c&&!d&&!e&&!f);enum_calls++;if(catalog_failure&&ready)return REMOVED;Device v={0};v.version=1;if(b<5){v=hardware[b];v.next=b+1;if(ready&&b==1)v.flags|=4;}*(Device*)(uintptr_t)c=v;return 0;}if(number==0x91){CK(b>=257&&b<=261&&d&&!e&&!f);Binding v={1,b,c,c==1?2:4,1,c==3?((1<<1)|(1<<12)):0,2,0};CK((c==1&&b==258)||(c==2&&b==259)||(c==3&&b==260));*(Binding*)(uintptr_t)d=v;binds++;return 0;}if(number==0x95){CK((b==258||(catalog_failure&&(b==259||b==260)))&&c==1&&!d&&!e&&!f);revokes++;return 0;}CK(0);return INVALID;}
ABI void __dong_panic(void){fprintf(stderr,"unexpected Dong panic\n");exit(2);}
static void launcher(void){main_mode=1;boot[0]=1;boot[1]=7;boot[2]=0x101;boot[8]=0x999;hardware[0]=pci(0xe0000000,0x8086,1,0x010601);hardware[1]=pci(0xe0001000,0x8086,2,0x010802);hardware[2]=pci(0xe0002000,0x1af4,0x1052,0);hardware[3]=ps2();hardware[4]=pci(0xe0004000,0x8086,3,0x020000);for(unsigned i=0;i<5;i++){hardware[i].token=257+i;hardware[i].generation=1;}CK(service_main()==(catalog_failure?0x05120009:0x051200ff));CK(revokes==(catalog_failure?3:1)&&binds==3&&ready==1&&enum_calls==(catalog_failure?7:12)&&yields==(catalog_failure?1024:1025));main_mode=0;}
int main(int argc,char**argv){CK(argc<=2);catalog_failure=argc==2&&!strcmp(argv[1],"catalog-failure");catalog();ranks();interrupts();recovery();launcher();printf("device manager native checks passed %lu; irq_rounds=1024; launcher_bindings=3; launcher_revocations=%lu\n",(unsigned long)checks,(unsigned long)revokes);return 0;}
