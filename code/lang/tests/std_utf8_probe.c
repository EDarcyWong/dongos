#define _GNU_SOURCE
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"core.utf8 check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
struct Bytes {const uint8_t *ptr;uint64_t len;};
struct Decode {uint32_t scalar;uint32_t pad;uint64_t width;};
extern uint64_t DG u8_decode_size(void),u8_scalar_off(void),u8_width_off(void);
extern uint8_t DG u8_decode(struct Bytes,uint64_t,struct Decode*);
extern uint8_t DG u8_encode(uint32_t,struct Bytes,uint64_t*);
extern uint8_t DG u8_validate(struct Bytes);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected core.utf8 panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
static uint8_t *read_file(const char *path,uint64_t *size){
    FILE *f=fopen(path,"rb");
    if(!f){fprintf(stderr,"cannot open %s\n",path);exit(2);}
    fseek(f,0,SEEK_END); long n=ftell(f); fseek(f,0,SEEK_SET);
    if(n<0){fprintf(stderr,"bad size\n");exit(2);}
    uint8_t *buf=malloc((size_t)n);
    if(fread(buf,1,(size_t)n,f)!=(size_t)n){fprintf(stderr,"short read\n");exit(2);}
    fclose(f); *size=(uint64_t)n; return buf;
}
struct GDecode { uint8_t front[8]; struct Decode d; uint8_t back[8]; };
struct GWritten { uint8_t front[8]; uint64_t v; uint8_t back[8]; };
#define DECG(g) do{for(int _g=0;_g<8;_g++)CHECK((g).front[_g]==0xa5 && (g).back[_g]==0xa5);}while(0)
#define WG(g) do{for(int _g=0;_g<8;_g++)CHECK((g).front[_g]==0xa5 && (g).back[_g]==0xa5);}while(0)

int main(int argc,char **argv){
    CHECK(argc==6);
    CHECK(u8_decode_size()==16);
    CHECK(u8_scalar_off()==0 && u8_width_off()==8);
    CHECK(sizeof(struct Decode)==16 && offsetof(struct Decode,scalar)==0 && offsetof(struct Decode,width)==8);
    struct GDecode gd; struct Decode *d=&gd.d;
    struct GWritten gw; uint64_t *written=&gw.v;

    uint64_t fsize=0; uint8_t *full=read_file(argv[1],&fsize);
    CHECK(fsize%9==0); uint64_t n=fsize/9; CHECK(n==1112064);
    {
        uint8_t ib[8+8+8]; uint8_t *in=ib+8;
        uint8_t ob[8+8+8]; uint8_t *out=ob+8;
        for(uint64_t i=0;i<n;i++){
            uint32_t scalar; uint8_t width; uint8_t bytes[4];
            memcpy(&scalar,full+i*9,4);
            width=full[i*9+4];
            memcpy(bytes,full+i*9+5,4);
            memset(ob,0xa5,sizeof(ob));
            memset(&gw,0xa5,sizeof(gw)); *written=UINT64_C(0x1111111111111111);
            CHECK(u8_encode(scalar,(struct Bytes){out,8},written));
            CHECK(*written==width);
            CHECK(!memcmp(out,bytes,width));
            for(int k=width;k<8;k++)CHECK(out[k]==0xa5);
            for(int g=0;g<8;g++){CHECK(ob[g]==0xa5);CHECK(ob[8+8+g]==0xa5);}
            WG(gw);
            memset(&gd,0xa5,sizeof(gd));
            memset(ib,0xa5,sizeof(ib)); memcpy(in,bytes,4); memset(in+4,0xcc,4);
            uint8_t insnap[8]; memcpy(insnap,in,8);
            CHECK(u8_decode((struct Bytes){in,4},0,d));
            CHECK(d->scalar==scalar); CHECK(d->width==width); CHECK(d->pad==UINT32_C(0xa5a5a5a5));
            DECG(gd);
            CHECK(!memcmp(in,insnap,8));
            for(int g=0;g<8;g++){CHECK(ib[g]==0xa5);CHECK(ib[8+8+g]==0xa5);}
        }
        free(full);
    }

    {
        uint64_t psize=0; uint8_t *pairs=read_file(argv[2],&psize);
        CHECK(psize==65536*7);
        uint8_t pair[8+2+8]; uint8_t *data=pair+8;
        for(uint64_t i=0;i<65536;i++){
            uint8_t b0=(uint8_t)(i>>8), b1=(uint8_t)(i&0xffu);
            uint8_t ok=pairs[i*7], width=pairs[i*7+1];
            uint32_t scalar; memcpy(&scalar,pairs+i*7+2,4);
            uint8_t vok=pairs[i*7+6];
            memset(pair,0xa5,sizeof(pair));
            data[0]=b0; data[1]=b1;
            uint8_t ds[8]; memcpy(ds,data,8);
            memset(&gd,0xa5,sizeof(gd));
            uint8_t r=u8_decode((struct Bytes){data,2},0,d);
            CHECK(r==ok);
            if(ok){CHECK(d->width==width);CHECK(d->scalar==scalar);CHECK(d->pad==UINT32_C(0xa5a5a5a5));}
            else {CHECK(d->scalar==UINT32_C(0xa5a5a5a5));CHECK(d->pad==UINT32_C(0xa5a5a5a5));CHECK(d->width==UINT64_C(0xa5a5a5a5a5a5a5a5));}
            DECG(gd);
            CHECK(!memcmp(data,ds,8));
            for(int g=0;g<8;g++)CHECK(pair[g]==0xa5&&pair[8+2+g]==0xa5);
            uint8_t v=u8_validate((struct Bytes){data,2});
            CHECK(v==vok);
            CHECK(!memcmp(data,ds,8));
            for(int g=0;g<8;g++)CHECK(pair[g]==0xa5&&pair[8+2+g]==0xa5);
        }
        free(pairs);
    }

    {
        uint64_t isize=0; uint8_t *inv=read_file(argv[3],&isize);
        CHECK(isize%9==0); uint64_t cnt=isize/9;
        uint8_t buf[8+8+8]; uint8_t *data=buf+8;
        for(uint64_t i=0;i<cnt;i++){
            uint8_t len=inv[i*9];
            memset(buf,0xa5,sizeof(buf));
            memcpy(data,inv+i*9+1,len);
            uint8_t ds[8]; memcpy(ds,data,8);
            memset(&gd,0xa5,sizeof(gd));
            CHECK(!u8_decode((struct Bytes){data,len},0,d));
            CHECK(d->scalar==UINT32_C(0xa5a5a5a5) && d->pad==UINT32_C(0xa5a5a5a5) && d->width==UINT64_C(0xa5a5a5a5a5a5a5a5));
            DECG(gd);
            CHECK(!memcmp(data,ds,8));
            for(int g=0;g<8;g++)CHECK(buf[g]==0xa5&&buf[8+8+g]==0xa5);
            CHECK(!u8_validate((struct Bytes){data,len}));
            CHECK(!memcmp(data,ds,8));
            for(int g=0;g<8;g++)CHECK(buf[g]==0xa5&&buf[8+8+g]==0xa5);
            uint8_t pre[8+2+8+8]; uint8_t *pd=pre+8; memset(pre,0xa5,sizeof(pre));
            pd[0]=0x41; pd[1]=0x42; memcpy(pd+2,inv+i*9+1,len);
            uint8_t pds[8]; memcpy(pds,pd,8);
            CHECK(!u8_validate((struct Bytes){pd,(uint64_t)(2+len)}));
            CHECK(!memcmp(pd,pds,8));
            for(int g=0;g<8;g++)CHECK(pre[g]==0xa5&&pre[8+2+len+g]==0xa5);
            memset(&gd,0xa5,sizeof(gd));
            CHECK(u8_decode((struct Bytes){pd,(uint64_t)(2+len)},0,d));
            CHECK(d->scalar==0x41 && d->width==1); DECG(gd);
            CHECK(!memcmp(pd,pds,8));
            for(int g=0;g<8;g++)CHECK(pre[g]==0xa5&&pre[8+2+len+g]==0xa5);
        }
        free(inv);
    }

    {
        uint64_t ssize=0; uint8_t *single=read_file(argv[4],&ssize);
        CHECK(ssize==256*8);
        uint8_t sb[8+1+8]; uint8_t *sd=sb+8;
        for(uint64_t i=0;i<256;i++){
            uint8_t b=single[i*8];
            uint8_t ok=single[i*8+1], width=single[i*8+2];
            uint32_t scalar; memcpy(&scalar,single+i*8+3,4);
            uint8_t vok=single[i*8+7];
            memset(sb,0xa5,sizeof(sb)); sd[0]=b;
            uint8_t ds[8]; memcpy(ds,sd,8);
            memset(&gd,0xa5,sizeof(gd));
            uint8_t r=u8_decode((struct Bytes){sd,1},0,d);
            CHECK(r==ok);
            if(ok){CHECK(d->width==width);CHECK(d->scalar==scalar);CHECK(d->pad==UINT32_C(0xa5a5a5a5));}
            else {CHECK(d->scalar==UINT32_C(0xa5a5a5a5));CHECK(d->pad==UINT32_C(0xa5a5a5a5));CHECK(d->width==UINT64_C(0xa5a5a5a5a5a5a5a5));}
            DECG(gd); CHECK(!memcmp(sd,ds,8));
            for(int g=0;g<8;g++)CHECK(sb[g]==0xa5&&sb[8+1+g]==0xa5);
            CHECK(u8_validate((struct Bytes){sd,1})==vok);
            CHECK(!memcmp(sd,ds,8));
            for(int g=0;g<8;g++)CHECK(sb[g]==0xa5&&sb[8+1+g]==0xa5);
        }
        free(single);
    }
    {
        uint64_t rsize=0; uint8_t *random=read_file(argv[5],&rsize);
        CHECK(rsize%24==0); uint64_t rn=rsize/24; CHECK(rn>=2000);
        uint8_t rb[8+16+8]; uint8_t *rd=rb+8;
        for(uint64_t i=0;i<rn;i++){
            uint8_t len=random[i*24];
            uint8_t vok=random[i*24+17], ok=random[i*24+18], width=random[i*24+19];
            uint32_t scalar; memcpy(&scalar,random+i*24+20,4);
            memset(rb,0xa5,sizeof(rb));
            memcpy(rd,random+i*24+1,len);
            uint8_t ds[16]; memcpy(ds,rd,16);
            CHECK(u8_validate((struct Bytes){rd,len})==vok);
            CHECK(!memcmp(rd,ds,16));
            for(int g=0;g<8;g++)CHECK(rb[g]==0xa5&&rb[8+16+g]==0xa5);
            memset(&gd,0xa5,sizeof(gd));
            uint8_t r=u8_decode((struct Bytes){rd,len},0,d);
            CHECK(r==ok);
            if(ok){CHECK(d->width==width);CHECK(d->scalar==scalar);CHECK(d->pad==UINT32_C(0xa5a5a5a5));}
            else {CHECK(d->scalar==UINT32_C(0xa5a5a5a5));CHECK(d->pad==UINT32_C(0xa5a5a5a5));CHECK(d->width==UINT64_C(0xa5a5a5a5a5a5a5a5));}
            DECG(gd); CHECK(!memcmp(rd,ds,16));
            for(int g=0;g<8;g++)CHECK(rb[g]==0xa5&&rb[8+16+g]==0xa5);
        }
        free(random);
    }

    {
        uint8_t sbuf[8+8+8]; uint8_t *s=sbuf+8; memset(sbuf,0xa5,sizeof(sbuf));
        s[0]=0xc3; s[1]=0xa9; s[2]=0x41;
        uint8_t ss[8]; memcpy(ss,s,8);
        memset(&gd,0xa5,sizeof(gd)); CHECK(u8_decode((struct Bytes){s,3},0,d)); CHECK(d->scalar==0xe9 && d->width==2); DECG(gd); CHECK(!memcmp(s,ss,8)); for(int g=0;g<8;g++)CHECK(sbuf[g]==0xa5 && sbuf[8+3+g]==0xa5);
        memset(&gd,0xa5,sizeof(gd)); CHECK(u8_decode((struct Bytes){s,3},2,d)); CHECK(d->scalar==0x41 && d->width==1); DECG(gd); CHECK(!memcmp(s,ss,8)); for(int g=0;g<8;g++)CHECK(sbuf[g]==0xa5 && sbuf[8+3+g]==0xa5);
        { memset(&gd,0xa5,sizeof(gd)); uint8_t bf[16]; memcpy(bf,d,16);
          CHECK(!u8_decode((struct Bytes){s,3},3,d)); CHECK(!memcmp(d,bf,16)); DECG(gd); CHECK(!memcmp(s,ss,8)); for(int g=0;g<8;g++)CHECK(sbuf[g]==0xa5 && sbuf[8+3+g]==0xa5); }
        { memset(&gd,0xa5,sizeof(gd)); uint8_t bf[16]; memcpy(bf,d,16);
          CHECK(!u8_decode((struct Bytes){s,3},4,d)); CHECK(!memcmp(d,bf,16)); DECG(gd); CHECK(!memcmp(s,ss,8)); for(int g=0;g<8;g++)CHECK(sbuf[g]==0xa5 && sbuf[8+3+g]==0xa5); }
        { memset(&gd,0xa5,sizeof(gd)); uint8_t bf[16]; memcpy(bf,d,16);
          CHECK(!u8_decode((struct Bytes){s,3},UINT64_MAX,d)); CHECK(!memcmp(d,bf,16)); DECG(gd); CHECK(!memcmp(s,ss,8)); for(int g=0;g<8;g++)CHECK(sbuf[g]==0xa5 && sbuf[8+3+g]==0xa5); }
        { memset(&gd,0xa5,sizeof(gd)); uint8_t bf[16]; memcpy(bf,d,16);
          CHECK(!u8_decode((struct Bytes){s,3},1,d)); CHECK(!memcmp(d,bf,16)); DECG(gd); CHECK(!memcmp(s,ss,8)); for(int g=0;g<8;g++)CHECK(sbuf[g]==0xa5 && sbuf[8+3+g]==0xa5); }
        { memset(&gd,0xa5,sizeof(gd)); uint8_t bf[16]; memcpy(bf,d,16);
          CHECK(!u8_decode((struct Bytes){NULL,0},0,d)); CHECK(!memcmp(d,bf,16)); DECG(gd); }

        uint8_t ob[8+8+8]; uint8_t *o=ob+8;
        memset(ob,0xa5,sizeof(ob));
        memset(&gw,0xa5,sizeof(gw)); *written=UINT64_C(0x9999999999999999);
        CHECK(u8_encode(0x10ffff,(struct Bytes){o,4},written)); CHECK(*written==4 && !memcmp(o,"\xf4\x8f\xbf\xbf",4));
        for(int k=4;k<8;k++)CHECK(o[k]==0xa5);
        for(int g=0;g<8;g++){CHECK(ob[g]==0xa5&&ob[8+8+g]==0xa5);} WG(gw);
        memset(ob,0xa5,sizeof(ob)); memset(&gw,0xa5,sizeof(gw)); *written=UINT64_C(0x9999999999999999);
        { uint8_t b2[8+8+8]; memcpy(b2,ob,sizeof(ob)); uint64_t wb=*written;
          CHECK(!u8_encode(0x10ffff,(struct Bytes){o,3},written)); CHECK(*written==wb); CHECK(!memcmp(ob,b2,sizeof(ob))); WG(gw); }
        memset(ob,0xa5,sizeof(ob)); memset(&gw,0xa5,sizeof(gw)); *written=UINT64_C(0x9999999999999999);
        { uint8_t b2[8+8+8]; memcpy(b2,ob,sizeof(ob)); uint64_t wb=*written;
          CHECK(!u8_encode(0x41,(struct Bytes){o,0},written)); CHECK(*written==wb); CHECK(!memcmp(ob,b2,sizeof(ob))); WG(gw); }
        { uint32_t bad[]={UINT32_C(0xd800),UINT32_C(0xdfff),UINT32_C(0x110000),UINT32_C(0xffffffff),UINT32_C(0x7fffffff)};
          for(size_t k=0;k<sizeof(bad)/sizeof(bad[0]);k++){
            memset(ob,0xa5,sizeof(ob)); memset(&gw,0xa5,sizeof(gw)); *written=UINT64_C(0x9999999999999999);
            uint8_t b2[8+8+8]; memcpy(b2,ob,sizeof(ob)); uint64_t wb=*written;
            CHECK(!u8_encode(bad[k],(struct Bytes){o,8},written)); CHECK(*written==wb); CHECK(!memcmp(ob,b2,sizeof(ob))); WG(gw);
          } }
        { struct {uint32_t sc; uint64_t w; uint8_t bytes[4];} expect[]={
            {0x7f,1,{0x7f,0,0,0}},{0x80,2,{0xc2,0x80,0,0}},{0x7ff,2,{0xdf,0xbf,0,0}},
            {0x800,3,{0xe0,0xa0,0x80,0}},{0xffff,3,{0xef,0xbf,0xbf,0}},
            {0x10000,4,{0xf0,0x90,0x80,0x80}},{0xfeff,3,{0xef,0xbb,0xbf,0}},
            {0,1,{0,0,0,0}},{0x10ffff,4,{0xf4,0x8f,0xbf,0xbf}}};
          for(size_t k=0;k<sizeof(expect)/sizeof(expect[0]);k++){
            memset(ob,0xa5,sizeof(ob)); memset(&gw,0xa5,sizeof(gw)); *written=0;
            CHECK(u8_encode(expect[k].sc,(struct Bytes){o,8},written));
            CHECK(*written==expect[k].w); WG(gw);
            CHECK(!memcmp(o,expect[k].bytes,expect[k].w));
            for(int kk=(int)expect[k].w;kk<8;kk++)CHECK(o[kk]==0xa5);
            for(int g=0;g<8;g++)CHECK(ob[g]==0xa5&&ob[8+8+g]==0xa5);
          } }
        { struct {uint32_t sc; uint64_t w; uint8_t bytes[4];} wsc[]={
            {0x7f,1,{0x7f,0,0,0}},{0x80,2,{0xc2,0x80,0,0}},
            {0x800,3,{0xe0,0xa0,0x80,0}},{0x10000,4,{0xf0,0x90,0x80,0x80}}};
          for(size_t k=0;k<sizeof(wsc)/sizeof(wsc[0]);k++){
            uint32_t sc=wsc[k].sc; uint64_t w=wsc[k].w;
            memset(ob,0xa5,sizeof(ob)); memset(&gw,0xa5,sizeof(gw)); *written=0;
            CHECK(u8_encode(sc,(struct Bytes){o,w},written)); CHECK(*written==w);
            CHECK(!memcmp(o,wsc[k].bytes,w));
            for(int kk=(int)w;kk<8;kk++){CHECK(o[kk]==0xa5);} WG(gw);
            for(int g=0;g<8;g++)CHECK(ob[g]==0xa5&&ob[8+8+g]==0xa5);
            memset(ob,0xa5,sizeof(ob)); memset(&gw,0xa5,sizeof(gw)); *written=UINT64_C(0x9999999999999999);
            { uint8_t b2[8+8+8]; memcpy(b2,ob,sizeof(ob)); uint64_t wb=*written;
              CHECK(!u8_encode(sc,(struct Bytes){o,w-1},written)); CHECK(*written==wb); CHECK(!memcmp(ob,b2,sizeof(ob))); WG(gw); }
            memset(ob,0xa5,sizeof(ob)); memset(&gw,0xa5,sizeof(gw)); *written=UINT64_C(0x9999999999999999);
            { uint8_t b2[8+8+8]; memcpy(b2,ob,sizeof(ob)); uint64_t wb=*written;
              CHECK(!u8_encode(sc,(struct Bytes){o,0},written)); CHECK(*written==wb); CHECK(!memcmp(ob,b2,sizeof(ob))); WG(gw); }
          } }

        CHECK(u8_validate((struct Bytes){NULL,0}));
        { uint8_t vg[8+12+8]; uint8_t *v=vg+8; memset(vg,0xa5,sizeof(vg));
          uint8_t b[]={0xef,0xbb,0xbf,0x41,0x00,0xe2,0x82,0xac,0xf0,0x9f,0x98,0x80};
          memcpy(v,b,12);
          uint8_t vs[12]; memcpy(vs,v,12);
          CHECK(u8_validate((struct Bytes){v,12}));
          CHECK(!memcmp(v,vs,12));
          for(int g=0;g<8;g++)CHECK(vg[g]==0xa5 && vg[8+12+g]==0xa5);
          CHECK(!u8_validate((struct Bytes){v,11}));
          CHECK(!memcmp(v,vs,12));
          for(int g=0;g<8;g++)CHECK(vg[g]==0xa5 && vg[8+12+g]==0xa5); }
    }

    puts("native core.utf8 probes passed");return 0;
}
