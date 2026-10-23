# Runtime page-table forest audit

`mm.runtime_roots.audit` is the read-only P2ROOT13 component. It audits an actual
kernel `paging.Space` and zero to sixteen actual user Spaces via `pg.inspect`.
It does not acquire BKL, stop users, execute a TLB/cache instruction, mutate a
PTE, establish physical ownership, reclaim a table, or enable the later runtime
large-page/EXEC/WC consumers. Those remain separate work and acceptance gates.

The caller is trusted to enumerate **every** relevant live, dormant and retiring
root and to keep their descriptors, pools, metadata and lifetimes stable for the
whole call. A supplied array is not evidence that it covers memory/Catalog/domain
state. The later consumer must derive this enumeration under its real BSP/BKL
transaction, bind Catalog token/incarnation and memory generation separately,
and provide the relevant quiescence and lease proof. Numeric pointer validation
cannot establish that arbitrary memory is readable/writable or that two virtual
addresses do not secretly alias the same physical storage.

`Root` contains a real Space pointer, unique caller identity 0..15 and nonzero
generation. These fields label results; this component cannot authenticate their
relationship to the Catalog. Kernel results use identity `KERNEL_ID` and generation
zero. Every pool is at most 256 tables. Each descriptor must have a valid
32..52-bit physical address mask and NX support. The canonical kernel descriptor
is trusted to carry the actual CPUID hardware limit. Each user retains its own
descriptor limit; a transient view uses the smaller of its own mask and the
kernel hardware mask for its complete private pool, present parent/leaf address
bits, reserved bits and leaf extent. High address bits are rejected before
extracting a PA; masking them away cannot turn an invalid entry into a low PA.
The source descriptors are never rewritten. Physical pools are disjoint; the actual
Space, table pools, metadata, root descriptor array, output array and Report are
checked for complete virtual-storage overlap, range overflow and alignment.

The forest follows `user.memory.load_candidate` exactly: every user PML4 entry
**1..511**, including the low-half entries 1..255, must equal the corresponding
canonical kernel entry. Only the hardware-accessed bit may differ in these
non-leaf references; a nonzero entry in place of kernel zero is rejected. Dirty
is accepted on leaves, not treated as a hardware update to a PML4 reference.
The kernel's complete tree is scanned once; each user's private slot0 is scanned
once. Shared entries borrow the canonical hardware-width tree: a kernel52
parent above bit47 remains valid in a user48 shared slot. The private48 mask
limits that user's own pool and slot0, and does not truncate the borrowed
canonical references. Full raw equality, A-only variation and exact zero apply
at all shared slots. No foreign child, duplicate parent or cycle is allowed inside a private
tree. Shared kernel aliases are returned once, rather than once per user root.
The result's `shared_entries` and `kernel_scans` make that convention explicit.

All reachable table indices must have metadata1, every metadata1 must be
reachable, and the reachable count must equal `Space.used_total`. Metadata2 is
`PENDING`, not free or reclaimable: the component has no complete linear
`paging.Retired` receipt set and therefore refuses the forest without changing
the isolated table, metadata or receipt. Other malformed metadata and links are
also refused. There is no reclaim operation in this module.

The physical query is an arbitrary nonempty byte interval, with PA zero,
overflow and intervals outside the trusted kernel hardware limit rejected.
A query above a narrower user's private limit is still valid when it is inside
the hardware limit, since it may find a canonical kernel alias. Every overlapping 4KiB or 2MiB leaf
produces an `Alias`: actual root/identity/generation, VA and PA of the **clipped
intersection**, intersection bytes, effective WRITE/USER/EXECUTE flags, leaf
UC/WC selector and original leaf size. Parent RW/US restrictions and NX are
combined across the path. Reserved/global/unsupported cache encodings,
effective writable-executable leaves and effective high-half USER leaves are
rejected. The cache flags identify the PTE/PDE PAT selector; they do not prove
the PAT MSR, MTRR effective type, hardware cache state or actual throughput.
Cross-alias W^X is a later owner's decision over these complete records.

Consecutive intersections coalesce only when root, identity, generation,
effective permissions/cache and original leaf size agree and **both** VA and PA
are contiguous. The scan still validates and counts every leaf. Thus 512
consecutive split 4KiB leaves can occupy one output record; a single changed
permission or replaced PA forms separate segments. A 2MiB leaf and an adjacent
4KiB leaf never merge, nor do consecutive VAs repeatedly aliasing the same PA.

The output limit is 64 alias segments. Capacity exhaustion, including a smaller
caller array, returns `CAPACITY` without changing any output byte or Report.
`audit` additionally requires a caller-owned `*Scratch`, aligned to 64 bytes,
with `sizeof(Scratch)` readable/writable bytes. Its contents need not be
initialized and are consumed workspace, **not an output receipt**: they may
change on success or a later failure. Do not share it between concurrent calls,
retain pointers into it as published results, or overlap it with any Space,
table pool, metadata, Root array, output array or Report.

Scratch owns the 64-record staging array and seventeen cached views. The
component first performs a bounded pairwise storage preflight using small local
descriptors. It checks every complete input, output and workspace interval,
including partial overlaps, before its first Scratch write. Numeric/alignment/
overflow and storage rejection therefore leave even Scratch untouched. After
preflight, all inputs and outputs still remain unchanged on every failure;
only Scratch is expendable. Successful commit leaves the unused output tail
untouched. No large array is copied into a local frame or passed by value.
The compiler's existing 4096-byte per-function frame restriction is retained.
A real post-scheduler caller must separately budget its Scratch lease and full
call-chain stack usage.

The first formal execution, job `76079278fbaf49358c4765d958416937`, refused all
eight production/mutant compilations with E0601 (at least 4112 frame bytes versus
4096 allowed). That failure is retained and is not a test pass. The caller-owned
Scratch revision addresses that actual restriction without changing the compiler
limit, forest rules, capacity rules or output-atomic contract.

The next formal job, `06b9aaa2156f47418b9237fadbf0231e`, ran for 17.407s
with zero skips and failed: all eight debug/release production/mutant Dong
compilations and both object-format assemblies succeeded, but C linking was
blocked by `-Werror=misleading-indentation` at the raw oracle's same-line
`continue; U first=...` statement. The C formatting revision uses braces and
separate statements; `-Werror` and every oracle assertion remain enabled. This
failed run is retained and does not establish a passing native execution.

P2ROOT13 subsequently reached integrated revision15 after independent passing
host verification. That historical result covered fixtures with matching
48-bit masks. P2MASK18 addresses a later production integration finding:
`boot.memory_startup` uses real CPUID physical width, while `user.memory` builds
private Spaces with a fixed 48-bit descriptor. Requiring equal masks therefore
refused valid forests on hardware with a different physical width. The new
bounded views preserve both hardware and private limits without changing the
production root builders or broadening the earlier acceptance claim.

Status values are OK0, INVALID1, CAPACITY2, SHARED_MISMATCH3, FOREIGN4,
MALFORMED5, ACCOUNTING6, PENDING7 and STORAGE8. Errors are evidence that an owner
cannot use this forest as a closed set. They never authorize resource reuse.

`tests.test_runtime_roots` stages and compiles the production module plus real
production paging in debug/release, assembles ELF64 and COFF, then executes an
independent C raw walker and storage guards. The fixture creates real Spaces and
copies entries1..511 with the production layout. It checks hidden aliases,
byte intersections, 2MiB overlap, effective parent permissions/NX, leaf A/D,
sixteen users, real 512-leaf split and single-page protect/replace segmentation,
actual paging initializations for kernel36/40/46/52 with user48, and a kernel52
pool and shared parent above bit47 with a valid low private48 pool. The C walker
independently reads each real Space mask and recomputes its hardware/private
bound, parent/leaf reserved bits, 2MiB extent and query range. Precise rejection
controls cover pool starts and pool tails, parents, 4KiB/2MiB leaves beyond
either hardware or the private limit, and queries crossing the hardware limit.
The existing cases retain
slot1 mismatch, private foreign/cycle, metadata2 produced by real
unmap, capacities, source/output overlaps and numeric overflow. Scratch contents
are intentionally excluded from post-preflight content-invariance checks, but
all outer guards remain checked. Null/misaligned/overflowing Scratch, overlap
with every input/output class and partial pool overlap must fail without any
write, including to Scratch. Dirty Scratch is reused across successful calls.
Five real Dong
mutants ignore shared equality, accept a private foreign link, or omit a hidden
RO alias, ignore the hardware limit, or replace the private limit with a wider
hardware mask; each must compile and normally exit at its exact independent oracle
failure. Source/backend fingerprints, both object formats, commands, stdout,
stderr and result receipts are saved under `build/test/runtime-roots/run-*`.

Implementation delivery has not run these tests. Only the coordinator's fresh
zero-skip, stable-source verification can establish their result. No OS/VM is
started by this host test. Passing it does not close P2 or replace actual guest
multi-root/PCID/large-page/EXEC/WC evidence.
