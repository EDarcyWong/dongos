bits 64
default rel
global transform_host_avx2,transform_upper_probe,transform_host_vendor
extern svc_transform_rows
section .text
; No AVX instruction occurs before CPUID.XSAVE/OSXSAVE/AVX, XCR0 x87+SSE+
; YMM and CPUID.7.AVX2 have all been independently observed on this host.
transform_host_avx2:
    push rbx
    xor eax,eax
    cpuid
    cmp eax,7
    jb .none
    mov eax,1
    cpuid
    and ecx,0x1c000000
    cmp ecx,0x1c000000
    jne .none
    xor ecx,ecx
    xgetbv
    and eax,7
    cmp eax,7
    jne .none
    mov eax,7
    xor ecx,ecx
    cpuid
    test ebx,1<<5
    jz .none
    mov eax,1
    pop rbx
    ret
.none:
    xor eax,eax
    pop rbx
    ret
; Return the real CPUID hypervisor vendor words without assuming a vendor.
transform_host_vendor:
    push rbx
    mov r8,rdi
    mov eax,0x40000000
    xor ecx,ecx
    cpuid
    mov [r8],ebx
    mov [r8+4],ecx
    mov [r8+8],edx
    pop rbx
    ret
; Called only after the independent gate succeeds and candidate flag=1.
; The sampler does not otherwise touch YMM15: this observes vzeroupper.
transform_upper_probe:
    sub rsp,8
    vpcmpeqd ymm15,ymm15,ymm15
    call svc_transform_rows
    vextracti128 xmm0,ymm15,1
    vptest xmm0,xmm0
    setnz al
    movzx eax,al
    vzeroupper
    add rsp,8
    ret
section .note.GNU-stack noalloc noexec nowrite progbits
