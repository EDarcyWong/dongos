# 接续 Claude 未完成任务

用户因 Claude 额度不足要求转交 DeepSeek。原 C16、C18、C21、C19、C20 已暂停，分别由 [D14](../tasks/D14-board.md)、[D15](../tasks/D15-board.md)、[D16](../tasks/D16-board.md)、[D17](../tasks/D17-board.md)、[D18](../tasks/D18-board.md) 接续。

五项已通过 coordination MCP 发布为待领取，不代表已启动或验收。源码、说明和测试已复制至本工作区，仅适配目录和构建编号；具体修复、原完整契约、可写范围和交付要求均在任务书中。使用 DeepSeek worker MCP 领取，再按任务书修改及提交。D1～D13 保持已验收，不重开。

原交付与候选保留，`handoffs/D14`～`D18` 保存只读历史副本及来源指纹。C21 没有完整交付，D16 必须完成真实验证后再提交。Codex 负责独立复验与集成。见[本轮总审查](../../reviews/2026-10-18-mcp-review-and-claude-handoff.md)。

最终 MCP 复核时，DeepSeek 客户端已领取全部五项，状态均为 `in_progress`，Claude 原件指纹一致。客户端自行执行不产生协调器 CLI 作业；Codex 没有自动启动模型。
