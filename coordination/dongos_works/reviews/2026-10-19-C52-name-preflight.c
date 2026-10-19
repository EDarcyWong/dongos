/* Observe reads without a crash: Windows clears PAGE_GUARD and the handler
 * resumes the same instruction. All declared name bytes are allocated. */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef struct { uint64_t op,dst,left,right,imm; } Ins;
typedef struct { const uint8_t *m; uint64_t mn; const uint8_t *i; uint64_t in;
    uint64_t parameters,slots; const Ins *ir; uint64_t count,ret; } Fn;
extern uint64_t ABI dong_c52_emit(const Fn*,uint64_t,uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n) {
    (void)k;(void)l;(void)f;(void)n;exit(87);
}
static uint8_t *watched;
static volatile LONG reads;
static LONG CALLBACK observe(PEXCEPTION_POINTERS event) {
    EXCEPTION_RECORD *record=event->ExceptionRecord;
    uintptr_t address=(uintptr_t)record->ExceptionInformation[1];
    if(record->ExceptionCode==0x80000001u && record->NumberParameters>=2 &&
       address>=(uintptr_t)watched && address<(uintptr_t)watched+4096) {
        if(record->ExceptionInformation[0]!=0)exit(88);
        InterlockedIncrement(&reads);
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
static void run(unsigned item,unsigned length,unsigned count) {
    watched=VirtualAlloc(NULL,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!watched)exit(90);
    memset(watched,'m',4096);
    Fn functions[2]={{watched,length,(const uint8_t*)"a",1,1,1,NULL,0,0},
                     {watched,length,(const uint8_t*)"b",1,1,1,NULL,0,0}};
    if(item) {
        functions[0].m=functions[1].m=(const uint8_t*)"m";
        functions[0].mn=functions[1].mn=1;
        functions[0].i=functions[1].i=watched;
        functions[0].in=functions[1].in=length;
    }
    Fn before[2];memcpy(before,functions,sizeof(functions));
    uint64_t written=0xa5a5a5a5a5a5a5a5ull;
    DWORD old;reads=0;
    if(!VirtualProtect(watched,4096,PAGE_READONLY|PAGE_GUARD,&old))exit(91);
    uint64_t status=dong_c52_emit(functions,count,NULL,0,NULL,0,&written);
    LONG observed=reads;
    int unchanged=written==0xa5a5a5a5a5a5a5a5ull&&!memcmp(before,functions,sizeof(functions));
    printf("{\"field\":\"%s\",\"length\":%u,\"functions\":%u,\"status\":%u,\"name_page_reads\":%ld,\"output_and_table_unchanged\":%s}\n",
           item?"item":"module",length,count,(unsigned)status,(long)observed,unchanged?"true":"false");
    if(!unchanged || status!=(length==64?3u:1u))exit(92);
    if(!VirtualFree(watched,0,MEM_RELEASE))exit(93);
}
int main(void) {
    PVOID handler=AddVectoredExceptionHandler(1,observe);if(!handler)return 94;
    for(unsigned item=0;item<2;item++) {
        run(item,64,1);  /* Valid name: the observation must detect the real read. */
        run(item,65,1);  /* C48 itself rejects an invalid name without a read. */
        run(item,65,2);  /* Duplicate scan reads the invalid name before C48. */
    }
    if(!RemoveVectoredExceptionHandler(handler))return 95;
    return 0;
}
