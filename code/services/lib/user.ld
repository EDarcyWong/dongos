OUTPUT_FORMAT(elf64-x86-64)
ENTRY(_start)
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); stack PT_GNU_STACK FLAGS(6); }
SECTIONS {
    . = 0x1000;
    .text : { *(.text .text.*) *(.rodata .rodata.*) } :text
    . = ALIGN(4096);
    .data : { *(.data .data.*) } :data
    .bss : { *(.bss .bss.*) *(COMMON) } :data
    /DISCARD/ : { *(.dynamic) *(.dynsym) *(.dynstr) *(.gnu.hash) *(.hash) *(.eh_frame*) *(.note*) *(.comment) }
}
