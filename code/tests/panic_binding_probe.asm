bits 64
section .rdata
global cpu_exception_stack_ranges
global cpu_exception_stack_ranges_end
cpu_exception_stack_ranges:
    dq 0xffffffff80020000, 0xffffffff80024000
    dq 0xffffffff80026000, 0xffffffff8002a000
    dq 0xffffffff8002c000, 0xffffffff80030000
cpu_exception_stack_ranges_end:
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
