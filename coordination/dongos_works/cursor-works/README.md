# Cursor 工作区

2026-10-18最新：CR16 R1及CR17～CR19均已独立验收并真实集成；本轮主线18项（含Claude C29及2组合）0skip通过，CR16原生R8覆盖闭合。CR19只含已过门禁内核，门禁独立分配给Claude C31；不改本人的生产源码归属。见[集成记录](../reviews/2026-10-18-C29-CR16-CR19-integration.md)。下方待修/待领取为历史，以MCP为准。

2026-10-18最新：CR11～CR15已验收并集成到主线，15组件测试+1真实组合通过0skip，先前CR11/CR12/CR13待修说明均为历史。CR16正式3项通过但原生[:24]仅含RAX，按[R1](reviews/2026-10-18-CR16-R1.md)有限补测；CR17原在途、CR18/CR19继续队列，保持客户端手动。见[集成记录](../reviews/2026-10-18-CR11-CR16-review-integration.md)。

2026-10-18追加复验：CR13正式3项0skip通过，但须补原任务的原生输入寄存器保留观察，见[R1](reviews/2026-10-18-CR13-R1.md)；原交付与有效内存/guard及负控保留，未验收/集成。其它在途任务保留，不启动CLI。

2026-10-18最新复验：CR12正式3项通过，但原生只读输入夹具未齐，退回[R1](reviews/2026-10-18-CR12-R1.md)；CR11本次快照冲突未运行测试，保留R2并按[说明](reviews/2026-10-18-CR11-snapshot-retry.md)重新提交。其它已派任务保留，不重写已闭项，不新增派单。
2026-10-18追加 MCP 派单：[CR16](tasks/CR16-board.md)一元操作、[CR17](tasks/CR17-board.md)立即数移位、[CR18](tasks/CR18-board.md)块标签/跳转、[CR19](tasks/CR19-board.md)固定寄存器除余；原CR12～CR15保留。只发布不领取，客户端通过worker MCP执行，不启动CLI；CR11最新为submitted待复验。见[本批说明](../reviews/2026-10-18-more-mcp-allocation.md)。

最新派单（2026-10-18）：新增[CR12](tasks/CR12-board.md)整数内存load、[CR13](tasks/CR13-board.md)store、[CR14](tasks/CR14-board.md)整数cast、[CR15](tasks/CR15-board.md)LEA地址语句。四项独立，不依赖CR11，先补原CR11 R1仅剩端点测试再按客户端工作量领取；只写各自4文件，不启动Agent CLI。详见[本批说明](../reviews/2026-10-18-next-emitters-allocation.md)。
2026-10-18 CR11 R1复验：正式3项通过0skip，原epilogue别名及RBP/栈平衡漏点已闭；仅剩原R1的written端点溢出测试，继续原任务有限返修，不重开其它已闭项。见[剩余要求](reviews/2026-10-18-CR11-R1-remaining.md)。
最新复验（2026-10-18）：CR8/CR9/CR10均已验收并集成，主线同9项通过0skip；CR11退回原任务R1：补epilogue各自完整描述符/别名预检和RBP/栈平衡原生观察。正式3项通过不能替代两处已证实的漏检。见[本轮记录](../reviews/2026-10-18-Cursor-DeepSeek-review.md)及[CR11 R1](reviews/2026-10-18-CR11-R1.md)。保持客户端手动执行，不新开重复任务；下方旧状态保留历史。
最新（2026-10-18）：CR1～CR7现均已集成，CR5正式与主线同3项各通过、0skip。新发布[CR8](tasks/CR8-board.md)基址位移、[CR9](tasks/CR9-board.md)整数装入、[CR10](tasks/CR10-board.md)条件跳转、[CR11](tasks/CR11-board.md)栈帧序尾四项，依赖均已集成；通过MCP读取/领取后在Cursor客户端手动执行，不启动Agent CLI。见[本批记录](../reviews/2026-10-18-CR5-and-next-allocation.md)。下方旧状态保留历史。

## 2026-10-18 当前复验与集成

CR2、CR7及本轮新提交CR3/CR4/CR6均已独立验收并真实集成到主线，源码保持验收hash，永久测试已通过。CR1维持已集成；CR5因CR4依赖满足后已由客户端手动领取，当前进行中，未启动Cursor CLI。见[CR7验收](reviews/2026-10-18-CR7-acceptance.md)、[CR3/CR4/CR6验收](reviews/2026-10-18-CR3-CR4-CR6-acceptance.md)、[第一批集成](../reviews/2026-10-18-CR2-CR7-D14-D18-LM7-integration.md)、[后续集成](../reviews/2026-10-18-Cursor-followup-integration.md)。下方旧待复验/进行中状态保留历史；实时以MCP为准。本轮不新增派单。

2026-10-18 最新 MCP 核对：CR3、CR4、CR6、CR7 进行中，CR5 待领取并等待 CR4 验收，尚无这五项的新提交。本轮未抢占或启动 Cursor CLI；CR2 保持已验收、尚未集成。见[客户端复验](../reviews/2026-10-18-client-deliveries.md)，实时以 MCP 为准。

## 2026-10-18 新增主要开发批次（当前）

用户要求后续主要新增任务分配给 Cursor。CR2 R1 已经独立验收，尚未集成，见[验收](reviews/2026-10-18-CR2-R1-acceptance.md)。新增以下五项，均已通过 coordination MCP 发布；保持在客户端手动发起，不启动 Cursor CLI。下方“CR2待补交、不新增CR3”等描述为历史，已由本批次取代。

| 任务 | 内容 | 依赖 |
| --- | --- | --- |
| [CR3](tasks/CR3-board.md) | 无碰撞的 NASM 内部符号编码 | 无 |
| [CR4](tasks/CR4-board.md) | 无分配的定宽整数十进制文本 | 无 |
| [CR5](tasks/CR5-board.md) | 复用 CR4 的 NASM BSS 声明 | CR4 验收后领取 |
| [CR6](tasks/CR6-board.md) | 条件分支和落空边规划 | 无 |
| [CR7](tasks/CR7-board.md) | SysV INTEGER 返回值扩展规划 | 无 |

通过 Cursor worker MCP 查看完整任务、最新 rev 后领取；完成后真实落盘并提交。只改任务声明的 Cursor 文件，不改主线，也不接手 DeepSeek 已领取的 D14～D18；CR5 的依赖只读。源码为 Dong，独立测试必须实际执行原生代码，禁止把崩溃/构建错误当负控成功。详见[分工偏好](../ALLOCATION.md)，实时状态以 MCP 为准；发布不表示 Cursor 已启动。

2026-10-18 集成更新：CR1已集成到code/lang/bootstrap及主线永久测试。见[集成记录](../reviews/2026-10-18-batch3-integration.md)。


## 2026-10-18 CR2 R1待手动补交

CR2 R1 已补交待复验（仅修 case5 测试；源码未改）。历史：正式3项测试通过，但尾部label别名被非法标签遮蔽，暂不验收；仅修原case5并追加交付。详见[复验返修](reviews/2026-10-18-CR2-R1.md)。不新增CR3，不加入自动写入队列。下方CR2发布记录保留为历史。

## 2026-10-18 新任务 CR2

CR2 已交付待复验，见[交付](deliveries/CR2.md)。[CR2](tasks/CR2-board.md)。受限NASM数据声明，复用已集成CR1；保持手动领取/执行。

下方为此前任务与验收记录，实时状态以统一索引/控制台为准。

## 2026-10-18 CR1 R1验收通过

R1 已通过Codex独立复验及追加坏源码控制，CR1已验收并完成主线模块集成。见[本轮验收](reviews/2026-10-18-CR1-R1-acceptance.md)。历史：最新正式4项测试通过，但独立负控确认验收覆盖缺口，CR1进入R1返修，不另建重复任务。详见reviews/2026-10-18-CR1-R1.md；源码保持原实现，先修原测试和交付说明。

下方较早状态为历史。

当前协作入口：[项目总目录](../README.md)、[统一索引](../index.json)。本目录已迁移到 `coordination/dongos_works/`；普通源码仍在根 `code/`。CLI在组合后的隔离副本执行，历史记录的绝对路径及hash保留。

2026-10-18：CR1 已交付待复验，见[交付](deliveries/CR1.md)。

2026-10-18：发布首项 L3 独立组件任务。Cursor 只维护本目录内授权的源码、说明、测试及交付；Codex 负责独立验收和之后的主线集成。任务书优先于通用约定。

| 编号 | 任务 | 状态 | 任务书 |
| --- | --- | --- | --- |
| CR2 | 受限 NASM 只读数据声明 | R1 交付待复验（[交付](deliveries/CR2.md)，[R1](reviews/2026-10-18-CR2-R1.md)） | [CR2](tasks/CR2-board.md) |
| CR1 | NASM 字节常量编码器 | 已集成（[记录](reviews/2026-10-18-CR1-R1-acceptance.md)） | [CR1](tasks/CR1-nasm-byte-literals.md) |

先阅读 [协作约定](CONTRACT.md) 和任务书。领取后更新本表及对应任务书；完成后写 `deliveries/CR1.md` 并保持“交付待复验”。`reviews/` 由 Codex 写入，不能自行标记已验收。

当前文件归属：Codex 维护 `lang/bootstrap/semantic_types.dg`、主线语义/流程与集成；Claude C1～C6（包括 `source_position`）与 DeepSeek D1～D13 已验收，当前没有待返修任务。Cursor 不改这些实现、测试或状态文件。CR1 源码暂放 `cursor-works/src/`，测试暂放 `cursor-works/tests/`，不会被正在执行的主线语料扫描或测试发现纳入；验收后由 Codex 决定集成位置。

没有自动执行、定时检查或关机。发布任务书不代表 Cursor 已开始执行。
