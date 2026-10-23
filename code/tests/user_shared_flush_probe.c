/* Production ASM control flow and selector; privileged local flush is mocked. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef TEST_RUNTIME_LEVEL
#error TEST_RUNTIME_LEVEL is required
#endif
#if TEST_RUNTIME_LEVEL != 4 && TEST_RUNTIME_LEVEL != 6 && TEST_RUNTIME_LEVEL != 7
#error unsupported test runtime
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
extern U ABI user_shared_flush_mode(U cr4);
extern void ABI user_shared_abi_call(U *result);
/* A stale BSP flag must never select the current CPU's flush operation. */
U user_pcid_enabled;

enum { ACTIVE=1, LOCAL=2, MOV_CR3=3, ALL_TAGS=4, REJECT_PGE=5, APS=6 };
static U actual_cr4, active_status, local_status, ap_status;
static unsigned events[8], event_count, checks, cases;
static const char *case_name;

static void check(int ok,const char *reason){
    ++checks;
    if(!ok){
        fprintf(stderr,"P2_FLUSH_ORACLE %s/%s runtime=%u\n",
                case_name,reason,(unsigned)TEST_RUNTIME_LEVEL);
        exit(1);
    }
}
static void event(unsigned value){
    check(event_count<sizeof events/sizeof events[0],"event-overflow");
    events[event_count++]=value;
}
U ABI user_shared_mock_active(U alignment){
    check(alignment==8,"active-call-stack");event(ACTIVE);return active_status;
}
U ABI user_shared_mock_local(U alignment){
    check(alignment==8,"local-call-stack");event(LOCAL);
    /* This calls the unchanged production selector with the mocked CR4 read.
       MOV CR3 and INVPCID themselves are never executed on the host. */
    U mode=user_shared_flush_mode(actual_cr4);
    if(mode==2){event(REJECT_PGE);return 1;}
    check(mode<=1,"invalid-flush-selector");event(mode?ALL_TAGS:MOV_CR3);
    return local_status;
}
U ABI user_shared_mock_broadcast(U virtual_address,U scope,U alignment){
    check(alignment==8,"broadcast-call-stack");
    check(virtual_address==0&&scope==1,"broadcast-arguments");
    event(APS);return ap_status;
}

static void selector(void){
    static const struct {U cr4;U mode;} vectors[]={
        {0,0},{UINT64_C(1)<<17,1},{UINT64_C(1)<<7,2},
        {(UINT64_C(1)<<17)|(UINT64_C(1)<<7),2},
        {UINT64_C(0x300620),0},{UINT64_C(0x320620),1},
        {UINT64_C(0x3006a0),2},{UINT64_C(0x3206a0),2}
    };
    case_name="PGE-rejection";
    for(unsigned stale=0;stale<2;++stale){
        user_pcid_enabled=stale;
        for(unsigned i=0;i<sizeof vectors/sizeof vectors[0];++i){
            check(user_shared_flush_mode(vectors[i].cr4)==vectors[i].mode,"selector");
            check(user_pcid_enabled==stale,"selector-writes-old-flag");
        }
    }
}

static void invoke(const char *name,U cr4,U old_flag,U active,U local,U ap,
                   U expected,const unsigned *order,unsigned length){
    static const U preserved[]={
        UINT64_C(0x1020304050607080),UINT64_C(0x2131415161718191),
        UINT64_C(0x32425262728292a2),UINT64_C(0x435363738393a3b3),
        UINT64_C(0x5464748494a4b4c4),UINT64_C(0x65758595a5b5c5d5)
    };
    struct {U left;U result[9];U right;} out;
    case_name=name;actual_cr4=cr4;user_pcid_enabled=old_flag;
    active_status=active;local_status=local;ap_status=ap;
    event_count=0;memset(events,0,sizeof events);memset(&out,0xa5,sizeof out);
    out.left=UINT64_C(0x72696768742d4c31);out.right=UINT64_C(0x6c6566742d523231);
    user_shared_abi_call(out.result);
    check(out.left==UINT64_C(0x72696768742d4c31)&&out.right==UINT64_C(0x6c6566742d523231),"output-guards");
    check(out.result[0]==expected,"result");
    check(out.result[1]==out.result[2]&&(out.result[1]&15)==0,"restored-stack");
    for(unsigned i=0;i<6;++i)check(out.result[3+i]==preserved[i],"callee-saved-register");
    check(user_pcid_enabled==old_flag,"old-flag-mutated");
    check(event_count==length&&!memcmp(events,order,length*sizeof *order),"callback-order");
    ++cases;
}

static void inactive(void){
#if TEST_RUNTIME_LEVEL == 4
    static const unsigned plain[]={LOCAL,MOV_CR3},tagged[]={LOCAL,ALL_TAGS},pge[]={LOCAL,REJECT_PGE};
#elif TEST_RUNTIME_LEVEL == 6
    static const unsigned plain[]={LOCAL,MOV_CR3,APS},tagged[]={LOCAL,ALL_TAGS,APS},pge[]={LOCAL,REJECT_PGE};
#else
    static const unsigned plain[]={ACTIVE,LOCAL,MOV_CR3,APS},tagged[]={ACTIVE,LOCAL,ALL_TAGS,APS},pge[]={ACTIVE,LOCAL,REJECT_PGE};
#endif
    invoke("inactive-plain",0,0,1,0,0,1,plain,sizeof plain/sizeof *plain);
    invoke("old-flag-is-not-CR4",UINT64_C(1)<<17,0,1,0,0,1,tagged,sizeof tagged/sizeof *tagged);
    invoke("old-flag-cannot-enable-PCIDE",0,1,1,0,0,1,plain,sizeof plain/sizeof *plain);
    invoke("inactive-PGE-rejected",UINT64_C(1)<<7,0,1,0,0,0,pge,sizeof pge/sizeof *pge);
    invoke("inactive-PCIDE-PGE-rejected",(UINT64_C(1)<<17)|(UINT64_C(1)<<7),1,1,0,0,0,pge,sizeof pge/sizeof *pge);
#if TEST_RUNTIME_LEVEL == 7
    static const unsigned failed_local[]={ACTIVE,LOCAL,ALL_TAGS};
#else
    static const unsigned failed_local[]={LOCAL,ALL_TAGS};
#endif
    invoke("local-failure-no-broadcast",UINT64_C(1)<<17,0,1,7,0,0,failed_local,sizeof failed_local/sizeof *failed_local);
#if TEST_RUNTIME_LEVEL >= 6
    invoke("AP-failure-rejected",UINT64_C(1)<<17,0,1,0,9,0,tagged,sizeof tagged/sizeof *tagged);
#endif
}
static void broadcast(void){
#if TEST_RUNTIME_LEVEL == 7
    static const unsigned order[]={ACTIVE,LOCAL,ALL_TAGS,APS};
#elif TEST_RUNTIME_LEVEL == 6
    static const unsigned order[]={LOCAL,ALL_TAGS,APS};
#else
    static const unsigned order[]={LOCAL,ALL_TAGS};
#endif
    invoke("broadcast-required",UINT64_C(1)<<17,0,1,0,0,1,order,sizeof order/sizeof *order);
}
static void active(void){
#if TEST_RUNTIME_LEVEL == 7
    static const unsigned order[]={ACTIVE};
    invoke("active-success-no-fallback",UINT64_C(1)<<17,0,0,7,9,1,order,1);
    invoke("active-error-no-fallback",UINT64_C(1)<<17,0,UINT64_MAX,0,0,0,order,1);
    invoke("active-error-two-no-fallback",0,1,2,0,0,0,order,1);
    invoke("active-error-seven-no-fallback",0,0,7,0,0,0,order,1);
#else
    /* Runtime4/6 must not call the runtime7 active-domain hook at all. */
    inactive();
#endif
}
int main(int argc,char **argv){
    case_name="arguments";check(argc==2,"scenario-required");
    if(!strcmp(argv[1],"all")){selector();inactive();broadcast();active();}
    else if(!strcmp(argv[1],"selector"))selector();
    else if(!strcmp(argv[1],"broadcast"))broadcast();
    else if(!strcmp(argv[1],"active-error"))active();
    else check(0,"unknown-scenario");
    printf("P2_FLUSH_PASS runtime=%u checks=%u cases=%u scenario=%s hardware=mock\n",
           (unsigned)TEST_RUNTIME_LEVEL,checks,cases,argv[1]);
    return 0;
}
