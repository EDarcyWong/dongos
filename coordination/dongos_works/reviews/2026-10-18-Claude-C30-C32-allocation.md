# Claude C30～C32 MCP派单

2026-10-18，用户在复验期间要求继续给Claude分配任务，通过coordination MCP查询现有队列和依赖后正式发布。

| 编号 | 任务 | 只读依赖 |
| --- | --- | --- |
| [C30](../claude-works/tasks/C30-board.md) | NASM缩放索引地址操作数 | cursor:CR4 decimal_integer |
| [C31](../claude-works/tasks/C31-board.md) | 固定RDI/RSI除法异常门禁分支 | cursor:CR4 decimal_integer |
| [C32](../claude-works/tasks/C32-board.md) | 固定寄存器字节复制/清零发射 | 无 |

C30新增base+index*scale+disp，不修改CR8/CR15。C31只生成zero/signed MIN/-1/success的门禁路由，与CR19已过门禁除余内核分工；异常输入由marker夹具观察，不执行硬件除法。C32只发射rep movsb及xor/rep stosb，不重写D1标准库；上游负责DF=0、访问有效性和COPY不重叠。三项完整接口、精确文本、输入/别名/端点、失败原子性、有限原生向量与实际坏Dong要求均在任务书。

每项只修改本人works中的生产Dong、说明、定向测试和交付四文件，不改活动编译器/内核、主线或其它负责人文件。创建前核对全队列、新旧模块及写路径无冲突，CR4为integrated；逐项MCP read_document回读完整未截断，回执/hash在同名JSON。

发布时三项均todo/rev1，auto_dispatch/auto_verify=false；由Claude客户端worker MCP get_task/read_document、claim、执行后submit，Codex独立复验再验收/集成。未启动模型CLI、自动领取或恢复原已归档五项移交任务。新任务尚未实现/测试，发布成功不代表完成。Cursor现有队列保持原归属，DeepSeek/LM Studio本轮不新增。
