# Native typed program to NASM module

`emit(program,workspace,out,written)` renders a published `program_ir.Program`
into complete deterministic NASM text. The workspaces are caller-owned `text`,
`piece` (at least 1024 bytes), parameter `kinds`, and SysV `locations`. The
backend reuses the native symbol, instruction, checked arithmetic, width/load/
store, comparison, branch, frame and SysV argument-planning modules.

Symbols derive from the checked canonical module path and declaration name.
The backend uses the bottom-level `sysv_integer_args.plan`; it does not inherit
the older component wrappers' 16-expanded-word limit. Slice pairs are never
split across register/stack placement. Stack arguments are assigned before
register arguments, and all arguments are independent frame snapshots.
The outgoing stack area is 16-aligned; frame plus outgoing area may not exceed
4080. The prologue preserves RBP; only caller-saved registers are otherwise used.

## Runtime behavior

Narrow loads sign/zero extend according to semantic type. Pointer stores use
the exact language width; slice memory loads/stores use two 64-bit words.
Integer casts normalize to the destination width. Debug add/subtract/multiply
and negate check overflow, including narrow ranges; unsigned negation is
checked `0-x` (carry), signed negation uses signed overflow. Release and explicit
wrapping intrinsics wrap. Division by zero, signed MIN/-1, invalid shifts and
slice indices trap in both modes. Unsafe pointer arithmetic/index scaling wrap
like the existing seed compiler. Pointer indexing has no invented length bound.

Runtime errors currently terminate with `ud2`, without the final L3 diagnostic
runtime. Every function also ends in a fail-closed trap before the next label,
and a noreturn call is followed by a trap. This is an executable intermediate
backend, not full compiler/guest acceptance. Struct/array locals use exact-byte overlap-safe copies and zeroed literal padding. Strings and checked static constants live in deterministic read-only data; static arrays do not consume frame space. Subslice bounds are checked in both modes. Additional language constructs remain explicitly unsupported by lowering.

## Atomicity

Statuses: OK=0, INVALID=1, CAPACITY=2, UNSUPPORTED=3, FRAME=4.
Before any mutation, descriptor ranges/alignment and overlap against the complete
frontend arena, sources, IR prefixes and both descriptors are checked. Output,
written and all four workspaces must be mutually disjoint and separate from
those inputs. INVALID leaves caller bytes unchanged. Once preflight succeeds,
workspaces may change on failure, but output and written remain unchanged for
all failures. The complete module is rendered to `workspace.text` first; only
success copies its exact used bytes to out and updates written. Output tails
and guards remain unchanged. A piece capacity below 1024 returns CAPACITY.

## Reproduction

From `code/`, with NASM/GCC available:

`NASM=/tmp/dongos-tools/usr/bin/nasm python -m unittest lang.tests.test_bootstrap_native_compiler -v`

The test uses Python only to build the initial native compiler executable.
Every target IR instruction and target NASM byte is then produced by actual
Dong modules at runtime from source bytes. The unchanged artifact comparator
runs against an independent C oracle. Generic Dong source covers nested pairs,
20-word calls, spare-register whole-pair placement, single-evaluation lvalues,
narrow signed operations, overflow modes and runtime traps. Both modes include
capacity/alias/guard checks and a real Dong source mutation whose generated
artifact returns normally but fails the independent value oracle. Per-run
commands, source hashes and results live under `build/test/bootstrap-native-compiler/`.
