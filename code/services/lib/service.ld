OUTPUT_FORMAT(elf64-x86-64)
ENTRY(_start)
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); dynamic PT_DYNAMIC FLAGS(6); stack PT_GNU_STACK FLAGS(6); }
SECTIONS {
    . = 0x1000;
    .text : { *(.text .text.*) } :text
    .rodata : { *(.rodata .rodata.*) } :text
    .dynsym : { *(.dynsym) } :text
    .dynstr : { *(.dynstr) } :text
    .gnu.hash : { *(.gnu.hash) } :text
    .hash : { *(.hash) } :text
    .rela.dyn : { *(.rela.dyn) } :text
    . = ALIGN(4096);
    .data : { *(.data .data.*) } :data
    .dynamic : { *(.dynamic) } :data :dynamic
    .bss : { *(.bss .bss.*) *(COMMON) } :data
    /DISCARD/ : { *(.eh_frame*) *(.note*) *(.comment) }
}
