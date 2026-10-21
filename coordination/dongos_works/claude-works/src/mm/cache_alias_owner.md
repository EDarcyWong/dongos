# Fixed-root framebuffer cache migration

`mm.cache_alias_owner` is a component candidate for the normal kernel's future
framebuffer WC consumer. It executes existing `cache_type_plan.plan_migration`
and actual `paging.unmap_live`, `reclaim` and `map_live` calls. A complete
migration is revoke all aliases, first all-reader TLB barrier, reclaim exact
retirements, all-reader cache maintenance, PAT4 write/readback, WC remap, second
all-reader TLB barrier, then publish complete. It never frees or unpins the
framebuffer. Successful and failed transactions both retain its trusted lease.

The public API is `bind(*const Config,*Context) -> u64`,
`execute_migration(*Context) -> u64`, `seal(*Context) -> u64`, and read-only
scalar `audit(*const Context,index) -> u64`. Config contains actual Space and
TLB Domain pointers, physical base/page count, alias and ReaderConfig slices,
a caller-owned Retired slice, a synchronous callback and opaque cookie.
Context storage must initially be zeroed, aligned, writable and disjoint from
all source/workspace storage. Its fields are private. Binding is a full
write-before-validation boundary: failed bind leaves Context, receipts and
all sources unchanged. No public numeric ABI size is hardcoded; use `sizeof`.

## Unsafe contract

The caller is the sole BSP writer, IF=0, before user/scheduler root handoff,
with PGE/PCIDE disabled and no interrupt/NMI/exception access to the windows.
It supplies a trusted live framebuffer lease, not a buddy RAM allocation.
Every declared object/slice is actually accessible for its entire declared
size and remains alive. Numeric pointer checks cannot establish accessibility.
All descriptor, Domain/CPU/mailbox/Ops, actual table/metadata and receipt
storage must be mutually disjoint, including unused declared tails. MTRR
arrays for separate readers use separate storage. No external writer modifies
Space, aliases or reader descriptions during the binding lifetime; hardware
callback CPU readback updates are the explicit exception.

The region has 1..4096 pages and 1..4 disjoint contiguous supervisor RW/NX
aliases. Only initial WB/UC PAT selectors are accepted. The bound full root
pool has at most256 tables; this includes the normal kernel's128-table pool.
Every reader has an ONLINE fixed identity/epoch/root and trusted PAT/CR0/MTRR
snapshot. Caching is enabled. Initial PAT is uniform, valid, with entry0 WB
and entry3 UC. MTRR resolution and PAT combination are checked on every page
for every reader, not only the first address or BSP. Effective old type must
be uniformly WB or UC; mixed/undefined/conflicting types are conservatively
rejected. Target effective type must be WC.

`paging.inspect` supplies the actual private backing pool identity. The bounded
walker validates parent ranges/unique ownership/no cycles, reachable metadata,
all leaf encodings and the complete closed framebuffer alias set. Hidden HHDM
or other aliases, wrong PA/permissions/cache, target-covering large leaves and
malformed parents fail without writes. Other unrelated large mappings remain
allowed. When changing PAT4, any other existing PAT4 consumer is rejected,
including a PAT4 large leaf. New PAT preserves every byte except entry4.

Source alias/MTRR hashes, original range pointer/lengths and stable CPU
identities are rechecked before execution. The Domain broadcast sequence may
advance normally; it is not used as a topology epoch. Binding pool identity
and the full raw tree are checked again before the first publication.

## Callback and replies

Callback is `unsafe fn(cookie:u64, phase:u64, root:u64, value:u64,
replies:*Reply, count:usize) u64`. A nonzero result is preserved as the original
error. FIRST_BARRIER(2), CACHE_MAINT(3), PAT_UPDATE(4), SECOND_BARRIER(6) must
perform their actual hardware action synchronously on all readers and fill
one Reply per reader: ack, online epoch, root, CR0, PAT and MTRR snapshot hash.
A zero aggregate return is insufficient; every readback must match. PAT
callbacks update the Domain CPU PAT records to the actual readback. A missing,
wrong or stale reply stops the transaction. PAT_UPDATE is still called to
confirm PAT when entry4 already has WC. Cache maintenance is required even
when the initial effective type is UC.

REVOKE(1), REMAP(5) and RECLAIM(8) are post-action audit notifications. `value`
is the affected VA for revoke/remap, receipt index for reclaim, new PAT for
PAT_UPDATE, old effective type for CACHE_MAINT, zero for barriers. These audit
callbacks must not change the transaction storage; any nonzero result also
poisons and retains the exact completed state. In the native model they allow
independent observation at each actual page operation. This abstraction does
not claim that native host tests executed WBINVD, WRMSR or privileged TLB flush.

## Retirements, failure and audit

The caller supplies at least pages*aliases distinct Retired objects, up to16384.
They are dynamic caller workspace rather than a one-megabyte kernel BSS array.
All declared receipt storage is initialized only after bind has fully passed.
Every unmap receipt is retained, even when it retires zero table pages. Reclaim
starts only after all first-barrier acknowledgements; successful earlier
reclaims remain counted if a later stage fails. Mid-remap allocation failure
keeps partial WC PTEs, original framebuffer ownership and unreclaimed receipts,
while complete stays false. No failed transaction can be resumed or reused.
Repeated successful execute is an audited no-op; sealed contexts cannot mutate.

Audit indices:0 bound,1 poisoned,2 busy,3 sealed,4 lease held,5 complete,
6 current/failing phase,7 original error,8 revoked pages,9 receipts produced,
10 receipts reclaimed,11 remapped pages,12 callback count,13 first-barrier
reader mask,14 cache mask,15 PAT-confirmation mask,16 second-barrier mask.
The final Reply array and exact pending receipts remain available in the
compiler-described Context/workspace for independent raw inspection.

## Verification and integration boundary

Permanent unittest compiles actual Dong in debug/release, assembles ELF64 and
COFF, and executes explicit SysV native calls. An assembly capture restores
and checks RBX/RBP/R12-R15 and RSP after the production execute returns. The
independent C oracle walks real page tables and all metadata/receipts at each
callback; it does not treat production query or planner output as its oracle.
It checks 1/4/16 readers, maximum4096 pages/four-alias binding, full descriptor
boundaries, hidden/large aliases, malformed parents/metadata, per-page MTRR,
every revoke/remap/reclaim failure, both barriers/cache/PAT failures, missing
or wrong replies, epoch changes, busy/seal/no-op and actual partial-remap OOM.

Four actual wrong Dong sources skip cache maintenance, retain an old selector
on one remap, publish complete before the second barrier, or continue reclaim
after missing ACK. Each compiles/links and normally returns before the raw C
invariant rejects it. Full inputs including transitive DG, C/Python, this
contract and delivery are hashed before/after. Missing tools fail, never skip.

This component is not yet proof of normal GOP integration or true hardware WC
performance. The normal consumer must supply actual MTRR capture, privileged
callbacks and real SMP guest positive/negative evidence; TCG cannot establish
physical WC throughput. Do not mark the entire P2/WC stage complete from native
component results alone. Earlier uncompiled placeholder versions are archived
under the coordinator takeover evidence; their completion claims are obsolete.
