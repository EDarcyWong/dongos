bits 64
default rel
%ifndef RUNTIME_LEVEL
%define RUNTIME_LEVEL 7
%endif
section .text
global user_shared_barrier
global user_shared_flush_mode,user_shared_local_flush
%if RUNTIME_LEVEL >= 7
extern dong_user_smp_barrier
%endif
%if RUNTIME_LEVEL >= 6
extern smp_invalidate_all
%endif
; Same serialized process/BKL transaction as page-table mutation. Every tag on
; BSP and each actual online AP must retire before object/map reuse.
user_shared_barrier:
 sub rsp,8
%if RUNTIME_LEVEL >= 7
 call dong_user_smp_barrier
 test rax,rax
 jz .success
 cmp rax,1                       ; only a genuinely inactive domain falls back
 jne .failed
%endif
 call user_shared_local_flush
 test rax,rax
 jnz .failed
%if RUNTIME_LEVEL >= 6
 xor edi,edi                     ; scope1 requires virtual=0
 mov esi,1                       ; real smp.tlb full-translation broadcast ABI
 call smp_invalidate_all
 test rax,rax
 jnz .failed
%endif
.success:
 mov eax,1
 add rsp,8
 ret
.failed:
 xor eax,eax
 add rsp,8
 ret

; Pure selector also tested natively. Software's old BSP PCID flag is not
; authoritative after P6 installs per-CPU PCIDs. PGE is forbidden by both
; admitted kernel contracts; accepting it would make CR3 reload incomplete.
user_shared_flush_mode:
 test rdi,1<<7
 jnz .global_unsupported
 test rdi,1<<17
 jnz .tagged
 xor eax,eax
 ret
.tagged:
 mov eax,1
 ret
.global_unsupported:
 mov eax,2
 ret

user_shared_local_flush:
 sub rsp,8
 mov rdi,cr4
 call user_shared_flush_mode
 cmp eax,1
 je .tagged
 test eax,eax
 jnz .failed
 mov rax,cr3
 mov cr3,rax
 jmp .success
.tagged:
 sub rsp,16
 mov qword [rsp],0
 mov qword [rsp+8],0
 mov eax,2                       ; every PCID, including globals
 invpcid rax,[rsp]
 add rsp,16
.success:
 xor eax,eax
 add rsp,8
 ret
.failed:
 mov eax,1
 add rsp,8
 ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
