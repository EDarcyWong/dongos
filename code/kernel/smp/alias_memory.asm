bits 64
default rel
%include "smp.inc"
extern kernel_fail
global alias_local,alias_boxes_table,alias_ap_command

; Keep this exact descriptor synchronized with smp.alias_memory.Box and its
; independently checked compiler layout. None of these routines maps memory.
struc AliasBox
 .sequence: resq 1
 .ack: resq 1
 .command: resq 1
 .virtual: resq 1
 .value: resq 1
 .result: resq 1
 .fault: resq 1
 .root: resq 1
 .epoch: resq 1
 .cr0: resq 1
 .cr4: resq 1
 .efer: resq 1
 .pat: resq 1
 .cap: resq 1
 .default_type: resq 1
 .bits: resq 1
 .variable: resq 32
 .old_gate: resq 2
 .idt: resq 1
 .cpu: resq 1
endstruc
%if AliasBox_size != 416
%error incorrect alias hardware mailbox ABI
%endif
section .bss
align 8
alias_box_pointers: resq 16
section .text
alias_boxes_table:
 lea rax,[rel alias_box_pointers]
 ret

; Called from the existing ping ISR after all caller registers were saved.
; Outstanding commands exist only before scheduling; a sealed owner leaves
; sequence==ack, so subsequent ordinary ping interrupts have no side effects.
alias_ap_command:
 push rbx
 mov rax,[gs:SmpContext.logical_id]
 cmp rax,16
 jae .done
 lea rdx,[rel alias_box_pointers]
 mov rbx,[rdx+rax*8]
 test rbx,rbx
 jz .done
 mov rax,[rbx+AliasBox.sequence]
 cmp rax,[rbx+AliasBox.ack]
 jbe .done
 mov rdi,rbx
 mov rsi,[gs:SmpContext.self]
 call alias_local
 test rax,rax
 jz .ack
 mov [rbx+AliasBox.fault],rax
.ack:
 mfence
 mov rax,[rbx+AliasBox.sequence]
 mov [rbx+AliasBox.ack],rax
.done:
 pop rbx
 ret

; unsafe SysV(box,cpu)->status, IRQs masked, shared root and fixed topology.
; The command performs the actual operation before capturing controls/MSRs.
alias_local:
 push rbp
 push rbx
 push r12
 push r13
 push r14
 push r15
 sub rsp,24
 mov r12,rdi
 mov r13,rsi
 pushfq
 pop rax
 test eax,0x200
 jnz alias_hw_bad
 mov [r12+AliasBox.cpu],r13
 sidt [rsp]
 cmp word [rsp],14*16+15
 jb alias_hw_bad
 mov rax,[rsp+2]
 cmp rax,[r13+SmpContext.idt]
 jne alias_hw_bad
 mov [r12+AliasBox.idt],rax
 mov r14,[r12+AliasBox.command]
 cmp r14,1
 je alias_hw_capture
 cmp r14,2
 je alias_hw_read
 cmp r14,3
 je alias_hw_execute
 cmp r14,4
 je alias_hw_try_write
 cmp r14,5
 je alias_hw_flush
 cmp r14,6
 je alias_hw_cache
 cmp r14,7
 je alias_hw_pat
 cmp r14,8
 je alias_hw_page
 jmp alias_hw_bad
alias_hw_read:
 mov rax,[r12+AliasBox.virtual]
 mov rax,[rax]
 mov [r12+AliasBox.result],rax
 jmp alias_hw_capture
alias_hw_execute:
 ; The owned payload is exactly mov eax,imm32;ret, with no SIMD/ABI effects.
 call [r12+AliasBox.virtual]
 mov [r12+AliasBox.result],rax
 jmp alias_hw_capture
alias_hw_try_write:
 mov r15,[r12+AliasBox.idt]
 add r15,14*16
 mov rax,[r15]
 mov [r12+AliasBox.old_gate],rax
 mov rax,[r15+8]
 mov [r12+AliasBox.old_gate+8],rax
 lea rax,[rel alias_write_fault]
 mov [r15],ax
 shr rax,16
 mov [r15+6],ax
 shr rax,16
 mov [r15+8],eax
 mfence
 mov rdi,[r12+AliasBox.virtual]
 mov rsi,[r12+AliasBox.value]
 mov qword [r12+AliasBox.fault],0
alias_write_attempt:
 mov [rdi],rsi
alias_write_after:
 mov rax,[r12+AliasBox.old_gate]
 mov [r15],rax
 mov rax,[r12+AliasBox.old_gate+8]
 mov [r15+8],rax
 mfence
 mov rax,[r12+AliasBox.fault]
 mov [r12+AliasBox.result],rax
 jmp alias_hw_capture
alias_hw_flush:
 mov rax,cr3
 mov cr3,rax
 jmp alias_hw_capture
alias_hw_cache:
 wbinvd
 jmp alias_hw_capture
alias_hw_pat:
 mov r15,cr0
 mov rax,r15
 or eax,0x40000000
 and eax,0xdfffffff
 mov cr0,rax
 wbinvd
 mov rax,[r12+AliasBox.value]
 mov rdx,rax
 shr rdx,32
 mov ecx,0x277
 wrmsr
 wbinvd
 mov rax,cr3
 mov cr3,rax
 mov cr0,r15
 jmp alias_hw_capture
alias_hw_page:
 mov rax,[r12+AliasBox.virtual]
 invlpg [rax]
alias_hw_capture:
 mov rax,cr3
 mov [r12+AliasBox.root],rax
 mov rax,cr0
 mov [r12+AliasBox.cr0],rax
 mov rax,cr4
 mov [r12+AliasBox.cr4],rax
 mov rax,[r13+SmpContext.online_epoch]
 mov [r12+AliasBox.epoch],rax
 mov ecx,0xc0000080
 rdmsr
 shl rdx,32
 or rax,rdx
 mov [r12+AliasBox.efer],rax
 mov ecx,0x277
 rdmsr
 shl rdx,32
 or rax,rdx
 mov [r12+AliasBox.pat],rax
 mov eax,1
 cpuid
 shr ebx,24
 cmp rbx,[r13+SmpContext.apic_id]
 jne alias_hw_bad
 mov eax,0x80000008
 cpuid
 movzx eax,al
 mov [r12+AliasBox.bits],rax
 mov ecx,0xfe
 rdmsr
 shl rdx,32
 or rax,rdx
 mov [r12+AliasBox.cap],rax
 movzx r14d,al
 cmp r14d,16
 ja alias_hw_bad
 shl r14d,1
 mov ecx,0x2ff
 rdmsr
 shl rdx,32
 or rax,rdx
 mov [r12+AliasBox.default_type],rax
 xor r9d,r9d
alias_hw_variables:
 cmp r9d,32
 jae alias_hw_success
 xor eax,eax
 cmp r9d,r14d
 jae alias_hw_save_variable
 lea ecx,[r9d+0x200]
 rdmsr
 shl rdx,32
 or rax,rdx
alias_hw_save_variable:
 mov [r12+AliasBox.variable+r9*8],rax
 inc r9d
 jmp alias_hw_variables
alias_hw_success:
 xor eax,eax
 jmp alias_hw_return
alias_hw_bad:
 mov eax,0x06120001
alias_hw_return:
 add rsp,24
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbx
 pop rbp
 ret

; Only a present supervisor write fault at the exact owned probe instruction
; can resume. Neither arbitrary faults nor NX failures are recoverable here.
alias_write_fault:
 push rax
 push rcx
 push rdx
 push r8
 push r9
 push r10
 sub rsp,16
 sidt [rsp]
 mov r10,[rsp+2]
 lea r8,[rel alias_box_pointers]
 xor ecx,ecx
.find:
 cmp ecx,16
 jae .unexpected
 mov r9,[r8+rcx*8]
 test r9,r9
 jz .next
 cmp [r9+AliasBox.idt],r10
 je .found
.next:
 inc ecx
 jmp .find
.found:
 cmp qword [r9+AliasBox.command],4
 jne .unexpected
 cmp qword [r9+AliasBox.fault],0
 jne .unexpected
 lea rax,[rel alias_write_attempt]
 cmp [rsp+72],rax
 jne .unexpected
 mov rax,cr2
 cmp rax,[r9+AliasBox.virtual]
 jne .unexpected
 mov rax,[rsp+64]
 cmp rax,3
 jne .unexpected
 mov qword [r9+AliasBox.fault],1
 lea rax,[rel alias_write_after]
 mov [rsp+72],rax
 add rsp,16
 pop r10
 pop r9
 pop r8
 pop rdx
 pop rcx
 pop rax
 add rsp,8
 iretq
.unexpected:
 mov eax,0x06120002
 jmp kernel_fail
