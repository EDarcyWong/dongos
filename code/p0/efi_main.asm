; P0：在 UEFI 文本控制台和独立的 COM1 UART 上输出启动信息。
        bits 64
        default rel

%include "uefi.inc"

%ifndef P0_TEST
%define P0_TEST 0
%endif

COM1_BASE               equ 0x3f8
UART_DATA               equ COM1_BASE + 0
UART_INTERRUPT_ENABLE   equ COM1_BASE + 1
UART_FIFO_CONTROL       equ COM1_BASE + 2
UART_LINE_CONTROL       equ COM1_BASE + 3
UART_MODEM_CONTROL      equ COM1_BASE + 4
UART_LINE_STATUS        equ COM1_BASE + 5
UART_SCRATCH            equ COM1_BASE + 7
UART_TX_READY           equ 0x20
UART_TX_EMPTY           equ 0x40
UART_POLL_LIMIT         equ 0x100000

; isa-debug-exit 是自动验收专用设备，不属于正常启动的硬件接口。
%if P0_TEST
QEMU_EXIT_PORT          equ 0xf4
QEMU_EXIT_PASS          equ 0x10   ; QEMU 进程状态：(0x10 << 1) | 1 = 33。
QEMU_EXIT_FAIL          equ 0x11
%endif

        section .text
        global efi_main

; 功能：执行 P0 控制台与串口验收，然后停机以保留屏幕输出。
; 输入：rcx = ImageHandle，rdx = EFI_SYSTEM_TABLE*，微软 x64 ABI。
; 输出：串口 hello 与 DONGOS_P0_PASS；失败时不输出成功标记；不返回。
; 破坏：rax、rcx、rdx、r8-r11、xmm0-xmm5、标志；不修改非易失寄存器。
; 中断/锁：仅在 UEFI 启动入口调用，不可在中断中调用，无需持锁。
efi_main:
        endbr64
        sub     rsp, 40                  ; 32 字节影子空间 + 8 字节局部变量。
                                         ; 入口 rsp % 16 = 8，call 前对齐到 16。
        mov     rcx, [rdx + EFI_SYSTEM_TABLE.ConOut]
        lea     rdx, [hello_utf16]
        call    [rcx + EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL.OutputString]
        mov     [rsp + 32], rax           ; 不能依赖易失寄存器跨调用保存状态。

        call    p0_serial_init
        test    eax, eax
        jz      .failed
        lea     rcx, [hello_ascii]
        call    p0_serial_write
        test    eax, eax
        jz      .failed
        cmp     qword [rsp + 32], EFI_SUCCESS
        jne     .report_failure

        lea     rcx, [pass_ascii]
        call    p0_serial_write
        test    eax, eax
        jz      .failed
%if P0_TEST
        mov     eax, QEMU_EXIT_PASS
        out     QEMU_EXIT_PORT, eax
%endif
        jmp     .halt

.report_failure:
        lea     rcx, [fail_ascii]
        call    p0_serial_write
.failed:
%if P0_TEST
        mov     eax, QEMU_EXIT_FAIL
        out     QEMU_EXIT_PORT, eax
%endif
.halt:
        cli
        hlt
        jmp     .halt

; 功能：检测兼容 16550 的 COM1，并初始化为 115200 波特、8N1、无中断。
; 输入：无；要求 COM1 I/O 端口可用，当前执行级别允许 in/out。
; 输出：eax = 1 表示可用，eax = 0 表示未检测到 UART。
; 破坏：rax、rdx、r8、标志；不修改非易失寄存器。
; 中断/锁：仅启动时调用，不可在中断中调用；调用方独占 COM1，无需持锁。
p0_serial_init:
        mov     dx, UART_SCRATCH
        in      al, dx
        mov     r8b, al
        mov     al, 0x5a
        out     dx, al
        in      al, dx
        cmp     al, 0x5a
        mov     al, r8b                   ; 恢复检测前的 scratch 值，mov 不改标志。
        out     dx, al
        jne     .unavailable

        mov     dx, UART_LINE_CONTROL
        mov     al, 0x03
        out     dx, al                    ; 先清除继承的 DLAB，确保可访问 IER。
        mov     dx, UART_INTERRUPT_ENABLE
        xor     eax, eax
        out     dx, al                    ; 禁止 UART 中断。
        mov     dx, UART_LINE_CONTROL
        mov     al, 0x80
        out     dx, al                    ; DLAB = 1，访问波特率除数。
        mov     dx, UART_DATA
        mov     al, 1
        out     dx, al                    ; 除数低字节：115200 / 1。
        mov     dx, UART_INTERRUPT_ENABLE
        xor     eax, eax
        out     dx, al                    ; 除数高字节。
        mov     dx, UART_LINE_CONTROL
        mov     al, 0x03
        out     dx, al                    ; DLAB = 0，8 位数据，无校验，1 位停止。
        mov     dx, UART_FIFO_CONTROL
        mov     al, 0xc7
        out     dx, al                    ; 启用并清空收发 FIFO。
        mov     dx, UART_MODEM_CONTROL
        mov     al, 0x0b
        out     dx, al                    ; DTR、RTS、OUT2；禁用 loopback。
        mov     eax, 1
        ret
.unavailable:
        xor     eax, eax
        ret

; 功能：通过 COM1 轮询发送 NUL 结尾的 ASCII 字符串，并等待发送器清空。
; 输入：rcx = 字符串地址；必须已成功调用 p0_serial_init。
; 输出：eax = 1 表示全部发送完成，eax = 0 表示 UART 等待超时。
; 破坏：rax、rcx、rdx、r8、r9、标志；不修改非易失寄存器。
; 中断/锁：仅启动时调用，不可在中断中调用；调用方独占 COM1，无需持锁。
p0_serial_write:
.next_byte:
        mov     r9b, [rcx]
        test    r9b, r9b
        jz      .drain
        mov     r8d, UART_POLL_LIMIT
        mov     dx, UART_LINE_STATUS
.wait_ready:
        in      al, dx
        test    al, UART_TX_READY
        jnz     .send
        pause
        dec     r8d
        jnz     .wait_ready
        jmp     .timeout
.send:
        mov     dx, UART_DATA
        mov     al, r9b
        out     dx, al
        inc     rcx
        jmp     .next_byte
.drain:
        mov     r8d, UART_POLL_LIMIT
        mov     dx, UART_LINE_STATUS
.wait_empty:
        in      al, dx
        test    al, UART_TX_EMPTY
        jnz     .complete
        pause
        dec     r8d
        jnz     .wait_empty
.timeout:
        xor     eax, eax
        ret
.complete:
        mov     eax, 1
        ret

        section .rdata
hello_utf16: dw __utf16__("DongOS: hello, x86-64 UEFI!"), 13, 10, 0
hello_ascii: db "DongOS: hello, x86-64 UEFI!", 13, 10, 0
pass_ascii:  db "DONGOS_P0_PASS", 13, 10, 0
fail_ascii:  db "DONGOS_P0_FAIL: UEFI OutputString", 13, 10, 0
