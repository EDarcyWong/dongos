# Native typed program to NASM module

`emit(program,workspace,out,written)` renders a published
`program_ir.Program` into deterministic NASM text. The caller owns text,
piece (at least 1024 bytes), parameter kinds and argument locations. Actual
Dong frontend, typed IR, lowering and this backend produce target code;
Python only bootstraps the compiler and supplies an independent seed oracle.

## Language values and control flow

The backend supports scalar and pointer values, function addresses/storage/
indirect calls, slices, strings, exact-byte struct/array construction and
overlap-safe copies, mutable globals and static constants/relocations.
Method symbols include canonical module/item identity and the nominal
receiver name; alias receivers resolve to that declaration. Both method call
forms use the selected declaration and evaluate the receiver once before
arguments. Aggregate values cannot generally cross a function boundary by
value; supported scalar/pointer/pair signatures remain checked.

Optional/result occupy two 64-bit slots. Empty optionals, error results and
payload-free variants zero unused payload; narrow payload high bits are
normalized. Payload-free enums occupy one word and enums with payloads occupy
two. Cross-module static enum constants retain their tag and payload.
Wrapping a payload first performs its normal coercion, including read-only
pointer conversion. Match, try, orelse, range/array/slice for and defer lower
through the real typed flow graph. Cleanup follows lexical reverse order;
return values survive cleanup, loop exits use their proper cleanup boundary,
and noreturn cleanup is reflected in reachability.

## Function ABI and frame budget

SysV uses the real argument planner. A supported two-word value is placed
whole in registers or whole on the stack; it is never split and does not
consume a spare single register when moved to the stack. Arguments are
independent frame snapshots and outgoing stack storage is 16-aligned.
Bodyless extern declarations are unsafe by default; ABI and unsafe are part
of function types. Actual scalar/pointer external declarations emit linker
symbols, and explicit definitions retain their canonical module symbol and
publish a checked linker alias at the same address.

Win64 scalar definitions bridge to the SysV internal body. Calls reserve
32-byte shadow space and place additional arguments on the stack. Bridges
preserve RDI/RSI and XMM6–15, along with the remaining nonvolatile registers.
Entry and normal return clear DF. Link names use NASM's dollar escape,
including register-like identifiers.

The combined frame/outgoing bound is `F + W + A + O <= 4080`; adding the
common return address and saved RBP gives a worst-case 4096-byte total.
F is the 16-rounded local/temporary frame. For a Win64 definition,
`W = align16(176 + 8*max(parameter_count-6,0)) + 16`; otherwise W is zero.
A is the largest object alignment when greater than 16, accounting for
dynamic alignment/padding and saved R12. O is the current aligned SysV
outgoing area or Win64 shadow/stack area. Dynamic alignment uses R12 while
RBP retains the frame chain. A legal type alignment of 4096 does not imply
that a local of that alignment fits this budget. Static objects do not consume
local frame space; oversized locals reject before alignment arithmetic.

## Memory, checks and panic

Loads extend according to signedness and width; stores use the exact language
width. Slice values use two words. Debug arithmetic checks overflow; release
and explicit wrapping operations wrap. Bounds, invalid shifts, division by
zero and signed MIN/-1 remain checked in both modes. Unsafe pointer arithmetic
follows the seed contract without inventing a length bound.

Guards call the target-provided SysV ABI:

`__dong_panic(u32 kind,u32 line,*const u8 file,usize length)noreturn`

Kinds are bounds=1, overflow=2, division by zero=3, shift=4 and signed
MIN/-1=5. Paths come from the corresponding source and lines from its original
node token. Panic does not run defer. A real exported target definition is
used when present; otherwise NASM declares the external runtime.
`ud2` remains a fail-closed protection if noreturn returns and at unreachable
tails, not the normal panic ABI.

Volatile/unaligned memory supports 8/16/32/64-bit integer widths. Atomics are
restricted to u32/u64 and use ordinary load, xchg, lock cmpxchg and lock xadd
as specified. compiler_fence emits no CPU instruction. Inline asm accepts
only cli, sti, hlt, pause, int3, lfence, sfence and mfence.

## Output atomicity and linking boundary

Statuses: OK=0, INVALID=1, CAPACITY=2, UNSUPPORTED=3, FRAME=4.
Preflight checks descriptor ranges/alignment and overlap against the complete
frontend arena, sources, IR prefixes and descriptors. Output, written and all
four workspaces must be mutually disjoint and separate from those inputs.
INVALID leaves caller bytes unchanged. After preflight, workspace bytes may
change on failure, but output and written stay unchanged for every failure.
The complete module is first rendered into workspace.text; success copies
only the used bytes and publishes written. Output tails/guards stay unchanged.
A piece capacity below 1024 returns CAPACITY.

NASM output can use a normal linker to resolve external symbols. The built-in
native_assembler accepts an extern only when the same final assembly actually
defines that symbol; even unused extern declarations must resolve. There is no
dynamic linker or external symbol loader.

Complete G5 NASM execution coverage does not mean every supported language
program can already be assembled by native_assembler. Its current dialect
does not encode XMM/movdqu, the atomic instructions or the inline-asm whitelist.
Those paths use actual NASM assembly and the applicable CPU/diagnostic
oracles. Selected native ELF,
static-pointer/target-runtime cases and the 49-module self-compilation fixed
point validate the built-in assembler's implemented dialect.

## Permanent gates and evidence

From code/ with NASM and a suitable GCC available:

- `python -m unittest lang.tests.test_g5_full_native -v`: 51 tests and
  27 requirement groups, independent seed and CPU oracles, actual semantic
  mutants, panic diagnostics, both ABIs, source/driver/object provenance.
- `python -m unittest lang.tests.test_g5_closure_native -v`: debug/release
  seed and native full-ELF fixed points, 56 MiB arena, 64 KiB guarded stack,
  512 KiB source bundle and 2 MiB ELF caps, 32 atomic preflights and genuine
  semantic/capacity failures.
- `python -m unittest lang.tests.test_l3_sysv_native -v` and the method,
  defer and for modules retain focused real execution and failure oracles.

The full gate's full-coverage.json, rather than the CLI's intentionally
limited scope_complete=false receipt, decides complete G5 coverage.
The Linux/POSIX native-compiler suite has separate platform requirements;
this Windows integration does not claim it ran. Host evidence does not replace
a new DongOS guest/self-compilation/persistence run for the enlarged compiler.
See [G5 full gate](../../docs/g5-differential.md),
[closure](../../docs/g5-closure.md) and the
[completion receipt](../../../coordination/dongos_works/codex-works/reviews/2026-10-22-G5-completion.md)
for actual jobs, independent reviews and integration state.
