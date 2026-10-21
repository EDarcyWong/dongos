# L3MAIN12 — [L3本地集成] 将有限G5差分runner接入主线工具入口

负责人：codex。状态：待领取。

把deepseek:L3经实际源码审查及正式零skip复验验收的有限runner和说明原字节集成code主线tools/g5_differential.py、docs/g5-differential.md，保留候选完整证据/known-gap边界。候选在同一实现中明确支持works与code/tools两种真实根定位，主线副本必须与accepted候选逐字节SHA一致，不重写算法或支持矩阵。本项新增test_g5_runner_entry仅验证实际主线模块/CLI导入、正确源码根和防覆盖边界；完整语言/ABI/语义坏体/真实nativeELF由依赖L3正式全矩阵证明，不能仅凭入口测试替代。必要时实际主线再跑有限全矩阵，源码/闭包SHA记录且0skip。不得扩大为整个G5已完成，不改已验收bootstrap生产源/数据库索引。源审、正式入口测试与真实候选→主目录文件指纹后分别accept/integrate；仍无PR，全部本轮任务闭合后直接提交GitHub main并核对再关机。

## 可修改文件

- `tools/g5_differential.py`
- `lang/tests/test_g5_runner_entry.py`
- `docs/g5-differential.md`
- `codex-works/deliveries/L3MAIN12.md`

## 定向验收

- `module:lang.tests.test_g5_runner_entry`

交付：`codex-works/deliveries/L3MAIN12.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
