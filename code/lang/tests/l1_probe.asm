; Independent SysV whole-pair stack rollback and RAX/RDX return probe.
bits 64
default rel
section .text
global l1_asm_roundtrip
extern l1_optional_stack
extern l1_result_stack
extern l1_event_stack
l1_asm_roundtrip:
    push rbp
    mov rbp,rsp
    sub rsp,16
    mov qword [rsp],1
    mov qword [rsp+8],0xff85
    call .arguments
    call l1_optional_stack
    cmp rax,1
    jne .failed
    cmp rdx,0xff85
    jne .failed
    mov qword [rsp],17
    mov qword [rsp+8],0
    call .arguments
    call l1_result_stack
    cmp rax,17
    jne .failed
    test rdx,rdx
    jnz .failed
    mov qword [rsp],2
    mov qword [rsp+8],0xfff9
    call .arguments
    call l1_event_stack
    cmp rax,2
    jne .failed
    cmp rdx,0xfff9
    jne .failed
    mov eax,313
    jmp .done
.failed:
    xor eax,eax
.done:
    mov rsp,rbp
    pop rbp
    ret
.arguments:
    mov edi,1
    mov esi,2
    mov edx,3
    mov ecx,4
    mov r8d,5
    mov r9d,6
    ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
