# L3FOR1 — L3/L3A range/array/slice for 与 bool match 原生降级候选

负责人：codex。状态：待领取。

基于已集成L3METHODLOW1主线的独立 lower_program 候选，闭合 range/array/slice for 和 bool match（不纳入仍在复验的L3DEFER1候选）。for范围/源表达式仅求值一次，数组/切片遍历原存储不复制底层，数组临时值必须维持整个循环生命周期；循环变量逐次快照且不可写，支持break/continue与嵌套循环，u64边界不可溢出。bool match单次求值，显式true/false及最后wildcard，支路局部和返回保持语义。复用现有IR/NASM，不改ABI。覆盖真实native/seed/C差分、原工作池容量/别名/源稳定、不可将编译失败当负控的真实错误董变体。仅候选；独立验收后集成任务必须与已验收defer真实合并并补for/match+defer组合后重新复验，不能用此候选覆盖defer实现。

## 可修改文件

- `codex-works/l3-for/src/bootstrap/lower_program.dg`
- `codex-works/l3-for/docs/for-match-lowering.md`
- `codex-works/tests/test_l3_for_native.py`
- `codex-works/deliveries/L3FOR1.md`

## 定向验收

- `discover:codex-works/tests:test_l3_for_native.py`

交付：`codex-works/deliveries/L3FOR1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
