; Independent hand-written scalar SysV x86-64 references. Same algorithms,
; input order, forward loop bounds and call boundary as kernels.dg; no SIMD,
; formula substitution or REP-copy shortcut. All registers used are volatile.
bits 64
default rel
section .text
global ref_sum, ref_lcg, ref_mix, ref_array_sum, ref_array_copy
align 16
ref_sum:
    cld
    xor eax,eax
    xor ecx,ecx
.loop:
    cmp rcx,rdi
    jae .done
    add rax,rcx
    inc rcx
    jmp .loop
.done:
    cld
    ret
align 16
ref_lcg:
    cld
    mov rax,rsi
    xor ecx,ecx
    mov r8,6364136223846793005
    mov r9,1442695040888963407
.loop:
    cmp rcx,rdi
    jae .done
    imul rax,r8
    add rax,r9
    inc rcx
    jmp .loop
.done:
    cld
    ret
align 16
ref_mix:
    cld
    mov rax,rsi
    xor ecx,ecx
    mov r8,0x9e3779b97f4a7c15
.loop:
    cmp rcx,rdi
    jae .done
    mov rdx,rax
    xor rdx,rcx
    test dl,1
    jnz .odd
    add rax,rcx
    xor rax,r8
    jmp .advance
.odd:
    imul rax,rax,3
    xor rax,rcx
.advance:
    inc rcx
    jmp .loop
.done:
    cld
    ret
align 16
ref_array_sum:
    cld
    xor eax,eax
    xor ecx,ecx
.loop:
    cmp rcx,rsi
    jae .done
    add rax,[rdi+rcx*8]
    inc rcx
    jmp .loop
.done:
    cld
    ret
align 16
ref_array_copy:
    cld
    xor ecx,ecx
.loop:
    cmp rcx,rdx
    jae .done
    mov r8,[rsi+rcx*8]
    mov [rdi+rcx*8],r8
    inc rcx
    jmp .loop
.done:
    mov rax,rdx
    cld
    ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
