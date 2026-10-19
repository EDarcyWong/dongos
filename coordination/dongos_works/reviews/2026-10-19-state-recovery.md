# DongOS 状态库追查与恢复（2026-10-19）

按用户明确要求执行工作区级恢复，使用新增协调器 `recover-state` 命令事务写入并由协调器导出 index。没有手工改库或 index 绕过验收；恢复已有事实，不进行新的组件验收/集成，不声称重新执行历史原生测试。

## 原因与证据

- `git reflog` 显示工作区于北京时间2026-10-19 10:11:03从GitHub克隆；`.gitignore` 忽略 `coordination/*_works/.local/`，原SQLite、候选副本和作业日志未随Git带入。没有证据表明是运行中删库。
- 重建库 `PRAGMA integrity_check=ok`，只有95条 `imported` 事件（北京时间12:21至12:35），无原验收、集成、返修、归档事件。旧任务书按发布时状态重导入是状态降级的直接原因。
- 启动修复前备份 `.local/index-before-startup-repair-20261019.json` 与Git提交 `0a020e1` 的原index在JSON层面完全一致。快照生成于北京时间2026-10-19 00:06:35，原文件SHA256：`f3ab929e33419f40dfc417217d588acf8b1b26cbac50724a51942a11e438c171`。
- 8项返修与 `2026-10-19-Claude-Cursor-submitted-review.json` 的final_tasks全字段一致。原正式28项测试通过，但独审测试契约缺口未关闭，恢复rework，不设为accepted。
- 55项integrated的204个验收文件指纹全部核对：118个逐字节匹配，86个转换CRLF为LF后匹配，无其它差异。Git `core.autocrlf=true`；原验收指纹不重写，规范化比较不冒充新复验。
- 47个代码组件在主线的 `.dg/.md` 共94份与works交付逐一比较，LF规范化后一致。LM Studio八项是其专属文档/固定数据集成。
- C1～C6独立验收记录及D1～D13既有独立验收/最终D12验收记录仍在，源码、测试、说明可查。保留19项accepted，不提升为integrated。
- Claude C16/C18/C19/C20/C21原归档、移交记录在，对应DeepSeek已集成，恢复paused+archived，禁止重新领取。

## 恢复操作

[逐项审计JSON](2026-10-19-state-recovery-audit.json)覆盖95项任务、432份文件核对、94份主线映射，以及各任务原审查文件的SHA256。先预览，再以同一snapshot/audit加 `--apply` 执行。

北京时间12:43:01恢复完成。事务前备份：`.local/backups/2026-10-19T04-43-00+00-00-56b7eb18/`。回执：`.local/backups/recovery-2026-10-19T04-43-00+00-00-56b7eb18.json`。

每项使用 `max(原快照rev,重建库rev)+1` 保存，保留原审查/复验/候选编号，增加state_recovery来源，写state_restored和总恢复事件。所有自动派单/复验、全局自动化关闭。

| 状态 | 数量 | 范围 |
| --- | ---: | --- |
| integrated | 55 | 原验收及真实集成记录 |
| accepted | 19 | C1～C6、D1～D13，仅历史独立验收 |
| rework | 8 | C33～C36、CR20～CR23 |
| submitted | 2 | C37、C38 |
| todo | 6 | CR24～CR29 |
| paused+archived | 5 | C16、C18～C21，默认隐藏 |

## 防护与限制

新增缺库/空库保护：非空快照存在时拒绝重导入覆盖。服务启动、项目首次加载、手动sync前生成完整SQLite备份。恢复入口绑定项目、快照和逐项证据，拒绝覆盖已有真实操作/作业，事务内复核指纹和rev，禁止重复恢复。

原候选副本17份、原作业表及原始日志没有随Git克隆，无法仅凭快照重建。本次保留候选编号和历史复验JSON，不伪造副本、成功作业或新测试；依赖旧副本的交付查看/重放仍可能提示不存在，可查现存已集成文件和审查记录。迁移必须保存整个works及 `.local`。未启动AI CLI、OS/VM、提交或推送。

## 恢复后验证

- 协调器84项Python测试：83通过，1项因本机Windows文件符号链接不可用跳过；3项前端API测试通过。最终恢复校验代码调整后，6项恢复专项再次通过。`git diff --check`通过。
- 实际执行sync并重启服务，首页HTTP 200；项目API返回90项活动任务，分布55 integrated、19 accepted、8 rework、2 submitted、6 todo。5项归档仍隐藏，只有CR24～CR29为todo。
- 对所有95项逐一断言：状态、归档标志、依赖、历史verification/review_note/integration_note/candidate/archive_note与原快照相同，rev全部增加。sync只记录8项任务书旧hash的document_changed，不改变状态、证据或归档。
- SQLite完整性检查ok，项目validate为空，全局自动化false，jobs=0；95条state_restored及1条总恢复事件可查。
- 恢复完成并重启后的完整SQLite另备份于 `.local/backups/2026-10-19T04-44-52+00-00-eec01e3d/`。服务保持在 `http://127.0.0.1:8765/`。
