# G5CLOSURE1 — G5 最终编译器闭包在56MiB pure job预算内的回归修复

负责人：codex。状态：待领取。

用户授权G5补齐并独立复验集成。真实最终6模块overlay在现有tools.compiler_job.exercise下失败：seed 3/0/2/6 frontend=57144296；证据code/build/test/g5-closure/run-7403d0762d5e。定位limits/紧凑化容量及目标panic runtime链接；保持实际56MiB arena、64KiB stack、2MiB最终ELF和同源固定点，不通过放宽用户/目标预算或宿主构造IR/修补产物规避。此任务独立候选compiler_job，测试借用G5FULL1最终6模块只读；native_assembler如需修复由G5FULL1声明路径实现。真实源构建debug/release、32原子预检、native语义/后端容量拒绝及真实两阶段ELF固定点，零skip源稳定官方复验后验收。无OS/VM/AI CLI/commit/push。

## 可修改文件

- `codex-works/g5-closure/src/bootstrap/compiler_job.dg`
- `codex-works/tests/test_g5_closure_native.py`
- `codex-works/g5-closure/docs/closure.md`
- `codex-works/deliveries/G5CLOSURE1.md`

## 定向验收

- `discover:codex-works/tests:test_g5_closure_native.py`

交付：`codex-works/deliveries/G5CLOSURE1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
