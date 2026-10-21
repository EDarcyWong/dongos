# Fragmented order-9 allocation refusal

P2OOM4 supplies a disposable fixture and a read-only guest oracle for the
remaining fragmented-allocation branch of P2SMP3. It does not add a production
test switch or change the normal kernel, allocator or shared-owner code.
Formal task status is recorded by the coordinator independently of this text.

The startup arena has 1,024 pages. Its 128-page table pool and 16-page stack
leave 880 free pages. The fixture uses the real buddy API to allocate the second
512-page half, hold the other 368 available pages one by one, release the large
half, retain one page from that half, and release the 368 temporary pages.
The result has 879 free pages, exceeding the requested 512, but neither half
can supply an aligned order-9 block. No allocation result is mocked.

Injection occurs immediately before the original `REPORT.free_before` and
original `buddy.alloc(allocator,9)`. Only a fresh isolated copy of
`kernel/smp/large_memory.dg` changes. The complete source manifest binds both
the original and exact injected source; all other producer bytes are retained.
The fixture's temporary address list is static so it respects Dong's 4 KiB
frame budget. It is absent from normal builds. Raw test-only metadata pointers
are read using the actual audited Allocator/Space layout, checked in both host
compilation and the completed guest layout before decoding.

Before the actual order-9 attempt, the fixture records the entire 128-byte
allocator, all 1,024 16-byte metadata records, the 64-byte Space, all 128 table
metadata bytes, and a hash of the complete 128-page table pool with hardware
A/D bits masked. The guest oracle requires those snapshots to match after the
real OutOfMemory return. It independently walks every free list, accounts for
all 1,024 pages, proves the three exact retained allocations, and rejects
cycles, overlap, unreachable heads and any order-9/order-10 free block.

The expected result is a stopped production-style runtime7 build: exact OOM
`0x02000007`, phase0/steps0/held0/complete0; unbound owner; zero publication,
invalidation, retirement and reader-probe counters; unchanged healthy online
reader domain; absent shared large window; ordinary unchanged table pool.
The BSP must halt at the linked `kernel_fail.halt` under its original root.
Compile failure, timeout, a general panic, merely low total memory, or a forged
successful report do not satisfy this gate. A normal desktop is not expected
from this deliberate fatal-allocation fixture.

The physical oracle uses QMP to save host-side raw dumps. It never writes guest
memory or registers. ELF/layout/completed-build inputs, original and injected
Dong source, UART/BootInfo, all physical chunk hashes and their ordered
addresses/roles are archived and rechecked in offline replay. The read-only
data disk and frozen source tree must remain byte-identical and QEMU cleanup
must complete. The replay has no dependency on the original checkout or ESP.

From `code/`:

```powershell
python -m unittest tests.test_p2_fragmented_fixture -v
python -m tests.run_p2_fragmented_qemu --reuse-esp <completed-fixture-esp> --cpus 4
python -m tests.run_p2_fragmented_qemu --reuse-esp <completed-fixture-esp> --cpus 1
python -m tests.run_p2_fragmented_qemu --replay <result.json>
```

Host tests execute the same injected Dong allocation flow in debug/release,
assemble ELF64 and COFF, and call it against an independent C raw-ledger
oracle. A contiguous baseline obtains the real 512-page lease. The fragmented
case returns OOM with the complete ledger unchanged. Returning the hole or
failing to return a temporary page are actual wrong Dong sources that compile,
link and run normally, then fail the independent exact free-count assertion.
Separate tests enforce the single source-change boundary and complete compiled
fixture layout/frame budget. No test is skipped when required tools are absent.

This is a reproducible, real allocator fragmentation fixture on QEMU, not an
exhaustive test of arbitrary firmware fragmentation or a claim that every
machine can provide a 2 MiB block. The normal P2SMP3 single/four-CPU success,
AP-shootdown omission negative, persistent lease and desktop/P5 regressions
remain separate evidence. EXEC, graphics WC, arbitrary post-scheduler user
address-space mutation and real WC hardware performance remain outside it.

On 2026-10-21 the actual fixture passed on one and four CPUs. Both halted with
the exact allocation error, 879 free pages, largest free order 8, hole at
physical `0x600000`, 42 reachable ordinary tables and no large-window leaf.
The complete allocator, metadata, Space and software page-table bits were
unchanged; the owner stayed unbound and the reader domain stayed healthy.
The fixture kernel is 2,031,184 bytes (65,968 bytes below the loader limit).
The unchanged normal kernel is 2,006,608 bytes (90,544 bytes headroom).

Raw archives and the separate-process replay index are under
`coordination/dongos_works/.local/p2oom4-f6f28af590/`:
`independent-guest-index.json` binds both fault guests;
`normal-baseline-replay.json` binds the earlier normal one/four-CPU guests
and the actual AP-shootdown omission negative, all re-decoded successfully.
Host checks passed three tests with zero skips; the coordinator's formal
verification and acceptance receipts remain the authority for task status.
