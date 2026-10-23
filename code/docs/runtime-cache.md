# Post-scheduler GOP cache migration component

`mm.runtime_cache` provides the P2CACHE20 core transaction and an independently
testable atomic drawing gate. It does not yet install the production framebuffer
ledger, multiplex the scheduler poll hook, or guard normal/panic/NMI drawing
entries. Those adapters and an actual guest execution require a later shared
integration task. Linking these files or passing a host test does not establish
runtime integration, hardware cache behavior or physical display performance.

The owner runs one complete **WC → UC → WC** transaction. It does not change
PAT or MTRRs. Every online CPU must initially report PAT0=WB, PAT3=UC and
PAT4=WC, identical complete PAT/MTRR state, normal CR0 caching and PGE disabled.
Each subsequent readback must match that CPU's initial CR0/CR4 and the complete
initial PAT/MTRRs. PCIDE may remain enabled: the existing user Domain supplies
the real all-tag barrier. This component never weakens the older fixed-root
`cache_alias_owner` PCIDE rejection or its permanent seal.

`bind(Context*, Config*)` consumes caller arena storage. Context and Work have
64-byte alignment; a separate `Page[]` supplies one linear Retired receipt for
every page of every alias. The configured capacity is checked before mutation,
up to 65,536 linear alias pages. This is a storage bound, not a promise that an
integrated kernel has allocated enough arena pages. No component BSS allocation,
heap allocation, larger compiler frame limit or increased 2 MiB image budget is
introduced. Work is consumed scratch and may change after a rejected preflight;
all source descriptors, tables, metadata, Context, Page storage, gate, ledger
and publication epoch remain unchanged by a failed preflight. Retired storage
must initially be zero, so a held linear receipt cannot be overwritten.

Config contains the actual kernel hardware `paging.Space`, full memory root
set, actual BootInfo pointer, full published alias ledger, user Domain, gate,
publication epoch, deadline and trusted hardware/identity readers. BootInfo's
raw GOP base and size determine the physical interval; rounding includes both
partial edge pages. A caller cannot select a shorter framebuffer interval.
The independent Check callback must re-enumerate actual memory descriptors,
Catalog token/incarnation and the published ledger under CPU0's BKL, including
preloaded, dormant and retiring roots. Comparing the provided array to itself
does not fulfill this authority contract. The component also checks every
admitted Domain root against the supplied memory slot/root. Memory generation,
Catalog incarnation and Domain incarnation are separate namespaces: none are
equated. Immutable Space fields, root identities, raw Domain process fields
and topology are independently bound and rechecked throughout the transaction.

The initial complete forest scan must exactly equal the published ledger, in
canonical forest order. Extra aliases, missing USER aliases, stale identities,
EXEC, unsupported cache selectors, 2 MiB GOP leaves and unaligned ledger ranges
are rejected. Every original USER and WRITE bit is retained; NX is mandatory.
There must be one complete kernel HHDM alias and at least one private USER
alias. This bounded implementation supports the ordinary HHDM PML4[256] plus
private slot0 topology, with GOP and kernel pool physical addresses below
512 GiB. A different shared topology is refused, not silently omitted.

The permanent anchor `HHDM + kernel_pool_physical` must already map that actual
non-GOP table-pool page as WB/RW/NX. This proves that removing every GOP mapping
cannot detach the borrowed HHDM PML4[256] reference. Its raw parent entry remains
bound, allowing only hardware Accessed changes. Each private alias is modified
through its own real Space. The canonical shared kernel tree is modified once;
borrowed foreign table PAs are never admitted to the private paging walker.

The supported GOP begins at or above 1 MiB. All variable MTRR base/mask pairs,
capability/default registers, physical width and all eleven fixed MTRR MSRs are
captured and retained, including zero unused variable slots. The planner
independently resolves every rounded GOP page and requires WB-compatible MTRRs.
Fixed registers are preserved and compared in full; low-memory fixed-range
resolution is outside this component's admitted GOP envelope. PAT4/WC and
PAT3/UC therefore remain the exact unchanged selectors for the two rounds.

The execution order is:

1. Verify actual CPU0, IF=0, exact raw kernel CR3/tag0, BKL ownership, a healthy
   active Domain, complete root/ledger identity and the complete current forest.
2. Atomically close the drawing gate and drain writers that already entered.
   Capture every online CPU with the real Domain all-tag barrier. Users remain
   captured while CPU0 owns BKL.
3. Remove every rounded GOP page from every ledger alias. Wait for the first
   complete online all-tag ACK. Only then reclaim that round's linear Retired
   receipts and prove the complete GOP forest is empty.
4. Request actual local SFENCE/WBINVD on every online CPU, followed by full
   hardware readback. Each reply carries its CPU, request sequence, completed
   barrier, raw root, CR0/CR4, PAT and complete MTRRs. A callback return value or
   aggregate flush count cannot earn a maintenance ACK.
5. Restore the exact original VA/PA/USER/WRITE shape using UC. Complete the
   second all-tag barrier and recheck the full forest and hardware state.
6. Repeat removal, first ACK, reclamation, maintenance, WC restoration, second
   ACK and full revalidation. Open the gate only after both rounds succeed;
   commit one new ledger epoch. No fallible action follows gate opening.

Every failure after the transaction begins poisons the Domain, retains the GOP
lease and remaining receipts, and forces the gate closed. There is no rollback,
early remap, early reclamation, lease release or return-to-user fallback. The
component is one-shot. Errors use `0x0615_0001` Invalid, `0002` Authority,
`0003` Forest, `0004` Hardware, `0005` Held, `0006` Deadline, `0007` Capacity and
`0008` Storage. Real paging/Domain errors, including Domain timeout
`0x0609_0005`, retain their original code.

`runtime_cache_reader.asm` contains the future actual privileged reader and
SFENCE/WBINVD entry, with no WRMSR or hidden CR3 switch. The same file implements
real atomic gate enter/leave/close/drain/open helpers. Writers must use a
nonblocking try-enter; panic/NMI callers that cannot enter must immediately use
serial output without waiting for BKL. Closing preserves active writer counts;
open requires the exact current token and a completed zero-writer drain.
The closed word has a transient closing bit while epoch/drain state is
published, and an atomic opener claim precedes reopening. Existing writers can
still leave during that publication; a racing drain/open cannot consume an
unpublished token or regress a later opener's epoch.
Underflow, overflow, wrong tokens, repeated close/drain/open and stale opening
are rejected. Production entry-point wiring is explicitly still pending.

`tests.test_runtime_cache` stages real Dong paging, forest and Domain sources,
compiles debug/release within the existing 4096-byte frame limit, and assembles
both ELF64 and COFF. An independent C raw walker checks all kernel/USER aliases,
preserved RO/RW/NX flags, retirement metadata and linear receipts at each actual
protocol boundary. The C identity authority uses separately stored publication
data, with different memory and Domain generation values. Hardware callbacks
are explicitly mocked; privileged ASM is assembled but never called in the
host process. The gate's actual native atomic instructions are exercised using
deterministic writer/close/drain interleavings and failure checks.

Five genuine wrong Dong implementations omit USER revocation, reclaim without
the first ACK, omit per-CPU maintenance, accept a wrong PAT4 readback or open the
gate while mappings are absent. Each must compile and exit normally with rc1
at its exact independent C diagnostic. Production controls cover complete
restoration, preflight atomicity, missing roots/aliases, separate generation
corruption, a real undeclared USER mapping, non-WB MTRRs, insufficient receipt
capacity, source overlap, PGE/tagged kernel,
missing CPU ACK, bad maintenance and changed MTRRs. Native commands, source and
tool fingerprints, raw outputs, object/executable hashes and failure receipts
are retained under `build/test/runtime-cache/run-*`. No tests, compiler, OS or VM
were run during implementation. Only independent zero-skip, source-stable
coordinator verification can establish host acceptance.
