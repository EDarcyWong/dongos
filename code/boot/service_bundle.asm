; Optional UEFI file loading extension. All public entries use Win64 ABI.
; No calls after EBS, no global mutable state, no BootInfo v1 changes.
bits 64
default rel
%include "uefi.inc"
%include "service_handoff.inc"
SB_LOAD_ERROR equ 0x8000000000000001
SB_UNSUPPORTED equ 0x8000000000000003
SB_DEVICE_ERROR equ 0x8000000000000007

section .text
global service_bundle_load, service_handoff_validate

; RCX=BootServices*, RDX=open ESP root FileProtocol*, R8=*out handoff PA.
; Returns EFI_STATUS; failure preserves *out. Caller retains/closes root.
; Success owns three EfiLoaderData allocations through EBS/kernel handoff.
service_bundle_load:
    endbr64
    push rbp
    push rbx
    push rsi
    push rdi
    push r12
    push r13
    push r14
    push r15
    sub rsp, 632                     ; shadow/5th arg, locals,512B FileInfo; aligned
    cld
    mov r12, rcx
    mov r13, rdx
    mov r14, r8
    mov qword [rsp+40], 0             ; open file
    mov qword [rsp+56], 0             ; bundle PA
    mov qword [rsp+64], 0             ; arena PA
    mov qword [rsp+72], 0             ; handoff PA
    mov qword [rsp+80], 0             ; bundle pages
    test r12, r12
    jz .invalid
    test r13, r13
    jz .invalid
    test r14, r14
    jz .invalid
    mov rcx, r13
    lea rdx, [rsp+40]
    lea r8, [sb_path]
    mov r9d, EFI_FILE_MODE_READ
    mov qword [rsp+32], 0
    call [r13+EFI_FILE_PROTOCOL.Open]
    test rax, rax
    jnz .failed
    cmp qword [rsp+40], 0
    je .load_error
    mov qword [rsp+88], 512
    mov rcx, [rsp+40]
    lea rdx, [sb_file_info_guid]
    lea r8, [rsp+88]
    lea r9, [rsp+112]
    call [rcx+EFI_FILE_PROTOCOL.GetInfo]
    test rax, rax
    jnz .failed
    mov rax, [rsp+88]
    cmp rax, EFI_FILE_INFO_size
    jb .load_error
    cmp rax, 512
    ja .load_error
    mov rdx, [rsp+112+EFI_FILE_INFO.Size]
    cmp rdx, EFI_FILE_INFO_size
    jb .load_error
    cmp rdx, rax
    ja .load_error
    test qword [rsp+112+EFI_FILE_INFO.Attribute], EFI_FILE_DIRECTORY
    jnz .load_error
    mov r15, [rsp+112+EFI_FILE_INFO.FileSize]
    cmp r15, 8192
    jb .load_error
    cmp r15, SERVICE_BUNDLE_MAX_BYTES
    ja .load_error
    test r15, 4095
    jnz .load_error
    mov [rsp+48], r15
    mov rcx, r15
    shr rcx, 12
    mov [rsp+80], rcx
    lea rdx, [rsp+56]
    call .allocate
    test rax, rax
    jnz .failed
    mov rdi, [rsp+56]
    mov rcx, r15
    shr rcx, 3
    xor eax, eax
    rep stosq
    xor ebx, ebx                     ; bounded file cursor
.read_more:
    cmp rbx, r15
    je .read_eof
    mov rbp, r15
    sub rbp, rbx
    cmp rbp, 0x100000
    jbe .chunk
    mov ebp, 0x100000
.chunk:
    mov [rsp+96], rbp
    mov rcx, [rsp+40]
    lea rdx, [rsp+96]
    mov r8, [rsp+56]
    add r8, rbx
    call [rcx+EFI_FILE_PROTOCOL.Read]
    test rax, rax
    jnz .failed
    mov rax, [rsp+96]
    test rax, rax
    jz .load_error
    cmp rax, rbp
    ja .load_error
    add rbx, rax
    jmp .read_more
.read_eof:
    ; A growth race must not silently publish a truncated container.
    mov qword [rsp+96], 1
    mov rcx, [rsp+40]
    lea rdx, [rsp+96]
    lea r8, [rsp+111]
    call [rcx+EFI_FILE_PROTOCOL.Read]
    test rax, rax
    jnz .failed
    cmp qword [rsp+96], 0
    jne .load_error
    mov rcx, [rsp+56]
    mov rdx, r15
    call sb_bundle_header
    test rax, rax
    jnz .failed
    mov rcx, [rsp+40]
    mov qword [rsp+40], 0             ; Close consumes the handle; do not double close
    call [rcx+EFI_FILE_PROTOCOL.Close]
    test rax, rax
    jnz .failed
    mov ecx, SERVICE_ARENA_PAGES
    lea rdx, [rsp+64]
    call .allocate
    test rax, rax
    jnz .failed
    mov rdi, [rsp+64]
    mov ecx, SERVICE_ARENA_BYTES / 8
    xor eax, eax
    rep stosq                        ; no stale firmware bytes in future user RAM
    mov ecx, 1
    lea rdx, [rsp+72]
    call .allocate
    test rax, rax
    jnz .failed
    mov rdi, [rsp+72]
    mov ecx, 512
    xor eax, eax
    rep stosq
    mov rdi, [rsp+72]
    mov rax, SERVICE_HANDOFF_MAGIC
    mov [rdi+ServiceHandoff.magic], rax
    mov qword [rdi+ServiceHandoff.version], SERVICE_HANDOFF_VERSION
    mov qword [rdi+ServiceHandoff.size], ServiceHandoff_size
    mov qword [rdi+ServiceHandoff.flags], SERVICE_HANDOFF_LOADED
    mov rax, [rsp+56]
    mov [rdi+ServiceHandoff.bundle_physical], rax
    mov [rdi+ServiceHandoff.bundle_bytes], r15
    mov rax, [rsp+80]
    mov [rdi+ServiceHandoff.bundle_pages], rax
    mov rax, [rsp+64]
    mov [rdi+ServiceHandoff.arena_physical], rax
    mov qword [rdi+ServiceHandoff.arena_bytes], SERVICE_ARENA_BYTES
    mov qword [rdi+ServiceHandoff.arena_pages], SERVICE_ARENA_PAGES
    mov [rdi+ServiceHandoff.self_physical], rdi
    xor eax, eax
    xor ecx, ecx
.sum:
    add rax, [rdi+rcx*8]
    inc ecx
    cmp ecx, ServiceHandoff_size/8
    jb .sum
    neg rax
    mov [rdi+ServiceHandoff.checksum], rax
    mov rcx, rdi
    mov rdx, rdi
    call service_handoff_validate
    test rax, rax
    jnz .failed
    mov rax, [rsp+72]
    mov [r14], rax                    ; final publication only
    xor eax, eax
    jmp .done
.invalid:
    mov rax, EFI_INVALID_PARAMETER
    jmp .done
.load_error:
    mov rax, SB_LOAD_ERROR
.failed:
    mov [rsp+104], rax
    mov rcx, [rsp+40]
    test rcx, rcx
    jz .free_handoff
    mov qword [rsp+40], 0
    call [rcx+EFI_FILE_PROTOCOL.Close]
    test rax, rax
    jz .free_handoff
    mov rax, SB_DEVICE_ERROR
    mov [rsp+104], rax
.free_handoff:
    mov rcx, [rsp+72]
    mov edx, 1
    call .free
    mov rcx, [rsp+64]
    mov edx, SERVICE_ARENA_PAGES
    call .free
    mov rcx, [rsp+56]
    mov rdx, [rsp+80]
    call .free
    mov rax, [rsp+104]
.done:
    cld
    add rsp, 632
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    pop rbp
    ret

; Private Win64 helper with R12=BootServices. RCX=pages,RDX=*allocation.
; Store ownership before validating allocator output, so failure can clean up.
.allocate:
    sub rsp, 56
    mov [rsp+40], rcx
    mov [rsp+48], rdx
    mov dword [rsp+32], 0xffffffff
    mov dword [rsp+36], 0
    mov r8, rcx
    mov ecx, AllocateMaxAddress
    mov edx, EfiLoaderData
    lea r9, [rsp+32]
    call [r12+EFI_BOOT_SERVICES.AllocatePages]
    test rax, rax
    jnz .allocate_done
    mov rax, [rsp+32]
    mov rdx, [rsp+48]
    mov [rdx], rax
    test rax, rax
    jz .allocate_zero
    test rax, 4095
    jnz .allocate_bad
    mov rdx, [rsp+40]
    shl rdx, 12
    add rax, rdx
    jc .allocate_bad
    dec rax
    shr rax, 32
    jnz .allocate_bad
    xor eax, eax
    jmp .allocate_done
.allocate_bad:
    mov rax, SB_UNSUPPORTED
    jmp .allocate_done
.allocate_zero:
    xor ecx, ecx
    mov rdx, [rsp+40]
    call [r12+EFI_BOOT_SERVICES.FreePages]
    test rax, rax
    jz .allocate_bad
    mov rax, SB_DEVICE_ERROR
.allocate_done:
    add rsp, 56
    ret
; RCX=base,RDX=pages; zero means no acquired resource. Caller frame RSP+104
; is reached at +152 after our return address and40-byte call shadow frame.
.free:
    test rcx, rcx
    jz .free_done
    sub rsp, 40
    call [r12+EFI_BOOT_SERVICES.FreePages]
    test rax, rax
    jz .free_ok
    mov rax, SB_DEVICE_ERROR
    mov [rsp+152], rax
.free_ok:
    add rsp, 40
.free_done:
    ret

; Input RCX=readable complete container,RDX=exact byte length. Structural
; boot envelope only; kernel exec.bundle verifies every hash before use.
sb_bundle_header:
    mov rax, 0x31435653474e4f44       ; DONGSVC1
    cmp [rcx], rax
    jne .bad
    cmp dword [rcx+8], 1
    jne .bad
    cmp dword [rcx+12], 128
    jne .bad
    cmp dword [rcx+16], 128
    jne .bad
    cmp [rcx+24], rdx
    jne .bad
    cmp qword [rcx+32], 4096
    jne .bad
    mov r8d, [rcx+20]
    dec r8d
    cmp r8d, 30
    ja .bad
    inc r8d
    shl r8d, 7
    add r8d, 128
    mov r9d, 72
.reserved:
    cmp byte [rcx+r9], 0
    jne .bad
    inc r9d
    cmp r9d, 128
    jb .reserved
.padding:
    cmp r8d, 4096
    jae .valid
    cmp byte [rcx+r8], 0
    jne .bad
    inc r8d
    cmp r8d, 4096
    jb .padding
.valid:
    xor eax, eax
    ret
.bad:
    mov rax, SB_LOAD_ERROR
    ret

; RCX=readable handoff, RDX=its physical page base (may use a VA alias inRCX).
; Validates all fields, checksum, low4G ranges and pairwise allocations.
service_handoff_validate:
    test rcx, rcx
    jz .bad
    test rdx, rdx
    jz .bad
    test rdx, 4095
    jnz .bad
    mov rax, rdx
    add rax, 4095
    jc .bad
    shr rax, 32
    jnz .bad
    mov rax, SERVICE_HANDOFF_MAGIC
    cmp [rcx+ServiceHandoff.magic], rax
    jne .bad
    cmp qword [rcx+ServiceHandoff.version], SERVICE_HANDOFF_VERSION
    jne .bad
    cmp qword [rcx+ServiceHandoff.size], ServiceHandoff_size
    jne .bad
    cmp qword [rcx+ServiceHandoff.flags], SERVICE_HANDOFF_LOADED
    jne .bad
    cmp [rcx+ServiceHandoff.self_physical], rdx
    jne .bad
    mov r8, [rcx+ServiceHandoff.bundle_physical]
    test r8, r8
    jz .bad
    test r8, 4095
    jnz .bad
    mov r9, [rcx+ServiceHandoff.bundle_bytes]
    cmp r9, 8192
    jb .bad
    cmp r9, SERVICE_BUNDLE_MAX_BYTES
    ja .bad
    test r9, 4095
    jnz .bad
    mov rax, r9
    shr rax, 12
    cmp [rcx+ServiceHandoff.bundle_pages], rax
    jne .bad
    add r9, r8                        ; bundle exclusive end
    jc .bad
    lea rax, [r9-1]
    shr rax, 32
    jnz .bad
    mov r10, [rcx+ServiceHandoff.arena_physical]
    test r10, r10
    jz .bad
    test r10, 4095
    jnz .bad
    cmp qword [rcx+ServiceHandoff.arena_bytes], SERVICE_ARENA_BYTES
    jne .bad
    cmp qword [rcx+ServiceHandoff.arena_pages], SERVICE_ARENA_PAGES
    jne .bad
    mov r11, r10
    add r11, SERVICE_ARENA_BYTES
    jc .bad
    lea rax, [r11-1]
    shr rax, 32
    jnz .bad
    cmp r8, r11
    jae .bundle_disjoint
    cmp r10, r9
    jb .bad
.bundle_disjoint:
    lea rax, [rdx+4096]
    cmp rdx, r9
    jae .self_bundle_disjoint
    cmp r8, rax
    jb .bad
.self_bundle_disjoint:
    cmp rdx, r11
    jae .self_arena_disjoint
    cmp r10, rax
    jb .bad
.self_arena_disjoint:
    xor eax, eax
    xor edx, edx
.sum:
    add rax, [rcx+rdx*8]
    inc edx
    cmp edx, ServiceHandoff_size/8
    jb .sum
    test rax, rax
    jnz .bad
    ret
.bad:
    mov rax, EFI_INVALID_PARAMETER
    ret

section .rdata
sb_path: dw __utf16__("\SERVICES.BIN"), 0
sb_file_info_guid: dd 0x09576e92
                   dw 0x6d3f,0x11d2
                   db 0x8e,0x39,0x00,0xa0,0xc9,0x69,0x72,0x3b
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
