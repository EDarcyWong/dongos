# DongOS 项目任务

2026-10-18最新复验：C29、CR16～CR19均已验收并真实集成，主线16组件+2组合共18项通过0skip、来源稳定；C29快照问题及CR16原R1闭合。另通过MCP给Claude发布C30～C32，见[复验集成](reviews/2026-10-18-C29-CR16-CR19-integration.md)、[新派单](reviews/2026-10-18-Claude-C30-C32-allocation.md)。

2026-10-18最新Claude复验：C26～C28已验收并真实集成，主线12组件+1真实组合共13项通过0skip、来源稳定；C29快照中止未跑测试，原交付待重提，未集成。见[本轮记录](reviews/2026-10-18-C26-C29-review-integration.md)。

2026-10-18最新Cursor复验：CR11～CR15已全部验收并真实集成，主线15项及新增组合1项共16项0skip通过；历史CR11/12/13返修闭合。新交CR16仅补原生R8覆盖，未集成。见[本轮记录](reviews/2026-10-18-CR11-CR16-review-integration.md)。

2026-10-18新增Claude任务：已通过MCP发布C26～C29（CL可变移位、寄存器间接调用、条件移动、RIP符号取址），依赖已集成、四项互不冲突，由Claude客户端领取执行。见[派单记录](reviews/2026-10-18-Claude-C26-C29-allocation.md)。

2026-10-18清理：Claude原C16/C18/C19/C20/C21已通过MCP归档，从默认任务列表隐藏；对应DeepSeek替代任务全部已集成，历史文件保留，见[清理记录](reviews/2026-10-18-Claude-handoff-archive.md)。

2026-10-18追加复验：C25已验收并真实集成，正式与主线同3项各0skip通过、来源稳定；CR13仅补原生输入寄存器保留观察，见[本轮记录](reviews/2026-10-18-C25-CR13-followup.md)。Claude原五份暂停任务的DeepSeek替代项D14～D18已全部集成，暂停仅保留移交历史。

最新集成（2026-10-18）：Claude C22/C23/C24均已验收并真实集成，正式同12项与主线12+1组合共13项均0skip通过、来源稳定。Cursor CR12仅补只读输入夹具；CR11本次快照冲突未执行测试，需重新提交现有R2后复验。本轮不新增任务，见[本轮记录](reviews/2026-10-18-C22-C24-mainline-integration.md)。
最新追加派单（2026-10-18）：通过 coordination MCP 新增 Cursor CR16～CR19 四项、Claude C24/C25 两项；原 CR12～CR15、C22/C23 保留，均不替客户端领取或启动 CLI。CR11 为提交待复验，DeepSeek 不新增。见[本轮任务](reviews/2026-10-18-more-mcp-allocation.md)。

最新派单（2026-10-18）：按用户新授权发布Cursor CR12～CR15四项及Claude C22/C23两项，均为独立L3发射组件，依赖已集成且避开CR11和Codex语义主线。通过各自worker MCP查看/领取/交付，客户端手动执行，未启动模型CLI；DeepSeek暂不可用，不新增任务。见[本批任务](reviews/2026-10-18-next-emitters-allocation.md)。
最新（2026-10-18）：D20已由Codex按用户授权接手完成并验收集成，正式与主线同4项各0skip通过；CR11 R1两大漏点已闭，仅剩原written端点溢出夹具，继续原任务有限返修。见[本轮复验](reviews/2026-10-18-D20-Codex-CR11-R1.md)。DeepSeek暂不可用，不新增任务。下方D20返修为历史。
最新复验（2026-10-18）：Cursor CR8/CR9/CR10已独立验收并真实集成，正式同9项与主线9项分别通过0skip；CR11、DeepSeek D20正式测试虽通过，独立审查证明原生观察/别名负控未齐，已在原任务追加R1并通过MCP退回返修，未集成。见[本轮复验](reviews/2026-10-18-Cursor-DeepSeek-review.md)。源码由原负责人修复，Cursor保持手动，本轮无新派单。
最新派单（2026-10-18）：D19 R1、LM8均已集成后，按用户要求只给DeepSeek新增[D20](deepseek-works/tasks/D20-board.md)：有界最短SLEB128 i64解码，限定本人works模块/说明/测试/交付4文件，依赖已集成D19；不占用Cursor或Codex语义主线，不自动启动CLI。任务状态以MCP为准。

最新（2026-10-18，D19 R1/LM8）：两项均已独立验收并真实集成，正式及主线同5项各通过、0skip、指纹稳定。D19另4种选择性别名漏检坏董共8次原生准确拒绝，关闭首交R1；LM8隔离候选已同步正式数据/交付及主线fixture/永久检查。见[本轮集成](reviews/2026-10-18-D19-R1-LM8-integration.md)。下面待返修/执行中为历史，实时以MCP为准。

最新（2026-10-18，CR5及新批次）：CR5已独立验收并集成，正式与主线同3项各通过、0skip、来源稳定。新增Cursor CR8～CR11四项、DeepSeek D19一项、LM Studio LM8一项，均待领取且未自动执行；Claude新派单延后约至21:22，原五项移交记录继续暂停保留。见[本批记录](reviews/2026-10-18-CR5-and-next-allocation.md)、[分工](ALLOCATION.md)与[Claude预备说明](CLAUDE_NEXT.md)。下方状态为历史，实时以MCP为准。

最新集成（2026-10-18）：通过MCP复验Cursor/LM Studio新交付后，CR2/CR3/CR4/CR6/CR7、DeepSeek D14～D18、LM7共11项已真实集成，主线34项通过、0skip。CR5已由Cursor手动领取进行中，本轮无新派单。见[第一批](reviews/2026-10-18-CR2-CR7-D14-D18-LM7-integration.md)及[后续三项](reviews/2026-10-18-Cursor-followup-integration.md)；下方较早状态保留历史，实时以MCP/进度图为准。

最新（2026-10-18）：网页新增实时任务进度图，按七种状态显示任务、依赖阻塞、运行作业，支持筛选和详情跳转。DeepSeek D16 R1已验收，现D1～D18全部独立验收，新增组件尚未集成；见[D16验收](deepseek-works/reviews/2026-10-18-D16-R1-acceptance.md)及[进度图验证](reviews/2026-10-18-task-progress-ui.md)。下方较早状态保留历史。

最新交付复验（2026-10-18）：DeepSeek D14/D15/D17/D18 已验收、尚未集成，D16 原夹具有限返修；Cursor 四项进行中、CR5 等待 CR4；LM7 待领取。本轮16项定向通过但D16另有真实测试漏检，不计入已验收，见[三客户端审查](reviews/2026-10-18-client-deliveries.md)。下方派单与交接状态保留历史，实时以MCP为准。

最新分工：新增开发主要给 Cursor，少量给 DeepSeek，LM Studio 只做最简单任务，见[分配约定](ALLOCATION.md)。本轮新增 Cursor CR3～CR7 五项、LM Studio LM7 一项，DeepSeek 不新增、继续在途 D14～D18；Cursor 保持客户端手动执行。

2026-10-18：Claude 的五项未完成任务已暂停，转交 DeepSeek D14～D18，最终核对时已全部领取、进行中；LM6 已验收并集成，Cursor CR2 R1 已验收、尚未集成，Cursor 继续手动执行。见[本轮 MCP 复验与交接](reviews/2026-10-18-mcp-review-and-claude-handoff.md)和 [DeepSeek 入口](deepseek-works/README.md)。

本目录集中保存 DongOS 的协作任务、任务测试、交付、审查和运行记录：

- `claude-works/`、`cursor-works/`、`deepseek-works/`、`gemini-works/`、`lmstudio-works/`：各助手任务及相关文件。
- `project.json`：项目名称与源码目录（当前 `../../code`）。
- `index.json`：派生统一任务索引，不手改。
- `.local/`：本项目状态库、执行副本、测试回执与日志，Git忽略。

源码位于根目录 `code/`。逻辑任务路径如 `cursor-works/src/...` 在主目录中映射到本目录，在隔离执行副本中与项目源码组合，以兼容现有构建与测试。任务书和交付里的历史绝对路径保留用于溯源。

控制台运行与多项目说明见 [协调项目](../README.md)。
