# bootstrap.frontend: bounded native checking pipeline

This module owns the compiler orchestration: `modules.load → names.collect → binding.check → semantic_types.analyze_program`. It consumes an explicit source catalog and calls actual Dong implementations. It performs no filesystem access, Python callbacks, allocation, or code generation.

## Public ABI

```text
Options { entry:usize, roots:usize, max_depth:usize }          // 24 bytes
Limits { tokens,nodes,strings,edges,types,fields,limbs,text,
         math_limbs,math_work:usize }                       // 80 bytes
unsafe check(options:*const Options, sources:[]const modules.Source,
             limits:*const Limits, storage:[]u8, result:*Result)u64
```

All structures are 8-aligned on x86-64. Export `dong_frontend_check` takes the same arguments, with source/storage slices split into pointer and count. Source is the existing 40-byte `modules.Source`.

`Result` is 360 bytes: eight u64 fields `status,exit_code,stage,code,detail,source,offset,used`, then a 296-byte Graph. Graph has 18 constant slice descriptors in this exact order:

`arena,sources,units,tokens,strings,nodes,edges,symbols,refs,types,fields,node_types,values,value_states,limbs,layouts,field_offsets,info`

The final Graph field is `entry:usize`, a Unit index, always zero on success. Types are respectively byte, Source, Unit, lexer.Token, byte, expression.Node, modules.Edge, names.Symbol, binding.Ref, semantic.Type, semantic.Field, usize, semantic.Value, byte, u32, type_layout.Layout, usize and semantic.Info. All published slices are immutable borrows; there is no hidden copy to a host AST.

## Publication and lifetime

Success publishes only used graph prefixes. Node-indexed arrays use global node-pool indices; Unit token/node IDs and Ref LOCAL targets retain their existing local-index convention. `types/fields/limbs` lengths are successful semantic counts; `values` is meaningful only where `value_states==2`. Layout and field-offset arrays match the published types/fields. Runtime Info uses the semantic layer's flags and type identifiers without reinterpretation.

Graph.arena is the entire caller-declared storage extent, including unused tail. Lowering may use it to reject output aliases with any retained frontend allocation. Source descriptors, paths and bytes remain separately borrowed and must stay alive.

The caller owns storage and must discard the Graph before reusing/resetting it. Each call initializes a fresh D12 arena over that storage; it never reads state left by a previous compilation. No rewind occurs while a successful graph is live. There are no global variables.

A failure publishes an empty Graph: all slice pointers/counts zero, entry=NONE. Intermediate pools may have changed; they are never published as a usable program. A nonzero `unchecked_initializers` from the full runtime checker is an internal error, never success.

## States

- 0 OK: exit_code 0, complete checked graph within currently supported semantics
- 1 INVALID: caller descriptor/option/path preflight rejection; all storage and Result bytes remain unchanged
- 2 CAPACITY: exit_code 2, bounded arena or stage pool exhausted
- 3 SOURCE: exit_code 1, source rejected by a native stage
- 4 UNSUPPORTED: exit_code 1, unsupported construct or explicit depth bound
- 5 INTERNAL: exit_code 2, downstream graph/descriptor contract failure

Result.stage is WORKSPACE0, MODULES1, NAMES2, BINDING3, SEMANTIC4. Code/detail preserve the underlying stage status, rather than flattening useful diagnostic information. Source is a catalog index or NONE. Offset is relative to the source after skipping exactly one leading UTF-8 BOM, as in modules.load. Later-stage unit/token positions are translated using the actual Unit and Token pools.

INVALID is a return value only: do not read an untouched Result as though it had been published.

## Memory budgets and validation

Source catalog and path rules are those of modules.load, including explicit roots and canonical relative `.dg` paths. All read-only descriptors may share storage. Caller-provided writable Result/storage must be disjoint from each other and the complete descriptors, source paths and source byte ranges. Full endpoint, multiplication and alignment checks precede source-content reads and arena allocation. All nested source spans are checked before inspecting any path content. Unsafe callers still guarantee that valid-looking spans are actually accessible.

The arena is caller supplied and may start unaligned. core.arena handles natural alignment. Its 40 allocations comprise six module pools, two name pools, three binding pools, 24 semantic pools and five runtime pools. Units and module states have source-count capacity; symbol/ref/local pools use the declared node capacity. Semantic math tokens/nodes each have fixed capacity eight, as required by the synthetic arithmetic evaluator; text/limb working capacities are explicit Limits.

Runtime arrays reserve Info[Nodes], initialization[Nodes], snapshots[2×ceil(Nodes/8)×Depth], breaks[ceil(Nodes/8)×Depth], loop_seen[Depth]. The snapshot and break pools are bit-packed; each slot has its own rounded-up tail byte. The initialized pool remains byte-per-node, and oversized callers remain valid. Multiplication is checked before use. No live pool is reused and the immutable Graph.arena lifetime is unchanged. A declared depth of 256 is a traversal limit, not a promise that a target's stack is large enough. Explicit host budgets must be sized for the actual compiler closure.

Result.used is the arena high-water mark for this invocation. On a reservation failure it is the successfully reserved prefix, not the total required size. On a completed reservation it includes all reserved capacities, not only published graph lengths. Storage after used remains untouched. Capacity failure does not silently resize or retry.

## Verification

`NASM=/path/to/nasm python -m unittest lang.tests.test_bootstrap_frontend -v`

Tests build the real closure in a frozen private source snapshot, assemble ELF64 and COFF, and execute both modes through a C observation harness. The harness supplies read-only source bytes/catalog/options/limits; checks descriptor errors, guards, graph references, exact capacity, diagnostic atomicity and repeated arena reuse. The actual 13-module semantic-checker and 19-module frontend/diagnostic source closures must pass native checking with explicit large budgets. These source-checking results are not self-host success. Real Dong mutations replace full runtime checking with declaration-only checking and misroute cross-module error sources; the resulting native executions must be rejected by independent status/diagnostic assertions. A retained summary records source stability, artifact fingerprints, executed cases and explicit false self-host/OS-VM flags.

This is a native frontend integration. It does not implement a complete compiler backend, target filesystem provider, stage1/stage2 build, or DongOS self-compilation.

