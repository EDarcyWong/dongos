# 按源码与异机交接更新任务和任务图

2026-10-20，Asia/Shanghai。主线基准为345570f；异机恢复来源固定3a4704dbc1f84b90984dd0fcfeed8f53414ec49c。本轮没有切分支、合并PR8、提交/推送或运行OS/VM。

## 已补回的事实

- 找到PR8的161条原任务索引，以及相对main Git134条缺失的27条档案：16 integrated、9 paused、CX14 in_progress、CX15 submitted；17条保留原passed复验。paused含取消/归档，不重新派单。
- P2大页/通用别名/PAT已在异机分支开发，主线已有受控ELF W^X；不能按旧复选框判作从未实现。
- P5主线账本和整块DMA日志已完成；PR7已有停止后VirtIO复位并持有DMA的真实control/fault证据，另有DMA全块别名拒绝候选。安全排空/回收/恢复仍另验。
- P6普通用户SMP、tickless及init DAG已在主线接线；首代跨AP观察、正常GUI/USB回归和KVM计时是验收缺口，不是重新开发调度器。
- L3A输入输出、64KiB栈、56MiB编译作业等有原任务/代码/独审；L3B四份1,892,632字节ELF固定点已有正式历史。任务图把L3B记为异机完成，主线集成单列。
- L3C真实客体已经运行；CX14失败于SYSRET消耗RCX，24字节桥缺R10→RCX。原L3-RESUME明确下一步CX15登记→窄范围CX16的27字节桥→新快照双启，不能写成客体从未实现或从未运行。

完整来源、任务身份、版本、验证与逐文件差异见[异机台账](2026-10-20-cross-machine-task-ledger.md)和[JSON档案](2026-10-20-cross-machine-task-ledger.json)。它们保留异机完成事实，不直接覆盖当前主线调度库，也不将缺失build产物判作未开发。

## 实际集成登记

9项原任务已有独立验收，其36个交付文件当前仍全部匹配正式指纹。生产已经在478b1ed实际进入主线；逐项核对生产仅有允许的行尾差异，永久测试路径适配保留语义/原子性/只读/ABI及真实坏Dong，CR40的增强边界另行审查。

| 任务 | 当前状态 / rev |
| --- | --- |
| claude:C49 | integrated / 11 |
| claude:C50 | integrated / 11 |
| cursor:CR38 | integrated / 10 |
| cursor:CR39 | integrated / 8 |
| cursor:CR40 | integrated / 14 |
| cursor:CR41 | integrated / 8 |
| cursor:CR42 | integrated / 8 |
| deepseek:D25 | integrated / 6 |
| deepseek:D27 | integrated / 6 |

以上均通过MCP、显式dongos及最新rev登记，未手改state、数据库或index。依据见[集成指纹证据](2026-10-20-mainline-registration-evidence.json)。本地活动任务为121项：100 integrated、19 accepted、2 submitted；与异机161条历史档案分开统计。

## 实际测试与限制

| 检查 | 实际结果 | 回执 |
| --- | --- | --- |
| 主线A：C49/C50/CR38/39/40 | 20项，0skip，775.031秒，前后SHA稳定 | code/build/test/mainline-reconcile-A-685abf9a29c1/result.json |
| 主线B：CR41/42/D25/D27/C52 | 20项，0skip，979.781秒，前后SHA稳定 | code/build/test/mainline-reconcile-B-c059672f0b7a/result.json |
| NASM兼容定向，root独立重跑 | 10项，0skip，0.331秒 | code/build/test/CX6-local-15abbf5df64b/result.json及CXNASM3交付 |
| 任务图API/项目隔离/格式回归 | 9项，0skip，9.052秒 | unittest discover -s coordination/tests -p test_roadmap.py -v |

以上共59个不同的定向测试通过；不等于完整语言/OS/VM/阶段验收。

最终总manifest为 `code/build/test/mainline-reconcile-manifest-7b9946416f59/manifest.json`，SHA256 `71d52a794180ab062dfb3e837b82bfbe0251dc90c0c4f35d6e0ad29b842574b4`。84个受测输入的前后/当前SHA一致、36个原交付正式指纹全部匹配、10份组件summary与当前实物一致；9个生产模块只作行尾规范化后相同。

首轮主线C52因NASM3.02分组帮助漏探警告，setUpClass失败，0tests（run-d0a567604d4b），失败事实保留。仅修公共测试helper与兼容测试：帮助明示分组语法时追加-h -w，保留旧版能力检测、真实错误传播、完整警告名和-Wall/-Werror；真实ELF64/COFF重定位正反对照及其它警告仍错误均通过。生产组件未改。

C52正式作业d44eec8c18924b5988557c105ff14728实际6项0skip/136.510秒通过，但本机旧Windows执行器将正常退出的process_stopped=None记为停止待确认，未登记verification。实际核对作业进程退出后，使用官方confirm_pause/resume解锁并保留interrupted与原日志；没有手填结果。异机pool:WINVERIFY1已有WindowsJob生命周期修复、11项真实独立测试和集成记录，当前应恢复该已完成差集，不重派实现。

本地C52和维护任务CXNASM3仍submitted，不因本地通过越过正式登记；异机已完成任务记录也不因此撤销。

## 编号与文件保护

初查只看main漏掉另一电脑已存在的CX6/CR43，两个临时任务同号异义。发现后已官方pause/archive并[完整备份](2026-10-20-local-number-collision-backup.json)，取消本轮P5设计派单；NASM维护改为未占用的CXNASM3。没有让较大rev同步覆盖另一契约，也没有把取消项恢复凑数量。

更新文件包括roadmap.json、progress-map.md、任务索引入口、分工说明和语言门禁顶部；原历史段落保留。原先已有的控制台UI及浏览器测试改动未触碰。
