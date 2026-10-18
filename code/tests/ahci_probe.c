/* Independent AHCI/ATA byte and state oracle. Never accesses a device or DMA. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#define ABI __attribute__((sysv_abi))
#define INVALID UINT64_C(0x09010001)
#define RANGE UINT64_C(0x09010002)
#define UNSUP UINT64_C(0x09010003)
#define BADID UINT64_C(0x09010004)
#define CHECKSUM UINT64_C(0x09010005)
#define BUSY UINT64_C(0x09010006)
#define CLEANUP UINT64_C(0x09010007)
#define TIMEOUT UINT64_C(0x09010008)
#define BADCOMP UINT64_C(0x09010009)
#define DEVICE UINT64_C(0x0901000a)
#define BADSTATE UINT64_C(0x0901000b)
#define GUARD UINT64_C(0xdea1beef5a6170e5)
typedef struct {uint64_t token,physical,length;} Lease;
typedef struct {uint64_t physical_bits,s64a;} Caps;
typedef struct {uint64_t sectors,sector_bytes,flush_ext,write_cache,valid;} Info;
typedef struct {uint64_t opcode,lba,sectors;} Request;
typedef struct {uint64_t clb,fb,ctba,data,bytes,opcode,lba,sectors;uint8_t header[32],table[144];} Command;
typedef struct {uint64_t generation,pending,faulted,held,opcode,expected,start_ms,timeout_ms,last_ms,completed;} State;
typedef struct {uint64_t generation,ci,sact,interrupts,tfd,serr,prdbc,now_ms;uint8_t fis[256];} Sample;
typedef struct {uint64_t phase,elapsed_ms,boh,bohc,cmd,ci,sact;} EngineInput;
typedef struct {uint64_t target,clear_mask,set_mask,wait_mask,next_phase;} Action;
extern ABI void ah_sizes(uint64_t *);
extern ABI uint64_t ah_identify(const uint8_t *,size_t,Info *);
extern ABI uint64_t ah_build(const Lease *,const Caps *,const Info *,const Request *,Command *);
extern ABI uint64_t ah_arm(State *,uint64_t,uint64_t,uint64_t,uint64_t);
extern ABI uint64_t ah_poll(State *,const Sample *,uint64_t *);
extern ABI uint64_t ah_poll_with_policy(State *,const Sample *,uint64_t,uint64_t *);
extern ABI uint64_t ah_completion_policy(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
extern ABI void ah_policy_constants(uint64_t *);
extern ABI uint64_t ah_engine(const EngineInput *,Action *);
extern ABI uint64_t ah_mutant_hits(void);
extern ABI uint64_t ah_completion_mutant_hits(void);
static uint64_t assertions,builders,identifies,polls,engines,policy_polls,policy_ids;
static void check(int okay,const char *what,int line) {
    assertions++;
    if(!okay) {
        uint64_t hits=ah_mutant_hits();
        if(hits) fprintf(stderr,"AHCI_BUILDER_MUTANT_PATH_HIT=%" PRIu64 "\n",hits);
        hits=ah_completion_mutant_hits();
        if(hits) fprintf(stderr,"AHCI_COMPLETION_MUTANT_PATH_HIT=%" PRIu64 "\n",hits);
        fprintf(stderr,"AHCI oracle line %d: %s\n",line,what);exit(1);
    }
}
#define C(x) check(!!(x),#x,__LINE__)
ABI void __dong_panic(uint64_t code,uint64_t a,uint64_t b,uint64_t c) {
    fprintf(stderr,"unexpected DG panic %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",code,a,b,c);exit(99);
}
static uint64_t rng=UINT64_C(0xcafe57e80123456b);
static uint64_t random64(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static uint64_t get(const uint8_t *p,size_t n){uint64_t v=0;for(size_t i=0;i<n;i++)v|=(uint64_t)p[i]<<(8*i);return v;}
static void put(uint8_t *p,uint64_t v,size_t n){for(size_t i=0;i<n;i++)p[i]=(uint8_t)(v>>(8*i));}
static Info disk={UINT64_C(0xffffffffffff),512,1,1,1};
static Lease lease={1,UINT64_C(0x200000),131072};
static Caps caps={48,1};

/* Oracle uses ATA task-file byte positions, not the DG implementation. The
   entire native Command including all reserved bytes must match this image. */
static void build_case(Lease l,Caps c,Info d,Request r,uint64_t error){
    struct {uint64_t pre;Command value;uint64_t post;} out;
    memset(&out,0xa7,sizeof out);out.pre=out.post=GUARD;
    Command previous=out.value;
    uint64_t rc=ah_build(&l,&c,&d,&r,&out.value);builders++;
    C(rc==error);C(out.pre==GUARD&&out.post==GUARD);
    if(error){C(!memcmp(&previous,&out.value,sizeof previous));return;}
    uint8_t expected[240]={0};
    uint64_t n=r.opcode==0xec?512:(r.opcode==0xea?0:r.sectors*512);
    uint64_t address[8]={l.physical,l.physical+1024,l.physical+2048,l.physical+4096,n,r.opcode,r.lba,r.sectors};
    for(size_t i=0;i<8;i++)put(expected+8*i,address[i],8);
    uint8_t *header=expected+64,*fis=expected+96,*prd=fis+128;
    header[0]=(uint8_t)(5+(r.opcode==0x35?64:0));header[2]=(uint8_t)(n?1:0);
    put(header+8,l.physical+2048,8);
    fis[0]=0x27;fis[1]=0x80;fis[2]=(uint8_t)r.opcode;
    if(r.opcode==0x25||r.opcode==0x35){
        const unsigned positions[6]={4,5,6,8,9,10};
        for(size_t i=0;i<6;i++)fis[positions[i]]=(uint8_t)(r.lba>>(i*8));
        fis[7]=0x40;put(fis+12,r.sectors,2);
    }
    if(n){put(prd,l.physical+4096,8);put(prd+12,n-1,4);}
    C(!memcmp(expected,&out.value,sizeof expected));
    C(get(out.value.header,4)==((r.opcode==0x35?UINT64_C(64):0)+5+(n?UINT64_C(65536):0)));
    C(get(out.value.header+4,4)==0);C(get(out.value.header+8,8)==out.value.ctba);
    C(!(out.value.clb&1023)&&!(out.value.fb&255)&&!(out.value.ctba&127));
    C(out.value.data+n<=l.physical+l.length);C(!n||get(out.value.table+140,4)+1==n);
    C(!n||!(get(out.value.table+128,8)&1));C(!n||(get(out.value.table+140,4)&1));
}
static void builders_test(void){
    build_case(lease,caps,(Info){0},(Request){0xec,0,0},0);
    build_case(lease,caps,disk,(Request){0xea,0,0},0);
    const uint64_t lb[]={0,1,255,256,65535,65536,UINT64_C(0xffffff),UINT64_C(0x1000000),
        UINT64_C(0xffffffff),UINT64_C(0x100000000),UINT64_C(0xff3456789abc),UINT64_C(0xffffffffff7f)};
    for(size_t i=0;i<sizeof lb/sizeof *lb;i++)for(unsigned n=1;n<=128;n++)for(unsigned w=0;w<2;w++){
        uint64_t rc=n>disk.sectors-lb[i]?RANGE:0;
        build_case(lease,caps,disk,(Request){w?0x35:0x25,lb[i],n},rc);
    }
    for(unsigned i=0;i<2000;i++){
        Caps c={32+(random64()%21),random64()%2};uint64_t limit=c.s64a?(UINT64_C(1)<<c.physical_bits):UINT64_C(0x100000000);
        uint64_t slots=(limit-131072)/4096;
        Lease l={random64()|1,(1+random64()%slots)*4096,131072};
        Request r={(i&1)?0x25:0x35,random64()%(disk.sectors-128),1+random64()%128};
        build_case(l,c,disk,r,0);
        if(i%4==0){r.sectors=129;build_case(l,c,disk,r,RANGE);}
    }
    const uint64_t badpa[]={0,1,4095,4097,UINT64_C(0x100000000),UINT64_MAX-4095};
    for(size_t i=0;i<sizeof badpa/sizeof *badpa;i++){Lease l=lease;l.physical=badpa[i];build_case(l,(Caps){52,0},disk,(Request){0x25,0,1},RANGE);}
    for(unsigned bits=32;bits<=52;bits++){
        uint64_t limit=UINT64_C(1)<<bits;Lease l={1,limit-131072,131072};
        build_case(l,(Caps){bits,1},disk,(Request){0x35,123,128},0);
        l.physical+=4096;build_case(l,(Caps){bits,1},disk,(Request){0x25,0,1},RANGE);
    }
    Lease l=lease;l.token=0;build_case(l,caps,disk,(Request){0x25,0,1},RANGE);
    l=lease;l.length--;build_case(l,caps,disk,(Request){0x25,0,1},RANGE);
    l.length=UINT64_MAX;build_case(l,caps,disk,(Request){0x25,0,1},RANGE);
    const Caps badcaps[]={{31,1},{53,1},{48,2},{0,0}};
    for(size_t i=0;i<sizeof badcaps/sizeof *badcaps;i++)build_case(lease,badcaps[i],disk,(Request){0xec,0,0},INVALID);
    const Request badreq[]={{0xec,1,0},{0xec,0,1},{0xea,1,0},{0xea,0,1},{0x25,0,0},
        {0x35,0,129},{0x25,UINT64_C(0xffffffffffff),1},{0x25,UINT64_C(0xfffffffffffe),2},
        {0x25,UINT64_MAX,UINT64_MAX},{0x60,0,1}};
    const uint64_t baderr[]={INVALID,INVALID,INVALID,INVALID,RANGE,RANGE,RANGE,RANGE,RANGE,UNSUP};
    for(size_t i=0;i<sizeof badreq/sizeof *badreq;i++)build_case(lease,caps,disk,badreq[i],baderr[i]);
    Info d=disk;d.flush_ext=0;build_case(lease,caps,d,(Request){0x25,0,1},0);
    build_case(lease,caps,d,(Request){0x35,0,1},UNSUP);build_case(lease,caps,d,(Request){0xea,0,0},UNSUP);
    const Info badinfo[]={{0,512,1,1,1},{UINT64_C(0x1000000000000),512,1,1,1},{9,4096,1,1,1},
        {9,512,2,1,1},{9,512,1,2,1},{9,512,1,1,0},{9,512,1,1,2}};
    for(size_t i=0;i<sizeof badinfo/sizeof *badinfo;i++)build_case(lease,caps,badinfo[i],(Request){0x25,0,1},INVALID);
    Command out;memset(&out,0xa5,sizeof out);Command before=out;Request r={0xec,0,0};
    C(ah_build(NULL,&caps,&disk,&r,&out)==INVALID);C(!memcmp(&out,&before,sizeof out));
    C(ah_build(&lease,NULL,&disk,&r,&out)==INVALID);C(ah_build(&lease,&caps,NULL,&r,&out)==INVALID);
    C(ah_build(&lease,&caps,&disk,NULL,&out)==INVALID);C(ah_build(&lease,&caps,&disk,&r,NULL)==INVALID);
}
static void id_fixture(uint8_t *raw){memset(raw,0,512);put(raw,0x0040,2);put(raw+49*2,0x300,2);
    put(raw+83*2,0x6400,2);put(raw+85*2,0x20,2);put(raw+86*2,0x2400,2);put(raw+87*2,0x4000,2);
    put(raw+100*2,disk.sectors,8);put(raw+106*2,0x6003,2);}
static void identify_case(uint8_t *raw,size_t bytes,uint64_t error,Info expected){
    struct {uint64_t pre;Info value;uint64_t post;} out;
    memset(&out,0x97,sizeof out);out.pre=out.post=GUARD;Info before=out.value;
    uint64_t rc=ah_identify(raw,bytes,&out.value);identifies++;C(rc==error);C(out.pre==GUARD&&out.post==GUARD);
    C(!memcmp(&out.value,error?&before:&expected,sizeof before));
}
static void identifies_test(void){
    struct {uint64_t pre;uint8_t raw[512];uint64_t post;} input;input.pre=input.post=GUARD;
    uint8_t *raw=input.raw;id_fixture(raw);identify_case(raw,512,0,disk);
    put(raw+106*2,0x4000,2);identify_case(raw,512,0,disk);
    put(raw+85*2,0,2);Info no_cache=disk;no_cache.write_cache=0;identify_case(raw,512,0,no_cache);
    const unsigned wordidx[]={0,0,49,49,83,83,83,86,87,106,106};
    const unsigned value[]={0x8040,0x0044,0x200,0x100,0x2400,0xc400,0x6000,0x2000,0,0,0x5000};
    for(size_t i=0;i<sizeof value/sizeof *value;i++){id_fixture(raw);put(raw+wordidx[i]*2,value[i],2);identify_case(raw,512,UNSUP,disk);}
    id_fixture(raw);put(raw+100*2,0,8);identify_case(raw,512,BADID,disk);
    put(raw+100*2,UINT64_C(0x1000000000000),8);identify_case(raw,512,BADID,disk);
    id_fixture(raw);raw[510]=0x33;identify_case(raw,512,BADID,disk);
    id_fixture(raw);raw[510]=255;identify_case(raw,512,0,disk);
    id_fixture(raw);raw[510]=0xa5;unsigned sum=0;for(unsigned i=0;i<511;i++)sum+=raw[i];raw[511]=(uint8_t)(0-sum);
    identify_case(raw,512,0,disk);raw[3]^=1;identify_case(raw,512,CHECKSUM,disk);
    id_fixture(raw);put(raw+83*2,0x4400,2);Info no_flush=disk;no_flush.flush_ext=0;identify_case(raw,512,0,no_flush);
    id_fixture(raw);put(raw+86*2,0x0400,2);identify_case(raw,512,0,no_flush);
    /* Word86 highbits have no word83 validity rule. */
    id_fixture(raw);put(raw+86*2,0xa400,2);identify_case(raw,512,0,disk);
    for(unsigned i=0;i<600;i++){id_fixture(raw);Info d=disk;d.sectors=1+(random64()&UINT64_C(0xfffffffffffe));
        d.flush_ext=random64()%2;d.write_cache=random64()%2;put(raw+100*2,d.sectors,8);
        put(raw+83*2,0x4400+(d.flush_ext?0x2000:0),2);put(raw+86*2,0x400+(d.flush_ext?0x2000:0),2);
        put(raw+85*2,d.write_cache?0x20:0,2);identify_case(raw,512,0,d);}
    id_fixture(raw);uint8_t saved[512];memcpy(saved,raw,512);identify_case(raw,511,INVALID,disk);identify_case(raw,513,INVALID,disk);
    C(!memcmp(saved,raw,512));C(input.pre==GUARD&&input.post==GUARD);
    identify_case(NULL,512,INVALID,disk);C(ah_identify(raw,512,NULL)==INVALID);
}
static State armed(uint64_t op,uint64_t bytes){State s={0};C(ah_arm(&s,op,bytes,100,1000)==0);
    C(s.generation==1&&s.pending==1&&!s.faulted&&s.held==1&&s.expected==bytes&&s.start_ms==100&&s.last_ms==100);return s;}
static Sample completed(const State *s,int pio){Sample x={0};x.generation=s->generation;x.prdbc=s->expected;x.now_ms=101;x.tfd=0x50;
    if(pio){x.interrupts=2;x.fis[0x20]=0x5f;x.fis[0x21]=0x60;x.fis[0x22]=0x58;x.fis[0x2f]=0x50;x.fis[0x31]=2;}
    else{x.interrupts=1;x.fis[0x40]=0x34;x.fis[0x41]=0x40;x.fis[0x42]=0x50;}return x;}
static State poll_case(State s,Sample x,uint64_t error,uint64_t value){
    struct {uint64_t pre;State s;uint64_t post;} state={GUARD,s,GUARD};
    struct {uint64_t pre,value,post;} out={GUARD,UINT64_C(0xabcdef0123456789),GUARD};
    Sample before=x;uint64_t rc=ah_poll(&state.s,&x,&out.value);polls++;C(rc==error);
    C(state.pre==GUARD&&state.post==GUARD&&out.pre==GUARD&&out.post==GUARD);C(!memcmp(&before,&x,sizeof x));
    if(error){C(out.value==UINT64_C(0xabcdef0123456789));C(state.s.held==1&&state.s.pending==1&&state.s.faulted==1);
        State old=state.s;C(ah_arm(&state.s,s.opcode,s.expected,1200,100)==CLEANUP);C(!memcmp(&old,&state.s,sizeof old));
        uint64_t result=99;C(ah_poll(&state.s,&x,&result)==CLEANUP&&result==99);C(!memcmp(&old,&state.s,sizeof old));
    }else{C(out.value==value);C(!state.s.faulted&&state.s.held==1);C(state.s.pending==(value?0:1));
        C(state.s.completed==s.completed+value&&state.s.last_ms==x.now_ms);}
    return state.s;
}
static void polls_test(void){
    const uint64_t ops[]={0xec,0x25,0x35,0xea};
    for(unsigned i=0;i<4;i++){
        State s=armed(ops[i],i==3?0:(i==0?512:65536));Sample x=completed(&s,0);State done=poll_case(s,x,0,1);
        C(ah_arm(&done,ops[i],s.expected,102,1000)==0);C(done.generation==2&&done.completed==1);
        x=completed(&s,0);x.ci=1;x.prdbc=0;x.interrupts=0;memset(x.fis,0,256);s=poll_case(s,x,0,0);
        x=completed(&s,0);x.now_ms=102;poll_case(s,x,0,1);
    }
    State s=armed(0xec,512);Sample x=completed(&s,1);poll_case(s,x,0,1);
    for(unsigned i=0;i<8;i++){
        x=completed(&s,1);
        if(i==0)x.fis[0x20]=0x34;else if(i==1)x.fis[0x21]=0x40;else if(i==2)x.fis[0x22]=0x50;
        else if(i==3)x.fis[0x2f]=0x58;else if(i==4)x.fis[0x2f]=0xd0;
        else if(i==5)x.fis[0x30]=1;else if(i==6)x.fis[0x31]=1;else x.fis[0x21]=0x61;
        poll_case(s,x,BADCOMP,0);
    }
    s=armed(0x25,512);x=completed(&s,1);poll_case(s,x,BADCOMP,0);
    for(unsigned i=0;i<18;i++){
        x=completed(&s,0);uint64_t error=BADCOMP;
        switch(i){case 0:x.generation++;break;case 1:x.ci=2;break;case 2:x.sact=1;break;
        case 3:x.interrupts=UINT64_C(1)<<32;break;case 4:x.tfd=65536;break;case 5:x.serr=UINT64_C(1)<<32;break;
        case 6:x.prdbc=UINT64_C(1)<<32;break;case 7:x.now_ms=99;break;case 8:x.tfd=0x80;break;
        case 9:x.tfd=8;break;case 10:x.prdbc=511;break;case 11:x.fis[0x40]=0x5f;break;
        case 12:x.fis[0x41]=0x41;break;case 13:x.fis[0x42]=0x58;break;
        case 14:x.interrupts=0x20;break;case 15:x.now_ms=1100;error=TIMEOUT;break;
        case 16:x.now_ms=1101;error=TIMEOUT;break;default:x.serr=1;error=DEVICE;break;}
        poll_case(s,x,error,0);
    }
    const uint64_t errorbits[]={4,24,26,27,28,29,30};
    for(size_t i=0;i<sizeof errorbits/sizeof *errorbits;i++){x=completed(&s,0);x.interrupts|=UINT64_C(1)<<errorbits[i];poll_case(s,x,DEVICE,0);}
    x=completed(&s,0);x.tfd|=1;poll_case(s,x,DEVICE,0);x.tfd=0x70;poll_case(s,x,DEVICE,0);
    x=completed(&s,0);x.ci=1;x.interrupts=0;x.now_ms=1099;s=poll_case(s,x,0,0);
    x=completed(&s,0);x.now_ms=1098;poll_case(s,x,BADCOMP,0);x.now_ms=1100;poll_case(s,x,TIMEOUT,0);
    State empty={0},before=empty;uint64_t result=17;Sample zero={0};C(ah_poll(&empty,&zero,&result)==BADSTATE&&result==17);
    C(!memcmp(&before,&empty,sizeof before));C(ah_poll(NULL,&zero,&result)==INVALID);C(ah_poll(&empty,NULL,&result)==INVALID);
    const uint64_t badshape[][2]={{0xec,0},{0xec,513},{0xea,512},{0x25,0},{0x35,513},{0x25,65537},{0x60,512}};
    for(size_t i=0;i<sizeof badshape/sizeof *badshape;i++){C(ah_arm(&empty,badshape[i][0],badshape[i][1],0,100)==INVALID);C(!memcmp(&before,&empty,sizeof before));}
    C(ah_arm(&empty,0x25,512,0,0)==INVALID);C(ah_arm(&empty,0x25,512,0,600001)==INVALID);
    C(ah_arm(&empty,0x25,512,UINT64_MAX,1)==INVALID);C(ah_arm(NULL,0x25,512,0,100)==INVALID);
    s=armed(0x25,512);before=s;C(ah_arm(&s,0x25,512,102,100)==BUSY);C(!memcmp(&s,&before,sizeof s));
    empty.generation=UINT64_MAX;C(ah_arm(&empty,0x25,512,0,100)==BADSTATE);
    empty=(State){0};empty.completed=UINT64_MAX;C(ah_arm(&empty,0x25,512,0,100)==BADSTATE);
    empty=(State){0};empty.held=2;C(ah_arm(&empty,0x25,512,0,100)==BADSTATE);
    empty=(State){0};empty.last_ms=1;C(ah_arm(&empty,0x25,512,0,100)==BADSTATE);
}
static void policy_case(State original,Sample sample,uint64_t policy,uint64_t error,uint64_t value){
    struct {uint64_t pre;State value;uint64_t post;} box={GUARD,original,GUARD};
    struct {uint64_t pre,value,post;} out={GUARD,UINT64_C(0xabcdef0123456789),GUARD};Sample before=sample;
    uint64_t rc=ah_poll_with_policy(&box.value,&sample,policy,&out.value);policy_polls++;
    C(rc==error);C(box.pre==GUARD&&box.post==GUARD&&out.pre==GUARD&&out.post==GUARD);
    C(!memcmp(&before,&sample,sizeof sample));
    if(error==INVALID){C(!memcmp(&original,&box.value,sizeof original));C(out.value==UINT64_C(0xabcdef0123456789));return;}
    State wanted=original;
    if(error){wanted.faulted=wanted.pending=wanted.held=1;C(out.value==UINT64_C(0xabcdef0123456789));
        State saved=box.value;uint64_t result=99;C(ah_poll_with_policy(&box.value,&sample,policy,&result)==CLEANUP&&result==99);C(!memcmp(&saved,&box.value,sizeof saved));
    }else{wanted.pending=value?0:1;wanted.last_ms=sample.now_ms;wanted.completed+=value;C(out.value==value);}
    C(!memcmp(&wanted,&box.value,sizeof wanted));
}
static uint64_t identity_model(const uint64_t v[6]){
    return v[0]==5549&&v[1]==2016&&v[2]==1&&v[3]==6&&v[4]==1&&(v[5]==0||v[5]==128)?1:0;
}
static void identity_case(const uint64_t v[6]){
    uint64_t actual=ah_completion_policy(v[0],v[1],v[2],v[3],v[4],v[5]);policy_ids++;C(actual==identity_model(v));
}
static void policies_test(void){
    uint64_t constants[2]={99,99};ah_policy_constants(constants);C(constants[0]==0&&constants[1]==1);
    /* Official VMware source: open-vm-tools/lib/include/vm_device_version.h,
       PCI_VENDOR_ID_VMWARE=15AD and PCI_DEVICE_ID_VMWARE_AHCI=07E0.
       Real selected-function PCI identity still has to be recorded by runtime. */
    for(unsigned field=0;field<6;field++){
        unsigned limit=field<2?65536:256;
        for(unsigned i=0;i<limit;i++){uint64_t v[6]={0x15ad,0x07e0,1,6,1,0};v[field]=i;identity_case(v);}
        const uint64_t wide[]={256,65536,UINT64_C(1)<<32,UINT64_C(1)<<63,UINT64_MAX};
        for(size_t i=0;i<sizeof wide/sizeof *wide;i++){uint64_t v[6]={0x15ad,0x07e0,1,6,1,0};v[field]=wide[i];identity_case(v);}
    }
    for(unsigned i=0;i<2000;i++){uint64_t v[6];for(unsigned j=0;j<6;j++)v[j]=random64();identity_case(v);}
    /* Exact captured last core.poll sample after acquire, own VMware run
       fb363f803a13485b/ahci-diagnostic.json. Diagnostic SHA-256
       c952bfb3386b9ff5f81b374c24e5eafb3e26faaa4e8b6a37fd367650357b0c08.
       This is empirical completed-snapshot compatibility, not a claim that
       initial DRQ=0 conforms to SATA's DPIOI1/on-wire requirements. */
    State s=armed(0xec,512);s.start_ms=s.last_ms=10000;s.timeout_ms=5000;
    Sample real={0};real.generation=1;real.interrupts=2;real.tfd=0x40;real.prdbc=512;real.now_ms=10136;
    const uint8_t pio[20]={0x5f,0x60,0x40,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,0,0};memcpy(real.fis+32,pio,sizeof pio);
    poll_case(s,real,BADCOMP,0);policy_case(s,real,0,BADCOMP,0);policy_case(s,real,1,0,1);
    /* Independent bit semantics: initial busy, device fault and error always
       fail; strict additionally requires DRQ. Ending busy/DRQ/fault/error fail
       in both modes. Other status bits keep the pre-existing ignored behavior. */
    for(uint64_t policy=0;policy<2;policy++)for(unsigned status=0;status<256;status++){
        Sample x=real;x.fis[0x22]=(uint8_t)status;
        int initial_bad=(status&128)||(status&32)||(status&1)||(!policy&&!(status&8));
        policy_case(s,x,policy,initial_bad?BADCOMP:0,initial_bad?0:1);
        x=real;x.fis[0x22]=0x48;x.fis[0x2f]=(uint8_t)status;
        int ending_bad=(status&128)||(status&32)||(status&1)||(status&8);
        policy_case(s,x,policy,ending_bad?BADCOMP:0,ending_bad?0:1);
    }
    for(unsigned status=0;status<256;status++){
        Sample x=real;x.tfd=status;uint64_t error=0;
        if((status&1)||(status&32))error=DEVICE;else if((status&128)||(status&8))error=BADCOMP;
        policy_case(s,x,1,error,error?0:1);
    }
    const uint64_t bytes[]={0,1,511,512,513,65536,UINT32_MAX,UINT64_C(1)<<32,UINT64_MAX};
    for(size_t i=0;i<sizeof bytes/sizeof *bytes;i++){Sample x=real;x.prdbc=bytes[i];policy_case(s,x,1,bytes[i]==512?0:BADCOMP,bytes[i]==512);}
    for(unsigned value=0;value<256;value++){
        Sample x=real;x.fis[0x20]=(uint8_t)value;policy_case(s,x,1,value==0x5f?0:BADCOMP,value==0x5f);
        x=real;x.fis[0x21]=(uint8_t)value;int valid=(value&15)==0&&(value&32)&&(value&64);policy_case(s,x,1,valid?0:BADCOMP,valid);
        x=real;x.fis[0x30]=(uint8_t)value;policy_case(s,x,1,value==0?0:BADCOMP,value==0);
        x=real;x.fis[0x31]=(uint8_t)value;policy_case(s,x,1,value==2?0:BADCOMP,value==2);
    }
    for(unsigned i=0;i<17;i++){
        Sample x=real;uint64_t error=BADCOMP;
        switch(i){case 0:x.generation++;break;case 1:x.ci=2;break;case 2:x.sact=1;break;
        case 3:x.interrupts=UINT64_C(1)<<32;break;case 4:x.tfd=65536;break;case 5:x.serr=UINT64_C(1)<<32;break;
        case 6:x.prdbc=UINT64_C(1)<<32;break;case 7:x.now_ms=9999;break;case 8:x.tfd=0x80;break;
        case 9:x.tfd=8;break;case 10:x.prdbc=511;break;case 11:x.interrupts=0;break;
        case 12:x.interrupts=0x20;break;case 13:x.interrupts=0x12;error=DEVICE;break;
        case 14:x.now_ms=15000;error=TIMEOUT;break;case 15:x.now_ms=15001;error=TIMEOUT;break;
        default:x.serr=1;error=DEVICE;break;}
        policy_case(s,x,1,error,0);
    }
    const unsigned errors[]={4,24,26,27,28,29,30};
    for(size_t i=0;i<sizeof errors/sizeof *errors;i++){Sample x=real;x.interrupts|=UINT64_C(1)<<errors[i];policy_case(s,x,1,DEVICE,0);}
    Sample pending=real;pending.ci=1;pending.interrupts=0;pending.prdbc=0;memset(pending.fis,0,256);policy_case(s,pending,1,0,0);
    for(unsigned index=0;index<3;index++){
        const uint64_t op[]={0x25,0x35,0xea};State other=armed(op[index],index==2?0:512);Sample x=completed(&other,1);x.fis[0x22]=0x40;
        policy_case(other,x,1,BADCOMP,0);x=completed(&other,0);policy_case(other,x,1,0,1);
        x.fis[0x42]|=8;policy_case(other,x,1,BADCOMP,0);
    }
    /* No matching DHRS FIS must be silently replaced by the PIO quirk. */
    Sample mixed=real;mixed.interrupts|=1;policy_case(s,mixed,1,BADCOMP,0);
    const uint64_t invalid[]={2,3,255,UINT64_C(1)<<32,UINT64_MAX};
    for(size_t i=0;i<sizeof invalid/sizeof *invalid;i++){
        policy_case(s,real,invalid[i],INVALID,0);State state=s;state.faulted=1;policy_case(state,real,invalid[i],INVALID,0);
    }
    State before=s;uint64_t value=0xabcdef;C(ah_poll_with_policy(NULL,&real,2,&value)==INVALID&&value==0xabcdef);
    C(ah_poll_with_policy(&s,NULL,2,&value)==INVALID&&value==0xabcdef&&!memcmp(&s,&before,sizeof s));
}
static void engine_case(EngineInput i,uint64_t error,Action expected){
    struct {uint64_t pre;Action a;uint64_t post;} out;memset(&out,0x87,sizeof out);out.pre=out.post=GUARD;Action before=out.a;
    uint64_t rc=ah_engine(&i,&out.a);engines++;C(rc==error);C(out.pre==GUARD&&out.post==GUARD);
    C(!memcmp(&out.a,error?&before:&expected,sizeof before));
}
static void engines_test(void){
    Action zero={0};
    for(unsigned bohc=0;bohc<32;bohc++)for(unsigned time=0;time<3;time++){
        EngineInput i={0,time==0?0:(time==1?1999:2000),1,bohc,0,0,0};Action a={0,0,0,0,1};uint64_t e=0;
        if(!(bohc&2)||(bohc&0x11)){if(i.elapsed_ms==2000)e=TIMEOUT;
            if(!(bohc&2)){a.target=1;a.set_mask=2;a.next_phase=0;}else{a.wait_mask=0x11;a.next_phase=0;}}
        engine_case(i,e,a);
    }
    engine_case((EngineInput){0,UINT64_MAX,0,0,0,0,0},0,(Action){0,0,0,0,1});
    engine_case((EngineInput){1,0,0,0,0x11,0,0},0,(Action){2,1,0,0,2});
    engine_case((EngineInput){1,0,0,0,0x10,0,0},0,(Action){0,0,0,0,2});
    engine_case((EngineInput){2,0,0,0,1,0,0},BADSTATE,zero);
    engine_case((EngineInput){2,499,0,0,0x8000,0,0},0,(Action){0,0,0,0x8000,2});
    engine_case((EngineInput){2,500,0,0,0x8000,0,0},TIMEOUT,zero);
    engine_case((EngineInput){2,500,0,0,0,0,0},0,(Action){0,0,0,0,3});
    engine_case((EngineInput){3,0,0,0,0x10,0,0},0,(Action){2,0x10,0,0,4});
    engine_case((EngineInput){3,0,0,0,0x8000,0,0},BADSTATE,zero);
    engine_case((EngineInput){4,499,0,0,0x4000,0,0},0,(Action){0,0,0,0x4000,4});
    engine_case((EngineInput){4,500,0,0,0x4000,0,0},TIMEOUT,zero);
    engine_case((EngineInput){4,500,0,0,0,0,0},0,(Action){0,0,0,0,5});
    engine_case((EngineInput){4,0,0,0,0x10,0,0},BADSTATE,zero);
    engine_case((EngineInput){5,0,0,0,0,0,0},0,(Action){0,0,0,0,6});
    engine_case((EngineInput){5,0,0,0,0x4000,0,0},BADSTATE,zero);
    engine_case((EngineInput){5,0,0,0,0,1,0},BADSTATE,zero);engine_case((EngineInput){5,0,0,0,0,0,1},BADSTATE,zero);
    engine_case((EngineInput){6,0,0,0,0,0,0},INVALID,zero);engine_case((EngineInput){0,0,2,0,0,0,0},INVALID,zero);
    engine_case((EngineInput){0,0,0,UINT64_C(1)<<32,0,0,0},INVALID,zero);
    Action out;memset(&out,0xa9,sizeof out);Action saved=out;
    C(ah_engine(NULL,&out)==INVALID);C(!memcmp(&out,&saved,sizeof out));EngineInput in={0};C(ah_engine(&in,NULL)==INVALID);
}
int main(void){
    uint64_t got[9]={0},wanted[]={sizeof(Lease),sizeof(Caps),sizeof(Info),sizeof(Request),sizeof(Command),sizeof(State),sizeof(Sample),sizeof(EngineInput),sizeof(Action)};
    ah_sizes(got);C(!memcmp(got,wanted,sizeof got));C(sizeof(Command)==240&&sizeof(Sample)==320);
    builders_test();identifies_test();polls_test();policies_test();engines_test();
    C(ah_mutant_hits()==0);
    C(ah_completion_mutant_hits()==0);
    printf("AHCI_MODEL_PASS assertions=%" PRIu64 " builders=%" PRIu64 " identify=%" PRIu64 " polls=%" PRIu64 " engine=%" PRIu64 " policy_polls=%" PRIu64 " policy_ids=%" PRIu64 " all-bytes=240 all-guards=ok no-hardware-io vmware-snapshot-quirk-replay=ok\n",assertions,builders,identifies,polls,engines,policy_polls,policy_ids);return 0;
}
