#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct {U version,owner,epoch,client,server,bytes,pixels,scale,glyphs;} Font;
extern ABI U font_memory_setup(U,U),font_memory_leaf(U,U),font_memory_mutate(U,U),font_memory_snapshot(U,void*),font_memory_commit(U),font_memory_abort(U),font_memory_get(U,U),font_memory_map(U,U,U,U,U),font_memory_copy(U,void*,U),font_memory_legacy(U,U);
extern ABI U font_desktop_setup(const void*),font_desktop_map(U),font_desktop_client(U,U,U,U,Font*),font_desktop_select(U),font_desktop_get(U,U);
extern ABI void font_paging_fault(U,U);
static unsigned checks,flushes,root_flushes,phase,unbinds;static U watch_id,watch_font,current_root;static unsigned char*fonts;static void*ram;
#define CK(x) do{++checks;if(!(x)){fprintf(stderr,"font check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static void die(const char*s){fprintf(stderr,"font ordering failed: %s\n",s);exit(1);}
static U address(U selected,U offset){return 0x4000000+selected*8192+(offset?4096:0);}
static U owner(U id){return ((id+1)<<32)|7;} // Catalog incarnation7 != root generation101.
ABI void __dong_panic(void){die("Dong panic");}
ABI U user_current_root(void){return current_root;}
/* Object-sharing paths are outside this font-portal probe and must not run. */
ABI U user_shared_barrier(void){die("unexpected object-sharing barrier");return 0;}
ABI U user_pcid_bind(U id,U root,U generation){(void)id;(void)root;(void)generation;die("unexpected bind");return 0;}
ABI U user_pcid_unbind(U id,U root){CK(id==watch_id&&root==0x100000+id*0x20000&&phase==3&&flushes);CK(!font_memory_get(1,id)&&!font_memory_get(2,id));unbinds++;return 1;}
ABI U user_entropy64(void*a,void*b){(void)a;(void)b;die("unexpected entropy");return 0;}
ABI void runtime_copy_bytes(void*d,const void*s,U n){memcpy(d,s,(size_t)n);}
ABI void runtime_invalidate(U address){(void)address;}
ABI void runtime_flush_root(void){root_flushes++;}
ABI void user_pcid_invalidate_root(U root){CK(root==0x160000||root==0x100000+watch_id*0x20000);}
ABI void user_pcid_flush_all(void){flushes++;if(phase==1||phase==2){if(font_memory_get(0,0)!=(phase==2))die("RESOURCE_FAILED cleared before full tag barrier");for(U p=0;p<2048;p++){if(font_memory_leaf(watch_id,0x72000000+p*4096)!=(address(watch_font,p)|2))die("partial or writable portal at barrier");}}if(phase==3&& (font_memory_get(1,watch_id)||font_memory_get(2,watch_id)))die("abort did not withdraw USER root before barrier");}
static void put32(void*p,uint32_t value){memcpy(p,&value,4);}
static void make_fonts(void){memset(fonts,0,5*8192);for(unsigned f=0;f<5;f++){unsigned char*p=fonts+f*8192;unsigned count=128+f,bitmap=48+count*32;memcpy(p,"DGFONT01",8);put32(p+8,1);put32(p+12,48);put32(p+16,count);put32(p+20,16+f*4);put32(p+24,48);put32(p+28,bitmap);put32(p+32,count);put32(p+36,16);put32(p+40,4);for(unsigned n=0;n<count;n++){unsigned char*r=p+48+n*32;put32(r,32+n);r[4]=r[6]=r[20]=1;put32(r+12,64);put32(r+16,n);p[bitmap+n]=(unsigned char)n;}}}
static void setup(U id){phase=flushes=root_flushes=unbinds=0;watch_id=id;watch_font=0;current_root=0;make_fonts();memset(ram,0,4096);font_paging_fault(0,0);CK(font_memory_setup(id,(U)(uintptr_t)ram)==0);CK(font_desktop_setup(fonts)==0);font_paging_fault(0,0);}
static void initial(U id){phase=1;watch_id=id;watch_font=0;CK(font_desktop_map(id)==0);phase=0;CK(font_desktop_get(0,id)==101&&font_desktop_get(1,id)==0);CK(font_memory_commit(id)==0);}
static void portal(U id,U selected){for(U p=0;p<2048;p++)CK(font_memory_leaf(id,0x72000000+p*4096)==(address(selected,p)|2));CK(!font_memory_leaf(id,0x71fff000)&&!font_memory_leaf(id,0x72800000));}
static void font_value(U id,U selected,Font*out){U scale=256+selected*64;CK(font_desktop_client(id,owner(id),33,scale,out)==0);CK(out->version==1&&out->owner==owner(id)&&out->epoch==33&&out->client==0x72000000&&out->server==0x72000000&&out->bytes==48+(128+selected)*33&&out->pixels==16+selected*4&&out->scale==scale&&out->glyphs==128+selected);CK((out->owner&0xffffffff)!=font_memory_get(3,id));}
static void unchanged(Font*out,const Font*before){CK(!memcmp(out,before,sizeof *out));}
int main(int argc,char**argv){CK(argc==2);const char*s=argv[1];
#ifdef _WIN32
 fonts=_aligned_malloc(5*8192,4096);ram=_aligned_malloc(4096,4096);
#else
 fonts=aligned_alloc(4096,5*8192);ram=aligned_alloc(4096,4096);
#endif
 CK(fonts&&ram);setup(8);Font out,poison;memset(&out,0xa5,sizeof out);poison=out;
 if(!strcmp(s,"initial-collision")){CK(font_memory_mutate(8,6)==0);unsigned char before[131104],after[131104];U n=font_memory_snapshot(8,before);CK(n==sizeof before);CK(font_desktop_map(8)!=0);CK(font_memory_snapshot(8,after)==n&&!memcmp(before,after,sizeof before));CK(!font_memory_leaf(8,0x72000000)&&!font_memory_get(0,0));}
 else if(!strcmp(s,"initial-abort")){font_paging_fault(17,0);CK(font_desktop_map(8)!=0&&!font_memory_get(0,0)&&!font_desktop_get(0,8));for(U i=0;i<16;i++)CK(font_memory_leaf(8,0x72000000+i*4096)==(address(0,i)|2));CK(!font_memory_leaf(8,0x72010000));phase=3;CK(font_memory_abort(8)==0&&unbinds==1);phase=0;for(U p=0;p<2048;p++)CK(!font_memory_leaf(8,0x72000000+p*4096));CK(font_memory_get(5,0)==1&&!font_memory_get(0,0));}
 else if(!strcmp(s,"wrong-slot")){U ids[]={0,1,2,3,4,5,6,13,16,UINT64_MAX};for(unsigned i=0;i<sizeof ids/sizeof ids[0];i++){CK(font_desktop_map(ids[i])!=0);CK(font_memory_map(ids[i],0,0,0x4000000,4272)!=0);CK(font_desktop_client(ids[i],owner(8),33,256,&out)!=0);unchanged(&out,&poison);}setup(13);CK(font_desktop_map(13)!=0&&font_memory_map(13,0,0,0x4000000,4272)!=0);}
 else if(!strcmp(s,"owned-span")){CK(font_memory_map(8,0,0,0x200000,4272)==0x04060004);CK(!font_memory_leaf(8,0x72000000)&&font_memory_get(5,0)==1);}
 else if(!strcmp(s,"unmapped-client")){CK(font_desktop_client(8,owner(8),33,256,&out)!=0);unchanged(&out,&poison);CK(!font_memory_leaf(8,0x72000000));}
 else {initial(8);
  if(!strcmp(s,"normal")){portal(8,0);font_value(8,0,&out);CK(font_memory_legacy(8,0)!=0&&font_memory_legacy(8,1)!=0);unsigned char data[16],old[16];memset(data,0x5a,sizeof data);memcpy(old,data,sizeof old);CK(font_memory_copy(8,data,0)==0x04060005&&!memcmp(data,old,sizeof data));CK(font_memory_copy(8,data,1)==0x04060004&&!memcmp(data,old,sizeof data));}
  else if(!strcmp(s,"dpi")){for(unsigned round=0;round<10;round++){U selected=(round+1)%5;phase=2;watch_id=3;watch_font=selected;CK(font_desktop_select(256+selected*64)==0);phase=0;portal(3,selected);watch_id=8;phase=2;font_value(8,selected,&out);phase=0;portal(8,selected);CK(!font_memory_get(0,0)&&font_desktop_get(1,8)==selected);}}
  else if(!strcmp(s,"late-replacement")){CK(font_desktop_select(320)==0);font_paging_fault(0,17);CK(font_desktop_client(8,owner(8),33,320,&out)!=0);unchanged(&out,&poison);CK(font_memory_get(0,0)&&font_desktop_get(1,8)==0);for(U p=0;p<16;p++)CK(font_memory_leaf(8,0x72000000+p*4096)==(address(1,p)|2));CK(font_memory_leaf(8,0x72010000)==(address(0,16)|2));CK(font_desktop_client(8,owner(8),33,320,&out)!=0&&font_memory_get(0,0));}
  else if(!strcmp(s,"writable")||!strcmp(s,"executable")||!strcmp(s,"wrong-physical")){U kind=!strcmp(s,"writable")?3:!strcmp(s,"executable")?4:5;CK(font_memory_mutate(8,kind)==0);CK(font_desktop_select(320)==0);unsigned char before[131104],after[131104];U n=font_memory_snapshot(8,before);CK(font_desktop_client(8,owner(8),33,320,&out)!=0);unchanged(&out,&poison);CK(font_memory_snapshot(8,after)==n&&!memcmp(before,after,sizeof before));CK(!font_memory_get(0,0)&&font_desktop_get(1,8)==0);}
  else if(!strcmp(s,"stale-generation")){CK(font_memory_mutate(8,1)==0);CK(font_desktop_client(8,owner(8),33,256,&out)!=0);unchanged(&out,&poison);portal(8,0);}
  else if(!strcmp(s,"bad-font")){put32(fonts+8192+48,0xd800);CK(font_desktop_select(320)!=0&&font_desktop_get(2,0)==0&&!font_memory_get(0,0));font_value(8,0,&out);portal(3,0);portal(8,0);}
  else if(!strcmp(s,"bad-owner")){U owners[]={0,8,((U)9<<32),((U)10<<32)|7};for(unsigned i=0;i<4;i++){CK(font_desktop_client(8,owners[i],33,256,&out)!=0);unchanged(&out,&poison);}CK(font_desktop_client(8,owner(8),0,256,&out)!=0);CK(font_desktop_client(8,owner(8),UINT64_C(0x100000000),256,&out)!=0);CK(font_desktop_client(8,owner(8),33,320,&out)!=0);unchanged(&out,&poison);}
  else if(!strcmp(s,"outside-stage")){CK(font_memory_map(8,0,0,0x4000000,4272)!=0&&!font_memory_get(0,0));portal(8,0);}
  else if(!strcmp(s,"current-root")){current_root=0x200000;CK(font_desktop_client(8,owner(8),33,256,&out)!=0);unchanged(&out,&poison);}
  else CK(0);
 }
 printf("GUI font native checks passed %u; scenario=%s; tag_barriers=%u; root_barriers=%u\n",checks,s,flushes,root_flushes);return 0;
}
