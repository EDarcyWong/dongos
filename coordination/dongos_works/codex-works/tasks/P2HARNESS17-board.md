# P2HARNESS17 — P2独立隔离SMP来源回归的临时目录自建修复

负责人：codex。状态：待领取。

正式PCID12作业37cd7ec1c22d4ed0818864377086d869中新增14+4tests/0skip均过，但既有test_user_smp_oracle七项在新隔离副本的test_completed_test_build...因ROOT/build/test不存在而TemporaryDirectory报WinError3，未进入来源断言。只修该旧测试在使用自身临时目录前mkdir(parents=True,exist_ok=True)，保持全部oracle/生产源码/来源门槛不变，不靠其它测试顺序建目录、不复制旧build产物。新增本轮P2审查进度记录，保留ROOT13正式4tests/0skip integrated15、WC14宿主4pass但真实build后identity缺receipt返修、PCID18pass但旧harness失败以及P2整体partial/先P2后P5顺序。独立新隔离7tests/0skip且源码稳定审查后集成；无OS/VM/AI CLI/commit/push。

## 可修改文件

- `tests/test_user_smp_oracle.py`
- `codex-works/reviews/2026-10-23-P2-preparation.md`
- `codex-works/deliveries/P2HARNESS17.md`

## 定向验收

- `module:tests.test_user_smp_oracle`

交付：`codex-works/deliveries/P2HARNESS17.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
