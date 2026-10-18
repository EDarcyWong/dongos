/* Independent whole-buffer pixel models. No guest, device, or third-party font. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"gfx oracle line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
typedef struct { int64_t left,top,right,bottom; } Rect;
typedef struct { uint32_t *ptr; size_t len,width,height,stride; } Surface;
typedef struct { Rect bounds; size_t count; bool full; Rect rects[16]; } Damage;
typedef struct { Surface surface; Rect rect; uint8_t opacity; bool visible; } Window;
typedef struct { const uint8_t *ptr; size_t len,width,height,stride; } Mask;
typedef struct { const uint8_t *ptr; size_t len,count,pixel_size,records,bitmap,bitmap_size; int64_t ascent,descent; } Atlas;
typedef struct { size_t width,height; int64_t bearing_x,bearing_y,advance_q6; const uint8_t *ptr; size_t len,stride; } Glyph;
extern ABI size_t gfx_surface_size(void),gfx_damage_size(void),gfx_window_size(void),gfx_atlas_size(void),gfx_glyph_size(void);
extern ABI uint32_t gfx_over(uint32_t,uint32_t),gfx_coverage(uint32_t,uint8_t);
extern ABI uint64_t gfx_fill(Surface *,const Rect *,uint32_t);
extern ABI uint64_t gfx_blit(Surface *,int64_t,int64_t,const Surface *,const Rect *,uint8_t);
extern ABI uint64_t gfx_mask(Surface *,int64_t,int64_t,const Mask *,uint32_t);
extern ABI uint64_t gfx_damage_init(const Rect *,Damage *),gfx_damage_add(Damage *,const Rect *);
extern ABI uint64_t gfx_compose(Surface *,const Window *,size_t,const Damage *,uint32_t);
extern ABI uint64_t gfx_atlas_open(const uint8_t *,size_t,Atlas *),gfx_lookup(const Atlas *,uint32_t,Glyph *,uint64_t *);
extern ABI uint64_t gfx_text(Surface *,const Atlas *,const uint8_t *,size_t,int64_t,int64_t,uint32_t,int64_t *);
ABI void __dong_panic(uint64_t kind) { fprintf(stderr,"unexpected Dong panic %llu\n",(unsigned long long)kind); exit(99); }
ABI void gfx_negative_hit(uint64_t kind) {
    static unsigned seen;
    if(kind<32&&!(seen&(1u<<(unsigned)kind))) {
        seen|=1u<<(unsigned)kind;fprintf(stderr,"GFX_NEGATIVE_HIT %u\n",(unsigned)kind);
    }
}
enum { CELLS=400, GUARD=8, TOTAL=CELLS+16 };
static uint32_t actual[TOTAL],expected[TOTAL],source[TOTAL],saved_source[TOTAL],before[TOTAL];
static uint32_t state=0x578bcdef;
static unsigned fills,blits,masks,compositions,rejected,atlas_checks,damage_checks;
static uint32_t random32(void) { state^=state<<13; state^=state>>17; state^=state<<5; return state; }
static uint32_t coverage(uint32_t value,uint8_t amount) {
    uint32_t result=0;
    for(unsigned shift=0;shift<32;shift+=8) result|=((((value>>shift)&255u)*amount+127u)/255u)<<shift;
    return result;
}
static uint32_t over(uint32_t dst,uint32_t src) {
    uint32_t result=0, inverse=255u-(src>>24);
    for(unsigned shift=0;shift<32;shift+=8) {
        uint32_t channel=((src>>shift)&255u)+(((dst>>shift)&255u)*inverse+127u)/255u;
        if(channel>255) channel=255;
        result|=channel<<shift;
    }
    return result;
}
static void reset(void) {
    for(size_t i=0;i<TOTAL;i++) actual[i]=expected[i]=random32();
    for(size_t i=0;i<TOTAL;i++) source[i]=saved_source[i]=random32();
}
static void equal_buffers(void) {
    CHECK(memcmp(actual,expected,sizeof actual)==0);
    CHECK(memcmp(source,saved_source,sizeof source)==0);
}
static bool in_rect(int64_t x,int64_t y,Rect r) { return x>=r.left&&x<r.right&&y>=r.top&&y<r.bottom; }
static void model_mask(Surface d,int64_t x,int64_t y,Mask m,uint32_t color) {
    for(size_t row=0;row<m.height;row++) for(size_t column=0;column<m.width;column++) {
        int64_t dx=x+(int64_t)column,dy=y+(int64_t)row;
        if(dx>=0&&dy>=0&&(uint64_t)dx<d.width&&(uint64_t)dy<d.height) {
            size_t at=GUARD+(size_t)dy*d.stride+(size_t)dx;
            expected[at]=over(expected[at],coverage(color,m.ptr[row*m.stride+column]));
        }
    }
}
static void raster_tests(void) {
    Surface d={actual+GUARD,CELLS,17,13,21}, s={source+GUARD,CELLS,9,7,11};
    for(unsigned iteration=0;iteration<1000;iteration++) {
        uint32_t p=random32(),q=random32(); uint8_t a=(uint8_t)random32();
        CHECK(gfx_over(p,q)==over(p,q)); CHECK(gfx_coverage(q,a)==coverage(q,a));
        reset(); Rect r={(int64_t)(random32()%51)-25,(int64_t)(random32()%41)-20,0,0};
        r.right=r.left+(int64_t)(random32()%40);r.bottom=r.top+(int64_t)(random32()%35);
        uint32_t color=random32(); CHECK(gfx_fill(&d,&r,color)==0);fills++;
        for(size_t y=0;y<d.height;y++) for(size_t x=0;x<d.width;x++)
            if(in_rect((int64_t)x,(int64_t)y,r))expected[GUARD+y*d.stride+x]=color;
        equal_buffers();
        reset(); int64_t x=(int64_t)(random32()%31)-15,y=(int64_t)(random32()%25)-12;
        Rect area={1,1,8,6};a=(uint8_t)random32();
        CHECK(gfx_blit(&d,x,y,&s,&area,a)==0);blits++;
        for(int64_t sy=1;sy<6;sy++)for(int64_t sx=1;sx<8;sx++) {
            int64_t dx=x+sx-1,dy=y+sy-1;
            if(dx>=0&&dy>=0&&(uint64_t)dx<d.width&&(uint64_t)dy<d.height) {
                size_t at=GUARD+(size_t)dy*d.stride+(size_t)dx;
                expected[at]=over(expected[at],coverage(source[GUARD+(size_t)sy*s.stride+(size_t)sx],a));
            }
        }
        equal_buffers();
        uint8_t bytes[96],saved[96];for(size_t i=0;i<sizeof bytes;i++)bytes[i]=saved[i]=(uint8_t)random32();
        Mask m={bytes+8,72,7,8,9};reset();color=random32();
        CHECK(gfx_mask(&d,x,y,&m,color)==0);masks++;model_mask(d,x,y,m,color);
        equal_buffers();CHECK(memcmp(bytes,saved,sizeof bytes)==0);
    }
    reset();memcpy(before,actual,sizeof actual);Rect invalid={2,0,1,2};
    CHECK(gfx_fill(&d,&invalid,0)!=0);rejected++;CHECK(memcmp(before,actual,sizeof actual)==0);
    Surface bad=d;bad.len=1;Rect full={0,0,17,13};
    CHECK(gfx_fill(&bad,&full,0)!=0);rejected++;CHECK(memcmp(before,actual,sizeof actual)==0);
    Rect area={0,0,9,7};CHECK(gfx_blit(&d,INT64_MAX,0,&s,&area,255)!=0);rejected++;
    CHECK(memcmp(before,actual,sizeof actual)==0);
    CHECK(gfx_blit(&d,0,0,&d,&full,255)!=0);rejected++;CHECK(memcmp(before,actual,sizeof actual)==0);
    uint8_t bytes[8]={0};Mask m={bytes,1,2,2,2};
    CHECK(gfx_mask(&d,0,0,&m,~0u)!=0);rejected++;CHECK(memcmp(before,actual,sizeof actual)==0);
    m=(Mask){(uint8_t *)d.ptr,16,2,2,2};
    CHECK(gfx_mask(&d,0,0,&m,~0u)!=0);rejected++;CHECK(memcmp(before,actual,sizeof actual)==0);
}
static void dirty_and_compositor_tests(void) {
    struct { uint64_t pre; Damage value; uint64_t post; } guarded;
    memset(&guarded,0xa5,sizeof guarded);Rect bounds={0,0,100,100};
    CHECK(gfx_damage_init(&bounds,&guarded.value)==0);damage_checks++;
    for(int64_t i=0;i<17;i++) {
        Rect r={i*4,1,i*4+2,3};CHECK(gfx_damage_add(&guarded.value,&r)==0);damage_checks++;
        CHECK(guarded.value.count<=16);CHECK(guarded.pre==UINT64_C(0xa5a5a5a5a5a5a5a5));CHECK(guarded.post==guarded.pre);
        for(int64_t j=0;j<=i;j++) {
            bool covered=false;for(size_t k=0;k<guarded.value.count;k++)if(in_rect(j*4,1,guarded.value.rects[k]))covered=true;
            CHECK(covered);
        }
    }
    CHECK(guarded.value.full&&guarded.value.count==1);
    Damage old=guarded.value;Rect bad={1,1,0,0};CHECK(gfx_damage_add(&guarded.value,&bad)!=0);rejected++;
    CHECK(memcmp(&old,&guarded.value,sizeof old)==0);
    CHECK(gfx_damage_init(&bounds,&guarded.value)==0);Rect a={1,1,4,4},b={3,3,6,6};
    CHECK(gfx_damage_add(&guarded.value,&a)==0&&gfx_damage_add(&guarded.value,&b)==0);
    CHECK(guarded.value.count==1&&guarded.value.rects[0].left==1&&guarded.value.rects[0].bottom==6);
    Surface d={actual+GUARD,CELLS,17,13,21},s={source+GUARD,CELLS,9,7,11};
    Window windows[2]={{s,{-3,2,6,9},255,true},{s,{8,-2,17,5},127,true}};
    Damage damage={0};damage.bounds=(Rect){0,0,17,13};damage.count=2;
    damage.rects[0]=(Rect){0,1,7,12};damage.rects[1]=(Rect){10,0,17,8};
    for(unsigned iteration=0;iteration<100;iteration++) {
        reset();uint32_t bg=random32();CHECK(gfx_compose(&d,windows,2,&damage,bg)==0);compositions++;
        for(size_t y=0;y<d.height;y++)for(size_t x=0;x<d.width;x++) {
            if(!in_rect((int64_t)x,(int64_t)y,damage.rects[0])&&!in_rect((int64_t)x,(int64_t)y,damage.rects[1]))continue;
            uint32_t pixel=bg;
            for(size_t i=0;i<2;i++)if(in_rect((int64_t)x,(int64_t)y,windows[i].rect)) {
                size_t sx=(size_t)((int64_t)x-windows[i].rect.left),sy=(size_t)((int64_t)y-windows[i].rect.top);
                pixel=over(pixel,coverage(source[GUARD+sy*s.stride+sx],windows[i].opacity));
            }
            expected[GUARD+y*d.stride+x]=pixel;
        }
        equal_buffers();
    }
    reset();memcpy(before,actual,sizeof actual);windows[1].surface.len=1;
    CHECK(gfx_compose(&d,windows,2,&damage,0)!=0);rejected++;CHECK(memcmp(before,actual,sizeof actual)==0);
}
static void put16(uint8_t *p,uint16_t value){p[0]=(uint8_t)value;p[1]=(uint8_t)(value>>8);}
static void put32(uint8_t *p,uint32_t value){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(value>>(8*i));}
static uint8_t font[192],original_font[192];
static size_t make_font(void) {
    memset(font,0,sizeof font);memcpy(font,"DGFONT01",8);put32(font+8,1);put32(font+12,48);
    put32(font+16,3);put32(font+20,14);put32(font+24,48);put32(font+28,144);put32(font+32,18);
    put32(font+36,3);put32(font+40,1);
    uint32_t cps[3]={65,0x4e2d,0xfffd};
    for(unsigned i=0;i<3;i++) {
        uint8_t *r=font+48+i*32;put32(r,cps[i]);put16(r+4,2);put16(r+6,3);put16(r+8,1);put16(r+10,2);
        put32(r+12,192);put32(r+16,i*6);put16(r+20,2);
        for(unsigned j=0;j<6;j++)font[144+i*6+j]=(uint8_t)((i*79+j*51)%256);
    }
    memcpy(original_font,font,sizeof font);return 162;
}
static void atlas_tests(void) {
    size_t length=make_font();struct {uint64_t pre;Atlas a;uint64_t post;} out;
    memset(&out,0xa5,sizeof out);CHECK(gfx_atlas_open(font,length,&out.a)==0);atlas_checks++;
    CHECK(out.pre==UINT64_C(0xa5a5a5a5a5a5a5a5)&&out.post==out.pre);
    CHECK(out.a.count==3&&out.a.records==48&&out.a.bitmap==144&&out.a.bitmap_size==18);
    Glyph g,before_g;memset(&g,0xa5,sizeof g);uint64_t found=9;
    CHECK(gfx_lookup(&out.a,0x4e2d,&g,&found)==0&&found==1);atlas_checks++;
    CHECK(g.width==2&&g.height==3&&g.bearing_x==1&&g.bearing_y==2&&g.advance_q6==192&&g.ptr==font+150&&g.len==6&&g.stride==2);
    before_g=g;CHECK(gfx_lookup(&out.a,100,&g,&found)==0&&found==0);CHECK(memcmp(&g,&before_g,sizeof g)==0);
    Atlas saved=out.a;
    const unsigned offsets[]={0,8,12,16,24,28,32,44,52,68,70,72};
    for(size_t i=0;i<sizeof offsets/sizeof offsets[0];i++) {
        memcpy(font,original_font,sizeof font);font[offsets[i]]^=0xff;
        uint8_t bad_font[sizeof font];memcpy(bad_font,font,sizeof font);
        CHECK(gfx_atlas_open(font,length,&out.a)!=0);rejected++;CHECK(memcmp(&saved,&out.a,sizeof saved)==0);
        CHECK(memcmp(bad_font,font,sizeof font)==0);
        CHECK(out.pre==UINT64_C(0xa5a5a5a5a5a5a5a5)&&out.post==out.pre);
    }
    memcpy(font,original_font,sizeof font);CHECK(gfx_atlas_open(font,length,&out.a)==0);
    Surface d={actual+GUARD,CELLS,17,13,21};int64_t advance=-1;
    const uint8_t text[]={65,0xe4,0xb8,0xad};reset();
    CHECK(gfx_text(&d,&out.a,text,sizeof text,1,4,0xffd0b090,&advance)==0&&advance==6);atlas_checks++;
    model_mask(d,2,2,(Mask){font+144,6,2,3,2},0xffd0b090);
    model_mask(d,5,2,(Mask){font+150,6,2,3,2},0xffd0b090);equal_buffers();
    const uint8_t newline[]={65,10,65};reset();
    CHECK(gfx_text(&d,&out.a,newline,sizeof newline,-1,3,0x80402010,&advance)==0&&advance==3);atlas_checks++;
    model_mask(d,0,1,(Mask){font+144,6,2,3,2},0x80402010);
    model_mask(d,0,5,(Mask){font+144,6,2,3,2},0x80402010);equal_buffers();
    const uint8_t invalid[]={65,0xc0,0xaf};reset();memcpy(before,actual,sizeof actual);advance=-77;
    CHECK(gfx_text(&d,&out.a,invalid,sizeof invalid,1,4,~0u,&advance)==UINT64_C(0x7010007));rejected++;
    CHECK(advance==-77&&memcmp(before,actual,sizeof actual)==0);
    CHECK(gfx_text(&d,&out.a,text,sizeof text,INT64_MAX,4,~0u,&advance)!=0);rejected++;
    CHECK(advance==-77&&memcmp(before,actual,sizeof actual)==0);
    CHECK(memcmp(font,original_font,sizeof font)==0);
}
int main(void) {
    CHECK(gfx_surface_size()==sizeof(Surface)&&gfx_damage_size()==sizeof(Damage)&&gfx_window_size()==sizeof(Window));
    CHECK(gfx_atlas_size()==sizeof(Atlas)&&gfx_glyph_size()==sizeof(Glyph));
    raster_tests();dirty_and_compositor_tests();atlas_tests();
    printf("gfx independent pixels passed: fills=%u blits=%u masks=%u compositions=%u damage=%u atlas=%u rejected=%u full-buffer-guards=ok\n",
           fills,blits,masks,compositions,damage_checks,atlas_checks,rejected);
    return 0;
}
