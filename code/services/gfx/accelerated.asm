; SysV composition of disjoint premultiplied ARGB buffers. The DG caller
; validates complete source/destination spans and clip before entering.
bits 64
default rel
global svc_composite_rows
global svc_copy_rows
section .text
; Opaque WB-to-WB damage copy. Avoid NT stores to RAM which will immediately
; be read for alpha composition. Display presentation uses a separate NT path.
svc_copy_rows:
    push r12
    push r13
    lea r12,[rdx*4]
    lea r13,[rcx*4]
    lea rax,[r8*4]
    sub r12,rax
    sub r13,rax
.row:
    test r9,r9
    jz .done
    mov r10,r8
.wide:
    cmp r10,16
    jb .vector
    movdqu xmm0,[rdi]
    movdqu xmm1,[rdi+16]
    movdqu xmm2,[rdi+32]
    movdqu xmm3,[rdi+48]
    movdqu [rsi],xmm0
    movdqu [rsi+16],xmm1
    movdqu [rsi+32],xmm2
    movdqu [rsi+48],xmm3
    add rdi,64
    add rsi,64
    sub r10,16
    jmp .wide
.vector:
    cmp r10,4
    jb .tail
    movdqu xmm0,[rdi]
    movdqu [rsi],xmm0
    add rdi,16
    add rsi,16
    sub r10,4
    jmp .vector
.tail:
    test r10,r10
    jz .next
    mov eax,[rdi]
    mov [rsi],eax
    add rdi,4
    add rsi,4
    dec r10
    jmp .tail
.next:
    add rdi,r12
    add rsi,r13
    dec r9
    jmp .row
.done:
    pop r13
    pop r12
    ret
svc_composite_rows:
    push r12
    push r13
    lea r12,[rdx*4]
    lea r13,[rcx*4]
    lea rax,[r8*4]
    sub r12,rax
    sub r13,rax
.row:
    test r9,r9
    jz .done
    mov r10,r8
.group:
    cmp r10,4
    jb .pixel
    movdqu xmm0,[rdi]
    movdqa xmm1,xmm0
    psrld xmm1,24
    pcmpeqd xmm1,[rel all_255]
    pmovmskb eax,xmm1
    cmp eax,65535
    jne .pixel
    movdqu [rsi],xmm0
    add rdi,16
    add rsi,16
    sub r10,4
    jmp .group
.pixel:
    test r10,r10
    jz .next
    mov eax,[rdi]
    mov ecx,eax
    shr ecx,24
    test ecx,ecx
    jz .advance
    cmp ecx,255
    je .opaque
    movd xmm0,eax
    movd xmm1,[rsi]
    pxor xmm3,xmm3
    punpcklbw xmm0,xmm3
    punpcklbw xmm1,xmm3
    mov eax,255
    sub eax,ecx
    movd xmm2,eax
    pshuflw xmm2,xmm2,0
    pmullw xmm1,xmm2
    paddw xmm1,[rel round_128]
    movdqa xmm2,xmm1
    psrlw xmm2,8
    paddw xmm1,xmm2
    psrlw xmm1,8
    paddw xmm0,xmm1
    packuswb xmm0,xmm3
    movd [rsi],xmm0
    jmp .advance
.opaque:
    mov [rsi],eax
.advance:
    add rdi,4
    add rsi,4
    dec r10
    jmp .group
.next:
    add rdi,r12
    add rsi,r13
    dec r9
    jmp .row
.done:
    pop r13
    pop r12
    ret
global svc_composite_opacity_rows
; Seven SysV arguments; opacity is Q8 in [0,256], validated by DG caller.
svc_composite_opacity_rows:
    mov r11,[rsp+8]
    cmp r11,256
    je svc_composite_rows
    test r11,r11
    jz .return
    push r12
    push r13
    lea r12,[rdx*4]
    lea r13,[rcx*4]
    lea rax,[r8*4]
    sub r12,rax
    sub r13,rax
    movd xmm5,r11d
    pshuflw xmm5,xmm5,0
    punpcklqdq xmm5,xmm5
    pxor xmm3,xmm3
.row:
    test r9,r9
    jz .done
    mov r10,r8
.pixel:
    test r10,r10
    jz .next
    mov r11d,4
    cmp r10,2
    jb .single_load
    mov r11d,8
    movq xmm0,[rdi]
    movq xmm1,[rsi]
    jmp .blend
.single_load:
    movd xmm0,[rdi]
    movd xmm1,[rsi]
.blend:
    punpcklbw xmm0,xmm3
    pmullw xmm0,xmm5
    paddw xmm0,[rel round_128]
    psrlw xmm0,8
    pshuflw xmm2,xmm0,255
    pshufhw xmm2,xmm2,255
    movdqa xmm4,[rel opacity_255]
    psubw xmm4,xmm2
    punpcklbw xmm1,xmm3
    pmullw xmm1,xmm4
    paddw xmm1,[rel round_128]
    movdqa xmm2,xmm1
    psrlw xmm2,8
    paddw xmm1,xmm2
    psrlw xmm1,8
    paddw xmm0,xmm1
    packuswb xmm0,xmm3
    cmp r11,8
    jne .single_store
    movq [rsi],xmm0
    jmp .advance
.single_store:
    movd [rsi],xmm0
.advance:
    add rdi,r11
    add rsi,r11
    shr r11,2
    sub r10,r11
    jmp .pixel
.next:
    add rdi,r12
    add rsi,r13
    dec r9
    jmp .row
.done:
    pop r13
    pop r12
.return:
    ret
section .rodata
align 32
opacity_255: times 8 dw 255
all_255: times 4 dd 255
round_128: times 8 dw 128
section .note.GNU-stack noalloc noexec nowrite progbits
