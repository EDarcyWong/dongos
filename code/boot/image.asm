; DongOS v1 image validation and bounded decoding. All public entries use the
; Microsoft x64 ABI. No firmware, SIMD, CPU SHA extensions or mutable globals.
; SHA-256 follows FIPS 180-4 sections 5/6.2; LZ4 follows lz4/doc/lz4_Block_format.md.
bits 64
default rel
%ifndef IMAGE_FILE_SIZE
    %include "image_manifest.inc"
%endif

section .text
global image_verify, image_unpack, sha256, lz4_decode

; Function: Validate all v1 header fields and whole-file loader-bound SHA-256.
; Input: RCX = image pointer, RDX = image byte length.
; Output: EAX = 0 success, 1 invalid; no image bytes modified.
; Clobbers: RAX, RCX, RDX, R8-R11, flags; nonvolatile registers preserved.
; Context: Boot only; readable input buffer required; no locks.
image_verify:
    push rbx
    push rsi
    sub rsp, 72                 ; 32 shadow + 32 digest + 8 alignment
    mov rbx, rcx
    mov rsi, rdx
    call image_header
    test eax, eax
    jnz .done
    cmp rsi, IMAGE_FILE_SIZE
    jne .bad
    mov rcx, rbx
    mov rdx, rsi
    lea r8, [rsp + 32]
    call sha256
    lea rdx, [expected_hash]
    lea r8, [rsp + 32]
    mov ecx, 32
    xor eax, eax
.compare:
    movzx r9d, byte [r8]
    xor r9b, [rdx]
    or eax, r9d
    inc r8
    inc rdx
    loop .compare
    test eax, eax
    setnz al
    movzx eax, al
    jmp .done
.bad:
    mov eax, 1
.done:
    add rsp, 72
    pop rsi
    pop rbx
    ret

; Function: Validate header and decompress into a separately allocated buffer.
; Input: RCX = image, RDX = file bytes, R8 = destination, R9 = capacity.
; Output: EAX = 0 success, 1 invalid; destination may be partial on failure.
; Clobbers: RAX, RCX, RDX, R8-R11, flags; nonvolatile registers preserved.
; Context: Boot only; caller must first image_verify; readable/writable buffers.
image_unpack:
    sub rsp, 40
    call image_header          ; header helper preserves input argument registers
    add rsp, 40
    test eax, eax
    jnz .bad
    mov rax, [rcx + 24]
    cmp r9, rax
    jb .bad
    mov r9, rax
    mov rdx, [rcx + 16]
    add rcx, 80
    jmp lz4_decode
.bad:
    mov eax, 1
    ret

; Function: Strict header validation with bounded sizes before field reads.
; Input: RCX = image pointer, RDX = bytes (preserved, as are R8/R9).
; Output: EAX = 0 valid, 1 invalid.
; Clobbers: RAX, R10, R11, flags only.
; Context: Internal boot helper; readable input buffer required; no locks.
image_header:
    cmp rdx, 80
    jb .bad
    cmp rdx, 4194304
    ja .bad
    mov rax, rcx
    add rax, rdx
    jc .bad
    mov rax, 0x31474d49474e4f44 ; "DONGIMG1"
    cmp [rcx], rax
    jne .bad
    cmp dword [rcx + 8], 1
    jne .bad
    cmp dword [rcx + 12], 80
    jne .bad
    mov rax, [rcx + 16]
    test rax, rax
    jz .bad
    mov r10, rdx
    sub r10, 80
    cmp rax, r10
    jne .bad
    mov rax, [rcx + 24]
    test rax, rax
    jz .bad
    cmp rax, 2097152
    ja .bad
    mov rax, 0xffffffff80000000
    cmp [rcx + 32], rax
    jne .bad
    cmp qword [rcx + 40], 0
    jne .bad
    cmp qword [rcx + 48], 1
    jne .bad
    mov rax, [rcx + 56]
    or rax, [rcx + 64]
    or rax, [rcx + 72]
    jnz .bad
    xor eax, eax
    ret
.bad:
    mov eax, 1
    ret

; Function: Safely decode one independent LZ4 block, including overlap matches.
; Input: RCX = compressed data, RDX = bytes, R8 = output, R9 = exact raw size.
; Output: EAX = 0 success, 1 invalid; partial output possible on failure.
; Clobbers: RAX, RCX, RDX, R8-R11, flags; all nonvolatile registers preserved.
; Context: Boot/host probe; separate readable input and writable output; no locks.
lz4_decode:
    push rbx
    push rbp
    push rsi
    push rdi
    push r12
    push r13
    push r14
    push r15
    mov rsi, rcx
    mov r12, rcx
    add r12, rdx
    jc .bad
    mov rdi, r8
    mov r14, r8
    mov r13, r8
    add r13, r9
    jc .bad
    xor r15d, r15d            ; whether a match has occurred
    cld
.sequence:
    cmp rsi, r12
    jae .bad                 ; final literal sequence must include a token
    movzx ebp, byte [rsi]
    inc rsi
    mov ebx, ebp
    shr ebx, 4
    cmp ebx, 15
    jne .literal_bounds
.literal_length:
    cmp rsi, r12
    jae .bad
    movzx eax, byte [rsi]
    inc rsi
    add rbx, rax
    jc .bad
    cmp eax, 255
    je .literal_length
.literal_bounds:
    mov rax, r12
    sub rax, rsi
    cmp rbx, rax
    ja .bad
    mov rax, r13
    sub rax, rdi
    cmp rbx, rax
    ja .bad
    mov rcx, rbx
    rep movsb
    cmp rsi, r12
    jne .offset
    cmp rdi, r13
    jne .bad
    test r15d, r15d
    jz .good
    cmp rbx, 5
    jb .bad
    jmp .good
.offset:
    mov rax, r12
    sub rax, rsi
    cmp rax, 2
    jb .bad
    movzx r10d, word [rsi]
    add rsi, 2
    test r10d, r10d
    jz .bad
    mov rax, rdi
    sub rax, r14
    cmp r10, rax
    ja .bad
    mov r11, rdi
    sub r11, r10
    mov ebx, ebp
    and ebx, 15
    cmp ebx, 15
    jne .match_length_done
.match_length:
    cmp rsi, r12
    jae .bad
    movzx eax, byte [rsi]
    inc rsi
    add rbx, rax
    jc .bad
    cmp eax, 255
    je .match_length
.match_length_done:
    add rbx, 4
    jc .bad
    mov rax, r13
    sub rax, rdi
    cmp rax, 12               ; LZ4 final match starts >= 12 raw bytes from end
    jb .bad
    cmp rbx, rax
    ja .bad
    mov r15d, 1
.match_copy:
    mov al, [r11]
    inc r11
    mov [rdi], al
    inc rdi
    dec rbx
    jnz .match_copy
    jmp .sequence
.good:
    xor eax, eax
    jmp .done
.bad:
    mov eax, 1
.done:
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbp
    pop rbx
    ret

; Function: Compute software SHA-256 over arbitrary-length message bytes.
; Input: RCX = message, RDX = length, R8 = 32-byte digest output.
; Output: Digest in canonical big-endian byte order; no return value.
; Clobbers: RAX, RCX, RDX, R8-R11, flags; all nonvolatile registers preserved.
; Context: Boot/host probe; valid input/output buffers, size < 2^61; no locks.
sha256:
    push rbx
    push rbp
    push rsi
    push rdi
    push r12
    push r13
    push r14
    push r15
    sub rsp, 136              ; shadow[32], padding[64], state[32], alignment[8]
    mov r12, rcx
    mov r13, rdx
    mov r14, r8
    mov r15, rdx
    shl r15, 3
    lea rsi, [sha256_initial]
    lea rdi, [rsp + 96]
    mov ecx, 8
    cld
    rep movsd
.whole_block:
    cmp r13, 64
    jb .padding
    mov rcx, r12
    lea rdx, [rsp + 96]
    call sha256_compress
    add r12, 64
    sub r13, 64
    jmp .whole_block
.padding:
    lea rdi, [rsp + 32]
    xor eax, eax
    mov ecx, 64
    rep stosb
    lea rdi, [rsp + 32]
    mov rsi, r12
    mov rcx, r13
    rep movsb
    mov byte [rdi], 0x80
    cmp r13, 56
    jb .final_block
    lea rcx, [rsp + 32]
    lea rdx, [rsp + 96]
    call sha256_compress
    lea rdi, [rsp + 32]
    xor eax, eax
    mov ecx, 64
    rep stosb
.final_block:
    mov rax, r15
    bswap rax
    mov [rsp + 88], rax
    lea rcx, [rsp + 32]
    lea rdx, [rsp + 96]
    call sha256_compress
    xor ecx, ecx
.digest:
    mov eax, [rsp + 96 + rcx * 4]
    bswap eax
    mov [r14 + rcx * 4], eax
    inc ecx
    cmp ecx, 8
    jb .digest
    add rsp, 136
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbp
    pop rbx
    ret

; Function: SHA-256 compression of one 64-byte block into eight state words.
; Input: RCX = block, RDX = native-endian state[8].
; Output: Updated state; no return value.
; Clobbers: Volatile registers and flags; all nonvolatile registers preserved.
; Context: Internal SHA helper, stack schedule, no locks or firmware calls.
sha256_compress:
    push rbx
    push rbp
    push rsi
    push rdi
    push r12
    push r13
    push r14
    push r15
    sub rsp, 264              ; schedule[64] and state pointer; leaf
    mov [rsp + 256], rdx
    mov rdi, rsp
    xor eax, eax
.load:
    mov r8d, [rcx + rax * 4]
    bswap r8d
    mov [rdi + rax * 4], r8d
    inc eax
    cmp eax, 16
    jb .load
.expand:
    mov r8d, [rdi + rax * 4 - 60]
    mov r9d, r8d
    ror r9d, 7
    mov r10d, r8d
    ror r10d, 18
    xor r9d, r10d
    shr r8d, 3
    xor r9d, r8d
    mov r8d, [rdi + rax * 4 - 8]
    mov r10d, r8d
    ror r10d, 17
    mov r11d, r8d
    ror r11d, 19
    xor r10d, r11d
    shr r8d, 10
    xor r10d, r8d
    add r9d, r10d
    add r9d, [rdi + rax * 4 - 64]
    add r9d, [rdi + rax * 4 - 28]
    mov [rdi + rax * 4], r9d
    inc eax
    cmp eax, 64
    jb .expand
    mov r15, [rsp + 256]
    mov eax, [r15]
    mov ebx, [r15 + 4]
    mov ecx, [r15 + 8]
    mov edx, [r15 + 12]
    mov r8d, [r15 + 16]
    mov r9d, [r15 + 20]
    mov r10d, [r15 + 24]
    mov r11d, [r15 + 28]
    mov rsi, rdi
    lea rdi, [sha256_constants]
    xor ebp, ebp
.round:
    mov r12d, r8d
    ror r12d, 6
    mov r13d, r8d
    ror r13d, 11
    xor r12d, r13d
    mov r14d, r8d
    ror r14d, 25
    xor r12d, r14d
    add r12d, r11d
    add r12d, [rdi + rbp * 4]
    add r12d, [rsi + rbp * 4]
    mov r13d, r9d
    xor r13d, r10d
    and r13d, r8d
    xor r13d, r10d
    add r12d, r13d
    mov r14d, eax
    ror r14d, 2
    mov r13d, eax
    ror r13d, 13
    xor r14d, r13d
    mov r13d, eax
    ror r13d, 22
    xor r14d, r13d
    mov r13d, eax
    xor r13d, ebx
    and r13d, ecx
    mov r15d, eax
    and r15d, ebx
    xor r13d, r15d
    add r14d, r13d
    mov r11d, r10d
    mov r10d, r9d
    mov r9d, r8d
    mov r8d, edx
    add r8d, r12d
    mov edx, ecx
    mov ecx, ebx
    mov ebx, eax
    mov eax, r12d
    add eax, r14d
    inc ebp
    cmp ebp, 64
    jb .round
    mov r15, [rsp + 256]
    add [r15], eax
    add [r15 + 4], ebx
    add [r15 + 8], ecx
    add [r15 + 12], edx
    add [r15 + 16], r8d
    add [r15 + 20], r9d
    add [r15 + 24], r10d
    add [r15 + 28], r11d
    add rsp, 264
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbp
    pop rbx
    ret

section .rdata
align 4
expected_hash: db IMAGE_EXPECTED_HASH_BYTES
sha256_initial:
    dd 0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a
    dd 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
sha256_constants:
    dd 0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5
    dd 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5
    dd 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3
    dd 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174
    dd 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc
    dd 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da
    dd 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7
    dd 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967
    dd 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13
    dd 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85
    dd 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3
    dd 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070
    dd 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5
    dd 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3
    dd 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208
    dd 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
