# Explicit graph compaction

`bootstrap.graph_compact.compact(g: *frontend.Graph, r: *Result) u64`
performs an optional, consuming ownership transition on a successful native
frontend graph. `OK = 0`; `INVALID = 1`.

## Ownership contract

The caller must exclusively own the graph descriptor and its mutable backing
arena, and supply a writable result descriptor. The successful graph, source
catalog, paths, and source bytes must still be live. Existing graph consumers
continue to treat a graph and its published arena as immutable; this operation
is not permission for consumers to reuse arbitrary scratch inside that arena.

On success, every previously borrowed arena or pool alias is invalidated. Use
only the updated graph descriptors afterward. Any lowered Program referring to
this graph must be discarded before compaction and rebuilt afterward. The source
catalog and source byte/path storage retain their addresses and contents.

The sixteen published used pools are packed in frontend allocation order, with
their original element alignments. Their counts, record bytes, and index-based
relationships are unchanged. Only their slice pointers and `graph.arena.len`
change. The graph's arena pointer does not change. Alignment padding is retained
but is not promised to be cleared or canonicalized. The discarded tail is not
zeroed or freed by the operation; it becomes available for caller-managed reuse.
No allocator, OS, or VM operation is performed.

`Result` reports `old_bytes`, `retained_bytes`, and `reclaimed_bytes`, with
`old_bytes = retained_bytes + reclaimed_bytes`. These describe the published
arena, not the caller's entire backing allocation or compiler peak memory.
Compacting an already compacted valid graph succeeds with zero reclaimed bytes
and leaves its descriptors and arena bytes unchanged.

## Validation and atomicity

Before writing anything, the implementation checks descriptor alignment, null
and overflowing spans, descriptor/arena/source separation, successful-graph
count relationships, pool extent multiplication, alignment, bounds, order,
non-overlap, and forward-only relocation destinations. On `INVALID`, all graph,
result, arena, and source bytes remain unchanged. No malformed pool is read
before preflight completes. Empty pool pointers are not dereferenced.

This is an unsafe API, not a memory-mapping oracle: numerically plausible but
unmapped graph or source descriptors cannot be validated without reading them.
The caller remains responsible for live descriptor and backing-memory validity;
structural preflight cannot establish graph provenance or semantic correctness.

## Native verification

`python -m unittest lang.tests.test_bootstrap_graph_compact -v` builds frozen
source snapshots in debug and release modes, then tests both compiler emission
modes. Set `NASM` and `CC` if the tools are not on PATH. The test checks all
sixteen used-pool hashes and exact packed addresses, source preservation,
compiler-driver assembly equality before and after compaction, immediate
released-tail overwrite, idempotence, allocation guards, and rejection with no
byte changes for malformed descriptors, spans, ordering, alignment, and overlap.
The test is host-native only and makes no guest-fit or complete self-host claim.
