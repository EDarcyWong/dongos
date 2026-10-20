# Semantic expression stack reduction

Candidate `semantic_types.dg` preserves public Workspace/API and all checks.
The former 1,056-byte seed rt_expr dispatch frame becomes a cold general
implementation. A small recursive dispatcher handles nonconstant binary,
call, try/orelse, slice/cast, array/repeat and struct paths. The large cold
frame is no longer live across those recursive edges. All original helper
depths, pure folding precedence, flags, contextual acceptance and control-flow
effects remain in place. Leaf/name/unary/field/index paths still use the
general implementation; there is no new global or arena scratch.

The test compares unchanged baseline and candidate across semantic cases and
the compiler source closure, then instruments generated assembly stack
reservations to measure actual dynamic low-water RSP. It distinguishes seed
frames from native compiler output. A smaller expression dispatcher does not
by itself prove 16 KiB compatibility, whole compiler memory bounds or guest
self-hosting. No kernel stack or memory limit changes are permitted here.

The first stable local run (1 test, 0 skips, 1552.319 seconds) measured seed
closure peak 53376 -> 32448 bytes. Independent native closure measurements
were 57936 -> 37056 bytes. These host probes use oversized arenas only to
isolate stack usage; they are not a 64 MiB guest memory receipt. Independent
20-case semantic checks and a type-capacity failure passed across eight
seed/native combinations, with identical assembly for the same baseline
closure. Those initial native artifacts used debug emission in both seed modes.

The permanent test now makes semantic/capacity expectations explicit, checks
semantic depth without parser nesting, measures native closure stack, compares
common-input assembly, assembles both object formats, and selects actual debug
or release native emission. This expanded version requires its own fresh run.
The user subsequently selected a compiler-only 64 KiB guarded stack under CX7;
that kernel integration is separate from CR47 and ordinary stacks stay 16 KiB.
