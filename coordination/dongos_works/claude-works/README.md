# Claude 工作区

2026-10-18最新：C29本次正式复验通过并已集成，前次快照待重提为历史。新队列[C30](tasks/C30-board.md)缩放索引操作数、[C31](tasks/C31-board.md)除法异常门禁、[C32](tasks/C32-board.md)内存复制/清零发射已通过MCP发布；本人客户端领取/执行/提交，依赖已集成，不启动CLI。见[派单](../reviews/2026-10-18-Claude-C30-C32-allocation.md)。

2026-10-18最新：C26/C27/C28已验收并集成，主线13项（含CL移位→条件选择目标→间接调用组合）0skip通过；C29正式快照中止未执行测试，请按[说明](reviews/2026-10-18-C29-snapshot-retry.md)通过worker MCP重提现有交付，无需重写算法。见[复验记录](../reviews/2026-10-18-C26-C29-review-integration.md)。下方四项待领取为发布时历史。

2026-10-18新队列：通过worker MCP领取[C26](tasks/C26-board.md)CL可变移位、[C27](tasks/C27-board.md)寄存器间接调用、[C28](tasks/C28-board.md)条件移动、[C29](tasks/C29-board.md)RIP符号取址。依赖均已集成，各仅4授权文件；先完成已领取项再领下一项，不启动模型CLI。见[完整分配](../reviews/2026-10-18-Claude-C26-C29-allocation.md)。

2026-10-18清理：原C16/C18/C19/C20/C21已归档，默认列表不再显示。对应D14/D15/D17/D18/D16均已集成；原暂停状态仅存于历史记录，不恢复或重复执行，见[记录](../reviews/2026-10-18-Claude-handoff-archive.md)。

2026-10-18追加集成：C25已验收并集成，主线同3项0skip通过、来源稳定，见[记录](../reviews/2026-10-18-C25-CR13-followup.md)。原暂停C16/C18/C19/C20/C21分别由D14/D15/D17/D18/D16完成并全部集成，无需恢复。下方C25继续原任务为此前状态。

2026-10-18最新：C22/C23/C24均已验收并真实集成，主线13项（含真实组合）通过0skip，原生产字节未改；C25继续原任务。见[集成记录](../reviews/2026-10-18-C22-C24-mainline-integration.md)。下方待领取/待复验为历史。
2026-10-18追加 MCP 派单：[C24](tasks/C24-board.md)加减溢出分支、[C25](tasks/C25-board.md)直接调用；原C22/C23继续有效，先处理已领取任务，再按工作量领取新项。不恢复原五项暂停移交任务，不启动CLI。见[本批说明](../reviews/2026-10-18-more-mcp-allocation.md)。

最新派单（2026-10-18）：用户已允许Claude接单，正式发布[C22](tasks/C22-board.md)比较生成规范bool与[C23](tasks/C23-board.md)wrapping整数二元运算，两项均待领取，不是原暂停任务的恢复。只维护各自4文件；通过worker MCP领取，客户端手动执行，没有启动CLI。见[本批任务](../reviews/2026-10-18-next-emitters-allocation.md)。
最新（2026-10-18）：用户允许等待1小时25分钟后派新任务；最早21:21:13，已安排一次后续派单预计约21:22:35（Asia/Shanghai）。目前未发布新Claude任务、未启动CLI，候选见[预备说明](../CLAUDE_NEXT.md)，执行前重查时间/归属/重复任务。C16/C18/C19/C20/C21继续暂停，对应D14～D18均已集成，原件/交付/返修历史保留，未删除。下方旧队列不恢复。

## 2026-10-18 额度不足，未完成任务已转交

用户要求交由 DeepSeek 完成。C16→D14、C18→D15、C21→D16、C19→D17、C20→D18；这五项 Claude 原任务已通过 MCP 暂停，原源码、候选副本、交付和返修历史保留。此前已验收或已集成的任务保持原状态。请执行 [DeepSeek 新任务](../deepseek-works/README.md)，不要继续修改 Claude 原件。见[本轮复验与交接](../reviews/2026-10-18-mcp-review-and-claude-handoff.md)。下方任务发布及队列描述为历史，当前状态以 MCP 为准。

## 2026-10-18 后续任务

新增C19迭代DFS后序、C20按前驱生成phi复制、C21带对齐原始常量池。C16～C18继续原队列，C13～C15本轮验收/集成另有记录。 [C19](tasks/C19-board.md)、[C20](tasks/C20-board.md)、[C21](tasks/C21-board.md)。实时状态以控制台为准。

## 2026-10-18 本轮集成

C13～C15已集成到主线lang/bootstrap及永久测试，10项主线/组合检查通过；C16～C18继续原任务。见[集成记录](../reviews/2026-10-18-C13-C15-LM5-integration.md)。以下发布状态为历史，实时以控制台为准。

2026-10-18 集成更新：C7～C12已集成到code/lang/bootstrap及主线永久测试。见[集成记录](../reviews/2026-10-18-batch3-integration.md)。


## 2026-10-18 新任务 C13～C18

[C13](tasks/C13-board.md)、[C14](tasks/C14-board.md)、[C15](tasks/C15-board.md)、[C16](tasks/C16-board.md)、[C17](tasks/C17-board.md)、[C18](tasks/C18-board.md)。六项独立工具，CLI按队列串行执行；无命令工具时由协调器跑测试，不虚构已执行结果。

下方为此前任务与验收记录，实时状态以统一索引/控制台为准。

## 2026-10-18 C7～C12验收通过

已发布6个独立纯Dong组件：C7控制流图可达性、C8 SysV整数参数规划、C9并行复制消环、C10栈槽布局、C11常量分支排序、C12作用域清理规划。全部在claude-works内，不占Codex活动文件；现已交付、通过Codex独立验收并完成主线模块集成。见[本轮验收](reviews/2026-10-18-C7-C12-acceptance.md)。

下方较早状态为历史。

当前协作入口：[项目总目录](../README.md)、[统一索引](../index.json)。本目录已迁移到 `coordination/dongos_works/`；普通源码仍在根 `code/`。CLI在组合后的隔离副本执行，历史记录的绝对路径及hash保留。

2026-10-18 最新验收：C6已独立3项复跑、两模式43194次新种子执行及6次真实坏实现拒绝，见[验收记录](reviews/2026-10-18-C6-acceptance.md)。C1～C6均已验收，当前没有待返修任务。本次按用户要求把新独立任务CR1发布到`cursor-works/`；下面C5发布C6的记录保留为历史。

2026-10-18 后续交付验收：C5已通过独立3项复跑、新种子5600次执行和8次真实坏实现拒绝，见[验收](reviews/2026-10-18-C5-acceptance.md)。新分配[C6源码位置定位](tasks/C6-source-position.md)，避开Codex运行时类型/流程。此前“未交付”核对保留为历史；C1～C5均已验收，DeepSeek D1～D13也已验收。

2026-10-18 较早核对（历史，已被上方验收取代）：当时C5仍待领取，尚无源码/测试/交付，见[状态记录](reviews/2026-10-18-C5-status.md)。当时保留原C5、不新增C6；后续交付与验收见上方。

2026-10-18，C1/C2 已由 Codex 独立审查、复跑与新种子最高8192位扩展验证，均**已验收（独立组件）**，见[验收记录](reviews/2026-10-18-C1-C2-acceptance.md)。原交付保留；语义层集成与L3自举仍由Codex继续推进。

C3/C4也已由Codex独立审阅、8项复跑及新种子扩展验证，**已验收（独立组件）**，见[本轮验收](reviews/2026-10-18-C3-C4-acceptance.md)。新分配C5原生单行诊断格式化，避开Codex的`bootstrap.semantic_types`及常量/类型/布局集成；不据此关闭L3。

| 编号 | 任务 | 状态 | 任务书 |
| --- | --- | --- | --- |
| C7 | 控制流图合法性与可达性 | 已集成 | [C7](tasks/C7-board.md) |
| C8 | SysV 整数参数位置规划 | 已集成 | [C8](tasks/C8-board.md) |
| C9 | 并行复制循环消解 | 已集成 | [C9](tasks/C9-board.md) |
| C10 | 栈帧局部槽布局 | 已集成 | [C10](tasks/C10-board.md) |
| C11 | 常量分支表排序与重复值检查 | 已集成 | [C11](tasks/C11-board.md) |
| C12 | 词法作用域退出清理顺序 | 已集成 | [C12](tasks/C12-board.md) |
| C6 | 原生UTF-8源码位置定位 | 已验收（[记录](reviews/2026-10-18-C6-acceptance.md)） | [C6](tasks/C6-source-position.md) |
| C5 | 原生单行诊断格式化 | 已验收（[记录](reviews/2026-10-18-C5-acceptance.md)） | [C5](tasks/C5-diagnostic-format.md) |
| C3 | AST 纯常量整数/布尔求值 | 已验收（[记录](reviews/2026-10-18-C3-C4-acceptance.md)） | [C3](tasks/C3-constant-arithmetic.md) |
| C4 | 目标类型布局引擎 | 已验收（[记录](reviews/2026-10-18-C3-C4-acceptance.md)） | [C4](tasks/C4-type-layout.md) |
| C1 | 任意精度有符号除法与余数 | 已验收（[原交付](deliveries/C1.md)） | [C1](tasks/C1-bigint-div.md) |
| C2 | 任意精度位运算与移位 | 已验收（[原交付](deliveries/C2.md)） | [C2](tasks/C2-bigint-bits.md) |

Claude C1～C12均已独立验收，C7～C12已完成主线模块集成。Codex负责模块加载、绑定、常量/类型/布局及运行时/流程集成；DeepSeek D1～D13已验收。通用历史约定见[CONTRACT](CONTRACT.md)，不能用其旧C1/C2接口替代新任务书。

通过协调器领取任务并更新状态，统一索引由协调器导出，不手改；接口说明见[AI任务指南](../../dongos_coordination/docs/AI_API.md)。完成后写入 `deliveries/对应编号.md` 并提交交付，保持“交付待复验”。Codex 独立审查、执行定向测试和负控后才可标记验收。返修追加原交付历史；`reviews/` 仅供 Codex 写入。禁止覆盖历史证据，不提交或推送，不启动 QEMU/VMware，不修改未授权文件。

这些是独立编译组件任务，不等于完整 Dong 编译器、自举或 L3 阶段已完成。当前不安排自动检查或关机。
