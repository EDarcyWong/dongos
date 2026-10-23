# G5DOC1 — G5主线集成后的后端契约与进度文档收尾

负责人：codex。状态：待领取。

用户授权G5独立复验并主线集成后同步进度文档。本项只在G5INT1验收后执行，更新nasm_program组件说明中已过时的enum/error/try/orelse/Win64/对齐/panic缺口描述，保留历史范围和当前预算。记录候选及主线真实正式job/测试数、四份完整ELF固定点SHA和独立复算、各任务实际状态与原始失败，不修改实现/旧通过证据、不把宿主G5外推为新G6客体或P5等OS阶段完成。协调角色另据这些真实结果更新工作区progress-map/roadmap/ALLOCATION（文档，不是数据库/index）。仅运行现有主线runner入口2项定向检查，零skip源码稳定；不OS/VM/CLI/commit/push。

## 可修改文件

- `lang/bootstrap/nasm_program.md`
- `codex-works/reviews/2026-10-22-G5-completion.md`
- `codex-works/deliveries/G5DOC1.md`

## 定向验收

- `module:lang.tests.test_g5_runner_entry`

交付：`codex-works/deliveries/G5DOC1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
