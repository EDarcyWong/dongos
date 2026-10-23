# G6DOC1 — 新G6宿主准备的独立证据审查与进度同步

负责人：codex。状态：待领取。

依赖G6PREP1独立零skip/源码稳定并实际集成后执行。只新增真实新构建宿主准备的最终审查回执（md/json）与交付；逐项从正式job原始receipt、fixture和4ELF、build-inputs、seed FAT及负控日志复算，记录真实checks数量/耗时/任务rev、源码和产物SHA、预算余量。静态managed frame公式与动态峰值分开，不冒充OS/VM、guest FLUSH/同盘双启或旧G6扩大范围；明确deepseek:L3/L3A任务已集成与整体阶段partial区别。协调角色同时据最新MCP同步工作区progress-map/roadmap/ALLOCATION文档，保留旧历史。最后独立入口检查及实际内容/本地链接审查后验收集成。不修改生产/永久测试，不OS/VM/CLI/commit/push。

## 可修改文件

- `codex-works/reviews/2026-10-23-G6-host-ready.md`
- `codex-works/reviews/2026-10-23-G6-host-ready.json`
- `codex-works/deliveries/G6DOC1.md`

## 定向验收

- `module:tests.test_compiler_guest_runner`

交付：`codex-works/deliveries/G6DOC1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
