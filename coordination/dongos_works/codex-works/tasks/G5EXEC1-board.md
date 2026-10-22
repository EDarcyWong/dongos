# G5EXEC1 — G5 函数指针、硬件内建、asm 与 Win64 执行闭环

负责人：codex。状态：待领取。

用户授权继续补齐所有G5缺口。独立候选从G5TAG1开发基线接续：函数地址/静态函数指针/先于实参的单次callee求值及间接调用；内存/atomic/compiler_fence内建与白名单asm；Win64声明/定义/双向调用、shadow space/栈参数与全部非易失寄存器/XMM6-15保存，真实机器执行及seed/C/汇编独立oracle。保持既有SysV pair、方法、tagged flow等行为，源/契约/readonly/失败原子性/容量/别名/guard检查及真实语义坏体；所有检查零skip。与DeepSeek前端返修候选不重叠，集成前合并已验收结果。此项通过后还需全语言矩阵/诊断审计及正式G5独立验收，不能将局部完成计为整体。无OS/VM/AI CLI/commit/push。

## 可修改文件

- `codex-works/g5-exec/src/bootstrap/semantic_types.dg`
- `codex-works/g5-exec/src/bootstrap/program_ir.dg`
- `codex-works/g5-exec/src/bootstrap/lower_program.dg`
- `codex-works/g5-exec/src/bootstrap/nasm_program.dg`
- `codex-works/tests/test_g5_exec_native.py`
- `codex-works/g5-exec/docs/execution.md`
- `codex-works/deliveries/G5EXEC1.md`

## 定向验收

- `discover:codex-works/tests:test_g5_exec_native.py`

交付：`codex-works/deliveries/G5EXEC1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
