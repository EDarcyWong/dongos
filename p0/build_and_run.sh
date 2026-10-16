#!/bin/sh
# P0：构建 UEFI 应用并在 QEMU + OVMF 中运行（已在 QEMU 8.2.2 + OVMF_CODE_4M.fd 实测）
# 依赖：nasm lld qemu-system-x86 ovmf
set -e
cd "$(dirname "$0")"
mkdir -p build esp/EFI/BOOT
nasm -f win64 -o build/efi_main.obj efi_main.asm
lld-link /subsystem:efi_application /entry:efi_main /nodefaultlib \
         /out:esp/EFI/BOOT/BOOTX64.EFI build/efi_main.obj
OVMF_DIR=${OVMF_DIR:-/usr/share/OVMF}
cp "$OVMF_DIR/OVMF_VARS_4M.fd" build/vars.fd
qemu-system-x86_64 -machine q35 -m 2G -serial stdio \
  -drive if=pflash,format=raw,readonly=on,file="$OVMF_DIR/OVMF_CODE_4M.fd" \
  -drive if=pflash,format=raw,file=build/vars.fd \
  -drive format=raw,file=fat:rw:esp
