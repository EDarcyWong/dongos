; BSP controller accessors. SysV, integer-only, preserve nonvolatile registers.
bits 64
default rel
global irq_hw_read32, irq_hw_read64, irq_hw_write32, irq_hw_in32
global irq_hw_flags, irq_hw_cr4, irq_hw_set_lapic, apic_eoi
section .text
irq_hw_read32:
    mov eax, [rdi]
    ret
irq_hw_read64:
    mov rax, [rdi]
    ret
irq_hw_write32:
    mov [rdi], esi
    ret
irq_hw_in32:
    mov dx, di
    in eax, dx
    ret
irq_hw_flags:
    pushfq
    pop rax
    ret
irq_hw_cr4:
    mov rax, cr4
    ret
irq_hw_set_lapic:
    mov [rel irq_lapic_base], rdi
    ret
apic_eoi:
    mov rax, [rel irq_lapic_base]
    mov dword [rax + 0xb0], 0
    ret
section .bss
alignb 8
irq_lapic_base: resq 1
section .note.GNU-stack noalloc noexec nowrite progbits
