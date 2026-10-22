# 新开发机整体任务信息核对

核对时间：2026-10-22T08:52:13+08:00（北京时间）。项目：dongos。源码：`4e1fede1cea3f6deeb86ca17561dfc4eb07edac5`，本地分支`main`。新机source_root为`D:\projects\projects3\2026\dongos\code`，works_root为`D:\projects\projects3\2026\dongos\coordination\dongos_works`，由MCP list_projects确认。

## 当前任务与迁移差额

| 指标 | MCP/HTTP本机实查 | 已提交最终审计（历史） |
| --- | --- | --- |
| 活动记录 | 159 | 141 |
| integrated | 138 | 122 |
| accepted | 19，全部historical=true | 19，全部历史记录 |
| 在途/提交待审 | CX14 in_progress rev2；CX15 submitted rev4 | 0 |
| 运行/排队作业 | 0 | 原快照0 |
| 校验问题 | 17条任务书缺失 | 原快照0 |

本机多出的18条记录与[异机原任务台账](2026-10-20-cross-machine-task-ledger.md)对应。17条缺原任务书；CX6则为运行库中的“源码读取接线”与当前Git归档的“NASM维护”同号异义。当前同名任务书不能作为运行库CX6的正确契约。本轮保留两份历史来源，不按更高rev或事件union强合，不将缺文件误报为源码未开发。

| 多出的记录 | 当前状态 | rev | 原任务书存在 |
| --- | --- | --- | --- |
| codex:CX10 [L3] P5服务启用既有64MiB共享帧表并保留物理验收 | integrated | 6 | 否 |
| codex:CX12 [L3] 原生汇编器使用有界短位移编码以保持2MiB执行上限 | integrated | 9 | 否 |
| codex:CX13 [L3] 单56MiB纯Dong自编译作业与客体入口 | integrated | 6 | 否 |
| codex:CX14 [L3] 受限客体编译启动与持久化控制服务 | in_progress | 2 | 否 |
| codex:CX15 [L3] 修正编译作业宿主验证器的Linux布局与u64格式兼容 | submitted | 4 | 否 |
| codex:CX6 [L3] 将有界源码读取器接入已有DongOS文件句柄 | integrated | 7 | 是（CX6契约有冲突） |
| codex:CX7 [L3] 编译器专用64KiB受保护栈配置与装载入口 | integrated | 12 | 否 |
| codex:CX8 [L3] 产物提交状态机接入既有H_WRITE/H_SYNC文件授权 | integrated | 6 | 否 |
| cursor:CR45 [L3] 受限文件清单批量装载为原生frontend源码目录 | integrated | 7 | 否 |
| cursor:CR46 [L3] 将原生前端诊断按有界回调发送给既有日志接收者 | integrated | 7 | 否 |
| cursor:CR47 [L3] 测量并降低semantic_types递归路径实际栈峰值 | integrated | 13 | 否 |
| pool:GUEST1 [L3] 客体编译输入的相对路径与根目录边界校验 | integrated | 9 | 否 |
| pool:GUEST2 [L3] 通过调用者读回调装载有界源码字节 | integrated | 6 | 否 |
| pool:GUEST3 [L3] 客体编译阶段内存预算与独占复用规划 | integrated | 9 | 否 |
| pool:GUEST4 [L3] 将现有编译器文本输出接入原生汇编器 | integrated | 13 | 否 |
| pool:GUEST5 [L3] 编译产物写入与FLUSH确认的有界状态机 | integrated | 16 | 否 |
| pool:MCPPOOL1 MCP公共任务池适配：DeepSeek、Claude、Cursor自主领取 | integrated | 8 | 否 |
| pool:WINVERIFY1 修复Windows定向复验正常退出后无法登记完成 | integrated | 9 | 否 |

## 源码与阶段依据

- 当前code目录相对HEAD原本无未提交改动，120个bootstrap Dong模块、66个nasm_模块；实际源文件及原集成报告已读取核对，原始文件摘要见JSON。
- P2EXEC1 integrated rev18、P2WC1 rev10、P2ALIAS8 rev6；真实页表/别名事务与正常消费者已在当前代码。最新既有release runtime7 kernel为1994448B，2MiB窗口余102704B，见[P2消费者](../../../code/docs/p2-alias-consumers.md)、[构建证据](2026-10-22-P2SIZE9-P2SIZE10-build.json)。
- P5CTX1/2精确身份、持有上下文和真实客体核验已集成。DMA drain仍UNKNOWN，安全回收/复用/恢复未闭环，见[P5上下文](../../../code/docs/p5-recovery-context-guest.md)。
- 可变全局量、静态地址、GLOBAL/.data、有限G5差分入口及跨宿主/零参数修复已在当前代码，见[正式矩阵](2026-10-22-L3-formal-matrix.json)与[最终复验报告](2026-10-22-final-validation.json)。八类完整语言差集仍保持partial。
- CX14旧在途记录与后继G6代码分开：controller/内核受限启动/只读借页/持久化在主线，既有runtime5/49模块真实同盘双启已验收，见[G6原记录](2026-10-21-g6-ci-execution.md)。本轮未重新启动VM，不直接授予CX14新验收。
- CX15旧提交有历史1项零skip独立复验；实际tools/compiler_job.py包含Linux宿主0x10000000链接地址和64位unsigned long long ABI修正。本轮不将旧复验当作新机新结果，不直接补记原任务完成。

## 本轮更新范围

更新roadmap.json、可读任务图和源码/协调目录的计划入口，使当前状态、已集成事实与历史快照分开；accepted和integrated保持区分。原任务书、交付、失败、验收指纹、数据库及派生index均不手改；运行库自动导出产生的state/index变化按其实际来源保留。没有调用任务状态变更、发布任务、AI CLI、OS/VM、提交、推送或关机。

后续先逐项核对旧机任务契约/交付来源、CX6身份与原领取者停止事实，再通过协调器决定历史归档、补回原文或正式复验。工程待办为P2多CR3/真实性能、P5安全恢复、P6/P7/P8回归与外部验收、P9及完整G5八类差集。不能把有限任务结项或新机缺build产物等同整个OS完成或源码缺失。

本轮检查结果补充在同名JSON的checks_this_run中；历史测试数字不是本轮运行结果。未查询远端最新CI，所有远端事实沿用已注明head/日期的历史证据。

## 本轮实际检查结果

任务图Python套件10项：9项通过，1项因Windows符号链接权限跳过；JavaScript API/DOM/进度套件17项全部通过、零skip。任务图schema、complete节点无真实待办、运行中HTTP JSON/Markdown逐字一致、新增Markdown链接及diff空白检查均通过。任务id/status/rev前后相同，生产源码原始字节摘要未变；17条迁移任务书问题仍如实保留，没有冒称协调器零问题。

## 后续处理完成

上述17条缺任务书、CX6同号历史和CX14/CX15旧状态均已按用户后续授权处理；本报告保留首次核对快照，不改写原数字。最新结果见[恢复收尾报告](2026-10-22-task-recovery/README.md)与[完成回执](2026-10-22-task-recovery/completion.json)。
