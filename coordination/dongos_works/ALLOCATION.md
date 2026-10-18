# DongOS 客户端分工（2026-10-18）

最新用户授权（2026-10-18）：复验C29/CR16～CR19同时继续向Claude派单，已发布C30～C32三项：缩放索引操作数、除法异常门禁、字节复制/清零发射。依赖已集成、各4文件、通过worker MCP手动执行，不启动CLI；原五项移交已归档不恢复。见[任务](reviews/2026-10-18-Claude-C30-C32-allocation.md)。

最新用户授权（2026-10-18）：继续给Claude派单，现通过coordination MCP新增C26～C29四项；C22～C25已集成，原移交五项已归档，不恢复。四项独立、依赖已集成，客户端领取执行，不启动CLI；Cursor原队列保留，DeepSeek/LM Studio本轮不新增。见[本批记录](reviews/2026-10-18-Claude-C26-C29-allocation.md)。

最新用户要求（2026-10-18）：继续向 Cursor 和 Claude 派单，统一使用 coordination MCP，不使用 CLI 派单或启动模型。已追加 Cursor CR16～CR19 四项、Claude C24/C25 两项；先前未完成任务继续有效，优先处理已领取/返修，不抢占其它文件。DeepSeek 暂不可用，不新增；LM Studio 本轮0新增。见[追加派单记录](reviews/2026-10-18-more-mcp-allocation.md)。

最新用户授权（2026-10-18）：Cursor继续主要新增开发，现发布CR12～CR15四项；Claude可以接单，现正式发布C22/C23两项。DeepSeek暂不可用，不再派单，D20已由Codex接手完成集成。Cursor先补CR11原R1仅剩端点夹具，再领取独立新项；LM Studio本轮0新增。见[本批记录](reviews/2026-10-18-next-emitters-allocation.md)。此段覆盖下方Claude尚未发布/DeepSeek继续新派的旧批次状态。
最新增量：D19 R1与LM8已验收并集成；本次仅给DeepSeek发布[D20](deepseek-works/tasks/D20-board.md)一项SLEB128有符号解码，依赖D19，未启动模型CLI。Cursor CR8～CR11继续原任务，Claude预留模块与延后派单安排保持原约定。下方D19/LM8待领取及D14～D18在途描述为此前批次历史。

当前批次：CR5已集成；新增Cursor CR8～CR11四项、DeepSeek D19一项、LM Studio LM8一项，均通过MCP发布待领取。只分配不启动模型。D14～D18现已集成，下方“未关闭/在途/本轮新增0”为旧批次历史。Claude延后候选及一次后续派单约定见[CLAUDE_NEXT.md](CLAUDE_NEXT.md)，不是当前已发布任务。暂停旧Claude任务未删除；新派单不得恢复已转交的原五项。

用户最新要求：尽量多给 Cursor，少给 DeepSeek，LM Studio 只做最简单任务。此约定替代此前“Claude 多分配”的偏好，只适用于 DongOS 项目，不修改其它项目的策略。

| 客户端 | 后续默认分配 | 执行方式 |
| --- | --- | --- |
| Cursor | 承担主要新增开发；有真实独立工作时每批约 4～6 项，按依赖领取 | 用户在 Cursor 客户端手动发起，通过 MCP 领取/提交，不启动 Agent CLI |
| DeepSeek | 少量补充，当前仅新增D20一项；先完成在途任务再加新任务 | 本人客户端通过MCP领取/交付，不复制成并行实现、不抢占 |
| LM Studio | 同一时刻最多 1 项；固定数据、小文档、简单整理为主，通常不超过两个可写文件（含交付） | worker MCP 查看/领取/提交，无文件工具时释放并说明，不以聊天正文冒充文件 |
| Claude | 当前可正常接单；最新C30～C32三项，按已领取优先逐项完成 | 本人客户端worker MCP领取/交付；旧移交五项已归档，不自动启动CLI |
| Codex | 维护主线、任务契约、交付审查、独立复验及集成 | accepted 与 integrated 分开登记 |

当前 DeepSeek 五项是用户上一轮要求转交后已领取的在途任务，不为满足新批次数量强行中断或重复派给 Cursor；本轮新增 DeepSeek 任务为 0。未来按小批次补充。

只分配有明确用途、边界和可验证交付的任务，不为凑数量重写已验收组件。工作先放各自 works，新任务文件不与活动主线/其它负责人重叠；依赖已验收/集成才可领取。Cursor 当前新增 CR3～CR7，LM Studio 新增 LM7；任务状态由 MCP 提供，本文件仅记录分配偏好，不是自动调度程序或启动指令。

CR3：NASM 内部符号编码；CR4：定宽整数十进制文本；CR5：BSS 声明（依赖 CR4）；CR6：条件分支与落空边规划；CR7：SysV INTEGER 返回规划。LM7：八条给定十进制数据，独立检查由 Codex 提供。具体接口、失败语义、只读依赖和验证范围以任务书为准。
