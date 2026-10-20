# WINVERIFY1 集成与正式验收记录

用户明确授权集成WINVERIFY1、重启服务、完成正式独立复验及验收；后续明确授权Codex直接修复该任务内容。

实际集成：
- runner.py已复制到coordination/dongos_coordination/runner.py，正式/候选SHA256均为40504e6f0ca2beca2d6e1a08b9c91735d978529854c575f3a4590cc325b08abe。
- 原runner备份coordination/.local/WINVERIFY1-integration/runner-before.py。
- 新增正式永久回归coordination/tests/test_windows_verification_finish.py；对实际正式包隔离复制执行11项，0skip，44.470秒。
- 无活动/排队作业时通过shutdown接口停止旧服务13684；隐藏启动新服务1388，13:57:27北京时间启动，HTTP/MCP健康。所有后续通过的正式作业process_stopped=true，结果已正常保存。
- 测试集成适配：允许正式/候选一致，仍验证临时副本精确加载候选；在正式隔离目录中定位只读协调服务依赖并复制到临时包，所有Python依赖前后SHA守卫。MCPPOOL1两份测试也作同样只读依赖定位适配。未弱化进程树停止、角色、令牌或验收门禁。

最终正式状态：

| 任务 | 状态 | rev | 正式tests | skips |
|---|---|---:|---:|---:|
| pool:WINVERIFY1 | integrated | 9 | 11 | 0 |
| claude:C52 | accepted | 18 | 6 | 0 |
| cursor:CR40 | accepted | 23 | 4 | 0 |
| pool:GUEST1 | accepted | 8 | 19 | 0 |
| pool:GUEST2 | accepted | 5 | 21 | 0 |
| pool:GUEST3 | accepted | 8 | 13 | 0 |
| pool:MCPPOOL1 | accepted | 7 | 12 | 0 |
| pool:GUEST5 | rework | 6 | 0 | 0 |
| pool:GUEST4 | in_progress | 2 | 0 | 0 |

WINVERIFY1与6个组件任务合计86项正式测试全部通过、零skip、来源稳定；验收使用最新rev和正式verification，未手填verification或绕过指纹。WINVERIFY1已登记integrated，其余六项只登记accepted，未冒充已集成主线。

GUEST5未验收：安全独立探针证实PENDING_FLUSH且written<total时可绕过写入直接FLUSH并报告DURABLE，已原任务rework rev6，证据2026-10-20-guest5-inconsistent.c/.json。GUEST4仍在实现，不提前验收。

正式结果/当前文件指纹/逐项产物审查见2026-10-20-formal-acceptance-evidence.json；C52另核对713产物SHA及130组原生ABI/返回值观察，见2026-10-20-C52-formal-final-evidence.json。本轮最终无活动或排队协调器作业，无遗留停止确认。未提交/推送Git或运行OS/VM；保留其它会话现存修改，状态文件由协调器正式API导出。

