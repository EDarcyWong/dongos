# Cursor 与 Claude 追加 MCP 派单

2026-10-18，按用户要求使用已配置 coordination-tasks MCP 发布；通过 initialize、tools/call 的 list_projects/list_tasks/get_task/read_document/create_task 完成，未使用协调 CLI、shell 或模型 CLI 派单/执行。MCP 的 stdio 服务连接不代表启动 AI 执行任务。

此前 Cursor CR12～CR15、Claude C22/C23 保留；本轮仅新增下表六项，不重复发布、不替客户端领取。CR11 最新为 submitted，本轮未声称复验通过或改动其实现。DeepSeek 暂不可用，不新增任务。

| 客户端 | 编号 | 任务 | 只读依赖 |
| --- | --- | --- | --- |
| cursor | [CR16](../cursor-works/tasks/CR16-board.md) | 64位整数一元与零比较发射 | 无 |
| cursor | [CR17](../cursor-works/tasks/CR17-board.md) | 64位立即数移位发射 | cursor:CR4 |
| cursor | [CR18](../cursor-works/tasks/CR18-board.md) | 基础块标签与无条件跳转发射 | cursor:CR4 |
| cursor | [CR19](../cursor-works/tasks/CR19-board.md) | 受控64位整数除法与余数发射 | 无 |
| claude | [C24](../claude-works/tasks/C24-board.md) | 64位加减溢出分支发射 | cursor:CR4 |
| claude | [C25](../claude-works/tasks/C25-board.md) | 复用内部符号编码的直接调用发射 | cursor:CR3 |

所有依赖创建前均核对为 integrated；每项限定本人 works 的 Dong 源码、说明、定向测试和交付四文件。新模块在主线及现有任务均无重复，活跃 Cursor/Claude 写路径两两检查无冲突。完整接口、精确 NASM 文本、参数范围、描述符/端点/别名预检、失败原子性、有限 debug/release 与 ELF64/COFF 原生语义负控要求已写入任务书。

新增 Cursor：一元操作、立即数移位、块标签/无条件跳转、已过门禁的固定寄存器除余内核；新增 Claude：有符号/无符号加减溢出分支、复用 CR3 的直接调用。除余调用方必须先排除除零和有符号最小值/-1；直接调用仍由上游负责参数及栈对齐，不能把这些组件当完整后端或 L3 自举。

先处理已领取或待返修任务，再按客户端工作量领取先前/新增项，不抢占或自动重派。执行者通过自己的 worker MCP 查看、领取、编辑落盘、提交；Codex独立复验后才验收/集成。此次仅发布任务，没有实现或测试通过的声明。

task-books 的 MCP read_document 往返读取均完整；索引由服务生成，未手改数据库或 index.json。
