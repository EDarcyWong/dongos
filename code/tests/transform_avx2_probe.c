#include <stdint.h>
uint64_t transform_sse2_entries,transform_avx2_groups,transform_avx2_opaque;
uint64_t transform_avx2_partial,transform_avx2_tail4,transform_avx2_scalar;
#define main transform_original_main
#include "transform_probe.c"
#undef main
extern ABI uint64_t transform_host_avx2(void),transform_upper_probe(const uint64_t*);
extern ABI void transform_host_vendor(uint32_t*);
extern ABI uint64_t svc_gather_vendor_fast(uint64_t,uint64_t,uint64_t),feature_test_graphics_features(void);
extern uint64_t feature_test_avx2,feature_test_gather_fast;
uint64_t vendor_negative_hits;
ABI uint64_t service_main(void){return 0;}

static void vendor_case(const unsigned char *bytes){
 uint32_t words[3];memcpy(words,bytes,12);
 unsigned expected=memcmp(bytes,"TCGTCGTCGTCG",12)!=0;
 uint64_t actual=svc_gather_vendor_fast(words[0],words[1],words[2]);
 if(actual!=expected&&vendor_negative_hits)fprintf(stderr,"VENDOR_NEGATIVE_HIT %llu\n",(unsigned long long)vendor_negative_hits);
 CHECK(actual==expected);
}
static void vendor_tests(void){
 const unsigned char vendors[][13]={"TCGTCGTCGTCG","KVMKVMKVM\0\0\0","VMwareVMware","Microsoft Hv","XenVMMXenVMM","prl hyperv  ","bhyve bhyve ","GenuineIntel","            ","TCGTCGTCGTCX"};
 for(unsigned i=0;i<sizeof vendors/sizeof vendors[0];i++)vendor_case(vendors[i]);
 /* All 12 bytes must match: every other value of every byte must enable. */
 unsigned char variant[12];
 for(unsigned pos=0;pos<12;pos++)for(unsigned value=0;value<256;value++){
  memcpy(variant,"TCGTCGTCGTCG",12);variant[pos]=(unsigned char)value;vendor_case(variant);
 }
 uint32_t words[3];transform_host_vendor(words);uint64_t supported=transform_host_avx2();
 for(unsigned i=0;i<2;i++){
  feature_test_avx2=0x11223344;feature_test_gather_fast=0x55667788;
  CHECK(feature_test_graphics_features()==supported);CHECK(feature_test_avx2==supported);
  CHECK(feature_test_gather_fast==(supported&&memcmp(words,"TCGTCGTCGTCG",12)!=0));
 }
 printf("vendor oracle passed: cases=3082 exact-TCG-only=ok KVM+VMware+other=enabled actual-features-gate=%llu actual-gather=%llu reinitialize=ok\n",(unsigned long long)supported,(unsigned long long)feature_test_gather_fast);
}

static void extra_guard_pages(void){
 size_t page=4096;uint8_t*a,*b,*c;
#ifdef _WIN32
 a=VirtualAlloc(NULL,page*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);b=VirtualAlloc(NULL,page*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);c=VirtualAlloc(NULL,page*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);CHECK(a&&b&&c);DWORD old;CHECK(VirtualProtect(a+page,page,PAGE_NOACCESS,&old));CHECK(VirtualProtect(b+page,page,PAGE_NOACCESS,&old));CHECK(VirtualProtect(c+page,page,PAGE_NOACCESS,&old));
#else
 page=(size_t)sysconf(_SC_PAGESIZE);a=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);b=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);c=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);CHECK(a!=MAP_FAILED&&b!=MAP_FAILED&&c!=MAP_FAILED);CHECK(mprotect(a+page,page,PROT_NONE)==0);CHECK(mprotect(b+page,page,PROT_NONE)==0);CHECK(mprotect(c+page,page,PROT_NONE)==0);
#endif
 /* Offset-map, source pixel and destination all terminate immediately before
    a PROT_NONE page. Gather may not load a wider source span or map tail. */
 for(unsigned width=1;width<=17;width++)for(unsigned opacity=1;opacity<=256;opacity+=51){
  uint32_t*s=(uint32_t*)(a+page)-1,*d=(uint32_t*)(b+page)-width;uint16_t*offsets=(uint16_t*)(c+page)-width;
  *s=opacity==256?0xff123456:0x80201040;uint32_t wanted[17];
  for(unsigned i=0;i<width;i++){offsets[i]=0;d[i]=0xff987654;wanted[i]=over(d[i],*s,opacity);}
  uint64_t command[13]={(uintptr_t)s,(uintptr_t)d,4,width*4,width,1,(uintptr_t)offsets,0,0,1,0,1,opacity};
  CHECK(transform_register_probe(command)==0);CHECK(memcmp(wanted,d,width*4)==0);
  if(svc_avx2==1&&svc_gather_fast==1){for(unsigned i=0;i<width;i++){d[i]=0xff987654;}CHECK(transform_upper_probe(command)==0);CHECK(memcmp(wanted,d,width*4)==0);}
 }
#ifdef _WIN32
 CHECK(VirtualFree(a,0,MEM_RELEASE));CHECK(VirtualFree(b,0,MEM_RELEASE));CHECK(VirtualFree(c,0,MEM_RELEASE));
#else
 CHECK(munmap(a,page*2)==0);CHECK(munmap(b,page*2)==0);CHECK(munmap(c,page*2)==0);
#endif
}

int main(int argc,char**argv){
 if(argc==2&&strcmp(argv[1],"--vendor")==0){vendor_tests();return 0;}
 CHECK((argc==2||argc==3)&&argv[1][0]>='0'&&argv[1][0]<='2'&&argv[1][1]==0);
 uint64_t supported=transform_host_avx2();svc_avx2=(unsigned)(argv[1][0]-'0');svc_gather_fast=svc_avx2;
 if(argc==3){CHECK(argv[2][0]>='0'&&argv[2][0]<='2'&&argv[2][1]==0);svc_gather_fast=(unsigned)(argv[2][0]-'0');}
 unsigned gather=svc_avx2==1&&svc_gather_fast==1;
 if(gather&&!supported){printf("AVX2_UNSUPPORTED independent-CPUID-XCR0-gate=0 tested-AVX2=0\n");return 77;}
 CHECK(transform_original_main()==0);extra_guard_pages();
 if(gather){CHECK(transform_avx2_groups>0&&transform_avx2_opaque>0&&transform_avx2_partial>0&&transform_avx2_tail4>0&&transform_avx2_scalar>0);CHECK(transform_sse2_entries==0);}
 else{CHECK(transform_sse2_entries>0&&transform_avx2_groups==0&&transform_avx2_opaque==0&&transform_avx2_partial==0&&transform_avx2_tail4==0&&transform_avx2_scalar==0);}
 printf("formal branch evidence: host-gate=%llu forced-flag=%llu gather-flag=%llu sse2=%llu gather8=%llu opaque8=%llu partial8=%llu tail4=%llu scalar=%llu guarded-map-source-destination=ok vzeroupper=%s\n",(unsigned long long)supported,(unsigned long long)svc_avx2,(unsigned long long)svc_gather_fast,(unsigned long long)transform_sse2_entries,(unsigned long long)transform_avx2_groups,(unsigned long long)transform_avx2_opaque,(unsigned long long)transform_avx2_partial,(unsigned long long)transform_avx2_tail4,(unsigned long long)transform_avx2_scalar,gather?"observed":"not-executed");return 0;
}
