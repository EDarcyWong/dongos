; Original SmpContext and TLB mailboxes remain separate objects. No raw old
; handler is entered with the new GS prefix. Poll also runs during IF0 BKL wait.
bits 64
default rel
%include "user_entry.inc"
extern user_smp_arch_flush
extern smp_tlb_mailboxes
global user_smp_legacy_observe,user_smp_arch_legacy
section .text
; Pure native callable (Header*, Mailbox*, vector, flushed, observation).
; Acknowledgement of scope0/1 requires the hardware flush to have succeeded.
user_smp_legacy_observe:
    mov r9,rsi
    mov rsi,[rdi+UserSmpCpu.smp]
    mov rax,[rdi+UserSmpCpu.logical_id]
    cmp rax,[rsi+SmpContext.logical_id]
    jne .bad
    cmp [rsi+SmpContext.self],rsi
    jne .bad
    cmp rdx,SMP_STOP_VECTOR
    je .stop
    cmp rdx,SMP_PING_VECTOR
    jne .tlb
    cmp qword [rsi+SmpContext.state],SMP_ONLINE
    jne .done
    mov rax,[rsi+SmpContext.ping_request]
    cmp rax,[rsi+SmpContext.ping_ack]
    jbe .done
    mov [rsi+SmpContext.ping_ack],rax
    inc qword [rsi+SmpContext.irq_count]
    jmp .done
.tlb:
    cmp rdx,SMP_TLB_VECTOR
    jne .bad
    mov r10,[r9+SmpMailbox.sequence]
    cmp r10,[r9+SmpMailbox.ack]
    jbe .done
    mov rax,[r9+SmpMailbox.scope]
    cmp rax,2
    je .observation
    cmp rax,1
    ja .bad
    cmp rcx,1
    jne .bad                       ; never ACK before actual all-tag invalidation
    jmp .ack
.observation:
    cmp rcx,1
    jne .bad
    mov [r9+SmpMailbox.observed],r8
.ack:
    mfence
    mov [r9+SmpMailbox.ack],r10
    inc qword [rsi+SmpContext.irq_count]
.done:
    xor eax,eax
    ret
.stop:
    ; CPU offlining needs an explicit queue-offline/retire handshake. The old
    ; stop request cannot silently halt a CPU owning a new RUNNING reference.
    mov qword [rsi+SmpContext.last_error],SMP_ERR_ABORTED
.bad:
    mov eax,1
    ret

user_smp_arch_legacy:
    push rbx
    push r12
    push r13
    mov r12,[gs:UserCpu.continuation]
    mov r13,[gs:UserSmpCpu.smp]
    cmp qword [r13+SmpContext.state],SMP_STOPPING
    je .stop
    mov rdi,r12
    xor esi,esi
    mov edx,SMP_PING_VECTOR
    xor ecx,ecx
    xor r8d,r8d
    call user_smp_legacy_observe
    test eax,eax
    jnz .done
    mov rax,[gs:UserSmpCpu.logical_id]
    shl rax,6
    lea rbx,[rel smp_tlb_mailboxes]
    add rbx,rax
    mov rax,[rbx+SmpMailbox.sequence]
    cmp rax,[rbx+SmpMailbox.ack]
    jbe .success
    cmp qword [rbx+SmpMailbox.scope],2
    je .probe
    cmp qword [rbx+SmpMailbox.scope],1
    ja .bad
    mov rdi,[gs:UserSmpCpu.logical_id]
    call user_smp_arch_flush
    test eax,eax
    jnz .done
    xor r8d,r8d
    jmp .publish
.probe:
    mov rax,[rbx+SmpMailbox.virtual]
    mov rdx,0xffff800000000000
    cmp rax,rdx
    jb .bad
    test rax,7
    jnz .bad
    mov r8,[rax]
.publish:
    mov rdi,r12
    mov rsi,rbx
    mov edx,SMP_TLB_VECTOR
    mov ecx,1
    call user_smp_legacy_observe
    jmp .done
.stop:
    mov rdi,r12
    xor esi,esi
    mov edx,SMP_STOP_VECTOR
    call user_smp_legacy_observe
    jmp .done
.bad:
    mov qword [rbx+SmpMailbox.fault],SMP_ERR_ARGUMENT
    mov eax,1
    jmp .done
.success:
    xor eax,eax
.done:
    pop r13
    pop r12
    pop rbx
    ret
