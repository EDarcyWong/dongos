; Replaces only hardware CPUID/RDSEED/RDRAND instructions in a private copy
; of context.asm. Carry results and architectural clobbers match the ISA.
bits 64
default rel
global user_test_cpuid,user_test_seed,user_test_random
extern drng_max,drng_seed,drng_random,seed_failures,random_failures
extern seed_calls,random_calls,cpuid_calls
section .text
user_test_cpuid:
    inc qword [rel cpuid_calls]
    cmp eax,0
    je .maximum
    cmp eax,1
    je .features
    cmp eax,7
    je .extended
    ud2
.maximum:
    mov eax,[rel drng_max]
    xor ebx,ebx
    xor ecx,ecx
    xor edx,edx
    ret
.features:
    xor eax,eax
    xor ebx,ebx
    mov ecx,[rel drng_random]
    shl ecx,30
    xor edx,edx
    ret
.extended:
    xor eax,eax
    mov ebx,[rel drng_seed]
    shl ebx,18
    xor ecx,ecx
    xor edx,edx
    ret
user_test_seed:
    inc qword [rel seed_calls]
    mov rax,[rel seed_calls]
    cmp rax,[rel seed_failures]
    jbe .failed
    mov rax,0x93be10ad73c84521
    stc
    ret
.failed:
    xor eax,eax
    clc
    ret
user_test_random:
    inc qword [rel random_calls]
    mov rax,[rel random_calls]
    cmp rax,[rel random_failures]
    jbe .failed
    mov rax,0xe327d813ab7ce410
    stc
    ret
.failed:
    xor eax,eax
    clc
    ret
