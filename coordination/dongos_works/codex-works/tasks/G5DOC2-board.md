# G5DOC2 — 主线G5最终检查点与内建汇编器契约同步

负责人：codex。状态：待领取。

G5INT1正式70项独立复验与真实集成已完成，用户授权同步状态和进度文档。本项仅更新主线八份进度/入口文档的最终实际job、测试数和integrated结论，以及native_assembler.md已过时的.data/extern/填充说明，补明确XMM/atomic/asm dialect边界。保留历史日期/失败/原G6旧head49模块profile，L3整体继续partial为扩大编译器新G6，完整NASM G5已闭、广泛纯ELF指令覆盖另列；不改实现/测试或旧候选。与G5DOC1的nasm_program.md及最终独审回执互补，不写库/index。现有runner入口2项定向检查+独立实际文档/链接审查，源稳定0skip后验收并集成；不OS/VM/CLI/commit/push。

## 可修改文件

- `README.md`
- `PLAN.md`
- `docs/progress-map.md`
- `docs/remaining-plan.md`
- `docs/language-l2-l3.md`
- `docs/l3-native-selfhost-progress.md`
- `docs/g5-differential.md`
- `docs/g5-closure.md`
- `lang/bootstrap/native_assembler.md`
- `codex-works/deliveries/G5DOC2.md`

## 定向验收

- `module:lang.tests.test_g5_runner_entry`

交付：`codex-works/deliveries/G5DOC2.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
