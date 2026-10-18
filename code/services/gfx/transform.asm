; Exact 128-column-strip sampler. DG validates all borrows and fills a live
; u16 byte-offset map. Four bounded scalar loads gather pixels into SSE2;
; no full-width speculative source load is made at a texture/row boundary.
bits 64
default rel
global svc_transform_rows
extern svc_avx2
extern svc_gather_fast
%ifdef TRANSFORM_PROBE
extern transform_sse2_entries,transform_avx2_groups,transform_avx2_opaque
extern transform_avx2_partial,transform_avx2_tail4,transform_avx2_scalar
%endif
%macro COUNT 1
%ifdef TRANSFORM_PROBE
    inc qword [rel %1]
%endif
%endmacro

%macro GATHER4 0
    movzx edx,word [rsi]
    movd xmm0,[rbx+rdx]
    movzx edx,word [rsi+2]
    movd xmm1,[rbx+rdx]
    punpckldq xmm0,xmm1
    movzx edx,word [rsi+4]
    movd xmm2,[rbx+rdx]
    movzx edx,word [rsi+6]
    movd xmm4,[rbx+rdx]
    punpckldq xmm2,xmm4
    punpcklqdq xmm0,xmm2
%endmacro

; src,dst are unpacked two-pixel word vectors. Rounding is exactly
; min(255,src + floor((dst*(255-srcAlpha)+127)/255)) for every channel.
%macro OVER2 2
    pshuflw xmm4,%1,255
    pshufhw xmm4,xmm4,255
    movdqa xmm10,xmm7
    psubw xmm10,xmm4
    pmullw %2,xmm10
    paddw %2,xmm8
    movdqa xmm10,%2
    psrlw xmm10,8
    paddw %2,xmm10
    psrlw %2,8
    paddw %1,%2
%endmacro

; Two independently emitted loops hoist the opacity decision out of every
; row/pixel. All XMM registers are volatile under the declared SysV ABI.
%macro ROWS 1
%%row:
    test r13,r13
    jz transform_done
    mov rax,r12
    imul rax,[r15+16]
    mov rbx,[r15]
    add rbx,rax
    mov rdi,r14
    mov rcx,[r15+32]
    mov rsi,[r15+48]
%%group:
    cmp rcx,4
    jb %%tail
    GATHER4
%if %1 == 256
    movdqa xmm1,xmm0
    psrld xmm1,24
    pcmpeqd xmm1,xmm9
    pmovmskb eax,xmm1
    cmp eax,65535
    je %%opaque_group
%endif
    movdqu xmm1,[rdi]
    movdqa xmm2,xmm0
    movdqa xmm6,xmm1
    punpcklbw xmm0,xmm3
    punpckhbw xmm2,xmm3
    punpcklbw xmm1,xmm3
    punpckhbw xmm6,xmm3
%if %1 != 256
    pmullw xmm0,xmm5
    paddw xmm0,xmm8
    psrlw xmm0,8
    pmullw xmm2,xmm5
    paddw xmm2,xmm8
    psrlw xmm2,8
%endif
    OVER2 xmm0,xmm1
    OVER2 xmm2,xmm6
    packuswb xmm0,xmm2
%%opaque_group:
    movdqu [rdi],xmm0
    add rdi,16
    add rsi,8
    sub rcx,4
    jmp %%group
%%tail:
    test rcx,rcx
    jz %%next_row
    movzx edx,word [rsi]
    mov eax,[rbx+rdx]
    test eax,eax
    jz %%advance
%if %1 == 256
    mov edx,eax
    shr edx,24
    cmp edx,255
    je %%opaque_pixel
%endif
    movd xmm0,eax
    punpcklbw xmm0,xmm3
%if %1 != 256
    pmullw xmm0,xmm5
    paddw xmm0,xmm8
    psrlw xmm0,8
%endif
    movd xmm1,[rdi]
    punpcklbw xmm1,xmm3
    OVER2 xmm0,xmm1
    packuswb xmm0,xmm3
    movd [rdi],xmm0
    jmp %%advance
%%opaque_pixel:
    mov [rdi],eax
%%advance:
    add rdi,4
    add rsi,2
    dec rcx
    jmp %%tail
%%next_row:
    add r14,[r15+24]
    add r12,[r15+72]
    add rbp,[r15+80]
    cmp rbp,[r15+88]
    jb %%y_ready
    sub rbp,[r15+88]
    inc r12
%%y_ready:
    dec r13
    jmp %%row
%endmacro

; VEX128 tail operations never overwrite the 256-bit constant registers.
%macro VGATHER4 0
    movzx edx,word [rsi]
    vmovd xmm0,[rbx+rdx]
    movzx edx,word [rsi+2]
    vmovd xmm1,[rbx+rdx]
    vpunpckldq xmm0,xmm0,xmm1
    movzx edx,word [rsi+4]
    vmovd xmm2,[rbx+rdx]
    movzx edx,word [rsi+6]
    vmovd xmm4,[rbx+rdx]
    vpunpckldq xmm2,xmm2,xmm4
    vpunpcklqdq xmm0,xmm0,xmm2
%endmacro
%macro VOVER 3
    vpshuflw %3,%1,255
    vpshufhw %3,%3,255
%ifidn %3,ymm4
    vpsubw ymm10,ymm7,%3
    vpmullw %2,%2,ymm10
    vpaddw %2,%2,ymm8
    vpsrlw ymm10,%2,8
    vpaddw %2,%2,ymm10
%else
    vpsubw xmm10,xmm7,%3
    vpmullw %2,%2,xmm10
    vpaddw %2,%2,xmm8
    vpsrlw xmm10,%2,8
    vpaddw %2,%2,xmm10
%endif
    vpsrlw %2,%2,8
    vpaddw %1,%1,%2
%endmacro
%macro AVXROWS 1
%%row:
    test r13,r13
    jz transform_avx_done
    mov rax,r12
    imul rax,[r15+16]
    mov rbx,[r15]
    add rbx,rax
    mov rdi,r14
    mov rcx,[r15+32]
    mov rsi,[r15+48]
%%group8:
    cmp rcx,8
    jb %%group4
    COUNT transform_avx2_groups
    vpmovzxwd ymm12,oword [rsi]
    vpcmpeqd ymm11,ymm11,ymm11
    vpgatherdd ymm0,[rbx+ymm12],ymm11
%if %1 == 256
    vpsrld ymm1,ymm0,24
    vpcmpeqd ymm1,ymm1,ymm9
    vpmovmskb eax,ymm1
    cmp eax,-1
    je %%opaque8
%endif
    vmovdqu ymm1,[rdi]
    vpunpcklbw ymm2,ymm0,ymm3
    vpunpckhbw ymm6,ymm0,ymm3
    vpunpcklbw ymm0,ymm1,ymm3
    vpunpckhbw ymm1,ymm1,ymm3
%if %1 != 256
    COUNT transform_avx2_partial
    vpmullw ymm2,ymm2,ymm5
    vpaddw ymm2,ymm2,ymm8
    vpsrlw ymm2,ymm2,8
    vpmullw ymm6,ymm6,ymm5
    vpaddw ymm6,ymm6,ymm8
    vpsrlw ymm6,ymm6,8
%endif
    VOVER ymm2,ymm0,ymm4
    VOVER ymm6,ymm1,ymm4
    vpackuswb ymm0,ymm2,ymm6
    jmp %%write8
%%opaque8:
    COUNT transform_avx2_opaque
%%write8:
    vmovdqu [rdi],ymm0
    add rdi,32
    add rsi,16
    sub rcx,8
    jmp %%group8
%%group4:
    cmp rcx,4
    jb %%scalar
    COUNT transform_avx2_tail4
    VGATHER4
%if %1 == 256
    vpsrld xmm1,xmm0,24
    vpcmpeqd xmm1,xmm1,xmm9
    vpmovmskb eax,xmm1
    cmp eax,65535
    je %%opaque4
%endif
    vmovdqu xmm1,[rdi]
    vmovdqa xmm2,xmm0
    vmovdqa xmm6,xmm1
    vpunpcklbw xmm0,xmm0,xmm3
    vpunpckhbw xmm2,xmm2,xmm3
    vpunpcklbw xmm1,xmm1,xmm3
    vpunpckhbw xmm6,xmm6,xmm3
%if %1 != 256
    vpmullw xmm0,xmm0,xmm5
    vpaddw xmm0,xmm0,xmm8
    vpsrlw xmm0,xmm0,8
    vpmullw xmm2,xmm2,xmm5
    vpaddw xmm2,xmm2,xmm8
    vpsrlw xmm2,xmm2,8
%endif
    VOVER xmm0,xmm1,xmm4
    VOVER xmm2,xmm6,xmm4
    vpackuswb xmm0,xmm0,xmm2
%%opaque4:
    vmovdqu [rdi],xmm0
    add rdi,16
    add rsi,8
    sub rcx,4
%%scalar:
    test rcx,rcx
    jz %%next_row
    COUNT transform_avx2_scalar
    movzx edx,word [rsi]
    mov eax,[rbx+rdx]
    test eax,eax
    jz %%advance
%if %1 == 256
    mov edx,eax
    shr edx,24
    cmp edx,255
    je %%opaque_pixel
%endif
    vmovd xmm0,eax
    vpunpcklbw xmm0,xmm0,xmm3
%if %1 != 256
    vpmullw xmm0,xmm0,xmm5
    vpaddw xmm0,xmm0,xmm8
    vpsrlw xmm0,xmm0,8
%endif
    vmovd xmm1,[rdi]
    vpunpcklbw xmm1,xmm1,xmm3
    VOVER xmm0,xmm1,xmm4
    vpackuswb xmm0,xmm0,xmm3
    vmovd [rdi],xmm0
    jmp %%advance
%%opaque_pixel:
    mov [rdi],eax
%%advance:
    add rdi,4
    add rsi,2
    dec rcx
    jmp %%scalar
%%next_row:
    add r14,[r15+24]
    add r12,[r15+72]
    add rbp,[r15+80]
    cmp rbp,[r15+88]
    jb %%y_ready
    sub rbp,[r15+88]
    inc r12
%%y_ready:
    dec r13
    jmp %%row
%endmacro

section .text
svc_transform_rows:
    push rbx
    push rbp
    push r12
    push r13
    push r14
    push r15
    mov r15,rdi
    mov r14,[r15+8]
    mov r13,[r15+40]
    mov r12,[r15+56]
    mov rbp,[r15+64]
    cmp qword [rel svc_avx2],1
    jne transform_sse2
    cmp qword [rel svc_gather_fast],1
    je transform_avx2
transform_sse2:
    COUNT transform_sse2_entries
    movq xmm5,[r15+96]
    pshuflw xmm5,xmm5,0
    punpcklqdq xmm5,xmm5
    pxor xmm3,xmm3
    movdqa xmm7,[rel transform_255]
    movdqa xmm8,[rel transform_round_128]
    movdqa xmm9,[rel transform_all_255]
    cmp qword [r15+96],256
    jne transform_partial
    ROWS 256
transform_partial:
    ROWS 0
transform_avx2:
    vpxor ymm3,ymm3,ymm3
    vpbroadcastw ymm5,word [r15+96]
    vpbroadcastw ymm7,word [rel transform_255]
    vpbroadcastw ymm8,word [rel transform_round_128]
    vpbroadcastd ymm9,dword [rel transform_all_255]
    cmp qword [r15+96],256
    jne transform_avx_partial
    AVXROWS 256
transform_avx_partial:
    AVXROWS 0
transform_avx_done:
    vzeroupper
transform_done:
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rbx
    ret
section .rodata
align 16
transform_255: times 8 dw 255
transform_round_128: times 8 dw 128
transform_all_255: times 4 dd 255
section .note.GNU-stack noalloc noexec nowrite progbits
