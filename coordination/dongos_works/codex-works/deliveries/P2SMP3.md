# P2SMP3 — shared kernel-root large transactions and persistent view

Implemented the declared 16-file scope. `mm.shared_paging` preserves the old
active Context/Stats ABI by composition, validates the fixed online reader
domain before publication, rejects reentrancy and permanently seals mutation.
The actual hardware callback invalidates the BSP and all APs before returning;
hardware failure is fail-stop before table reclamation. No P5 production file,
unrelated owner candidate, loader size ABI, Git commit or PR was changed.

`smp.large_memory` executes after the established SMP proof and before parallel
or user scheduling. It acquires an actual startup buddy order-9 lease, exercises
map/split/replace/reject-merge/restore/merge/split/unmap, checks all512 page tags
and all512 saved PTEs, then installs a permanent WB/RW/NX large leaf and seals
its owner. Full lease and all corresponding temporary retirements remain under
the protocol; the final 512 pages are held for the kernel lifetime.

Normal final release runtime7 builds and actual 1/4-CPU guests pass. The four-CPU
guest reaches the normal desktop and passes two stable P5CTX2 control snapshots.
The one-CPU gate observes completed P2 startup before parallel user assignment;
it does not claim a one-CPU desktop service topology. All 316 consumed build
inputs match the main workspace. Kernel size is 2,006,608 bytes, leaving 90,544
bytes of the unchanged 2 MiB load window. Both preserved P5 production SHA256s
remain unchanged.

Final guest archive:
`coordination/dongos_works/.local/p2smp3-47d6915707/final-guest-index.json`.
The successful report has phase11/steps2047, free880→368, cleanup tables equal
the original42, final tables44, invlpg2/full517/retired4, and exactly524 additional
broadcasts with1,572 AP acknowledgements in the four-CPU case. QMP independently
reads the complete root pool, buddy metadata, 2MiB lease, owner, online contexts
and mailboxes. Every physical dump is hashed; offline replay checks actual ELF,
layout, build source identities, UART/BootInfo, read order/address/role, all512
physical page boundary tags and the recomputed result. No guest memory or
register writes are used. Normal read-only data disks remain byte-identical;
all QEMU processes exit0 and cleanup is confirmed.

The actual negative build differs from the paired final frozen source only at
the AP shootdown call in `kernel/smp/large_memory.asm`. Local invalidation and
AP read probes remain. It successfully builds/boots, then fails precisely with
ProbeMismatch at phase3: actual replacement PTE and BSP read select page6 while
all AP mailboxes retain page5. The domain remains pending and the lease held.
Its raw negative replay passes. An earlier observer looked for an incorrect
UART marker and reported failure; that original result is retained in the
earlier p2smp3-6fd49c2a66 archive. It is not counted as a successful negative.

Targeted commands from `code/`:

```
python -m unittest tests.test_shared_large tests.test_p2_shared_large_guest tests.test_smp -v
python -m tests.run_p2_shared_large_qemu --reuse-esp <frozen-build>/esp --cpus 4
python -m tests.run_p2_shared_large_qemu --reuse-esp <frozen-build>/esp --cpus 1
python -m tests.run_p2_shared_large_qemu --reuse-esp <actual-bad-build>/esp --negative
python -m tests.run_p2_shared_large_qemu --replay <result.json>
```

Host tests execute real Dong debug/release and an independent C raw-table
oracle. Four actual source mutants per mode are rejected on their specified
ordering/range/domain invariants; counter-overflow seeding uses the real inner
Stats offset104, verified from the compiler layout. Three separate raw-oracle
tests reject report/ABI forgery, missing ACK, returned lease, aliases, table
cycles/unreachable/unzeroed slots/cache changes and corrupt buddy ledgers.
Existing SMP native state/trampoline/TLB-retention regression also passes.
The SMP runtime observer now derives expected final AP observation from the
actual P2 report; the legacy marker-B constant remains only for older builds.

All changes are physically present in the main workspace; status still requires
the coordinator's independent restricted subprocess verification and explicit
accept/integrate transitions. Reviewer evidence uses source inspection plus
separate C/raw oracles and a formal subprocess, not a claim of a second AI
reviewer. General multi-CR3 post-scheduler mutation, EXEC, graphics WC and PCID
hardware claims remain outside this completed shared-root ownership epoch.
Claude P2EXEC1/P2WC1 are separately assigned candidates; they are not completed
consumers or substitutes for normal guest integration.


## AI交付 2026-10-21T14:24:27+00:00 · codex-mcp-6fe7be60df984d37

P2SMP3 declared16 files implemented in the main workspace. Actual normal runtime7 release 1/4CPU and single-call AP-shootdown omission negative passed, complete raw replay passed. 316 build inputs match main; kernel2006608B/headroom90544B. Read-only physical pool/buddy/lease/domain/context/mailboxes prove persistent held512 pages,524 additional barriers and1572 AP ACKs on4CPU; desktop plus two stable P5 control observations passed. Independent C/raw host tests pass locally, no skip; request formal isolated checks tests.test_shared_large/tests.test_p2_shared_large_guest/tests.test_smp. Full evidence and preserved observer failure in codex-works/deliveries/P2SMP3.md and .local/p2smp3-47d6915707/final-guest-index.json. No second AI reviewer claim; source inspection plus independent C/raw oracles/formal subprocess. EXEC/WC and arbitrary user multi-CR3 remain separate.
