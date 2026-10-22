# G5TAG1 delivery

Candidate: `codex-works/g5-tag/src/bootstrap/` (semantic_types, program_ir,
lower_program, nasm_program). Mainline production files have not been replaced.

Implemented: optional/result representation and contextual payload wrapping,
error number validation and error results, try propagation with cleanup and
zeroed failure payload, lazy orelse including control transfer, nominal enum
constructors and exhaustive match, pattern payload locals, tagged static data.

Development evidence:

- First cold run `code/build/test/g5-tag/run-839be52fe03c`: 4 tests failed
  (three emission validation failures, one invalid private type in a public test
  signature). The real published IR exposed an unreachable COPY from slot zero
  after `orelse return`; this was removed. Original failure and IR dump remain.
- Second cold run: 4 tests passed, 0 skips, 347.285 seconds. Both target modes
  were compiled by seed and the actual candidate Dong compiler, assembled as
  ELF64 and COFF, linked and executed against independent C expectations.
- Separate development probe of static optional/result/error/enum initialization
  passed both modes through the same actual compiled candidate. This probe is
  supplementary evidence until included in the permanent test suite.

Expanded cold development run: 8 tests, zero skips, 697.095 seconds, passed.
Permanent cases now include exact 48-byte tagged aggregate/padding, tagged
array elements and static initializers, whole-pair SysV stack rollback followed
by the last scalar register, 13 invalid-source classes in both modes with
unpublished failed output, and a real Dong emitter mutation flipping an absent
optional tag. That bad compiler builds, links and normally executes; independent
C rejects its wrong tag with exit 17, while the same seed/good target passes.

Final source/flow audit found known enum subjects and wildcard arms incorrectly
merged dead paths into definite initialization. Fixed nominal tag tracking with
an unambiguous unknown sentinel and first-selected-arm tracking, preserved
known error-result failure, and rejected inferred unwrapped error storage.
Permanent regressions exercise known enum (including tag 2), optional, bool and
error-result subjects.

Final cold development: **9 tests, 0 skips, 685.517 s**, passed.
Evidence: `code/build/test/g5-tag/run-b3cba2e0eccd/`; 46 frozen candidate/closure
inputs stable, 16 executed differential records including 2 wrong-tag negative
records, 14 invalid-source classes in both modes. `frozen-inputs.json` preserves
the immutable initial snapshot separately from subsequent bad-driver builds.
Formal independent verification and real mainline integration remain required;
broader G5 execution/diagnostic/profile and cross-module gates remain open.


## AI交付 2026-10-22T07:23:39+00:00 · codex-mcp-a56c25d7f28e4bc4

实现和真实源码/flow审查完成，独立候选4模块。最终冷开发9tests/0skip/685.517s，run-b3cba2e0eccd，46项初始冻结依赖稳定，16真实差分记录含2正常执行错tag负控；14类非法源码两模式真实拒绝，静态48字节padding、pair栈回滚、known enum/optional/bool/error流均真实seed/Dong/C验证。交付列首轮失败及修复，未验收/未集成；请求独立定向复验。
