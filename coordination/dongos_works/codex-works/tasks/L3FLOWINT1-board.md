# L3FLOWINT1 — L3/L3A defer、for、bool match 主线合并与真实 ELF 组合验收

负责人：codex。状态：待领取。

依赖L3METHODLOW1已集成、L3DEFER1与L3FOR1独立候选验收；全部依赖验收后领取。保留原候选字节与历史，真实合并两候选到生产lower_program，for设置/恢复自身loop_cleanup边界，不覆盖defer。永久defer/for测试脱离works/project.json/overlay，从生产源码构建；方法G5门禁保留原8探针且新增4个for/bool探针，要求已闭合7路径全部真实执行，未知缺口仍明确失败。加入for+match+defer循环退出/返回pair/cleanup内临时数组组合，实际Dong输出交原生汇编器生成ELF，在宿主执行及exact/short/guard核验。独立集成测试运行全部永久方法/defer/for用例，共享冻结good编译器但每测试独立输入/记录，并分别真实构建坏callee/坏return清理/坏for步长；零skip源稳定后补独立新输入/ABI/清理复核。实际审查和真实生产合并通过后再登记两候选与集成任务integrated。不运行OS/VM或提交推送，不关闭完整G5/L3。

## 可修改文件

- `lang/bootstrap/lower_program.dg`
- `lang/bootstrap/lower_program.md`
- `lang/bootstrap/nasm_program.md`
- `lang/bootstrap/semantic_types.md`
- `lang/bootstrap/defer-lowering.md`
- `lang/bootstrap/for-match-lowering.md`
- `lang/tests/test_l3_defer_native.py`
- `lang/tests/test_l3_for_native.py`
- `lang/tests/test_l3_method_native.py`
- `tools/g5_differential.py`
- `docs/language-l2-l3.md`
- `codex-works/tests/test_l3_control_integration.py`
- `codex-works/deliveries/L3FLOWINT1.md`

## 定向验收

- `discover:codex-works/tests:test_l3_control_integration.py`

交付：`codex-works/deliveries/L3FLOWINT1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
