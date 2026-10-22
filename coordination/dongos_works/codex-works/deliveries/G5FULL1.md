# G5FULL1 work in progress

User request: finish remaining G5 gaps, independently verify and physically
integrate. Do not declare completion from finite runner success. No mainline
production files have been modified by this chat yet; all work uses declared
candidate paths. No OS/VM/AI CLI, commit or push, and no direct coordinator DB
or index writes. Do not spawn subagents without explicit authorization.

## Candidate stack

- G5TAG1: `g5-tag/src/bootstrap/{semantic_types,program_ir,lower_program,nasm_program}.dg`.
  optional/result/error/enum, static tagged data, known-subject match flow fix.
  9 cold development tests / 0 skips / 685.517 s, source_stable true,
  `code/build/test/g5-tag/run-b3cba2e0eccd`. Submitted rev3; official job
  `0b88a6b34394403aa5f080cf3117883b` queued.
- G5EXEC1: `g5-exec/src/bootstrap/` same four files, adds indirect function calls,
  memory/atomic/fence/asm, full scalar Win64 bridge with GPR/XMM6..15/RSP/DF and
  shadow/stack tests. 5 cold tests / 0 skips / 672.807 s, 47 frozen files stable,
  `code/build/test/g5-exec/run-d5f29f2e4a2d`. Submitted rev3; official job
  `d160a66b5b474034b5c4737cf88ccf03` queued.
- G5ALIGN1: `g5-align/src/bootstrap/` same four, adds FRAME_ALIGNMENT and R12
  aligned local frames (public IR ABI unchanged), shared 4096 budget with Win64.
  4 cold tests / 0 skips / 607.494 s, 47 frozen files stable,
  `code/build/test/g5-alignment/run-6e8a68bab57d`. Submitted rev3; official job
  `63906891bcf24084b1d507255e372f82` queued.
- G5PANIC1: `g5-panic/src/bootstrap/` those four plus frontend_diagnostics.dg.
  Adds actual target `__dong_panic(kind,line,file,len)` calls instead of UD2-only
  guards, exact categories 1..5, source path/line, no defer on panic. Also error
  number diagnostic classes E0302/E0602 with proper range checks. Development
  test `test_g5_panic_native.py` currently running, exec session 24762. First two
  tests passed; currently compiling/running bad-kind control. Task in_progress
  rev2, claim token `13103962c2734d7283f5df2b04fa4a1c`.
- G5FULL1: in_progress rev2, token `949e54882bcc4955820ba2bbe760ac03`.
  `g5-full/src/bootstrap/` currently copies the G5PANIC1 five files plus mainline
  native_assembler.dg. `g5-full/g5_differential.py` is currently an unmodified
  copy of mainline `tools/g5_differential.py`; it still needs adaptation.

All permanent component tests are in `codex-works/tests/test_g5_*_native.py`.
They build actual Dong compilers from source, execute seed and native targets in
debug/release, assemble ELF64+COFF, use independent C/ASM expectations and real
bad Dong variants. Initial frozen source maps are kept separately from mutable
bridge build bookkeeping, preventing later bad-driver builds hiding drift.
The test modules import each other (tagged helper especially); DO NOT edit any
submitted component test/source/delivery while independent jobs are queued or
running. Keep original development failures in build evidence.

## Extern unsafe original-owner fix

DeepSeek submitted `cursor:L3EXTUNSAFE1` rev4. Candidate:
`cursor-works/l3-extern-unsafe/src/bootstrap/semantic_types.dg` is exactly mainline
plus 4-line comment + `if n.c==NONE{flags|=2;}` in top_function before constructing
Type. Default unsafe for bodyless declarations, preserves ABI bit and bodyful
defaults. Task/test/source/delivery were read and reviewed. Official independent
job `4b0201fb098d427f8c7e6f0915c61d95` running as of 07:28 UTC. It has 7 tests,
real removed-hunk bad Dong, 13-module source closure and flags/Info identity,
imports, read-only/guards/capacity checks. Do not modify owner's candidate.
Merge the exact hunk into final G5FULL1 candidate only after independent pass.
Accept via latest rev and truthful source/test review note, then later actual
mainline integration; do not conflate accepted/integrated.

## Remaining work

1. Complete/review G5PANIC1 tests, fix any real failures only after process exits,
   submit truthful delivery and queue formal verification.
2. Poll official jobs compactly per task; formal coordinator worker serializes
   them. Actual source/contract review + zero skip + source_stable required
   before accept. Mainline must remain unchanged while these tests fingerprint
   its read-only closure.
3. Finish G5FULL1. A remaining confirmed implementation gap is terminating
   `defer`: semantic_types.rt_statement BLOCK currently explicitly rejects
   `cleanup_stops` with UNSUPPORTED. Seed allows `defer die()` (noreturn cleanup).
   Remove that explicit rejection in FINAL candidate (keep existing at-block-end
   live=false); lowering already emits cleanup CALL noreturn/UD2. Add real target
   test with external C noreturn stop callback that prints cleanup trace and
   exits, avoiding infinite loops. Keep no nested defer/control transfers.
4. Adapt final runner: include all GAPS names as required native successes;
   update 22 runtime checks from UD2 observation to actual PANIC kind+line;
   replace fallback negative's `self.gaps[-1]` (no gaps should remain) with a
   real capacity-limited C driver calling unchanged Dong compiler on valid same
   source, then bad Python substitutes actual seed success and provenance must
   reject. No unsupported/xfail/skip counted as success.
5. Final coverage should include all spec families and combine component tests
   against final candidate (can delegate their methods on one full test class
   with shared compiler). Add base AUDIT/globals/multimodule/padding, existing
   method/defer/for/control tests, all memory integer widths and atomic contention,
   new panic tests, explicit per-requirement manifest and actual pass tracking.
   Do not set scope_complete true in tearDown if any unittest failed/skipped.
6. Real native ELF check needs provided target panic definition, because emitted
   guard now calls external runtime. Emitter `defines_panic` recognizes exported
   `__dong_panic` alias and omits extern in that case. A fixture may define actual
   Dong `export("__dong_panic") fn panic(k:u32,line:u32,p:*const u8,n:usize)noreturn{loop{}}`
   (normal tested program never triggers it). Do not patch ELF/pointers. Use
   native.L3ANativeRegressionTests with final CANDIDATES six files and a new
   source passed to its pipeline, preserving fixed-address static pointers.
7. Source audit + final cold full matrix, official independent verification,
   accept G5FULL1 only after components passed. Then create/claim a separate
   integration task explicitly listing mainline paths, physically merge/copy
   final six modules, runner, permanent tests/docs and update old rejection tests
   (`test_bootstrap_semantic_runtime` currently expects enum/error unsupported;
   terminating defer old expectation also changes). Run meaningful mainline
   regression/selfhost closure checks and official integration checks. Only then
   register integrate via latest rev. Keep all unrelated dirty files untouched.

## Runtime/authoring details

Workspace root `D:/projects/projects3/2026/dongos`, compilation cwd `code/`.
Candidate roots are under `coordination/dongos_works/codex-works/`.
PowerShell shell, Python 3.13 + NASM/GCC from test_dongc.tool available. Each cold
compiler good/bad build takes several minutes; use yielded exec sessions and
concise commentary at least every 60 s. Never stop unrelated Python/NASM jobs.
Use coordination MCP first, latest project dongos/rev for mutations. Tools are
discoverable through ALL_TOOLS; print structuredContent only to avoid duplicates.

No skill, goal, automation, subagent, PR or commit has been created for this work.

## 2026-10-22 08:54 UTC continuation (supersedes stale pending items above)

All components are now independently passed and accepted: TAG rev5,
EXEC rev8 (retry 4f0f18a0cbbd46bab351012e9c8cd8ed, 5/0skip/660.789s),
ALIGN rev5, PANIC rev5 (4821a5587b7d44589a098dca990e007f, 3/0skip/784.012s),
and original-owner L3EXTUNSAFE1 rev6. None are physically integrated yet.
The exact extern hunk, noreturn-cleanup fix and wrapping constant/static fold
fixes are present in this final candidate.

First full development run `codex-works/build/G5-full/run-049534eb0342`
had fixture failures (Windows long path, CRLF hash, private type in a public
method fixture) and was stopped after identifying its owned process tree.
Second `code/build/test/G5-full/run-3a740d57fb42` passed these corrected paths,
including real ELF at fixed address, before stopping for caller-workspace
sizing. Neither interrupted run counts as a pass; process evidence is retained.
Current full cold run `code/build/test/G5-full/run-495c62b86369` includes
bounded caller pools while retaining all contract/guard/alias/capacity checks,
one real combined mutant with six isolated oracle fixtures, one reused cold
compiler object relinked to the independent native ELF caller, and an added
function/bool/pointer optional/result plus imported maximum-error payload case.
There are now 46 tests, 27 requirement groups; full result is still pending.

Native assembler now admits extern declarations only if a real definition is
present in the same final assembly, checked in pass one against pass-zero
labels; unresolved declarations, even unused, remain SYMBOL errors. The full
ELF test additionally executes raw resolved/unresolved cases and checks failure
output atomicity. This supports actual target panic runtime linkage.

Real pure-job closure checks uncovered existing profile capacities made too
small by the larger compiler. Initial failure: frontend nodes115000 versus
actual115973 (49 modules/177359 tokens), retained in
`code/build/test/g5-closure/run-7403d0762d5e`. Rebalanced nodes118000/tokens190000
fits the unchanged56MiB arena; next actual failure was backend text scratch
partition (stage2/CAPACITY/detail4), retained in `run-ac7fea62b5e4`.
Separately claimed task codex:G5CLOSURE1 owns compiler_job candidate and its
permanent real debug/release pure-job fixedpoint test. It rebalances backend
48MiB/8MiB partitions without increasing arena, stack or2MiB ELF contracts, and
appends an actual target nonreturning panic runtime only when externally
declared. Current cold closure run `code/build/test/G5-closure/run-cf86f8579747`
is pending. No fixedpoint success or overall G5 completion is claimed yet.
