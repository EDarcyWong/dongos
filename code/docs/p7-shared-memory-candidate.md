# P7 shared-memory candidate

The candidate lives at `build/test/p7-memory-candidate/kernel/user/memory.dg`.
It is not integrated into the production kernel until the serialized guest
validation finishes and the root agent authorizes promotion.

`unshare_range(id, base, pages)` and
`allocate_shared(source, target, source_base, target_base, pages)` are trusted
kernel broker interfaces. The broker supplies the exact recorded lease
apertures, validates roles, and enforces its aggregate 8 MiB budget. Each call
accepts 1 through 768 pages, corresponding to the broker's 3 MiB lease limit.
Neither API accepts a physical address or is exposed as a raw user syscall.

Both operations require exclusive BSP ownership with interrupts disabled,
noncurrent user roots, and no active ELF loader transaction. DMA-pinned roots
are rejected. An AP must not execute or retain translations for these roots;
future SMP user execution needs the common mutation lock and acknowledged
cross-CPU TLB invalidation before either API can be used there.

Withdrawal prechecks the entire range before mutation: every page must be
owned USER, WB and NX RAM with a consistent supervisor alias. The retained
arena scratch contains 768 distinct 56-byte paging retirement receipts and
768 frame indices, rounded to 11 pages. Even a receipt with no detached tables
is consumed after the root and tag barriers. The code then scans every live
root for surviving references. It restores writable supervisor aliases and
completes all fallible operations before zeroing and making unreferenced RAM
reusable. Shared survivors and DMA frames remain held.

Creation validates both full absent ranges first, then records every fresh or
recycled allocation through the allocator's journal hook. A new Frame is
journaled before its supervisor alias can fail, including allocations that
never reach `fresh()`'s return. Source and destination prefixes are withdrawn
and their receipts reclaimed before journaled RAM is considered for reuse.
A failed alias proof leaves the orphan held. The broker publishes a lease
only after successful completion.

An unexpected error after mutation permanently sets `UNSHARE_FAILED`; the
caller must stop scheduling. Pending receipts and held RAM are retained.
Expected policy rejections before mutation do not set this flag.

`python -m unittest tests.test_user_unshare -v` compiles the candidate in debug
and release modes and executes its actual paging, ownership and reclamation
bodies. Native adapters model only the arena and hardware invalidation
boundary. The tests cover shared last-reference withdrawal, same-root
survivors, duplicate physical pages, the 768-page bound and scratch guard,
complete failure prechecks, zero-table receipts, old pending receipts,
partial reclaim and alias-protection failures, reuse zeroing, target-table
exhaustion rollback, and supervisor alias creation failure. Actual altered
Dong source variants must be rejected by the same probe. These tests do not
constitute QEMU, VMware, or SMP hardware evidence.
