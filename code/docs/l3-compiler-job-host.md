# Host verifier layout

The verifier loads the guest's static ELF at 0x400000. On Linux its own non-PIE
executable is explicitly linked at 0x10000000; the normal non-PIE default would
already occupy the guest range and make MAP_FIXED_NOREPLACE fail. Keeping
non-PIE also supports the seed object's existing absolute relocations. On
Windows the PE executable's normal image base already leaves this range free.
This changes only the host verifier image; guest addresses stay unchanged.

The C fixture uses an explicitly asserted 64-bit unsigned long long type for
its ABI words and existing %llu diagnostics. This avoids LP64 uint64_t being
unsigned long and failing the strict format-warning check. Binary layouts and
the six-word calling convention remain unchanged.

Windows full fixed-point verification is available in this workspace. Linux
execution has not been performed here; ELF64 object assembly is checked on
Windows and is not presented as a Linux runtime result.
