# C30～C32复验、集成与Claude/Cursor新派单

2026-10-18，按用户要求，通过coordination MCP读取DongOS全队列、最新rev、任务书和交付，排队正式独立测试，同时逐项审查Dong源码、接口边界和测试有效性。最终C30/C31/C32三项均已验收并真实集成，主线13个不同组件测试通过、0skip，来源稳定。C31首交缺陷已由原Claude负责人本轮返修并独立闭合。没有启动模型CLI、OS/VM、提交或推送，没有手改状态库或派生index。

| 任务 | 正式定向结果 | 独立审查与处理 |
| --- | --- | --- |
| Claude C30 缩放索引操作数 | 4通过、0skip、来源稳定 | 已验收并真实集成；最长26字节小于局部48，真实LEA数值及原子性坏Dong有效 |
| Claude C31 除法门禁 R1 | 重提5通过、0skip、来源稳定 | 首交197>192缺陷先退回；本轮修复、16次独立边界重放正确，已验收集成 |
| Claude C32 字节复制/清零 | 4通过、0skip、来源稳定 | 已验收并真实集成；18向量/模式、只读源保护、0计数NULL、寄存器/guard及坏Dong有效 |

C31首交的4项测试通过未被当作验收结论：signed三目标均为MAX-1时，按契约精确文本为197字节，局部只有192字节；容量197、196、0在debug/release全部panic，分别应为OK、CAPACITY、CAPACITY。通过协调器原任务退回R1，由原Claude负责人将局部扩为224并正确推导197/79上界，补同/异20位目标容量与双格式组装，不改变接口/目标允许范围。重提后正式5项0skip通过；独立再跑5项0skip及16次二进制边界重放（同/异三目标×197/206/196/0×debug/release）全部正确、无panic。旧192坏体panic仅作缺陷回归敏感性，原正常返回错误路由与提前写原子性负控保持有效。详见[C31独立审查及R1闭合](2026-10-18-C31-independent.md)。

C30另做独立4项及选择性written端点/完整尾部别名坏Dong验证，详见[C30独立审查](2026-10-18-C30-independent.md)。C32已实际审查所有生产及C/Python/NASM观察器：只有预检后才发布，COPY源真实只读、目的全部字节/两端guard、RCX/RDI/RSI/RAX和受控其它寄存器、flags/DF，以及COPY变STOSB的正常执行数值拒绝均有效。

## 实物集成

C30/C32的.dg/.md按验收SHA256复制至code/lang/bootstrap；永久test_bootstrap_nasm_indexed_operand.py和test_bootstrap_nasm_memory_intrinsic.py仅适配主线路径和唯一产物位置，保留全部原断言、私有源码根和坏Dong。实际在code运行两模块共8项，0skip、0失败、0错误，13.907秒；生产/说明/永久测试/关联编译器与decimal_integer前后指纹稳定。两任务分别完成accept与integrate登记，最终rev6。

C31随后按R1验收hash另复制nasm_division_guard.dg/.md并新增同名永久测试，仅适配路径；主线5项0skip通过，7.140秒，来源稳定。最终C30/C31/C32均独立验收后登记真实集成，最终rev分别6/10/6。两组主线8+5共13个不同组件测试通过；没有把正式/独立/主线重复运行相加冒充测试种类。

证据目录：`coordination/dongos_works/.local/reviews/C30-C32-review/`，含首轮三份正式回执、逐文件集成映射、完整mainline.log/mainline-result.json与重跑脚本。C31初次独立二进制输入/输出/期望/JSON另复制保存在其下C31-independent，不依赖临时目录存续。首轮正式jobs为C30 `2715d68c37b346b0aa19c674065a4b38`、C31 `06064f522d404cca93f611c183862025`、C32 `f0007b21fd7f4e5cae4f7472eaa2e976`。C31 R1正式job为`6afdba1c152e4b83b665145186d31f13`，回执、映射、主线5项完整log/result及16次重放复制证据保存在`.local/reviews/C31-R1-review/`。

## 新派单

| 负责人/任务 | 内容 | 已集成只读依赖 |
| --- | --- | --- |
| [Cursor CR20](../cursor-works/tasks/CR20-board.md) | 数组/切片无符号边界门禁 | CR4 |
| [Cursor CR21](../cursor-works/tasks/CR21-board.md) | 完整64位移位计数门禁 | CR4 |
| [Cursor CR22](../cursor-works/tasks/CR22-board.md) | signed/unsigned乘法溢出门禁 | CR4 |
| [Cursor CR23](../cursor-works/tasks/CR23-board.md) | signed i64负号溢出门禁 | CR4 |
| [Claude C33](../claude-works/tasks/C33-board.md) | 复用消环规划的8槽GPR并行复制发射 | C9、CR14 |
| [Claude C34](../claude-works/tasks/C34-board.md) | 固定帧源的SysV调用实参建立/栈恢复 | C8、CR4、CR8 |

六项通过MCP正式发布，初始均todo/rev1、auto_dispatch/auto_verify=false，逐项回读完整未截断任务书并保存hash/创建回执至同名JSON。每项四文件（本人Dong模块、说明、定向测试、原编号交付），无活动路径冲突，不依赖C31或互相等待。Cursor优先CR20/21再CR22/23；Claude先完成C31 R1后C33/C34，该返修现已集成。客户端通过worker MCP手动领取/提交，不自动启动CLI或替客户端领取；本轮结束前Cursor已主动领取CR20。DeepSeek/LM Studio本轮0新增，原五项移交归档保留。

任务含精确文本/ABI、完整描述符/别名/端点、INVALID优先CAPACITY、失败原子性、独立原生oracle及真实坏Dong要求。独立审查已剔除MUL的CF/OF等价替换作为负控、澄清无符号高位比较与固定寄存器集合例外，并证明局部文本上界。新任务发布不代表实现或验收；实时状态仍以MCP为准。

本轮完成独立库组件集成与六项派单；完整Dong后端、CLI、目标I/O、stage1/stage2及DongOS内自举继续未完成。
