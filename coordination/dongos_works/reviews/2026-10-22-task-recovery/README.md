# 新开发机任务原文恢复与旧状态收尾

本次处理范围为原缺失17份任务书、CX6同号冲突以及CX14/CX15旧状态。源码基线为4e1fede；原文固定来源为50ab7cf9cde101691774a8480bdb7fcc07c766be（已合入主线的原PR8 head），没有从聊天或任务标题重新编造任务书。

## 原文和历史验收恢复

[恢复清单](restoration-manifest.json)逐文件记录Git blob与SHA256。17份缺失任务书及CX6正确契约共18份任务书按Git原始字节恢复，另恢复原交付等关联文件，合计35个文件。每项title/description/write_paths/checks/depends_on/document/delivery与运行库对应记录一致；源码实现没有被旧候选覆盖。

[历史指纹核对](historical-fingerprint-audit.json)逐项保留18份原记录、17项原passed复验、16项原integrated事实。所有历史指纹路径都有实物；LF/CRLF等价与真实后继内容分别列出，不修改原验收SHA、不把后继源码倒写为旧源码。没有重新授予这些既有组件验收。

| 原缺失任务书 | 规范入口 |
| --- | --- |
| codex:CX10 | [任务书](../../codex-works/tasks/CX10-board.md) |
| codex:CX12 | [任务书](../../codex-works/tasks/CX12-board.md) |
| codex:CX13 | [任务书](../../codex-works/tasks/CX13-board.md) |
| codex:CX14 | [任务书](../../codex-works/tasks/CX14-board.md) |
| codex:CX15 | [任务书](../../codex-works/tasks/CX15-board.md) |
| codex:CX7 | [任务书](../../codex-works/tasks/CX7-board.md) |
| codex:CX8 | [任务书](../../codex-works/tasks/CX8-board.md) |
| cursor:CR45 | [任务书](../../cursor-works/tasks/CR45-board.md) |
| cursor:CR46 | [任务书](../../cursor-works/tasks/CR46-board.md) |
| cursor:CR47 | [任务书](../../cursor-works/tasks/CR47-board.md) |
| pool:GUEST1 | [任务书](../../pool-works/tasks/GUEST1-board.md) |
| pool:GUEST2 | [任务书](../../pool-works/tasks/GUEST2-board.md) |
| pool:GUEST3 | [任务书](../../pool-works/tasks/GUEST3-board.md) |
| pool:GUEST4 | [任务书](../../pool-works/tasks/GUEST4-board.md) |
| pool:GUEST5 | [任务书](../../pool-works/tasks/GUEST5-board.md) |
| pool:MCPPOOL1 | [任务书](../../pool-works/tasks/MCPPOOL1-board.md) |
| pool:WINVERIFY1 | [任务书](../../pool-works/tasks/WINVERIFY1-board.md) |

## CX6身份分离

[身份核对](cx6-identity-resolution.md)及[JSON](cx6-identity-resolution.json)明确区分：当前有效codex:CX6是L3文件读取适配器；另一份本地NASM CX6原本已暂停归档，实际后继为已验收集成的codex:CXNASM3。旧NASM任务书、交付、状态及事件原文分别保全在cx6-local-nasm/，读取器的原支事件在cx6-reader-original/。不删除或伪造数据库旧事件，不把两种契约的验收混用。当前规范任务书与运行库契约已一致。

本机另外实际运行源码读取器和NASM能力探测共11项测试，零skip、15.131秒、exit0。CXNASM3独立delivery及原验收指纹未被CX6恢复操作改动。

## CX14/CX15后继证据与本轮正式复验

[G6源码绑定](g6-source-binding.json)逐项核对8个相关源码/工具/测试/契约文件，与原G6候选f54c35c内容LF等价；services.perform中真实compiler退出与启动门逐字符相同。新机换行差异不冒作逐字SHA相同。两项旧任务的后继工程实现确已在当前代码，而不是仅有交付文字。

原CX14宿主审查尚缺真实VM的结论保持原日期；其后G6原始验收报告记录了准确head的同盘双启、完整ELF、两位独审及1810份物理转储。原始大体积artifact没有迁移到新机，本轮不声称重新执行VM或重新解码未在本机的转储。仅依据明确绑定的既有原始验收回执，并对当前稳定代码运行新的声明定向测试。

CX14原交付入口缺失，协调者按本轮用户授权补建[迁移交付](../../codex-works/deliveries/CX14.md)，使用协调器人工提交入口登记；没有冒充原领取agent、转派开发或伪造其外部停止确认。随后排队正式隔离复验d1dd123835f04bedbbd8dfb903054ace。CX15恢复原始交付后排队正式隔离复验8d6893090cd74e3c96a9af844a27a15c。两项均须实际通过、零skip、source_stable及进程树停止确认后，才依据代码/契约/有效负控审查分别验收和登记真实主线集成。

最终正式结果、最新rev、校验与任务图同步回执见同目录completion.json；在该回执生成前，本报告不预记测试通过或任务完成。完整G5八类差集及P5/P2等阶段剩余范围不因任务登记收尾而关闭。

## 最终状态

本轮17份缺失任务书、CX6同号异义和CX14/CX15旧状态均已处理完成。CX14 integrated rev7，CX15 integrated rev8；CX6 integrated rev9，已恢复读取器契约，分离5条原NASM事件，耗时恢复为1轮/265秒，原始事件全部保留。协调器issues=0；核对时间2026-10-22T09:18:41+08:00。

当前MCP快照共164项活动任务：19 accepted、140 integrated、3 submitted、1 in_progress、1 rework。本轮同时观测到其它客户端新增5项并行任务，其状态按实时MCP继续变化，本轮没有接管或改动它们。

新协调器已安全重载，HTTP/MCP时间线确认CX6为1轮/265秒并显式保留5条分离事件。原17条校验问题已清零，CX14/CX15分别integrated rev7/rev8；本次没有接管并行新任务。

## 收尾回归

协调器完整回归158项：157通过，1项因Windows文件符号链接权限跳过，214.235秒、exit0；JavaScript API/DOM/进度17项全部通过、零skip。原有CX6全部原始事件仍在，当前派生时间线为1轮/265秒；CX14/CX15当前主目录声明文件继续逐项匹配新正式验收指纹，HTTP JSON与Markdown和本地文件一致，校验issues=0。原文件35项SHA与新增39个Markdown链接检查通过。
