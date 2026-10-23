; Identical UC/WC qword pattern. CPUID serializes both TSC boundaries;
; SFENCE drains preceding WC stores before the ending serialization.
bits 64
default rel
section .text
global wc_benchmark_trial,wc_benchmark_restore
wc_benchmark_trial:
 push rbx
 mov r9,rdx
 mov r11,rsi
 shr r11,3
 xor eax,eax
 cpuid
 rdtsc
 lfence
 shl rdx,32
 or rax,rdx
 mov r8,rax
 xor ecx,ecx
.write:
 mov rax,r9
 xor rax,rcx
 mov [rdi+rcx*8],rax
 inc rcx
 cmp rcx,r11
 jb .write
 sfence
 xor eax,eax
 cpuid
 rdtsc
 lfence
 shl rdx,32
 or rax,rdx
 sub rax,r8
 pop rbx
 ret
wc_benchmark_restore:
 mov rcx,rdx
 cld
 rep movsb
 sfence
 ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
