# MCPPOOL1 — MCP公共任务池适配：DeepSeek、Claude、Cursor自主领取

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

2026-10-20用户新规则：发布新任务不指定负责人，由DeepSeek、Claude、Cursor自主领取执行。覆盖ALLOCATION旧的定向派单与Claude不新增等历史偏好。本项不指定owner，任一上述客户端领取后完成共用MCP适配，不重复开发三个服务。

只读基线：工作区D:/projects/projects3/2026/dongos；coordination/dongos_coordination/mcp_server.py、mcp_config.py、client.py、store.py；coordination/tests/test_mcp.py、test_mcp_config.py；coordination/dongos_coordination/docs/MCP.md及coordination/README.md。store已支持公共pool编号、assignment_owner、领取和claim_token，MCP已有本人+unassigned初步查询；先识别缺口再改，禁止重复建设。

授权与交付：项目source_root为code/，协调源码在coordination/，不能混淆。所有改动只写声明的pool-works候选文件及自动交付报告；pool-works映射coordination/dongos_works/pool-works。mcp-pool内候选文件按相对路径一一对应coordination/正式文件。记录原文件SHA256、精确映射和差异；从最新正式源码只读创建临时完整测试副本并覆盖候选代码，测试临时HTTP/数据库，不能操作生产任务。两项pool-works/tests测试应自带临时夹具和导入路径，可被声明discover直接执行，不依赖未交付的手工副本。禁止修改正式协调源码、真实客户端配置、SQLite/index.json及其它任务文件，不用../绕过范围。基线变化须重新合并报告。候选提交后由Codex独立复验并真实集成。

功能：
1. initialize instructions、get_workflow、tools/list及文档统一说明默认公共池发布，三个客户端自主领取；启动owner继续绑定真实领取身份。worker不可覆盖owner/agent_id，不增加发布/验收/集成管理权限。
2. worker默认可查公共待领取与本人任务；owner=unassigned只查公共池。状态/关键词/分页/总数正确、无重复漏项；列出不等于领取。说明依赖、文件冲突处理。
3. coordinator create_task省略owner创建owner为空的pool任务；完整pool编号有效。保留旧显式负责人任务兼容，但新任务默认不指定。领取后任务ID和pool授权路径不变。
4. DeepSeek/Claude/Cursor均先读完整任务书、最新rev、依赖、review_note、write_paths，领取成功才编辑。相同rev并发领取仅一胜者；释放回公共池可供另一成员领取；旧rev、旧agent、旧claim_token及迟到提交不能覆盖新轮次；暂停停止确认与依赖/文件冲突保护保留。409重新查询，不抢占。
5. 核对mcp_config为三客户端输出正确worker身份及共用服务，仅必要时改候选配置生成代码；保留其它服务和配置备份语义。不安装真实配置、不输出凭据、不自动启动模型或轮询派单；文档给统一客户端提示及服务重载说明。
6. 若发现必须修改store/client才能完成，提交具体阻塞证据，由协调者另扩授权；不得越范围修改。

验收必须真实stdio MCP子进程+临时HTTP服务，不仅mock：三客户端分别发现公共任务并claim→submit；协调者省略owner发布；两个worker竞争；释放后换成员领取及旧令牌/版本拒绝；依赖与文件冲突；筛选分页；角色隔离/身份不可覆盖；旧定向任务兼容；配置生成与其它配置保留。声明定向测试真实通过且零skip，报告实际命令、数量、失败/skip、SHA和候选映射，未运行如实说明。不启动AI CLI、不提交推送、不运行OS/VM；submitted不是accepted/integrated，执行者不能自行验收。

## 可修改文件

- `pool-works/mcp-pool/dongos_coordination/mcp_server.py`
- `pool-works/mcp-pool/dongos_coordination/mcp_config.py`
- `pool-works/tests/test_mcp_pool.py`
- `pool-works/tests/test_mcp_pool_config.py`
- `pool-works/mcp-pool/dongos_coordination/docs/MCP.md`
- `pool-works/mcp-pool/README.md`
- `pool-works/deliveries/MCPPOOL1.md`

## 定向验收

- `discover:pool-works/tests:test_mcp_pool.py`
- `discover:pool-works/tests:test_mcp_pool_config.py`

交付：`pool-works/deliveries/MCPPOOL1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
