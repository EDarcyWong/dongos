# MCP 复验与 Claude 任务交接

2026-10-18，按用户要求通过已安装的 `coordination-tasks` stdio MCP 查询、排队复验并登记状态。Claude 额度不足，五项未完成任务暂停，转交 DeepSeek；原任务、候选副本、交付与失败回执保留，交接不代表验收。未自动启动任何模型 CLI，Cursor 继续手动执行。

## DeepSeek 接续任务

| 原任务 | 新任务 | 必须完成的工作 |
| --- | --- | --- |
| C16 | [D14](../deepseek-works/tasks/D14-board.md) | 修正合法 rel32 向后跳转案例的错误期望，保留原案例和负控 |
| C18 | [D15](../deepseek-works/tasks/D15-board.md) | 修复字符串表长度守卫自身下溢，补有限算术边界验证 |
| C21 | [D16](../deepseek-works/tasks/D16-board.md) | 接续因额度中断的对齐常量池，完成实现、测试和正式交付 |
| C19 | [D17](../deepseek-works/tasks/D17-board.md) | 修复后序遍历负控执行路径，以及原两处对齐夹具遮蔽 |
| C20 | [D18](../deepseek-works/tasks/D18-board.md) | 修复 phi 复制负控被无关前置正例提前拦截的问题 |

任务已通过 MCP 发布，初始为 `todo`，自动派单和自动复验关闭。DeepSeek 使用自己的 worker MCP 领取后开始修改；不修改 Claude 原件，不重复执行已验收的 D1～D13。新源码、说明和测试位于 `deepseek-works/`，只适配目录与构建编号，尚未代替负责人修复。每项 `handoffs/Dxx/provenance.json` 保存来源候选、原指纹、复制后指纹和具体返修要求，原任务书与已有交付也有只读副本；D16 明确记录原 C21 无完整交付。D17/D18 依赖已集成的 C7/C9，Codex 负责后续独立复验和集成。

## 本轮实际复验

| 交付 | 独立结果 | 处理 |
| --- | --- | --- |
| C19 | 3 项，2 通过、1 失败，0 skip，指纹稳定 | 不验收，返修后转 D17 |
| C20 | 3 项，2 通过、1 失败，0 skip，指纹稳定 | 不验收，返修后转 D18 |
| LM6 | 1 项通过，0 skip，指纹稳定 | 已验收；按指纹回写数据后主目录再跑 1 项通过，已集成 |

C19 正常边界、随机及十万节点深链通过；`bad-pre-emit` 在无关的 `alias positive 0` 前置正例退出 97，未抵达预期的 `post-order` 断言。另用真实原生执行检查原对齐案例 18/19：分别删除节点/边对齐检查的错误实现，在原夹具 debug/release 均错误通过；仅把合法数据放入原奇地址并在快照前初始化后，正确实现两模式通过，同一错误实现分别在案例 18/19 退出 93。共 12 次执行。只读私有证明未修改负责人文件。D17 已明确这两处有限修复，不能放宽断言把无关失败当作负控成功。

C20 边界选择和随机字典模型通过，包含实际 C9 并行复制符号调度组合；`bad-first-input` 在 `adjacent objects` 前置正例退出 96，未抵达指定 `phi-moves` 断言。D18 要求显式隔离无关预检，正式实现仍执行完整预检，负控诚实报告执行数量。

LM6 的 12 条固定 LEB128 数据已人工核对，独立整数编码与结构检查通过。模型交付明确未运行测试，本轮实际运行的是 unittest，不把建议命令视为执行结果。见 [LM6 验收](../lmstudio-works/reviews/2026-10-18-LM6-acceptance.md)。仅数据集成，不代表 L3 自举完成。

C16/C18 的最近重试、C21 的后半段执行均因 Claude 429 额度限制中断。C18 已有的是同一算术片段的有限标量见证，不是巨大公共输入复现，D15 保留此限定。Cursor CR2 仍为 `in_progress`，原案例 5 初始化修正已出现，但没有 R1 完整交付及重新提交，本轮未抢占或登记验收。

## 证据与协同检查

- [初始 MCP 快照](../.local/reviews/mcp-review-2a04a5ddb9d8/snapshot.json)、[交接来源和指纹](../.local/reviews/mcp-review-2a04a5ddb9d8/handoff-map.json)。
- C19 正式回执：`88a7c837e2d342e49efbeb301dbb0b87`；C20：`5cbbda58a7a6450eaa75f85c921299c2`；LM6：`3131875ab91c4aab81d9fafccfaa7cfd`。日志和结果保存在本项目 `.local/runs/<id>/`。
- [C19 对齐夹具原生证明](../.local/reviews/mcp-review-2a04a5ddb9d8/C19-alignment/result.json)、[LM6 主目录复跑](../.local/reviews/mcp-review-2a04a5ddb9d8/LM6-live-unittest.log)。
- 协调器增加 DeepSeek 测试目录的固定 discover 白名单；16 项 MCP 测试通过、0 skip，另 1 项结构化命令白名单检查通过。真实交接已使用相同检查入口，未允许任意 shell 命令。

Codex 本轮未启动模型 CLI、OS/VM 构建、全项目回归、提交或推送；定时任务与关机指令继续保持取消。

## 最终核对时的新补交

Cursor 随后手动提交了 CR2 R1 完整交付。Codex 通过 MCP 再排队正式复验：3 项通过、0 skip、指纹稳定，任务 `7d5997a9866e4351bda1934013ecf911`。逐字比较新旧测试，唯一修改正是原 case5 快照前合法标签初始化，与原有限错误实现两模式拒绝证明一致。源码和接口说明未变，R1 交付已补齐。现 CR2 已验收（独立组件），尚未集成；上方“待完整提交”为本轮初查时状态，见[最终验收](../cursor-works/reviews/2026-10-18-CR2-R1-acceptance.md)。Cursor 继续手动，不新增 CR3。

DeepSeek Harness 已安装的实际 stdio 配置也经过只读协议查询，身份为 deepseek，共可见 18 项任务，五项 D14～D18 均可见；该查询没有启动模型。最终 MCP 复核时，DeepSeek 客户端已自行领取全部五项，均为 `in_progress`。Claude 原件指纹一致；新文件可以随负责人执行发生变化。最终状态及指纹核对见[最终回执](../.local/reviews/mcp-review-2a04a5ddb9d8/final-receipt.json)。共 47 项：Claude 6 已验收、10 已集成、5 暂停；DeepSeek 13 已验收、5 进行中；Cursor 1 已集成、1 已验收；LM Studio 6 已集成。协调器 CLI 无排队或执行中作业，客户端 MCP 执行状态另以任务状态为准。
