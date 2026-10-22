# MCPPOOL1 交付：MCP 公共任务池适配

候选人：Cursor（`cursor-mcp-415ed5783a554f4e`）。状态：submitted，等待 Codex 独立复验与真实集成。

## 候选映射与 SHA256

| 候选（pool-works） | 正式路径 | 基线 SHA256 | 候选 SHA256 |
| --- | --- | --- | --- |
| `mcp-pool/dongos_coordination/mcp_server.py` | `coordination/dongos_coordination/mcp_server.py` | `ec0a703273fe3fd15d280adf4cb940ef8f15ff8d3849e95a9658236592e11a4d` | `5417cb1321b84043a81b93589e1243b591044b93d21ca4169c01c6a5b4ca6a51` |
| `mcp-pool/dongos_coordination/mcp_config.py` | `coordination/dongos_coordination/mcp_config.py` | `3ec4feb5c30aca234b35b031759f13fe9f0be3f3bc483052c1fc3b8b6400299e` | `a91518fed911f286db1b92e5087772513a18b0a411fa1f01bae51c5b176b3c8f` |
| `mcp-pool/dongos_coordination/docs/MCP.md` | `coordination/dongos_coordination/docs/MCP.md` | `be451ed3364320ba49a212c31034f94f35bec0cfb05a3b712cdb5ece3f8f670f` | `32030a82a27295b282bbf6e02156f4cef881ec3d10e98592b90f171b71763c4d` |

附加授权文件：

- `pool-works/mcp-pool/README.md` — `f58c9232ede99ff4065229288f4988fd628a927b20c9483c2b1ec9fbbcbbee42`
- `pool-works/tests/test_mcp_pool.py` — `412638a73cbd6fa854d2f83ab55e3db60973b695566f7cf088d1c997a9512885`
- `pool-works/tests/test_mcp_pool_config.py` — `e170f4002a0d94e3419859204fed0e29e620086765c5dc8f5a47c1544b557755`

未修改正式 `mcp_server.py` / `mcp_config.py` / `docs/MCP.md`、`store.py`、`client.py`、生产 SQLite/`index.json` 或真实客户端配置。公共编号、claim_token、依赖/路径冲突由基线 store 提供；本项只补 MCP 指令/工具说明、list 去重排序与文档。

## 功能差异摘要

1. initialize / coordinator 指令与 tools/list：默认公共池、三客户端自主领取；省略 owner → `pool:` + `pool-works/`。
2. worker `list_tasks`：本人 + 公共池去重后按 id 排序再分页；`owner=unassigned` 仅公共池；列出 ≠ 领取。
3. `mcp_config`：三客户端共用 `coordination-tasks`，安装时绑定 `--owner`；仅补充说明性 docstring，行为与基线一致。
4. 文档 `MCP.md` / README：统一客户端提示与集成回写说明。

## 定向测试

工作目录：`coordination/dongos_works`。

```text
python -m unittest discover -s pool-works/tests -p "test_mcp_pool*.py" -v
```

结果：Ran 12 tests in ~39s，OK，失败 0，skip 0。

覆盖：真实 stdio MCP 子进程 + 临时 HTTP/注册表；从正式包只读复制后覆盖候选；三客户端发现公共任务并 claim→submit；协调者省略 owner 发布；并发领取/释放换人/旧令牌拒绝；依赖与创建路径冲突 409；筛选分页；角色隔离与身份不可覆盖；旧定向任务兼容；配置生成/备份/碰撞拒绝。未操作生产任务库。

## 限制

- 未启动 AI CLI、未提交/推送、未运行 OS/VM/全回归。
- submitted ≠ accepted/integrated；集成须 Codex 将候选回写正式路径后由客户端重载 MCP。
- 基线 `coordination/tests/test_mcp_config.py` 实际已并入 `test_mcp.py`；本项自带 `test_mcp_pool_config.py` 覆盖候选配置。


## AI交付 2026-10-20T04:59:42+00:00 · cursor-mcp-415ed5783a554f4e

候选落盘：mcp_server（公共池指令/list去重排序/工具说明）、mcp_config（三客户端共用服务说明）、MCP.md与README映射。定向测试：在 coordination/dongos_works 执行 python -m unittest discover -s pool-works/tests -p "test_mcp_pool*.py" -v → Ran 12 tests OK，失败0 skip0；真实stdio MCP+临时HTTP，覆盖省略owner发池、三客户端claim→submit、并发/释放换人/旧令牌、依赖与路径冲突409、分页筛选、角色隔离与定向兼容、配置生成。未改正式源码/生产库/真实客户端配置；未跑OS/VM/全回归/AI CLI；submitted等待独立复验。详见 pool-works/deliveries/MCPPOOL1.md。
