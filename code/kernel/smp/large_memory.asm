bits 64
default rel
extern large_memory_data,large_memory_raw,large_memory_pt
extern smp_invalidate_all,kernel_fail
extern dong_shared_large_readers
global shared_large_readers
global shared_large_flush,shared_large_data,shared_large_raw,shared_large_pt
section .text
shared_large_readers:
    jmp dong_shared_large_readers
; Read-only, bounded hardware helpers use the same now-empty window as the
; pre-AP proof. The Dong owner holds the distinct current buddy lease.
shared_large_data:
    jmp large_memory_data
shared_large_raw:
    jmp large_memory_raw
shared_large_pt:
    jmp large_memory_pt
; IF=0 and PGE/PCIDE off are checked at each actual hardware barrier.
; Never return to a publisher/reclaimer unless every AP acknowledged.
shared_large_flush:
    pushfq
    pop rax
    test eax,0x200
    jnz .bad
    mov rax,cr4
    test eax,0x20080
    jnz .bad
    cmp rdi,1
    je .page
    cmp rdi,2
    jne .bad
    mov rax,cr3
    mov cr3,rax
    xor edi,edi
    mov esi,1
    jmp .readers
.page:
    invlpg [rsi]
    mov rdi,rsi
    xor esi,esi
.readers:
    sub rsp,8
    call smp_invalidate_all
    add rsp,8
    test rax,rax
    jnz .bad
    ret
.bad:
    mov eax,0x060f0001
    jmp kernel_fail
