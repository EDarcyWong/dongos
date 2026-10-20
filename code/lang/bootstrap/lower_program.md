# Native checked graph to program lowering

`lower(g,w,mode,result)` consumes only an unmodified successful
`frontend.Graph`. It uses semantic `Info`, resolved binding references, evaluated
scalar constants, layouts and field offsets. It does not parse source literals
again, ask the Python compiler to build IR, or infer types from syntax.

The caller supplies functions, instructions, argument records and a node-slot
map. The node-slot map must cover all graph nodes. Lowering allocates every
parameter/local before temporary evaluation, preserving lvalue addresses and
all earlier call arguments while nested expressions execute. Argument ranges
are reserved before recursively lowering their expressions. Slices remain
whole two-word values across calls and returns. Local/temporary byte offsets
are reused after their lifetime ends; frame requirements over 4080 fail.

## Supported source subset

Scalar constants, scalar/pointer/slice parameters and locals; bounded struct/array locals, exact-byte aggregate copies, named/repeated aggregate literals, decoded strings, raw slice construction and checked subslices; direct calls and
returns; integer casts and arithmetic, comparisons, short-circuit booleans,
wrapping add/sub/mul; address/dereference; exact typed field/index loads and
stores; slice `.ptr`/`.len`; blocks, if/else, while/loop, break/continue and
compound assignment. Assignment evaluates its address once. Scalar field
access through a struct pointer uses semantic field offsets. Static scalar, struct and array constants are emitted in read-only data; taking a static array subslice does not create a stack copy. Function export aliases are preserved.

Unsupported values/statements/intrinsics, mutable globals, methods/enums/error
declarations, foreign declarations and unsupported static initializers return UNSUPPORTED. Aggregate local alignment above 16 and frames above 4080 bytes remain explicit bounds. Even unsupported code after a return is rejected;
it is not silently omitted. Recursive syntax traversal is bounded at 256,
independent of the frontend's caller-selected depth limit.

## Results and failure atomicity

Statuses: OK=0, INVALID=1, CAPACITY=2, UNSUPPORTED=3, FRAME=4, BAD_GRAPH=5.
The Result contains status, unit/local-node, detail and a Program.

- INVALID descriptor/mode leaves every caller byte unchanged.
- All descriptor spans are checked for nonwrapping, required alignment and
  disjointness before writing. All four full scratch ranges and Result must be
  separate from each other, both descriptors, the entire declared frontend
  arena, source catalog and every full source path/text span.
- After valid preflight, scratch pools may change on failure. Result reports
  the failure and publishes a null graph and zero-length program pools.
- Only OK publishes immutable used prefixes. Pool guards and unadvertised
  capacity must never be written.

This unsafe API requires actual addressable descriptor backing memory and an
actual successful frontend graph. It is not an arbitrary-pointer validator.
The native compiler pipeline test exercises exact/one-short pools, aliases,
unchanged graph/source bytes, and caller guards in debug and release.
