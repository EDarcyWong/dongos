# L3METHODLOW1 — L3/L3A 方法整程序降级、原生符号与执行差分

负责人：codex。状态：待领取。

在已集成 L3METHOD1 R1 前端基础上，完成 METHOD 函数体及两种已解析方法调用的真实 lower_program/nasm_program 路径。callee 必须读取已发布 Info FUNCTION 的 unit/node，不能把 METHOD_CANDIDATE 组首项误当选中项。接收者仅求值一次且先于显式参数，嵌套调用参数池保留，方法符号包含名义 receiver 类型与模块避免同名冲突；保留 SysV/free 函数及失败原子性。新增真实 native 编译执行、seed 差分、同名不同 receiver/自由函数/跨模块/const/unsafe/stack/pair/副作用测试和真实错误 Dong 变体负控。更新已有 G5 method fixture 为必须支持，保留剩余 gap，不宣称完整 L3/G5/G6。独立定向零skip源稳定后登记验收集成。

## 可修改文件

- `lang/bootstrap/lower_program.dg`
- `lang/bootstrap/nasm_program.dg`
- `lang/bootstrap/lower_program.md`
- `lang/bootstrap/nasm_program.md`
- `lang/bootstrap/method-semantics.md`
- `lang/tests/test_l3_method_native.py`
- `tools/g5_differential.py`
- `docs/language-l2-l3.md`
- `codex-works/deliveries/L3METHODLOW1.md`

## 定向验收

- `module:lang.tests.test_l3_method_native`

交付：`codex-works/deliveries/L3METHODLOW1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
