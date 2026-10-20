/* Independent fixed-record bytes/checksum and two-slot recovery oracle. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"PREFERENCES_MODEL_ASSERT line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
#define ERR(n) (UINT64_C(0x07240000)+(n))
typedef struct {uint32_t background,surface,text,muted,accent,border,shadow,selection,danger,padding;uint64_t radius,shadow_size,scale,duration;} Theme;
typedef struct {uint64_t sequence;Theme theme;} Record;
extern ABI void prefs_sizes(uint64_t *),prefs_default(Theme *);
extern ABI uint64_t prefs_encode(const Theme *,uint64_t,uint8_t *,size_t),prefs_decode(const uint8_t *,size_t,Record *);
extern ABI uint64_t prefs_select(const uint8_t *,size_t,const uint8_t *,size_t,Record *,uint64_t *),prefs_next(uint64_t,uint64_t *);
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected preferences panic %llu\n",(unsigned long long)code);exit(99);}
ABI void preferences_negative_hit(uint64_t kind){static unsigned seen;if(!seen++){fprintf(stderr,"PREFERENCES_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}}
static uint64_t checks;
static unsigned encoded,corruptions,recovered,rejected,selected;
static struct {uint64_t pre;Record value;uint64_t post;} out;
static struct {uint64_t pre;uint8_t value[128];uint64_t post;} encoded_bytes;
static uint16_t u16(const uint8_t *p){uint16_t v;memcpy(&v,p,2);return v;}
static uint32_t u32(const uint8_t *p){uint32_t v;memcpy(&v,p,4);return v;}
static uint64_t u64(const uint8_t *p){uint64_t v;memcpy(&v,p,8);return v;}
static void w32(uint8_t *p,uint32_t v){memcpy(p,&v,4);}
static void w64(uint8_t *p,uint64_t v){memcpy(p,&v,8);}
static uint32_t adler(const uint8_t *p,unsigned backwards){
 uint32_t a=1,b=0;for(unsigned n=0;n<128;n++){unsigned at=backwards?127-n:n;unsigned byte=at>=104&&at<112?0:p[at];a=(a+byte)%65521;b=(b+a)%65521;}return (b<<16)|a;
}
static uint64_t checksum(const uint8_t *p){return ((uint64_t)adler(p,1)<<32)|adler(p,0);}
static void seal(uint8_t *p){w64(p+104,checksum(p));}
static void canonical(const Theme *t,uint64_t sequence,uint8_t *p){
 memset(p,0,128);memcpy(p,"DONGPREF",8);w32(p+8,1);w32(p+12,128);w64(p+16,sequence);
 const uint32_t colors[9]={t->background,t->surface,t->text,t->muted,t->accent,t->border,t->shadow,t->selection,t->danger};
 for(unsigned i=0;i<9;i++)w32(p+32+4*i,colors[i]);
 w64(p+72,t->radius);w64(p+80,t->shadow_size);w64(p+88,t->scale);w64(p+96,t->duration);seal(p);
}
static void same_theme(const Theme *a,const Theme *b){
 CHECK(a->background==b->background&&a->surface==b->surface&&a->text==b->text&&a->muted==b->muted&&a->accent==b->accent&&a->border==b->border&&a->shadow==b->shadow&&a->selection==b->selection&&a->danger==b->danger);
 CHECK(a->radius==b->radius&&a->shadow_size==b->shadow_size&&a->scale==b->scale&&a->duration==b->duration);
}
static void reset_out(void){out.pre=UINT64_C(0x1020304050607080);out.post=UINT64_C(0x8070605040302010);memset(&out.value,0xb7,sizeof out.value);}
static void guards(void){CHECK(out.pre==UINT64_C(0x1020304050607080)&&out.post==UINT64_C(0x8070605040302010));CHECK(encoded_bytes.pre==UINT64_C(0x1122334455667788)&&encoded_bytes.post==UINT64_C(0x8877665544332211));}
static void encode(const Theme *t,uint64_t sequence,uint8_t *p){
 uint8_t expected[128];canonical(t,sequence,expected);memset(encoded_bytes.value,0xcd,128);
 CHECK(prefs_encode(t,sequence,encoded_bytes.value,128)==0);CHECK(memcmp(encoded_bytes.value,expected,128)==0);guards();memcpy(p,encoded_bytes.value,128);encoded++;
 CHECK(u64(p+16)==sequence&&u32(p+8)==1&&u32(p+12)==128&&u16(p+24)==0&&u64(p+104)==checksum(p));
 reset_out();CHECK(prefs_decode(p,128,&out.value)==0);CHECK(out.value.sequence==sequence);same_theme(&out.value.theme,t);guards();
}
static void bad_decode(const uint8_t *p,size_t length){
 uint8_t saved[128];if(p)memcpy(saved,p,128);reset_out();Record old=out.value;
 CHECK(prefs_decode(p,length,&out.value)!=0);CHECK(memcmp(&old,&out.value,sizeof old)==0);if(p)CHECK(memcmp(saved,p,128)==0);guards();rejected++;
}
static void choice(const uint8_t *a,size_t alen,const uint8_t *b,size_t blen,uint64_t want_slot,const Theme *t,uint64_t sequence){
 uint8_t saved_a[128],saved_b[128];if(a)memcpy(saved_a,a,128);if(b)memcpy(saved_b,b,128);uint64_t slot=UINT64_MAX;reset_out();
 CHECK(prefs_select(a,alen,b,blen,&out.value,&slot)==0&&slot==want_slot);CHECK(out.value.sequence==sequence);same_theme(&out.value.theme,t);
 if(a){CHECK(memcmp(a,saved_a,128)==0);}if(b){CHECK(memcmp(b,saved_b,128)==0);}guards();selected++;
}
static void bad_choice(const uint8_t *a,size_t alen,const uint8_t *b,size_t blen,uint64_t error){
 uint64_t slot=UINT64_MAX;reset_out();Record old=out.value;
 CHECK(prefs_select(a,alen,b,blen,&out.value,&slot)==error&&slot==UINT64_MAX);CHECK(memcmp(&old,&out.value,sizeof old)==0);guards();rejected++;
}
static void bad_encode(const Theme *t,uint64_t sequence,size_t length){
 memset(encoded_bytes.value,0xcd,128);uint8_t saved[128];memcpy(saved,encoded_bytes.value,128);
 CHECK(prefs_encode(t,sequence,encoded_bytes.value,length)!=0);CHECK(memcmp(saved,encoded_bytes.value,128)==0);guards();rejected++;
}
int main(void){
 uint64_t sizes[2];prefs_sizes(sizes);CHECK(sizes[0]==sizeof(Theme)&&sizes[0]==72&&sizes[1]==sizeof(Record)&&sizes[1]==80);
 encoded_bytes.pre=UINT64_C(0x1122334455667788);encoded_bytes.post=UINT64_C(0x8877665544332211);reset_out();
 Theme base;prefs_default(&base);base.padding=0xdeadbeef;uint8_t a[128],b[128],damaged[128],older[128];
 uint64_t scales[]={256,320,384,448,512};for(unsigned i=0;i<5;i++){Theme t=base;t.scale=scales[i];t.radius=i*8;t.shadow_size=32-i*8;t.duration=i*250;encode(&t,i+1,a);}
 encode(&base,1,a);Theme next=base;next.scale=448;next.background=0xff223344;next.surface=0xff445566;encode(&next,2,b);memcpy(older,a,128);
 choice(a,128,b,128,1,&next,2);choice(b,128,a,128,0,&next,2);choice(a,128,a,128,0,&base,1);
 for(unsigned at=0;at<128;at++)for(unsigned bit=0;bit<8;bit++){
  memcpy(damaged,b,128);damaged[at]^=(uint8_t)(1u<<bit);bad_decode(damaged,128);corruptions++;
  choice(a,128,damaged,128,0,&base,1);choice(damaged,128,a,128,1,&base,1);recovered+=2;
 }
 for(size_t length=0;length<128;length++){bad_decode(b,length);choice(a,128,b,length,0,&base,1);bad_choice(b,length,b,length,ERR(5));}
 bad_decode(b,129);bad_decode(NULL,128);bad_encode(&base,1,127);bad_encode(&base,1,129);bad_encode(&base,0,128);bad_encode(NULL,1,128);
 /* Correct checksums cannot legitimize unsupported header/reserved/theme bytes. */
 const unsigned changed[]={0,8,12,24,68,112,127};for(unsigned i=0;i<sizeof changed/sizeof changed[0];i++){memcpy(damaged,b,128);damaged[changed[i]]^=1;seal(damaged);bad_decode(damaged,128);}
 memcpy(damaged,b,128);w64(damaged+16,0);seal(damaged);bad_decode(damaged,128);
 const uint64_t bad_scales[]={0,255,257,319,321,383,385,447,449,511,513,1024};
 for(unsigned i=0;i<sizeof bad_scales/sizeof bad_scales[0];i++){
  Theme t=base;t.scale=bad_scales[i];bad_encode(&t,1,128);memcpy(damaged,b,128);w64(damaged+88,bad_scales[i]);seal(damaged);bad_decode(damaged,128);
 }
 Theme invalid=base;invalid.background=0x80112233;bad_encode(&invalid,1,128);invalid=base;invalid.surface=0x80000000;bad_encode(&invalid,1,128);
 invalid=base;invalid.radius=33;bad_encode(&invalid,1,128);invalid=base;invalid.shadow_size=33;bad_encode(&invalid,1,128);invalid=base;invalid.duration=1001;bad_encode(&invalid,1,128);invalid=base;invalid.accent=0x01020000;bad_encode(&invalid,1,128);
 memcpy(damaged,b,128);w32(damaged+36,0x80000000);seal(damaged);bad_decode(damaged,128);
 memcpy(damaged,b,128);w64(damaged+72,33);seal(damaged);bad_decode(damaged,128);
 /* Same generation with different valid contents is a conflict, never a tie. */
 encode(&next,1,b);bad_choice(a,128,b,128,ERR(6));bad_choice(b,128,a,128,ERR(6));choice(a,128,a,128,0,&base,1);
 encode(&base,UINT64_MAX-1,a);encode(&next,UINT64_MAX,b);choice(a,128,b,128,1,&next,UINT64_MAX);choice(b,128,older,128,0,&next,UINT64_MAX);
 uint64_t value=17;CHECK(prefs_next(0,&value)==0&&value==1);CHECK(prefs_next(UINT64_MAX-1,&value)==0&&value==UINT64_MAX);value=17;CHECK(prefs_next(UINT64_MAX,&value)==ERR(7)&&value==17);
 memset(damaged,0,128);bad_choice(damaged,128,damaged,128,ERR(5));choice(NULL,128,b,128,1,&next,UINT64_MAX);bad_choice(NULL,128,NULL,128,ERR(5));
 /* Alias rejection happens before any encode byte can overwrite its Theme. */
 union {uint64_t align;uint8_t bytes[160];} alias;memset(alias.bytes,0xa5,sizeof alias.bytes);memcpy(alias.bytes,&base,sizeof base);uint8_t alias_old[160];memcpy(alias_old,alias.bytes,160);
 CHECK(prefs_encode((const Theme *)alias.bytes,1,alias.bytes,128)==ERR(1)&&memcmp(alias_old,alias.bytes,160)==0);
 CHECK(prefs_decode(b,128,NULL)==ERR(1));uint64_t slot=17;CHECK(prefs_select(a,128,b,128,NULL,&slot)==ERR(1)&&slot==17);guards();
 printf("preferences oracle passed: canonical=%u corrupt-bits=%u fallback=%u selected=%u reject-atomic=%u checksum=independent both-slots-and-guards=ok checks=%llu\n",encoded,corruptions,recovered,selected,rejected,(unsigned long long)checks);
 return 0;
}
