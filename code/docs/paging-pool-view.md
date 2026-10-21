# Actual paging pool identity

`mm.paging.inspect(space, out)` returns a `PoolView` from an actual initialized
Space. It exposes const table/metadata views, count, physical root, address mask,
used count and NX capability. It never constructs a Space or changes a table,
allocation record or control register. Existing Space/Context ABI is unchanged.

The unsafe caller supplies readable valid Space storage and writable output
storage when their numeric ranges are valid. Pointer values alone cannot prove
host accessibility or virtual-to-physical correspondence. The caller owns the
Space and all backing storage exclusively and keeps them alive; this view is
not a lock, lease or a snapshot of page-table bytes. Hidden physical aliases
must still be excluded by the owning transaction's complete bounded walk.

Before any write, inspect checks both complete descriptor endpoints/alignment
and rejects output overlap with the entire Space, table pool or metadata array.
The output size uses `sizeof`, never a stale numeric ABI constant. Failure leaves
all source/output bytes intact. Uninitialized Space returns NotInitialized.
The returned const pointers are the actual private Space backing pointers;
consumers do not supply an alternative purported pool and guess its identity.

P2EXEC1 and P2WC1 will use this as their full-root alias scanning input. This
accessor alone does not complete either transaction or enable EXEC/WC.
