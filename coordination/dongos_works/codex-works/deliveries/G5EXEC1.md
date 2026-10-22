# G5EXEC1 delivery

Candidate: semantic_types/program_ir/lower_program/nasm_program in
`codex-works/g5-exec/src/bootstrap/`. Mainline is unchanged by this task.

Implemented function addresses, static function pointers, indirect calls with
callee-before-arguments ordering, function-valued fields, memory/atomic/fence
intrinsics, asm, scalar Win64 definitions/declarations/direct/indirect calls and
full nonvolatile register wrapper preservation with a combined stack budget.

Development runs:

- First cold run: 4 tests, one failure in lowering of a function-valued field;
  memory, asm, enum regression and initial Win64 cases passed. The field had
  been treated as a method candidate. The fix checks for an actual selected
  METHOD declaration before choosing the receiver path.
- Second cold run: 4 tests, zero skips, 365.329 seconds, all passed. Includes
  an independent CPU checker for all nonvolatile GPRs/XMM6..15, exact RSP and DF,
  plus a Win64 observer that writes all shadow slots and reads all eight args.
- A subsequent run found a test fixture directory reused when proving the good
  Win64 case before its negative control. That run failed explicitly; the test
  now uses separate unique fixture names and never overwrites prior evidence.
- Final cold development: **5 tests, 0 skips, 672.807 s**, passed. Evidence
  `code/build/test/g5-exec/run-d5f29f2e4a2d/`; 47 immutable initial candidate/closure
  inputs stable, 16 actual differential records, including 2 negative records.
  Every privileged opcode is assembled and checked as bytes; safe instructions
  execute. A bad Dong emitter restores only XMM6..14: its compiler builds,
  links and normally executes the same Win64 target, then the independent
  checker rejects XMM15 corruption with exit 17. Same-input good and seed pass.

The candidate also incorporates the reviewed G5TAG1 known-subject match flow
correction. The initial source map is frozen separately from mutable driver
build bookkeeping, preventing a later bad-driver build from hiding source drift.

Both modes emit ELF64 and COFF objects and actually execute; COFF assembly is
not substituted for Win64 calling-convention execution. No OS/VM, commit, push,
acceptance or integration has been performed. Formal independent verification,
source/contract review and final mainline integration remain required.


## AI交付 2026-10-22T07:23:40+00:00 · codex-mcp-a56c25d7f28e4bc4

最终冷开发5tests/0skip/672.807s，run-d5f29f2e4a2d，47初始冻结依赖稳定，16真实差分记录含2正常执行XMM15坏体负控。函数指针callee先于参数、静态/字段/pair ABI、内存/atomic旧值、白名单asm字节，Win64真实双向/间接/8参数/shadow/RSP/DF/全部非易失GPR及XMM6..15通过；同输入good/seed对照。交付保存字段误判及fixture防覆盖失败。未验收/集成，等待独立复验。


## AI交付 2026-10-22T07:57:57+00:00 · codex-mcp-a56c25d7f28e4bc4

原正式作业d160a66b5b474034b5c4737cf88ccf03在协调器复制阶段检测来源变化，未执行CLI；该记录保留，不能算验证通过。已重新读取最新rev/status和空作业日志，候选4模块与永久测试仍是提交的开发通过版本，未改实现；当前源文件已冻结，重新提交等待新的独立复验。冷开发5tests/0skip/672.807s及真实XMM15正常执行负控证据保持。未验收/未集成。
