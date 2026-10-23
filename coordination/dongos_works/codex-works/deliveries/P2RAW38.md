# P2RAW38 delivery

Task: `dongos/codex:P2RAW38`, claimed rev2 by the coordinator. This implementation
does not claim, submit, accept or integrate the task. Task book SHA256:
`a0241674ab0a98c9ad1bd98a8a3bb93977763ac505d901928218df728b3c7e25`.
The original ENTRY21 and EXEC19 contracts were read before implementation.

## Change

The existing precise ENTRY adapter gains optional once-only caller-owned trace
admission: `bind_trace(Context*, []RawTrace, storage_base, storage_bytes, []Header*)!void`.
RawTrace is alignment64, size512, exactly32 slots/16KiB, with two successful
PROBE payload events per CPU. No record array is added to BSS; four pointer/range
words retain the binding. Raw184B, Header256B, Snapshot48B, old bind and typed
dispatch callback remain unchanged. No ASM file is modified.

Admission validates numeric containment/overflow, empty records, exact Context,
Domain/Cpu/arena/allocator separation and real initialized paging table/metadata
pools. Explicit Header inventory and context/capture/normal/DF/NMI/exception
stack checks complete before any trace-global publication. ENTRY binding
rechecks this entire admission before registering an active exception adapter.
The caller must still establish actual allocation
ownership and physical provenance; numeric virtual ranges cannot prove those.

The PF path checks the destination's64 words before the existing ticket consume.
Only successful `handle_fault` copies the original Raw, before/after tickets and
trusted metadata, then commits last. There is no new ACK, hardware read, clock,
allocator, logging, indirect callback or recovery scope. The saved Raw is
pre-ASM, and the returned continuation is recorded separately; this does not
claim post-ASM RIP or completed IRET. `user_entry.asm` remains the sole frame-RIP
writer. No production C/D service consumer is connected by this task.

## Verification boundary

The implementer has not compiled, run tests, executed an OS/VM, modified task
state, committed or pushed. Static source review is separate from independent
coordinator verification. Required checks remain
`module:tests.test_runtime_exec_entry` and `module:tests.test_user_smp_entry`.

The native admission fixture is explicitly synthetic; its paging pools are
initialized through actual `pg.init`, but it does not replace a production
`re.bind`, real allocation receipt, actual PF, hardware snapshot or IRET proof.
Full ELF64/COFF, debug/release compilation, closure stack budgets, native guards
and source-mutant outcomes must be established by the coordinator's real run.

All original host scenarios and three source mutations remain. New controls
define all32 slots on16 synthetic online CPUs, both payloads exactly once,
per-word nonempty-slot refusal, ticket/Raw/binding mismatches, replay/rearmed
third attempts, extent/actual-pool overlap, Header/stack early rejection and
failure-without-publication followed by successful corrected admission. The C
oracle independently describes every RawTrace field and computes expected512
bytes. Its narrow host SysV adapter runs the production apply/DG closure on the
allocated guarded16KiB exception arena; only that exact stack interior is
scratch, while canaries and persistent buffers remain checked. This is native
stack evidence, not privileged PF/IRET execution.

Three additional actual DG mutants skip empty-slot refusal, discard copied Raw
words, or save an unconsumed after-ticket. Together with the old three mutants,
the host module defines14 debug/release compilation variants. Successful
compilation/link and ordinary oracle rc1 are mandatory for every mutant; panic,
crash and compile failure cannot satisfy a control. Existing ELF64/COFF and
`-Werror`/MinGW ANSI printf flags, actual callback ABI rejection, forbidden
operation/indirect-call/recursion checks remain. Only `trace_empty` and
`trace_commit` extend the PF helper whitelist. Every function's measured frame
must be at most4KiB and the conservative closure sum below16KiB. These are
unexecuted checks in this delivery, not claimed passing measurements.

## Files and final freeze

Only the six declared paths were edited. Final implementation fingerprints:

| Path (relative to code) | SHA256 |
|---|---|
| `kernel/sched/runtime_exec_entry.dg` | `1f7701d7de9a04d2ac95f5f4209fff8c5049630e0932229c886f57ae1200552a` |
| `tests/runtime_exec_entry_probe.dg` | `6c2ce80c65bbc44d2a352dc480faa50e9517bdb58eb9f4abfc6d3400c7d99a7a` |
| `tests/runtime_exec_entry_probe.c` | `17ca1c92e0513a0eea609a1d1adedea3a5da0a8f9e17b7b903fed57144dce2ae` |
| `tests/test_runtime_exec_entry.py` | `844152bf0b0edbdeded79d871bd27b951207e7c774e132170224368c82bf6751` |
| `docs/runtime-exec-entry.md` | `064f5b190c7a0b998dff3a7d98a03d4377489bb2289631973708bc4d2619249d` |

This delivery's own fingerprint is reported externally with the final freeze.
The unchanged production `kernel/sched/user_entry.asm` fingerprint is
`b1e9057b772bb9367ee2a2de2762cd59025c57761b062e41b129097bcaa8a325`.
Source inspection found no definite remaining blocker. Actual compiler layouts,
single-frame/closure budgets, native execution and actual C/D integration remain
for independent verification; no implementation-side execution is claimed.


## AI交付 2026-10-23T02:12:36+00:00 · codex-mcp-daece153b59c4bd5

六声明路径已真实落主线工作树并冻结。新增caller-owned32×512B RawTrace，bind_trace显式headers前置admission，所有范围/actual pg.inspect池/Header四栈/空槽检查在任何新TRACE global发布前完成，ENTRY.bind全复核；保旧Raw184/Header256/精确dispatch/ASM唯一RIP写/once注册。根实际源码/原契约与独立审查fd4d324c740a21376c171e76918462ea13ad1914a196aba7b8a3e6e52cdedabf一致。根独立本机预检 tests.test_runtime_exec_entry 已rc0，1test/226.312s/0skip；debug/release共14真实生产/坏源码变体，完整ELF64/COFF汇编、-Werror、2 ABI E0301、实际host-selected16KiB exception stack pureASM+DG回调，生产闭包保守栈1344B/各帧<=4096，source/tool stable。证据code/build/test/runtime-exec-entry/run-20be7467fcb9与raw38-native-precheck-r1.log SHA c3285bbfbdc5c2e21392cc95d51a6bf2d1a19ba1cb081732359423192f831c3c。实现者未运行测试/编译/VM；正式两module尚未排队，当前未验收/集成。本组件不宣称生产C/D消费、真实Block物理所有权、实际PF/IRET或硬件WC通过，均留后续独立实际门。
