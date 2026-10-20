# 客户端 MCP 任务协作

Coordination 的本地 stdio MCP 桥让 Claude Code（含 VS Code 扩展）、Cursor Agent、LM Studio 聊天和 DeepSeek Harness 直接查看、领取和提交任务；Codex 另有协调角色，统一查看和管理所有负责人的任务。客户端启动的是 Python 协议桥，**不调用任何 AI CLI**。桥通过既有 HTTP API 操作任务，不直接写 SQLite/index.json。

## 启动和安装

先启动协调网页服务，默认 `http://127.0.0.1:8765`：

```powershell
python coordination/coordinate.py serve
```

从工作区根目录安装客户端配置（保留其它条目，修改前在原配置同目录备份）：

```powershell
python coordination/coordinate.py mcp-config --client claude --install
python coordination/coordinate.py mcp-config --client cursor --install
python coordination/coordinate.py mcp-config --client lmstudio --install
python coordination/coordinate.py mcp-config --client deepseek --install
python coordination/coordinate.py mcp-config --client codex --install
```

省略 `--install` 只输出配置；自定义端口用 `--url http://127.0.0.1:端口`。可用 `--target 路径 --install` 合并到其它支持相同结构的配置文件。不打印原配置或凭据，不覆盖同名的其它服务，重复安装无变化。目录迁移或 Python 更换后重新生成配置。

| 客户端 | 默认用户配置 | 使用方式 |
| --- | --- | --- |
| Claude Code / VS Code 扩展 | `~/.claude.json` 顶层 `mcpServers` | 新会话或重新连接 MCP 后使用 `coordination-tasks` |
| Cursor | `~/.cursor/mcp.json` | 在 Tools & MCP 中启用，然后由用户手动在 Agent 对话发起 |
| LM Studio | `~/.lmstudio/mcp.json` | Program / Integrations 中确认服务已启用，在支持工具调用的模型聊天中使用 |
| DeepSeek Harness | `$DSH_HOME/profiles/desktop/cordis.patch.yml`，默认 `~/.dsh/profiles/desktop/cordis.patch.yml` | 使用原生 `@deepseek-ai/dsh-mcp-client` 插件；桌面 profile 支持热重载，工具按服务器 namespace 出现 |
| Codex | `$CODEX_HOME/config.toml`，默认 `~/.codex/config.toml` | `mcp_servers.coordination-tasks`，启动参数 `--owner codex --role coordinator`；刷新MCP/新会话后使用13个协调工具 |

已经打开的客户端可能需要刷新 MCP 或新建会话；不会强制重启、发送聊天消息或更改工具自动批准策略。Claude Desktop 的聊天配置与 Claude Code 不同，如需该应用可用 `--client claude --target <claude_desktop_config.json> --install`；当前默认安装针对本机已有的 Claude Code/VS Code 扩展。

每个配置使用当前 Python 和 `coordinate.py` 的绝对路径，因此不依赖客户端的工作目录、PATH 或当前网页项目。协调项目本身仅依赖 Python 标准库，可单独复制运行，不依赖 DongOS 源码。注册新项目后通过 `list_projects` 查询，不需要给每个项目新增 MCP 服务器。

### Codex 的协调角色

按[官方 OpenAI MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)使用 `config.toml` 的 `[mcp_servers.<name>]`。`mcp-config --client codex` 输出可直接使用的 TOML；`--install` 只合并本服务的托管块并保存原文件备份，保留模型/账号设置、其它 MCP、已有工具过滤及批准策略。不会开启自动批准或启动模型轮次。

Codex 默认安装 `coordinator` 角色：下方8个执行工具加5个管理工具，共13个。`list_tasks` 不带owner时查看明确项目的全部负责人；领取/提交仍只针对Codex自己的工作。其它客户端提供9个 worker 工具（含停止确认），工具参数不能将自身提升为协调角色；`--role coordinator` 只接受 `--owner codex`。如只想用Codex作为执行者，可显式启动 `mcp --owner codex --role worker`。

| 协调工具 | 参数 | 行为 |
| --- | --- | --- |
| `create_task` | `project,id,title,write_paths`；可选 `owner,description,checks,depends_on` | 创建todo任务，保留路径、依赖及LM Studio简单任务约束，不调用执行器 |
| `change_task` | `project,task_id,rev,action,note` | action为rework/pause/resume/accept/integrate/archive/unarchive/reassign；转派须额外指定new_owner（unassigned表示公共领取）；登记明确返修、归档或真实审查/集成依据 |
| `queue_verification` | `project,task_id,rev` | 只排队已声明的定向测试，返回作业，不把排队成功当测试通过 |
| `list_jobs` | `project`；可选 `task_id` | 最近最多120个作业摘要；完整复验结论在get_task.verification |
| `read_job_log` | `project,job_id` | 读取该项目已登记作业的日志尾部，不执行日志文本 |

管理工具使用既有网页管理API，并始终设置明确的 `X-Coordination-Project`；403刷新令牌重试时也保留项目，不采用网页默认项目。普通领取/交付仍使用URL明确项目的v1任务接口。没有直接改库、绕过rev、自动派发AI CLI、取消作业或修改全局自动化的工具；Cursor继续手动执行。

`archive`仅适用于paused/accepted/integrated且没有活动作业的任务，需要说明及最新rev。归档保留原状态、源码、任务书、交付和事件，通过archived字段从网页、API和MCP默认任务列表隐藏，不冒充验收。已知完整task_id仍可get_task/read_document；导出中保留archived_tasks。归档任务不可继续领取、修改状态或排队，协调角色可用unarchive恢复到原状态（仍需说明和最新rev）；保留的任务书不会被扫描重新激活。

验收要求实际完成源码、契约及测试有效性审查；MCP还检查独立复验passed、source_stable、每项tests>0且零skip，Store继续检查当前状态和文件指纹。集成先做真实文件操作，再登记integrate，仍需主目录指纹与验收实物相同。不能用交付报告、空测试、跳过测试或过期指纹替代验收。角色是本机可信配置与工具集合边界，owner/agent_id不是独立安全身份，不将此服务暴露为远程多用户管理接口。

本机验证通过Codex app-server真实MCP发现全部13个工具，无模型调用或新建会话；隔离项目测试完成发布→领取/交付→真实独立测试→源码变化拒绝→验收/集成，并检查项目隔离及普通执行者不可调用管理工具。现有桌面进程的控制socket无法连接，未强制重启；若当前会话未出现新工具，请刷新MCP或使用新会话。证据：`coordination/.local/codex-mcp-audit/appserver-smoke-result.json`。

### DeepSeek Harness 的原生配置

已按本机 `0.2.1-rc.2` 所附 `dsh-mcp-client`、`dsh-app-boot` 和 `dsh-config-editor` 文档及实现核对：它不读取其它客户端的 `mcpServers` JSON。安装器在桌面 profile patch 中加入一个 `insert`，插入 `id=coordination-tasks` 的 MCP 插件，`serverName=coordination-tasks`、`transport=stdio`，启动参数绑定 `--owner deepseek`。不能把新插件写成只有 id 的覆盖项，否则会因找不到原条目而跳过。

仅更新带 BEGIN/END 标记的协调器托管块，原 YAML 注释、其它条目与 `!!js` 表达式保留。JSON flow mapping 本身是合法 YAML，不需要给协调器安装 YAML 依赖。写入时遵守 Harness 的 `package.json.lock` 协作锁并保留原配置备份；遇到配置并发修改或同名非托管服务时拒绝覆盖。可用 `--target` 选择其它 profile 的 `cordis.patch.yml`，不改根 `cordis.yml`、bundle 列表、登录凭据或现有模型配置。

2026-10-18 本机接入验证：桌面 Harness 热重载后启动了专属 Python MCP 子进程；再用该应用自带的 `@modelcontextprotocol/client 2.2.0` 验证真实连接，发现8个工具，成功查询 DongOS 项目及DeepSeek任务。验证不调用模型、不变更生产任务；证据为 `coordination/.local/deepseek-harness-audit/sdk-smoke-result.json`。客户端若未展示新工具，刷新/新建会话后查询 `coordination-tasks`。执行与其它客户端相同的领取/交付约定，提交仍需独立复验。

## 工具

| 工具 | 参数 | 行为 |
| --- | --- | --- |
| `get_workflow` | 无 | 当前绑定 owner、role、会话 agent_id、地址及执行约定 |
| `list_projects` | 无 | 项目编号及源码/任务目录 |
| `list_tasks` | `project`；可选 `owner,status,q,offset,limit` | worker默认当前负责人及公共待领取任务，Codex协调角色默认全部负责人；limit默认25，最大100 |
| `get_task` | `project,task_id` | 完整任务、最新 rev、依赖、write_paths、review_note、candidate |
| `read_document` | `project,task_id`；可选 `kind=task/delivery` | 任务书或交付、SHA256、truncated 标识 |
| `claim_task` | `project,task_id,rev` | 领取当前负责人或公共任务，受依赖、活动作业、路径冲突和版本检查约束 |
| `release_task` | `project,task_id,rev` | 释放本会话领取的任务，保留文件 |
| `acknowledge_pause` | `project,task_id,rev`；重连可传 `claim_token` | 原领取者已确实停止外部工作后确认；不能用于假装进程已停止 |
| `submit_task` | `project,task_id,rev`；可选 `report` | 追加真实交付报告，只进入 submitted，不验收、不集成 |

`task_id` 必须为完整编号，例如 `claude:C19`、`cursor:CR2` 或 `lmstudio:LM6`。owner 由服务启动参数绑定，工具参数不能覆盖 owner/agent_id。worker可只读查询其它负责人，领取可选择公共任务，交付只能是当前领取轮次的任务；worker没有发布、验收、集成等管理工具。Codex协调角色的额外能力见上表；所有角色均无shell或任意文件读写工具。

## 客户端执行提示

在各客户端对话中发送（Cursor 必须由用户手动发起）：

> 使用 coordination-tasks：先查看项目列表，选择 dongos；查询分配给你及公共池的 todo/rework 任务。读取完整任务、任务书和返修要求，确认依赖和文件范围。选择一项，用最新 rev 领取，收到成功响应后才开始。只修改授权文件；测试结果如实记录。完成后重新查询 rev，提交交付并等待独立复验。遇到409重新查询原因，不抢占、不无限重试；没有可执行任务就停止。

示例工具参数：

```json
{"project":"dongos","status":"todo","limit":25}
```

```json
{"project":"dongos","task_id":"cursor:CR2","rev":9}
```

示例中的 rev 仅展示格式，实际必须取最近查询响应。提交时可以增加 `report`，写实际实现、测试命令/数量、证据及限制；未运行测试明确写“未运行”。报告会追加到固定交付路径，原历史保留。省略 report 时该路径必须已有交付文件。

源码相对 `source_root`；`claude-works/...` 等助手路径映射到当前项目 `works_root`。本桥不上传实现文件；客户端需用自身编辑工具把授权实现落盘。`candidate` 非空表示最新源码还在独立副本，不代表已回写主目录。客户端应先确认原负责人/协调器完成交接；不能拿缺失的主目录文件重写旧候选。已有排队/运行作业不会被 MCP 抢占或重复启动。

LM Studio 继续只接少量简单任务，最多3个明确文本文件（含交付），不改测试/主线。模型需支持工具调用，服务需在客户端启用；没有文件编辑工具时，MCP 的领取/提交工具不会自动补上文件能力。此时应说明阻塞并释放任务，不得把生成在聊天中的文本声称为已写入文件。原本地模型 API 执行方式保留可用，不能与客户端重复领取同一任务。

## 会话、错误与边界

- 每个 MCP 进程默认生成独立 agent_id，避免多个会话互相提交任务。重连后先 get_workflow 核对标识；只有原领取者能释放/提交。关闭前释放未完成任务；意外中断由操作者确认后在网页退回待领取，再由新会话领取。操作员也可显式 `mcp --agent-id <稳定实例名>`，但不同并发实例不要共用该标识。
- 409 表示版本、领取、依赖或活动作业冲突；工具返回 isError 与状态码，不自动重试。403 令牌过期沿用客户端自动刷新一次；其它网络错误提示检查服务。不会把错误转换为成功或绕过校验。
- stdio 按 UTF-8 单行 JSON-RPC 传输；stdout 只有协议消息。支持 MCP 2025-06-18、2025-03-26、2024-11-05 的工具子集；未知版本协商回2025-06-18。未声明资源/提示模板/推送能力。单条输入上限1MiB，未知参数及无 id 的工具通知不会触发写入。
- 本接口面向同机可信客户端。owner/agent_id 是协作归属标签，不是多用户安全身份；不是远程公网服务。桥只连接 loopback HTTP，忽略系统代理、拒绝重定向，复用已有同源操作令牌。
- Cursor 保持手动执行。MCP 接入不代表网页派单后可自动向客户端聊天发消息，也不更改现有自动化总开关、任务自动派单开关或 CLI 队列。

验证：`python -m unittest discover -s coordination/tests -p test_mcp.py -v`。测试使用临时双项目、真实 HTTP 服务及真实 MCP 子进程，不调用模型；覆盖五负责人、协调生命周期、Unicode、历史追加、领取冲突/活动作业/依赖、版本/项目隔离、令牌刷新、断线、协议错误/超限、配置保留及Harness/Codex配置的锁/幂等/批准策略保留。

官方参考：[MCP stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)、[MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)、[Claude Code MCP](https://code.claude.com/docs/en/mcp)、[Cursor MCP](https://prod.cursor.com/help/customization/mcp)、[LM Studio MCP](https://lmstudio.ai/docs/app/mcp)。

## 公共领取与安全转派

发布时省略owner即可进入公共池，路径使用pool-works/。MCP默认列表包含公共任务；LM Studio仍受最多3个明确文本文件等限制。任务ID表示稳定身份，转派后不会随负责人改名，实际owner以当前任务字段为准。

领取返回claim_token，本进程自动保存。release_task、submit_task、acknowledge_pause可显式传claim_token以恢复同一领取实例；服务会同时检查owner、agent_id、最新rev与本轮令牌。不要从新轮次获取令牌后提交旧结果。

协调者pause会请求停止：本服务管理的CLI必须等实际进程退出；外部客户端必须先自行停止，再acknowledge_pause。停止等待期间不可转派或继续提交。暂停确认后，协调者使用change_task/action=reassign并明确new_owner和交接note；旧领取立即失效，新成员须重新领取。CLI恢复需要重新执行，没有操作系统级挂起/恢复功能。服务重启后无法确认的旧进程必须人工核对停止，不能自动接续。

当前提供9个worker工具、14个coordinator工具；上述旧接入验证记录保持原始历史，不代表本次客户端刷新或部署已完成。
