; Private BSP CPU tables and fatal-exception ABI. No firmware descriptors are
; referenced after cpu_init returns. All addresses below are kernel virtual.
%ifndef DONGOS_CPU_INC
%define DONGOS_CPU_INC

CPU_KERNEL_CODE_SELECTOR equ 0x08
CPU_KERNEL_DATA_SELECTOR equ 0x10
CPU_TSS_SELECTOR         equ 0x18
CPU_GDT_SIZE             equ 40
CPU_IDT_ENTRY_SIZE       equ 16
CPU_IDT_ENTRY_COUNT      equ 256
CPU_IDT_SIZE             equ CPU_IDT_ENTRY_SIZE * CPU_IDT_ENTRY_COUNT
CPU_IDT_INTERRUPT_GATE   equ 0x8e ; present, DPL0, 64-bit interrupt gate
CPU_GDT_CODE_DESCRIPTOR  equ 0x00af9b000000ffff ; L=1, D=0, accessed
CPU_GDT_DATA_DESCRIPTOR  equ 0x00cf93000000ffff ; writable, accessed
CPU_TSS_AVAILABLE       equ 0x89
CPU_TSS_BUSY            equ 0x8b

CPU_IST_DF               equ 1
CPU_IST_NMI              equ 2
CPU_IST_EXCEPTION        equ 3
CPU_IST_STACK_SIZE       equ 16384
CPU_TSS_SIZE             equ 104
CPU_TSS_RSP0             equ 4
CPU_TSS_RSP1             equ 12
CPU_TSS_RSP2             equ 20
CPU_TSS_IST1             equ 36
CPU_TSS_IST2             equ 44
CPU_TSS_IST3             equ 52
CPU_TSS_IST4             equ 60
CPU_TSS_IST5             equ 68
CPU_TSS_IST6             equ 76
CPU_TSS_IST7             equ 84
CPU_TSS_IOMAP_BASE       equ 102

; The CPU always saves SS,RSP,RFLAGS,CS,RIP in 64-bit mode. Hardware-error
; exceptions add an error qword; other stubs insert zero, then all push vector.
; Common entry saves all remaining GPRs and CR2. rsp is the interrupted RSP,
; not the current IST stack. Slots and the two selector fields are all qwords.
; kernel_exception_panic(rdi = *ExceptionContext) is SysV and must not return.
struc ExceptionContext
    .cr2:    resq 1
    .r15:    resq 1
    .r14:    resq 1
    .r13:    resq 1
    .r12:    resq 1
    .r11:    resq 1
    .r10:    resq 1
    .r9:     resq 1
    .r8:     resq 1
    .rdi:    resq 1
    .rsi:    resq 1
    .rbp:    resq 1
    .rdx:    resq 1
    .rcx:    resq 1
    .rbx:    resq 1
    .rax:    resq 1
    .vector: resq 1
    .error:  resq 1
    .rip:    resq 1
    .cs:     resq 1
    .rflags: resq 1
    .rsp:    resq 1
    .ss:     resq 1
endstruc

CPU_CONTEXT_SIZE   equ ExceptionContext_size
CPU_CONTEXT_CR2    equ ExceptionContext.cr2
CPU_CONTEXT_R15    equ ExceptionContext.r15
CPU_CONTEXT_R14    equ ExceptionContext.r14
CPU_CONTEXT_R13    equ ExceptionContext.r13
CPU_CONTEXT_R12    equ ExceptionContext.r12
CPU_CONTEXT_R11    equ ExceptionContext.r11
CPU_CONTEXT_R10    equ ExceptionContext.r10
CPU_CONTEXT_R9     equ ExceptionContext.r9
CPU_CONTEXT_R8     equ ExceptionContext.r8
CPU_CONTEXT_RDI    equ ExceptionContext.rdi
CPU_CONTEXT_RSI    equ ExceptionContext.rsi
CPU_CONTEXT_RBP    equ ExceptionContext.rbp
CPU_CONTEXT_RDX    equ ExceptionContext.rdx
CPU_CONTEXT_RCX    equ ExceptionContext.rcx
CPU_CONTEXT_RBX    equ ExceptionContext.rbx
CPU_CONTEXT_RAX    equ ExceptionContext.rax
CPU_CONTEXT_VECTOR equ ExceptionContext.vector
CPU_CONTEXT_ERROR  equ ExceptionContext.error
CPU_CONTEXT_RIP    equ ExceptionContext.rip
CPU_CONTEXT_CS     equ ExceptionContext.cs
CPU_CONTEXT_RFLAGS equ ExceptionContext.rflags
CPU_CONTEXT_RSP    equ ExceptionContext.rsp
CPU_CONTEXT_SS     equ ExceptionContext.ss

; cpu_exception_stack_ranges.._end is a read-only table of three
; {bottom,top} qword pairs in DF, NMI, EXCEPTION order. Bounds are [bottom,top).
; The corresponding labels are cpu_{df,nmi,exception}_stack_{bottom,top}.
%endif
