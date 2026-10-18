; Required Dong contract trap in the standalone EFI image, never a success path.
bits 64
default rel
section .text
global __dong_panic
__dong_panic:
    cli
.held:
    hlt
    jmp .held
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
