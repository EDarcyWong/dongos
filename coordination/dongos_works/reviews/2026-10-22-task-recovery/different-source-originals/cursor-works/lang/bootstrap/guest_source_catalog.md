# Bounded explicit source catalog

`load(inputs, entry, workspace, read_at, result)` converts at most 256 already
authorized file identifiers to `modules.Source` records. It neither opens nor
enumerates files. Each Input holds root (0 or 1), relative UTF-8 `.dg` path,
opaque callback context/file identifier, and a capacity at most 128 KiB.
Same-root duplicate paths are rejected. Cross-root duplicates remain separate
so the existing module resolver can diagnose ambiguity.

Workspace contains separate scratch, staged, storage, sizes and sources
slices. Scratch must exceed the largest file capacity by one byte; staged and
storage must each hold the sum of path lengths plus file capacities. Sizes
and sources must hold the entire input count. Every complete mutable range,
result, input descriptor, workspace descriptor and input path is checked for
alias/overflow before reading or writing. Disjoint read-only inputs may alias.

INVALID (1) and CAPACITY (2) write nothing and perform no reads. On SOURCE (3),
only temporary scratch/staged/sizes and Result may change; storage and sources
remain entirely unchanged. Result identifies the failed input, reader status
in code and original callback/protocol code in detail. EOF must be confirmed
for every file; short reads and exact-capacity probes use guest_source_reader.

Only after the last file succeeds are final bytes compacted into storage and
sources published in input order. Each returned path/bytes points into caller
storage, never staging, scratch or the stack. `used` is the actual byte count;
unused storage and Source tails are untouched. Storage and Source records
must remain alive through frontend use. Reuse requires releasing all aliases.
The call is synchronous and exclusively borrows all writable buffers.

Result ABI: seven u64 words, status/index/code/detail/used/count/entry. Successful
index is UINT64_MAX. Entry is an unchanged index into the input-order catalog.
This catalog does not grant root confinement or file permissions. Callbacks
must honor the reader ABI and be nonnull; accessible mapped storage is the
unsafe caller's responsibility. Success proves no guest execution or L3
completion.
