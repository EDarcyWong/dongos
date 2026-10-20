# MCPPOOL1 候选：公共任务池 MCP 适配

候选副本，对应正式路径映射：

| 候选 | 正式文件 |
| --- | --- |
| `dongos_coordination/mcp_server.py` | `coordination/dongos_coordination/mcp_server.py` |
| `dongos_coordination/mcp_config.py` | `coordination/dongos_coordination/mcp_config.py` |
| `dongos_coordination/docs/MCP.md` | `coordination/dongos_coordination/docs/MCP.md` |

## 变更要点

- 新任务默认省略 owner 发布到公共池；DeepSeek / Claude / Cursor 自主领取。
- worker `list_tasks` 默认本人 + 公共池，按 id 去重排序后分页；`owner=unassigned` 仅公共池；列出 ≠ 领取。
- 协调者 `create_task` 省略 owner → `pool:` + `pool-works/`；显式 owner 兼容旧定向任务。
- 指令、工具说明与文档统一说明依赖/路径冲突 409、claim_token 与释放回池语义。
- `mcp_config` 仍为三客户端输出正确 `--owner` 与共用 `coordination-tasks`；不安装真实配置、不输出凭据、不自动启动模型。

未改 `store.py` / `client.py`：公共编号、领取令牌与冲突保护已由基线提供。

## 测试与集成

定向测试：`pool-works/tests/test_mcp_pool.py`、`pool-works/tests/test_mcp_pool_config.py`。
测试从正式 `coordination/` 只读复制完整包，再覆盖本候选文件，对临时 HTTP/数据库运行，不操作生产任务。

集成由 Codex 独立复验后，将候选文件按上表回写正式路径并更新 README/MCP 文档。客户端侧重载 MCP 或新建会话即可；勿在验收前手改正式源码或真实客户端配置。
