# Native typed program to NASM module

`emit(program,workspace,out,written)` renders a published `program_ir.Program`
into complete deterministic NASM text. The workspaces are caller-owned `text`,
`piece` (at least 1024 bytes), parameter `kinds`, and SysV `locations`. The
backend reuses the native symbol, instruction, checked arithmetic, width/load/
store, comparison, branch, frame and SysV argument-planning modules.

Symbols derive from the checked canonical module path and declaration name.
Method symbols append `_t` and the hex bytes of the nominal receiver struct
name to the ordinary module/item symbol. Alias receivers use their resolved
nominal declaration. This separates methods on different structs and methods
from same-name free functions; module identity separates same-name structs in
different modules. The symbol is identical at each definition and call site.
Bodyless SysV methods use their checked external link name just like bodyless
free functions; explicit SysV method definitions retain the nominal symbol
and publish their linker alias at the same address.
The backend uses the bottom-level `sysv_integer_args.plan`; it does not inherit
the older component wrappers' 16-expanded-word limit. Slice pairs are never
split across register/stack placement. Stack arguments are assigned before
register arguments, and all arguments are independent frame snapshots.
The outgoing stack area is 16-aligned; frame plus outgoing area may not exceed
4080. The prologue preserves RBP; only caller-saved registers are otherwise used.

Explicit SysV definitions use the same implementation. Bodyless SysV
declarations emit `extern $name` and direct calls to that actual linker symbol;
they never emit a placeholder body. The default name is the declaration name,
overridden by `extern "sysv64"("name")` or `export("name")`. Definitions keep
their canonical module symbol and publish such names as aliases at the same
address. Linker identifiers use NASM's `$` escape, including register-like names.
Two modules may declare the same source name with different linker names.
The existing frontend restricts external declarations to scalar/pointer
signatures. Win64 remains unsupported; function-pointer calls, foreign data,
unresolved-symbol linking in the native ELF assembler and complete external
ABI coverage are separate work.

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

`python -m unittest lang.tests.test_l3_sysv_native -v` runs explicit definitions,
external C links, eight-argument calls, narrow signed values, guarded pointer
writes, linker aliases, module isolation, rejection atomicity and a real
mutated Dong emitter with an independently observed wrong call target. Each
mode assembles ELF64 and COFF; the host executes its native object format.
`python -m unittest lang.tests.test_l3_method_native -v` rebuilds the native
compiler and executes both method forms, overload selection, symbol isolation,
cross-module visibility, nominal aliases, const/unsafe receivers, single
receiver evaluation, nested/stack/pair arguments, pointer/slice/void/narrow
returns and recursion. C memory canaries and separate seed executions observe
actual generated code. A real Dong lowering mutant incorrectly using the
candidate head must compile/link/run and fail the independent value oracle.
The existing global/aggregate/SysV and runtime-guard observations also use the
new compiler objects. All successful targets run exact/one-short workspace,
alias, output atomicity, readonly graph/source/IR and guard checks.

`python -m unittest lang.tests.test_l3_defer_native lang.tests.test_l3_for_native -v`
rebuilds production sources without works overlays. The for module also tests
for/match/defer composition, pair returns through array-loop cleanups, and real
Dong-generated text consumed by the native assembler: the ELF executes on the
host and returns 69 in both modes. Exact/one-short output, guards and preserved
source bytes are checked. This host ELF execution is separate from DongOS G6.

The G5 runner retains the original eight fixtures and adds range/array/slice
for and bool match probes. Method, ordinary defer, explicit SysV and those four
control paths must pass actual native execution. Win64, enum, error, try and
orelse remain precise gaps. These are bounded probes, not complete G5 coverage;
function pointers, memory intrinsics, asm, complete ABI/diagnostics and broader
defer forms still require separate closure.
