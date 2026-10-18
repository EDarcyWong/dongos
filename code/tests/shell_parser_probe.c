#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
typedef struct{uint64_t count,verb_start,verb_length,path_start,path_length,body_start,body_length;uint8_t bytes[8192];} Parsed;
extern uint64_t SYSV sp_size(void),sp_parse(const uint8_t*,uint64_t,Parsed*,Parsed*);
void SYSV __dong_panic(uint64_t e,const uint8_t*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"parser panic %llx\n",(unsigned long long)e);exit(9);}
static int all(const void*p,size_t n,uint8_t x){const uint8_t*b=p;for(size_t i=0;i<n;i++)if(b[i]!=x)return 0;return 1;}
int main(int argc,char**argv){
 if(argc!=2||sp_size()!=sizeof(Parsed)){return 2;}FILE*f=fopen(argv[1],"rb");if(!f)return 3;uint64_t records=0,errors=0;
 while(1){uint64_t h[6];size_t n=fread(h,8,6,f);if(!n)break;if(n!=6||h[0]>10000||h[3]+h[4]+h[5]>8192)return 4;
  uint8_t input[10000],expected[8192];if(fread(input,1,(size_t)h[0],f)!=h[0]||fread(expected,1,(size_t)(h[3]+h[4]+h[5]),f)!=h[3]+h[4]+h[5])return 5;
  struct{uint8_t before[32];Parsed value;uint8_t after[32];} g;memset(&g,0xa5,sizeof g);Parsed work;uint64_t e=sp_parse(input,h[0],&g.value,&work);
  if(e!=h[1]||!all(g.before,32,0xa5)||!all(g.after,32,0xa5)){fprintf(stderr,"shell parser check failed vector %llu error=%llx expected=%llx\n",(unsigned long long)records,(unsigned long long)e,(unsigned long long)h[1]);return 1;}
  if(e){errors++;if(!all(&g.value,sizeof g.value,0xa5))return 6;}
  else{Parsed*p=&g.value;if(p->count!=h[2]||p->verb_start!=0||p->verb_length!=h[3]||p->path_length!=h[4]||p->body_length!=h[5]||memcmp(p->bytes,expected,(size_t)(h[3]+h[4]+h[5]))||!all(p->bytes+h[3]+h[4]+h[5],8192-(size_t)(h[3]+h[4]+h[5]),0)){
    fprintf(stderr,"shell parser check failed vector %llu decoded output\n",(unsigned long long)records);return 1;}
   if(p->count>=2&&p->path_start!=p->verb_length){return 7;}if(p->count>=3&&p->body_start!=p->verb_length+p->path_length)return 8;
  }
  records++;
 }
 fclose(f);printf("shell parser checks passed %llu errors=%llu\n",(unsigned long long)records,(unsigned long long)errors);return 0;
}
