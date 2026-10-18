OUTPUT_FORMAT(elf64-x86-64)
ENTRY(kernel_entry)
SECTIONS
{
    . = 0xffffffff80000000;
    __kernel_text_start = .;
    .text : { KEEP(*(.text.entry)) *(.text .text.*) }
    . = ALIGN(4096);
    __kernel_text_end = .;
    __kernel_rodata_start = .;
    .rodata : { *(.rodata .rodata.*) }
    . = ALIGN(4096);
    __kernel_rodata_end = .;
    __kernel_data_start = .;
    .data : { *(.data .data.*) }
    . = ALIGN(4096);
    __kernel_data_end = .;
    __kernel_bss_start = .;
    .bss : { *(.bss .bss.*) *(COMMON) }
    . = ALIGN(4096);
    __kernel_bss_end = .;
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
