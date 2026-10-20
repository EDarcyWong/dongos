# P5 shared frame table and real persistence validation

P5 now enables the existing 16384-frame (64 MiB) managed user allocation before
loading its first service. The loader-held service arena remains 32768 pages
(128 MiB); it also contains supervisor metadata. These are distinct budgets.
The ordinary service stack remains four pages. No service gains a new handle.
The old fixed 512-record frame table could not represent the current shell's
551 pages plus the FS and block services (712 image pages in total).

The non-catalog P5 shell's existing boot-trace mark is accepted only for slot
zero, mark one, and all other arguments zero. It is a diagnostic no-op. Other
callers and marks still fail; desktop catalog role checks remain unchanged.

The physical validator follows EXTENDED only after checking its complete table
extent against the held service arena and proving its actual metadata PTEs
map to the declared supervisor RW/NX/WB arena pages. Every used frame record
has a unique aligned physical page in that arena, its exact linear alias,
and a Boolean writable field. Existing user/private roots, code bytes, W^X,
stack guards, IPC, MMIO and DMA checks still run.

The command test is a functional correctness test. The old 3000-call/6000-syscall
pressure floors are replaced with exact ordered command/output checks,
calls == replies > 0, syscalls >= 2*calls, and monotonic timestamps. This does
not claim the old stress coverage. Errors and last_error must still be zero.
Write and sync must each succeed in their own command segment; cat must return
the exact payload and ls its exact size. Actual device FLUSH, both FAT copies,
clean bit and disk bytes are checked before a second boot of the same disk.

Real QEMU evidence: build/test/p5-storage/qemu/run-b30b43b81497/result.json.
Both boots passed with unchanged source inputs, 791 managed frames, 241 physical
reads per boot, eight stack guards and two channels. Write: 319 matched calls,
2194 syscalls; reboot: 204 matched calls, 956 syscalls. Both have zero errors.
The 34-byte PROBE.TXT SHA256 is
51d927be82eef864035f12b1fcb1c673d57e43ffe62ceb617c79c18bc423ff57.
The QEMU machine has 2 GiB physical RAM; the managed user quota is 64 MiB.
This proves storage persistence, not execution of the self-hosting compiler.

Seven portable tests exercise dynamic table ranges, forged mappings and records,
truncated reads, exact command oracles and real compiled boot-trace branch
behavior in both modes and formats, including the old rejecting branch mutant.
