# Native compiler arena facade

`compiler_driver.dg` connects a live successful `frontend.Graph` to the production
`lower_program` and `nasm_program` modules. It performs no host-side parsing, IR
construction or assembly formatting. Its exported SysV function is:

```c
uint64_t dong_native_emit(const Graph *, const EmitLimits *, uint64_t mode,
                         uint8_t *storage, uint64_t capacity,
                         uint8_t *out, uint64_t out_capacity, EmitResult *);
```

On x86-64 `EmitLimits` is seven u64 fields (56 bytes), in order: functions,
instructions, arguments, text, piece, parameters, locations. `EmitResult` is eight
u64 fields (64 bytes): status, stage, code, unit, node, detail, used, written.
Mode 0 is debug, 1 is release. `unit` and `node` are source graph indices on a
lowering failure; non-source locations use all-ones.

Status: 0 OK, 1 INVALID descriptor, 2 CAPACITY, 3 UNSUPPORTED, 4 FRAME,
5 INTERNAL. Stages: 0 workspace allocation, 1 lowering, 2 text emission.
`code` retains the original stage result; invalid/internal results from the
submodules are not misreported as valid source errors. Unsupported constructs
are never a successful compilation. The supported language and temporary trap
semantics are described in `lower_program.md` and `nasm_program.md`.

The graph descriptor, graph arena, source catalog and all path/source byte spans
must remain valid and immutable for the call. This unsafe API requires a real
successful frontend graph, not arbitrary forged graph-internal slices. Descriptor
alignment, span arithmetic, multiplication, and overlap with every output region
are checked before writes. Storage, final output and result must be mutually
disjoint, and none may overlap graph inputs or limits. INVALID leaves all caller
memory unchanged. A zero-length null storage/output span is valid and can yield
CAPACITY. Nonempty pointers must denote live accessible objects; span arithmetic
cannot establish host memory ownership.

The caller supplies a single bounded scratch arena. Arrays for functions,
instructions, argument records and node slots are allocated first, then NASM
staging/piece text and ABI planner scratch. `used` is total reserved storage,
not peak live data or an automatic target process memory guarantee. Checked
allocation failure returns CAPACITY without silently increasing the budget.

After preflight, scratch may change on failure. Result is published with written=0
for every non-INVALID failure; final output is unchanged. Successful emission
copies the complete staged assembly and publishes its exact byte count. No file,
assembler, linker or target disk I/O is performed here.
