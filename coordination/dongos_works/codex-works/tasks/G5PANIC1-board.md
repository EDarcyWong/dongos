# G5PANIC1 — G5 panic ABI、种类/路径/行号与前端诊断对齐

负责人：codex。状态：待领取。

继续用户授权G5完整覆盖。独立候选接续G5ALIGN1开发快照，修复原生guard统一UD2导致缺失目标提供的__dong_panic(kind,line,file,len)调用契约：边界1/算术2/除零3/移位4/有符号除法5、确切源码路径/行号、debug/release与wrapping，panic不执行defer，错误原子输出；保存来源与真实ELF/COFF/执行。补新error声明范围和重复编号的正式frontend_diagnostics类别，与seed对照。真实seed和Dong独立C panic观察器及正常成功对照、语义坏Dong类型负控；零skip源稳定官方复验后才验收集成。内置ELF汇编器对未解析panic/runtime符号必须显式失败，完整ELF测试提供真正目标panic实现，不借seedfallback。无OS/VM/CLI/commit/push；此项后仍需全矩阵和闭包回归，不能预先宣告整体G5。

## 可修改文件

- `codex-works/g5-panic/src/bootstrap/semantic_types.dg`
- `codex-works/g5-panic/src/bootstrap/program_ir.dg`
- `codex-works/g5-panic/src/bootstrap/lower_program.dg`
- `codex-works/g5-panic/src/bootstrap/nasm_program.dg`
- `codex-works/g5-panic/src/bootstrap/frontend_diagnostics.dg`
- `codex-works/tests/test_g5_panic_native.py`
- `codex-works/g5-panic/docs/panic.md`
- `codex-works/deliveries/G5PANIC1.md`

## 定向验收

- `discover:codex-works/tests:test_g5_panic_native.py`

交付：`codex-works/deliveries/G5PANIC1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
