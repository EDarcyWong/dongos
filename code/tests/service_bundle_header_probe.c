#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MSABI __attribute__((ms_abi))
#define LOAD_ERROR 0x8000000000000001ULL
extern uint64_t MSABI sb_bundle_header(const uint8_t*,uint64_t);
static uint8_t bytes[34*4096],before[34*4096];static uint64_t checks;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"BUNDLE_HEADER_MODEL_ASSERT line %u checks=%llu\n",__LINE__,(unsigned long long)checks);return 1;}}while(0)
static void put32(size_t at,uint32_t n){for(unsigned i=0;i<4;i++)bytes[at+i]=(uint8_t)(n>>(8*i));}
static void put64(size_t at,uint64_t n){for(unsigned i=0;i<8;i++)bytes[at+i]=(uint8_t)(n>>(8*i));}
static uint64_t fixture(unsigned count){memset(bytes,0,sizeof bytes);memcpy(bytes,"DONGSVC1",8);put32(8,1);put32(12,128);put32(16,128);put32(20,count);uint64_t total=(count+1ULL)*4096;put64(24,total);put64(32,4096);
 for(unsigned i=0;i<count&&i<32;i++){size_t at=128+i*128;bytes[at]='a';bytes[at+1]=(uint8_t)('0'+i/10);bytes[at+2]=(uint8_t)('0'+i%10);put64(at+32,4096+i*4096);put64(at+40,1);put64(at+48,2);bytes[4096+i*4096]=(uint8_t)(0xa5+i);}return total;}
static int check_result(uint64_t length,uint64_t expected){memcpy(before,bytes,sizeof bytes);CHECK(sb_bundle_header(bytes,length)==expected);CHECK(!memcmp(before,bytes,sizeof bytes));return 0;}
int main(void){
 const unsigned counts[]={1,16,18,31};for(unsigned c=0;c<4;c++){unsigned n=counts[c];uint64_t total=fixture(n);CHECK(bytes[4096]!=0);CHECK(!check_result(total,0));
  for(size_t at=72;at<128;at++){bytes[at]=0x81;CHECK(!check_result(total,LOAD_ERROR));bytes[at]=0;}
  for(size_t at=128+n*128;at<4096;at++){bytes[at]=0xa5;CHECK(!check_result(total,LOAD_ERROR));bytes[at]=0;}
  // Non-padding table bytes and the first payload byte are not header padding.
  bytes[128]=0x7f;bytes[4096]=0xff;CHECK(!check_result(total,0));
 }
 const uint32_t bad_counts[]={0,32,UINT32_MAX};for(unsigned i=0;i<3;i++){uint64_t total=fixture(1);put32(20,bad_counts[i]);CHECK(!check_result(total,LOAD_ERROR));}
 const uint64_t bad_lengths[]={0,1,4096,8191,8193,UINT64_MAX};for(unsigned i=0;i<6;i++){fixture(1);CHECK(!check_result(bad_lengths[i],LOAD_ERROR));}
 for(unsigned at=0;at<8;at++){uint64_t total=fixture(1);bytes[at]^=1;CHECK(!check_result(total,LOAD_ERROR));}
 const unsigned words[]={8,12,16};const uint32_t wrong[]={0,2,127,129,UINT32_MAX};for(unsigned i=0;i<3;i++)for(unsigned j=0;j<5;j++){uint64_t total=fixture(1);put32(words[i],wrong[j]);CHECK(!check_result(total,LOAD_ERROR));}
 const uint64_t offsets[]={0,128,4095,4097,UINT64_MAX};for(unsigned i=0;i<5;i++){uint64_t total=fixture(1);put64(32,offsets[i]);CHECK(!check_result(total,LOAD_ERROR));}
 puts("Boot bundle actual header passed counts=1,16,18,31 boundary32=reject payload31=nonzero");printf("Bundle header independent checks=%llu\n",(unsigned long long)checks);return 0;
}
