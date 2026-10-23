# Host verifier layout

The verifier loads the guest's static ELF at 0x400000. On Linux its own non-PIE
executable is explicitly linked at 0x10000000; the normal non-PIE default would
already occupy the guest range and make MAP_FIXED_NOREPLACE fail. Keeping
non-PIE also supports the seed object's existing absolute relocations. On
Windows the verifier is explicitly linked at 0x10000000. Its CRT worker waits
for the original thread to terminate, then reserves the 2 MiB ELF window at
0x400000 before calling the verifier. The loader releases only that reservation
when mapping an ELF, and reserves it again immediately after unmapping so the
host heap cannot reclaim it between compiles. See the shared
`tools.compiler_job.host_harness` adapter and the [G5 closure contract](g5-closure.md).
Guest addresses and static pointers stay unchanged.

The C fixture uses an explicitly asserted 64-bit unsigned long long type for
its ABI words and existing %llu diagnostics. This avoids LP64 uint64_t being
unsigned long and failing the strict format-warning check. Binary layouts and
the six-word calling convention remain unchanged.

Windows full fixed-point verification is available in this workspace. Linux
execution has not been performed here; ELF64 object assembly is checked on
Windows and is not presented as a Linux runtime result.

`python -m unittest tests.test_compiler_job_preparation` creates a new release
fixture and production compiler profile under a unique
`build/test/g6-preparation/run-*` directory. It checks the current canonical
source blob, the build's source and boot artifact hashes, the two host ELF
stages, and actual seed-disk FAT contents. Changed fixture or boot bytes must
be rejected. The retained receipt labels the result host-only; a seeded disk
readback is not guest durability or a successful G6 execution.
