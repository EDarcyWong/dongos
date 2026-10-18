; DongOS boot ABI v1. All pointers are physical addresses, identity-mapped in P1.
%ifndef DONGOS_BOOTINFO_INC
%define DONGOS_BOOTINFO_INC

BOOTINFO_MAGIC equ 0x544f4f42474e4f44 ; little-endian "DONGBOOT"
BOOTINFO_VERSION equ 1
BOOTINFO_EBS_EXITED equ 1
KERNEL_BASE equ 0xffffffff80000000
HHDM_BASE equ 0xffff800000000000

; Generated from BootInfo in lang/examples/boot/abi.dg before assembling P1.
%include "bootinfo_layout.inc"

%endif
