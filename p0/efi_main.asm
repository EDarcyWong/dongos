; boot/efi_main.asm：阶段 P0，UEFI 应用，在屏幕和串口上打印一行字
        bits 64
        default rel
        section .text
        global efi_main
; 输入：rcx = ImageHandle，rdx = SystemTable（微软 x64 调用约定）
efi_main:
        sub     rsp, 40                 ; 32 字节影子空间 + 8 字节对齐
        mov     rcx, [rdx + 64]         ; SystemTable->ConOut
        lea     rdx, [msg]
        call    [rcx + 8]               ; ConOut->OutputString(ConOut, msg)
.halt:  hlt
        jmp     .halt

        section .data
msg:    dw __utf16__("DongOS: hello, x86-64 UEFI!"), 13, 10, 0
