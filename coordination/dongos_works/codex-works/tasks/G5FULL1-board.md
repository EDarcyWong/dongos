# G5FULL1 — G5 完整语言矩阵、剩余语义差异与闭合证据候选

负责人：codex。状态：待领取。

继续用户明确授权补齐G5并独立复验集成。准备独立最终候选及规格覆盖清单，合并G5TAG1/G5EXEC1/G5ALIGN1/G5PANIC1和原负责人L3EXTUNSAFE1的已审查修复；冻结各组件交付，不回写它们。补剩余合法noreturn defer等真实seed差异；同源seed和Dong frontend/lower/nasm真实执行完整语言、ABI、检查/诊断矩阵，包含基本整数/指针/函数值、数组/结构体/padding/静态与可变全局、slice、optional/result/error/enum、method、if/loop/for/match/try/orelse/defer、SysV/Win64、内存/atomic/白名单asm、真实panic ABI。所有声明要求都有可执行记录、零skip/无fallback/无remaining，真实语义及来源坏体必须被oracle拒绝。固定点闭包/已有方法控制流回归另核；真实native_assembler完整ELF含目标panic实现，不改产物或借宿主构建IR。源/工具/产物和公开契约冻结稳定。最终候选验收依赖各组件正式通过并实际审查；此项不直接改主线，后续集成任务声明主线路径并真实复制合并后复验。无OS/VM/CLI/commit/push。

## 可修改文件

- `codex-works/g5-full/src/bootstrap/semantic_types.dg`
- `codex-works/g5-full/src/bootstrap/program_ir.dg`
- `codex-works/g5-full/src/bootstrap/lower_program.dg`
- `codex-works/g5-full/src/bootstrap/nasm_program.dg`
- `codex-works/g5-full/src/bootstrap/frontend_diagnostics.dg`
- `codex-works/g5-full/src/bootstrap/native_assembler.dg`
- `codex-works/g5-full/g5_differential.py`
- `codex-works/g5-full/requirements.json`
- `codex-works/tests/test_g5_full_native.py`
- `codex-works/g5-full/docs/coverage.md`
- `codex-works/deliveries/G5FULL1.md`

## 定向验收

- `discover:codex-works/tests:test_g5_full_native.py`

交付：`codex-works/deliveries/G5FULL1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
