# Claude 已移交暂停任务清理

2026-10-18，按用户要求，通过 coordination MCP archive 归档原 Claude C16、C18、C19、C20、C21。逐项重新核对对应 DeepSeek D14、D15、D17、D18、D16 均为 integrated，原任务为 paused 且无活动作业。

归档从网页和 MCP/API 默认任务列表隐藏，保留原状态及任务书、源码、测试、交付、审查和事件。完整 task_id 仍可 get_task/read_document 查询；导出 index.json 单独保留 archived_tasks。需要恢复时，协调角色以最新 rev 使用 change_task action=unarchive，恢复后仍是原 paused 状态，不自动启动或改变验收结果。

为完成清理，协调器新增 archive/unarchive 操作：仅已暂停/已验收/已集成任务可归档，需要说明及版本校验，无活动作业；归档后不能领取、恢复状态或排队，任务书扫描不会重新激活原件。无数据库或派生索引手工修改。空闲时平稳重启了本地协调服务，地址仍为 http://127.0.0.1:8765/。

验证：真实 MCP/HTTP 归档→默认列表隐藏→直接读文档/导出保留→拒绝旧 rev、普通 worker、直接 resume 和排队→恢复流程通过。test_mcp.py 17 项、test_coordination.py 27 项，共44项通过0skip；git diff --check通过。正式五项归档后核对网页/MCP隐藏、9个存在的相关文件指纹未变、导出记录完整，替代项仍已集成。证据 D:/projects/2026/dongos/coordination/dongos_works/.local/reviews/Claude-handoff-archive-b23e014e。

未删除交付、生产模块或审查历史，未启动模型 CLI、提交或推送。
