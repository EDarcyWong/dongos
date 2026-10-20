# L3 native compiler progress, 2026-10-20

L3 remains **incomplete**: PLAN.md requires the compiler to run on DongOS,
compile itself there, persist the product, and match the host artifact. The
following host evidence does not substitute for that guest acceptance.

## Frozen host fixed point

`build/test/native-fixedpoint/clean-debug/receipt.json` records a successful
49-module compiler closure, native stage1/stage2 assembly generation with an
empty PATH, and byte-identical assembly, ELF object, and linked host executable.
Source snapshots, exact commands, relocation diagnostics, and positive/negative
semantic controls are retained alongside the receipt.

- Assembly: 7,138,727 bytes,
  SHA256 `bda83036e4bc95fb48c02a952d059342bc74ebddb3022041c8bf6b9d53f2b454`.
- Object: 2,424,128 bytes,
  SHA256 `cafcc24684c589f1bd802753eb7fc450e01b10252c1edb428e525c84c13eb650`.
- Host executable: 2,438,304 bytes,
  SHA256 `f47e0302f2c3fba98d4dbbd7cdd1b9bde4607cd81634ea002eab5cd3383efef2`.

The host executable includes a C filesystem/CLI adapter and is not a guest
executable. These hashes describe the frozen source version, not subsequent
memory optimizations.

The later packed-flow source snapshot also passes a separate full host fixed
point: `build/test/native-fixedpoint/packed-debug/receipt.json`. Both stages
produce 7,140,752 assembly bytes, reserve 53,037,584 frontend bytes under the
bounded limits, and pass valid/invalid semantic controls. Assembly, object and
host executable match byte-for-byte between stages. This is the current
packed-flow closure, not the earlier hash set above.

## Native assembly and execution

`bootstrap.x86_encode` and `bootstrap.native_assembler` replace the external
assembler/linker for the emitted bounded NASM dialect. Unsupported syntax fails
explicitly. The assembler emits static ELF64 through `bootstrap.elf64_image`.

`build/test/bootstrap-native-assembler/run-34528bbba04b/summary.json` records
seven passing tests in debug/release, independent NASM byte/semantic oracles,
57 invalid/preflight classes, and the actual kernel ELF validator. The frozen
compiler assembly produces 1,948,079 text bytes and 25,064 data bytes in a
1,978,856-byte ELF, below the existing 2 MiB EXEC input limit. SHA256:
`d4c393ec46b567d9b03d7535ad8d062b1c7327f611a89637417a8609a35f8502`.

`build/test/native-assembled-execution/frozen-replay/README.md` and
`execution-report.json` preserve a fresh reproducible execution of that native
ELF compiler core in a bounded host loader. No NASM-built compiler core is
linked into that loader. Frozen seed/dependency manifests match before/after;
valid/invalid compiler inputs passed in the initial replay. Independent review
then found a truncated-program-header read in the host loader. The original
loader-validation evidence is preserved but superseded; checked table-extent
validation was added and the full replay again passed exact self-emission.
Expanded controls reject 125 malformed images in each of normal and ASan
loaders (250 executions). Independent truncation re-review passed as noted below. With
PATH empty the loaded core reproduces the exact assembly hash above in 16.58
seconds. The loader stages writable memory then makes text executable, never
writable and executable simultaneously.

The ELF entry is a callable compiler API, not a DongOS startup adapter. Kernel
ELF validation and host execution are not evidence of a guest launch.

## Memory reduction evidence

`build/test/bootstrap-semantic-runtime/packed-final-b51c08f59483/summary.json`
records packed-flow boundary/capacity/legacy-caller checks in both modes and a
real high-bit-loss mutant rejected by semantic-status assertions. General
regression runs are separate from this focused receipt.

`build/test/bootstrap-graph-compact/run-22c789ae6582/summary.json` records
explicit graph compaction in both seed modes, 39 atomic-invalid cases per mode,
all 16 used pool hashes, released-tail reuse, guards, idempotence, and unchanged
compiler-driver assembly in both emission modes. The consuming API invalidates
all prior arena aliases; ordinary immutable graph APIs are unchanged.

The frozen 49-source compiler fixture uses 53,031,456 frontend workspace bytes
under the measured bounded limits, then retains 24,973,808 graph bytes. Actual
lowering uses 517 functions, 102,048 instructions and 10,739 arguments. A
right-sized backend uses 16,737,448 workspace bytes, including 8 MiB intermediate
assembly, and produces the same 7,138,727 bytes. These measurements initially
used separate host allocations: their sum is not evidence of a single-arena
pipeline, a 16 KiB stack, or coexistence within the guest's shared 64 MiB pool.

`build/test/native-bounded-pipeline/summary.json` subsequently demonstrates
frontend, compacted graph, backend and 8 MiB output in ONE guarded 56 MiB
backing arena, with the same exact assembly hash. Logical source/catalog
storage adds 411,736 bytes outside that arena. This uses a frozen seed-debug
core, not a native-generated core. Guarded 16/32/48/56 KiB stacks fault during
the frontend; 60/64 KiB stacks succeed. A changed-suffix measurement is 58,624
bytes. Thus the existing guest 16 KiB stack is a concrete unresolved blocker;
neither the native-generated stack nor total guest process memory is proven.

## Remaining acceptance work

- Finish measuring and independently testing reduced frontend flow workspace
  and explicit, exclusive graph compaction, including phase peak memory.
- Integrate a bounded target source reader, diagnostics, and compiler startup.
- Integrate native assembly with the target compilation pipeline.
- Design bounded output/persistence and next-stage launch through existing
  authority; do not silently grant the compiler filesystem-write, process
  management, power, or expanded memory rights.
- Run true DongOS stages, durable FLUSH/restart checks, and compare matching
  target artifacts. Required host VM tools are currently unavailable.

The existing shared managed user arena is 64 MiB and user stack is 16 KiB.
An ELF fitting the EXEC file limit alone says nothing about total compilation
memory, stack depth, or coexistence with other guest processes. No guest rights,
capacity settings, OS launch, installation, or deployment was changed by these
host-only tests.

## Review boundary

The corrected host loader was independently rebuilt under ASan and all 112
truncated lengths 64 through 175 were rechecked without sanitizer findings.
The broader cumulative independent review did not finish: its tool operation
was stopped by a safety block. No substitute review or retry was performed.
Specific passing component receipts above remain valid evidence for their
stated scope; they are not a claim that the cumulative patch has completed
independent review or L3 acceptance.
