# L3SYSVREG1 — [L3A] 同步SysV支持后的既有负例预期

负责人：codex。状态：待领取。

接续codex:L3SYSV1，已有test_bootstrap_native_compiler.test_unsupported_source_fails_closed仍用extern sysv64声明作为唯一不支持负例，已被本轮新增能力覆盖。将此负例切换为仍未支持的extern win64，保持失败码、诊断、输出不变断言；真实SysV成功路径由L3SYSV1新测试覆盖。只修改这项永久测试与本交付，不改变其它测试。使用L3SYSV1实际原生编译器桥从相同bad模块源执行旧负例debug/release，独立定向完整复验见L3SYSV1；不以仅源文字检查代替执行。未执行完整旧模块须如实报告，既有宿主平台限制不改。零skip，不提交/推送。

## 可修改文件

- `lang/tests/test_bootstrap_native_compiler.py`
- `codex-works/deliveries/L3SYSVREG1.md`

## 定向验收

- `module:lang.tests.test_l3_sysv_native`
- `module:lang.tests.test_g5_runner_entry`

交付：`codex-works/deliveries/L3SYSVREG1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
