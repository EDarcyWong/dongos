# Claude与Cursor追加十项任务

2026-10-18，按用户“多生成一些任务给Claude和cursor”的要求，通过coordination MCP正式追加10项：Cursor CR24～CR29六项，Claude C35～C38四项。发布前查询DongOS完整80项队列、原任务书、最新rev和已集成源码契约；原有CR20～CR23、C33/C34继续原队列，本轮不复验或抢占这些任务。

## 已发布任务

| 负责人/编号 | 内容 | 只读依赖 |
| --- | --- | --- |
| [Cursor CR24](../cursor-works/tasks/CR24-board.md) | 32/64位顺序一致原子store，memory XCHG映射 | 无 |
| [Cursor CR25](../cursor-works/tasks/CR25-board.md) | 强原子compare-exchange，返回旧值 | 无 |
| [Cursor CR26](../cursor-works/tasks/CR26-board.md) | 原子fetch-add，旧值返回与模加法 | 无 |
| [Cursor CR27](../cursor-works/tasks/CR27-board.md) | 聚合赋值的重叠安全memmove | 已集成CR4 |
| [Cursor CR28](../cursor-works/tasks/CR28-board.md) | 8/16/32位debug算术结果范围门禁 | 已集成CR4 |
| [Cursor CR29](../cursor-works/tasks/CR29-board.md) | 允许空端点的切片lo/hi/len联合门禁 | 已集成CR4 |
| [Claude C35](../claude-works/tasks/C35-board.md) | 复用有序case规划的i64 switch分发链 | 已集成C11、CR9、CR4 |
| [Claude C36](../claude-works/tasks/C36-board.md) | 复用scope规划的零参清理调用，保护返回双字 | 已集成C12、CR4 |
| [Claude C37](../claude-works/tasks/C37-board.md) | SysV函数入口实参捕获到局部frame | 已集成C8、CR8、CR4 |
| [Claude C38](../claude-works/tasks/C38-board.md) | 静态内部符号指针dq与完整64位重定位/addend | 已集成CR3、CR4 |

十项均已创建，回读时为todo/rev1、auto_dispatch=false、auto_verify=false；逐项get_task/read_document核对描述、精确四文件、checks、依赖及完整未截断任务书，回执与SHA256保存于同名JSON。以后状态以MCP实时查询为准，不把本文件的发布快照当当前进度。

## 边界与验证约定

每项仅允许本人works中的生产Dong模块、同名说明、单份定向测试和原编号交付四文件。各模块路径互不重叠；不依赖尚待验收的CR20～CR23、C33/C34，也不重复已集成的普通MOV/算术组件。新增实现必须使用已集成规划/编码器的真实Dong接口，禁止换成宿主生产逻辑。Cursor承担六项主要新增，Claude四项保留实质工作量；没有为凑数量再加空包装。

任务书已明确精确文本、ABI/clobber、完整描述符/端点/别名、INVALID优先CAPACITY、失败全文与成功尾部保持、局部长度上界、debug/release原生执行、ELF64/COFF组装、独立oracle和正常执行后拒绝的真实坏Dong。重点审查包括：

- 原子32位成功/失败返回都规范为零扩展旧值；LOCK/XCHG编码检查与数值观察分开，有限并发仅作补充，不用偶发race冒充确定性负控。
- memmove在count0先退出，允许NULL且不访问内存，所有出口DF=0；最长263字节使用512局部区，不沿用不足的256上界。
- 窄范围检查在截断前使用完整64位候选，不替代先前64位算术自身溢出检查；u32上界先装寄存器以避开imm32符号扩展。
- slice允许lo==hi==len，分别独立验证hi<=len和lo<=hi。
- switch完整i64常量经CR9生成，最长1233字节用1280；scope清理只调用零参正常返回SysV函数，保存RAX/RDX且保持栈对齐，固定1024局部区。
- incoming capture限定CR11等价saved_mask=0及frame<=4080，首栈参数为rbp+16，目标槽唯一且不覆盖保存区，固定1024局部区。
- 静态指针四名字各64字节与极端i64 addend合法，最长560字节用576；ELF64/COFF分别检查完整64位重定位，大addend原生仅观察uint64位模式，不解引用。

依赖、模板、长度证明与x86/ABI风险已由并行只读审查交叉核对。研究提案见[Cursor六项](2026-10-18-Cursor-more-proposal.md)及[Claude四项](2026-10-18-Claude-more-proposal.md)；正式完整契约以MCP任务书为准。

## 执行顺序

两客户端先完成自己已领取/返修任务，再领取新项。Cursor建议CR24→CR25→CR26→CR27→CR28→CR29；Claude保留C34原队列，新项建议C35→C37→C36→C38。十项互不依赖，由本人客户端worker MCP手动读取、领取和提交；没有启动任何模型CLI、自动领取或替客户端执行。

本轮仅派单及记录，不运行新组件测试，不声称实现/验收/集成完成；DeepSeek/LM Studio本轮0新增，Claude原五项移交归档不恢复。没有手改数据库或派生index，没有提交/推送、OS/VM、定时任务或关机操作。完整L3后端接线、CLI、目标I/O和真正自举仍需后续完成。
