# LM3 交付说明

## 任务
简单文档：七种任务状态中文词典

## 交付文件
- `lmstudio-works/docs/task-status.zh-CN.json`
- `lmstudio-works/deliveries/LM3.md`

## 内容说明
- 顶层仅包含 `version` 和 `items`。
- `version` 为整数 1。
- `items` 恰好 7 项，顺序固定：todo, in_progress, submitted, rework, accepted, integrated, paused。
- 每项仅包含 `state`、`label`、`description`。
- `description` 为 1～30 个字符的简短中文，依次解释：尚未领取、已领取正在执行、已提交等待独立复验、需要修复再交付、独立复验通过但尚未集成、已完成集成及相关检查、暂停等待恢复。
- 未将提交等同验收，未将验收等同集成。
- 未声称这些任务当前已经完成。
- 不包含命令或模型配置。

## 测试
- 测试由 Codex 提供，路径：`lmstudio-works/tests/test_status_glossary.py`。
- 本交付未运行测试，未自行验收。
- 测试由协调器另行运行。

## 限制
- 仅编写文档，不改业务代码。
- 不提交、不推送、不运行 OS/VM。
- 不修改任务书、README 或调度器状态。
- 不修改归属外文件。
- 状态保持待复验，等待独立复验。
