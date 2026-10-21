# P2 shared kernel-root large pages

`smp.large_memory` runs after the existing real SMP stress/TLB proof and before
parallel tasks or user scheduling. `mm.shared_paging` wraps the existing live
transaction implementation with a fixed online reader domain. The BSP remains
the sole writer with IF clear; every reader must retain the same kernel CR3,
online epoch and PGE/PCIDE policy during this ownership epoch.

The hardware callback invalidates the BSP and synchronously waits for all APs.
Full-root reloads are used for large-page publication/conversion and detached
table retirement; INVLPG is used for individual replacement. A missing hardware
acknowledgement stops the kernel before reclamation. The unsafe callback must
never return on failure. The wrapper also rejects a changed domain before
publication, blocks reentrancy, and permanently rejects mutations after seal.

The production path acquires an actual aligned order-9 startup buddy lease,
maps `0xffffa80000000000`, and writes/reads both boundary words of all 512 pages.
APs warm page 5 through the 2 MiB mapping. The BSP splits it, replaces page 5
with held page 6, and requires every AP to observe the new value. A noncontiguous
merge is rejected with the exact PDE, all 512 PTEs and statistics unchanged.
Restoration, successful merge, another split and 512 unmaps reclaim all four
temporary tables only after the corresponding barriers. A final large view is
then published, read by all readers and sealed. Its original 512 pages remain
allocated for the kernel lifetime; they are never returned for DMA or reuse.

The final leaf is supervisor WB/RW/NX. It has no HHDM or other conflicting alias.
The current kernel-root view is persistent; arbitrary concurrent writers,
post-scheduler mutation across distinct user CR3s, PCID/PGE-enabled operation,
executable aliases and graphics WC are separate consumers and are not proved by
this work. The earlier `boot.large_memory` proof remains the pre-AP lifecycle
that returns its lease and restores an ordinary 4 KiB tree.

The 504-byte, 63-u64 report is checked against the actual compiler layout.
Success requires 524 completed broadcasts: 517 full flushes, two page
invalidations and five reader probes. For four CPUs this means 1,572 additional
AP acknowledgements. The free count drops from 880 to 368 and remains there;
the startup table count returns to its pre-proof baseline before the permanent
two-table mapping is established. The complete domain, context, mailboxes,
buddy metadata, table pool and held physical block are read through QMP without
changing guest memory or registers. Later runtime allocations may add ordinary
kernel mappings; the raw oracle audits the complete pool's structure and the
large lease's ownership/alias policy, not every unrelated runtime device policy.

From `code/`:

```powershell
python -m unittest tests.test_shared_large tests.test_p2_shared_large_guest tests.test_smp -v
python -m tests.run_p2_shared_large_qemu --reuse-esp <completed-runtime7-esp> --cpus 4
python -m tests.run_p2_shared_large_qemu --reuse-esp <completed-runtime7-esp> --cpus 1
python -m tests.run_p2_shared_large_qemu --replay <result.json>
```

The one-CPU run observes the completed P2 owner before parallel user-service
assignment; it is not a claim of a one-CPU graphical service topology. The
four-CPU run requires the normal desktop and two stable P5 control observations.
Actual negative validation uses a separately frozen build with only the AP
shootdown call omitted in this callback. Local invalidation and the AP read
probe remain intact. The expected failure is phase 3, ProbeMismatch, BSP page 6
versus AP page 5, with the lease held and the domain pending. Build failure,
timeout or a generic panic cannot satisfy that negative gate.

Host tests execute real Dong debug/release code with an independent C raw table
oracle, including reentrant calls and four semantic mutants. Separate raw
oracle tests reject missing acknowledgements, returned leases, extra aliases,
table cycles, unreachable/unzeroed tables, altered cache policy and forged
buddy metadata. Formal acceptance and local integration are recorded through
the coordinator; these commands alone do not alter task status.
