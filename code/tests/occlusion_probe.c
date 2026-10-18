/* Independent spatial coverage and scalar nearest-floor preimage oracles. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef struct{int64_t left,top,right,bottom;}Rect;
typedef struct{Rect rect;uint64_t first;}Part;
typedef struct{uint64_t count;Part parts[81];}Plan;
static uint64_t checks,cases,interiors,rejects,grid81,maxparts,negative;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"OCCLUSION_MODEL_ASSERT line %d: %s case=%llu\n",__LINE__,#x,(unsigned long long)cases);exit(1);}}while(0)
extern ABI void occlusion_sizes(uint64_t*);
extern ABI uint64_t occlusion_partition(const Rect*,const Rect*,uint64_t,Plan*),occlusion_interior(uint64_t,uint64_t,const Rect*,const Rect*,Rect*);
ABI void __dong_panic(uint64_t code){fprintf(stderr,"unexpected occlusion panic %llu\n",(unsigned long long)code);exit(99);}
ABI void occlusion_negative_hit(uint64_t kind){if(!negative++)fprintf(stderr,"OCCLUSION_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}
static const uint64_t PRE=UINT64_C(0xabcdefff12345678),POST=UINT64_C(0x87654321fffedcba);
static struct{uint64_t pre;Plan value;uint64_t post;} output;
static struct{uint64_t pre;Rect value;uint64_t post;} interior;
static uint64_t rng=UINT64_C(0x8a5cd789635d2dff);
static uint64_t random64(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static int compare(const void*a,const void*b){int64_t x=*(const int64_t*)a,y=*(const int64_t*)b;return(x>y)-(x<y);}
static int nonempty(const Rect*r){return r->left<r->right&&r->top<r->bottom;}
static int contains(const Rect*r,int64_t x,int64_t y){return r->left<=x&&x<r->right&&r->top<=y&&y<r->bottom;}
static unsigned highest(const Rect*r,unsigned n,int64_t x,int64_t y){unsigned result=0;for(unsigned i=0;i<n;i++)if(contains(r+i,x,y))result=i+1;return result;}
static __uint128_t area(const Rect*r){return(__uint128_t)((uint64_t)r->right-(uint64_t)r->left)*((uint64_t)r->bottom-(uint64_t)r->top);}
static unsigned edges(int64_t*out,const Rect*clip,const Rect*r,unsigned n,int vertical){
 unsigned used=0;out[used++]=vertical?clip->top:clip->left;out[used++]=vertical?clip->bottom:clip->right;
 for(unsigned i=0;i<n;i++){
  Rect q=r[i];if(q.left<clip->left)q.left=clip->left;if(q.top<clip->top)q.top=clip->top;if(q.right>clip->right)q.right=clip->right;if(q.bottom>clip->bottom)q.bottom=clip->bottom;
  if(nonempty(&q)){out[used++]=vertical?q.top:q.left;out[used++]=vertical?q.bottom:q.right;}
 }
 qsort(out,used,sizeof(*out),compare);unsigned unique=0;for(unsigned i=0;i<used;i++)if(!unique||out[i]!=out[unique-1])out[unique++]=out[i];return unique;
}
static void verify_plan(const Rect*clip,const Rect*r,unsigned n,const Plan*p){
 CHECK(p->count<=81);if(p->count>maxparts)maxparts=p->count;__uint128_t total=0;
 for(unsigned i=0;i<p->count;i++){
  const Part*a=p->parts+i;CHECK(nonempty(&a->rect)&&a->rect.left>=clip->left&&a->rect.top>=clip->top&&a->rect.right<=clip->right&&a->rect.bottom<=clip->bottom&&a->first<=n);
  for(unsigned j=0;j<i;j++){const Rect*b=&p->parts[j].rect;CHECK(!(a->rect.left<b->right&&b->left<a->rect.right&&a->rect.top<b->bottom&&b->top<a->rect.bottom));}
  __uint128_t amount=area(&a->rect);CHECK(total+amount>=total);total+=amount;
 }
 CHECK(total==area(clip));
 /* Independent sorted-edge decomposition queries every geometric cell and
    rejects hidden gaps, overlap, wrong provider and edges crossing an owner. */
 int64_t xs[10],ys[10];unsigned nx=edges(xs,clip,r,n,0),ny=edges(ys,clip,r,n,1);if(nx==10&&ny==10)grid81++;
 for(unsigned y=0;y+1<ny;y++)for(unsigned x=0;x+1<nx;x++){
  unsigned hits=0;uint64_t actual_first=99,expected_first=highest(r,n,xs[x],ys[y]);
  for(unsigned i=0;i<p->count;i++)if(contains(&p->parts[i].rect,xs[x],ys[y])){
   hits++;actual_first=p->parts[i].first;CHECK(p->parts[i].rect.right>=xs[x+1]&&p->parts[i].rect.bottom>=ys[y+1]);
  }
  CHECK(hits==1);CHECK(actual_first==expected_first);
 }
 Part empty={{0,0,0,0},0};for(unsigned i=(unsigned)p->count;i<81;i++)CHECK(memcmp(p->parts+i,&empty,sizeof empty)==0);
}
static void guards(void){CHECK(output.pre==PRE&&output.post==POST&&interior.pre==PRE&&interior.post==POST);}
static void partition(const Rect*clip,const Rect*r,unsigned n){
 Rect saved[4],before=*clip;memcpy(saved,r,sizeof saved);memset(&output.value,0x5a,sizeof output.value);
 CHECK(occlusion_partition(clip,r,n,&output.value)==0);CHECK(memcmp(clip,&before,sizeof before)==0&&memcmp(saved,r,sizeof saved)==0);verify_plan(clip,r,n,&output.value);guards();cases++;
}
static void reject_partition(const Rect*c,const Rect*r,uint64_t count){Plan before=output.value;CHECK(occlusion_partition(c,r,count,&output.value)!=0);CHECK(memcmp(&before,&output.value,sizeof before)==0);guards();rejects++;}
static int64_t model_bound(int64_t origin,int64_t sample,int64_t extent,uint64_t source){
 return origin+(int64_t)(((__uint128_t)(uint64_t)sample*(uint64_t)extent+source-1)/source);
}
static void preimage(uint64_t sw,uint64_t sh,const Rect*s,const Rect*t){
 Rect frozen_s=*s,frozen_t=*t;int64_t w=t->right-t->left,h=t->bottom-t->top;
 Rect expected={model_bound(t->left,s->left,w,sw),model_bound(t->top,s->top,h,sh),model_bound(t->left,s->right,w,sw),model_bound(t->top,s->bottom,h,sh)};
 memset(&interior.value,0xa5,sizeof interior.value);CHECK(occlusion_interior(sw,sh,s,t,&interior.value)==0);CHECK(memcmp(&interior.value,&expected,sizeof expected)==0);CHECK(memcmp(s,&frozen_s,sizeof *s)==0&&memcmp(t,&frozen_t,sizeof *t)==0);
 /* A second oracle enumerates actual floor samples; it does not invert ceil. */
 for(int64_t x=0;x<w;x++){uint64_t sx=(uint64_t)x*sw/(uint64_t)w;CHECK((s->left<=(int64_t)sx&&(int64_t)sx<s->right)==(interior.value.left<=t->left+x&&t->left+x<interior.value.right));}
 for(int64_t y=0;y<h;y++){uint64_t sy=(uint64_t)y*sh/(uint64_t)h;CHECK((s->top<=(int64_t)sy&&(int64_t)sy<s->bottom)==(interior.value.top<=t->top+y&&t->top+y<interior.value.bottom));}
 guards();interiors++;
}
static void reject_interior(uint64_t sw,uint64_t sh,const Rect*s,const Rect*t){Rect before=interior.value;CHECK(occlusion_interior(sw,sh,s,t,&interior.value)!=0);CHECK(memcmp(&before,&interior.value,sizeof before)==0);guards();rejects++;}
int main(void){
 output.pre=interior.pre=PRE;output.post=interior.post=POST;uint64_t sizes[3];occlusion_sizes(sizes);CHECK(sizes[0]==sizeof(Part)&&sizes[1]==sizeof(Plan)&&sizes[2]==81&&sizeof(Plan)==3248);
 Rect clip={0,0,100,100},r[4]={{1,2,91,92},{11,12,81,82},{21,22,71,72},{31,32,61,62}};
 partition(&clip,r,4);CHECK(grid81==1);for(unsigned n=0;n<=4;n++)partition(&clip,r,n);
 Rect full[4]={{0,0,100,100},{0,0,100,100},{0,0,100,100},{0,0,100,100}};partition(&clip,full,4);CHECK(output.value.count==1&&output.value.parts[0].first==4);
 Rect cross[4]={{10,-50,20,150},{-50,10,150,20},{50,-10,60,110},{-20,50,120,60}};partition(&clip,cross,4);
 Rect empty={7,3,7,80};partition(&empty,r,4);empty=(Rect){0,5,90,5};partition(&empty,r,4);
 for(unsigned iteration=0;iteration<6000;iteration++){
  int64_t x=(int64_t)(random64()%40)-20,y=(int64_t)(random64()%40)-20;clip=(Rect){x,y,x+(int64_t)(random64()%42),y+(int64_t)(random64()%42)};
  for(unsigned i=0;i<4;i++){int64_t l=(int64_t)(random64()%100)-50,t=(int64_t)(random64()%100)-50;r[i]=(Rect){l,t,l+(int64_t)(random64()%100),t+(int64_t)(random64()%100)};}
  partition(&clip,r,(unsigned)(random64()%5));
 }
 /* Entire signed coordinate domain is legal for partitioning: comparisons
    and compressed cells avoid a signed width/area overflow. */
 clip=(Rect){INT64_MIN,INT64_MIN,INT64_MAX,INT64_MAX};r[0]=(Rect){-10,-20,30,40};r[1]=(Rect){INT64_MIN,0,1,INT64_MAX};r[2]=(Rect){0,INT64_MIN,INT64_MAX,1};r[3]=(Rect){INT64_MAX-1,INT64_MAX-1,INT64_MAX,INT64_MAX};partition(&clip,r,4);
 CHECK(occlusion_partition(&clip,NULL,0,&output.value)==0);verify_plan(&clip,r,0,&output.value);
 /* Output may alias clip or opaque inputs: publication must follow snapshot. */
 clip=(Rect){0,0,100,100};memcpy(&output.value.parts[0].rect,&clip,sizeof clip);CHECK(occlusion_partition(&output.value.parts[0].rect,full,4,&output.value)==0);verify_plan(&clip,full,4,&output.value);
 memcpy(&output.value.parts[2],cross,sizeof cross);CHECK(occlusion_partition(&clip,(const Rect*)&output.value.parts[2],4,&output.value)==0);verify_plan(&clip,cross,4,&output.value);
 Rect bads[]={{2,0,1,1},{0,2,1,1}};
 reject_partition(NULL,r,1);reject_partition(&clip,NULL,1);reject_partition(&clip,r,5);reject_partition(&clip,r,UINT64_MAX);
 for(unsigned i=0;i<2;i++){reject_partition(&bads[i],r,4);Rect keep=r[3];r[3]=bads[i];reject_partition(&clip,r,4);r[3]=keep;}
 CHECK(occlusion_partition(&clip,r,4,NULL)!=0);
 for(uint64_t sw=1;sw<=13;sw++)for(uint64_t tw=1;tw<=13;tw++)for(uint64_t left=0;left<=sw;left++)for(uint64_t right=left;right<=sw;right++){
  Rect source={(int64_t)left,0,(int64_t)right,1},target={-7,-9,-7+(int64_t)tw,-8};preimage(sw,1,&source,&target);
 }
 for(unsigned i=0;i<2500;i++){
  uint64_t sw=1+random64()%8192,sh=1+random64()%8192;int64_t l=(int64_t)(random64()%(sw+1)),t=(int64_t)(random64()%(sh+1));Rect s={l,t,l+(int64_t)(random64()%(sw-(uint64_t)l+1)),t+(int64_t)(random64()%(sh-(uint64_t)t+1))};
  int64_t x=(int64_t)(random64()%30000)-15000,y=(int64_t)(random64()%30000)-15000;Rect target={x,y,x+1+(int64_t)(random64()%8192),y+1+(int64_t)(random64()%8192)};preimage(sw,sh,&s,&target);
 }
 Rect source={1,1,8191,8191},target={INT64_MIN,INT64_MAX-8192,INT64_MIN+8192,INT64_MAX};preimage(8192,8192,&source,&target);
 source=(Rect){0,0,1,1};target=(Rect){INT64_MAX-1,INT64_MIN,INT64_MAX,INT64_MIN+1};preimage(1,1,&source,&target);
 /* In-place source/target results use the same public pointer ABI. */
 source=(Rect){1,1,3,3};target=(Rect){-1,-2,4,5};Rect expected={1,0,3,4};CHECK(occlusion_interior(4,4,&source,&target,&source)==0&&memcmp(&source,&expected,sizeof expected)==0);
 source=(Rect){0,0,4,4};CHECK(occlusion_interior(4,4,&source,&target,&target)==0&&target.left==-1&&target.right==4);
 Rect valid={0,0,4,4},bad_source[]={{-1,0,1,1},{0,-1,1,1},{0,0,5,1},{0,0,1,5},{2,0,1,1},{0,2,1,1},{INT64_MIN,0,INT64_MAX,1}};
 for(unsigned i=0;i<sizeof bad_source/sizeof bad_source[0];i++)reject_interior(4,4,&bad_source[i],&valid);
 Rect bad_target[]={{0,0,0,1},{0,0,1,0},{0,0,8193,1},{INT64_MIN,0,INT64_MAX,1},{0,INT64_MIN,1,INT64_MAX}};
 for(unsigned i=0;i<sizeof bad_target/sizeof bad_target[0];i++)reject_interior(4,4,&valid,&bad_target[i]);
 reject_interior(0,4,&valid,&valid);reject_interior(4,0,&valid,&valid);reject_interior(8193,4,&valid,&valid);reject_interior(UINT64_MAX,4,&valid,&valid);reject_interior(4,4,NULL,&valid);reject_interior(4,4,&valid,NULL);CHECK(occlusion_interior(4,4,&valid,&valid,NULL)!=0);
 guards();CHECK(grid81>0);printf("occlusion oracle passed: plans=%llu preimages=%llu atomic-invalid=%llu grid81=%llu max-parts=%llu capacity81+full-i64+alias+guards=ok checks=%llu\n",(unsigned long long)cases,(unsigned long long)interiors,(unsigned long long)rejects,(unsigned long long)grid81,(unsigned long long)maxparts,(unsigned long long)checks);return 0;
}
