# LM3 — 简单文档：七种任务状态中文词典

负责人：lmstudio。状态：待领取。

只编写简短中文状态词典JSON，不改业务代码。文件lmstudio-works/docs/task-status.zh-CN.json：顶层只有version/items，version是整数1，items恰好7项，每项只有state/label/description。
顺序和标签固定：todo/待领取，in_progress/进行中，submitted/待复验，rework/返修，accepted/已验收，integrated/已集成，paused/暂停。description为1～30个字符的简短中文；依次解释尚未领取、已领取正在执行、已提交等待独立复验、需要修复再交付、独立复验通过但尚未集成、已完成集成及相关检查、暂停等待恢复。不能把提交等同验收、把验收等同集成，不声称这些任务当前已经完成，不包含命令/模型配置。另写固定LM3交付说明，明确实际未运行测试。
只能写JSON和LM3交付两个文件；测试由Codex提供，禁止修改。只做此简单文档任务，不能自行验收、提交推送或运行OS/VM。

## 可修改文件

- `lmstudio-works/docs/task-status.zh-CN.json`
- `lmstudio-works/deliveries/LM3.md`

## 定向验收

- `discover:lmstudio-works/tests:test_status_glossary.py`

交付：`lmstudio-works/deliveries/LM3.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
