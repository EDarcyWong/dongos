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
stores; slice `.ptr`/`.len`; blocks, if/else, while/loop, range/array/slice for,
bool match, ordinary defer, break/continue and
compound assignment. Assignment evaluates its address once. Scalar field
access through a struct pointer uses semantic field offsets. Static scalar, struct and array constants are emitted in read-only data; taking a static array subslice does not create a stack copy. Function export aliases are preserved.

Mutable globals use typed static addresses and exact-width loads/stores.
Explicit `extern "sysv64"` definitions use the ordinary SysV path. Bodyless
SysV declarations reserve no function, instruction or frame; the text backend
resolves their checked linker name. Scalar/pointer external signatures retain
the frontend's restrictions. Win64 definitions and declarations return
UNSUPPORTED, including unused declarations.

Pointer-to-struct methods use the same function IR and SysV ABI as free
functions, with the receiver as parameter zero. Both `get(p,x)` and `p.get(x)`
use the selected callee FUNCTION identity in semantic `Info` (unit/node), never
the binding candidate-group head. Receiver syntax adds one argument snapshot
before evaluating explicit arguments; functional syntax already includes it.
The complete argument range is reserved before nested calls. Receiver
expressions run exactly once and before explicit arguments. No Graph/ref/Info
bytes change. Enum receivers remain rejected by the frontend.

For loops reserve a binding snapshot and three hidden persistent slots before
temporaries. Range bounds evaluate once from left to right. Array places retain
their storage address; slices snapshot only their descriptor. Array temporary
objects remain pinned until loop exit. Continue enters the increment block;
break enters the end block, and half-open u64 iteration cannot over-increment
its maximum bound. Bool match evaluates and retains its scrutinee once.

Defer registration uses its unused node_slots cell as a compiler-only previous
link. Normal block exits clean to the saved scope head; return cleans to the
root, and loop transfers clean to that loop's saved head. While/loop/for each
save and restore the boundary, so match-arm break/continue cannot clean outer
registrations. Return values are fully evaluated first and protected while
cleanup calls reuse temporaries/registers. Graph and IR ABI remain unchanged.
The frontend still rejects terminating/nested/control-transfer cleanup forms.
See [defer](defer-lowering.md) and [for/match](for-match-lowering.md).

Unsupported values/statements/intrinsics, enums/error declarations
and unsupported static initializers return UNSUPPORTED. Aggregate local alignment above 16 and frames above 4080 bytes remain explicit bounds. Even unsupported code after a return is rejected;
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
