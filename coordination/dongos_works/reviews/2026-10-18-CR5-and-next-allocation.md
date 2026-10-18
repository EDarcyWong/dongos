# CR5集成与下一批任务

Codex通过实际已配置的coordination stdio MCP查询/验收/登记集成/发布任务，未直接修改状态库或派生索引。

CR5正式3项及适配主线后的同3项均通过，0skip、来源稳定；模块与说明按验收hash原样集成，永久测试仅适配路径/依赖根。详见[CR5复验与集成](2026-10-18-CR5-integration.md)。未改语义核心、CR1字节编码器或CR4十进制依赖，未声称完整L3代码生成器/自举完成。

本批新发布（均todo，不是已执行/已交付）：

| 客户端 | 任务 | 内容 | 依赖 |
| --- | --- | --- | --- |
| Cursor | [CR8](../cursor-works/tasks/CR8-board.md) | NASM基址加有符号位移操作数 | CR4 |
| Cursor | [CR9](../cursor-works/tasks/CR9-board.md) | 定宽常量装入64位寄存器 | CR4 |
| Cursor | [CR10](../cursor-works/tasks/CR10-board.md) | CR6规划到实际条件跳转文本 | CR4、CR6 |
| Cursor | [CR11](../cursor-works/tasks/CR11-board.md) | 有界SysV栈帧序言与尾声 | CR4 |
| DeepSeek | [D19](../deepseek-works/tasks/D19-board.md) | 最短ULEB128 u64有界解码 | 无 |
| LM Studio | [LM8](../lmstudio-works/tasks/LM8-board.md) | 照录8条固定基址位移JSON | 无 |

Cursor保持客户端手动执行；依赖均已集成，四项不同文件可独立领取。DeepSeek只新增一项，LM Studio同时只一项且只写数据/交付两个文件；其独立数据检查由Codex维护，正式数据尚未提交，不提前宣称该检查通过。

Claude本轮未发布新任务。已安排延后一次派单，最早21:21:13、预计约21:22:35（2026-10-18，Asia/Shanghai，实际以调度器为准）；候选与幂等检查见[预备说明](../CLAUDE_NEXT.md)。没有启动AI CLI、OS/VM、提交、推送、周期巡检或关机。

另核对原Claude暂停任务C16/C18/C19/C20/C21：对应D14～D18均已集成。它们只保留历史，不会领取/派发；当前MCP仅支持暂停/恢复等状态变更，不提供任务删除。用户本轮询问删除可行性，未执行删除；建议未来以归档隐藏保留追溯，而非丢失交付/返修历史。

最终MCP核对：新任务发布后，Cursor客户端已领取CR8～CR11，DeepSeek Harness已领取D19，均in_progress；LM8仍todo。所有任务auto_dispatch/auto_verify仍为false，Codex未启动客户端或AI CLI。先前“均todo”仅为发布瞬间快照，未将客户端正常领取回退。状态校验结果[]（无错误）。LM8独立检查准备验证：给定参考通过，5种类型/内容/数量篡改被拒绝；这不是LM8交付验收。
