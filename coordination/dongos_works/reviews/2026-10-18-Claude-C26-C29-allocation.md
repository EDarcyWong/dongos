# Claude C26～C29 MCP 派单

2026-10-18，按用户“继续给Claude分配任务”要求，通过当前配置的 coordination MCP list_projects/list_tasks/get_task/create_task/read_document 发布四项，均为客户端领取执行，未启动模型 CLI。

发布前 Claude C22～C25 均已 integrated，原五项暂停转交任务已归档；新任务不恢复旧任务。Cursor CR11～CR14 最新补交待复验，CR15进行中，CR16～CR19原队列保留，本轮不修改其状态或实现。

| 编号 | 任务 | 只读依赖 |
| --- | --- | --- |
| [C26](../claude-works/tasks/C26-board.md) | 64位CL可变移位发射 | 无 |
| [C27](../claude-works/tasks/C27-board.md) | 64位寄存器间接调用发射 | 无 |
| [C28](../claude-works/tasks/C28-board.md) | 复用谓词枚举的64位条件移动发射 | cursor:CR6 branch_plan |
| [C29](../claude-works/tasks/C29-board.md) | RIP相对内部符号地址发射 | cursor:CR3 nasm_symbol |

四项发布时为todo、rev1，auto_dispatch/auto_verify均false；未替Claude领取。C26固定CL输入，不改Cursor CR17的立即数移位；C27是寄存器间接call，与已集成C25符号直接call分开；C28只消费cmp后flags生成cmov；C29是RIP相对内部符号LEA，不改CR15基址位移取址。完整接口、精确文本、状态/别名/端点与容量失败契约见各任务书。

发布前核对主线及works无同名文件/重复任务，在途写路径及新任务之间无冲突；CR3/CR6依赖均integrated。每项仅本人works下生产Dong、说明、测试、交付四文件，任务书由MCP生成；不修改活动编译器、code/lang、内核或协调器。

任务要求实际Dong debug/release编译链接与原生运行、NASM ELF64/COFF组装、独立预期及有限安全向量。特别规定C26观察RCX兼任目的，C27有效双callee与调用栈/参数/返回，C28真/假分支及寄存器/flags保持，C29独立符号地址与只读名字；语义坏Dong必须原生执行后由指定结果拒绝，另保留提前写原子性负控。每模式主要原生向量至多24，不展开大矩阵，不运行OS/VM/全回归。它们是后端原语，不能据此声称完整Dong后端或L3自举完成。

MCP逐项read_document往返完整且未截断，任务书SHA256及真实创建回执见同名JSON。状态库与index.json均由协调器生成，未手改。执行者通过自身worker MCP get_task/read_document、claim、完成后submit，Codex独立复验再验收/集成。新任务尚未实现或测试，不将发布成功当作交付。
