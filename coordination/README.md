# 本地协作控制台

本轮17份缺失任务书、CX6同号异义和CX14/CX15旧状态均已处理完成。CX14 integrated rev7，CX15 integrated rev8；CX6 integrated rev9，已恢复读取器契约，分离5条原NASM事件，耗时恢复为1轮/265秒，原始事件全部保留。协调器issues=0；核对时间2026-10-22T09:18:41+08:00。

完整依据见[恢复报告](dongos_works/reviews/2026-10-22-task-recovery/README.md)与[整体任务图](dongos_works/progress-map.md)。同号事件分离使用下述证据绑定resolve-identity命令，不删除原事件或直接授予验收。

以下保留原有记录；其中日期、任务数量、机器路径和“当前/下一步”均属于各自历史检查点，最新状态以上述记录及协调器为准。

工作区根下 `code/` 保留原 DongOS 项目（包括构建产物）；`coordination/` 是独立的 Web、状态库及调度项目。Python 3.12+，标准库实现，不需要安装 npm/pip 依赖。原编译/测试命令在 `code/` 中执行。

在工作区根运行：

```powershell
python coordination/coordinate.py serve
# 另一终端中停止本服务
python coordination/coordinate.py stop
```

浏览器打开 http://127.0.0.1:8765。`start.ps1` 也可启动前台服务。端口可用 `serve --port 8766` 修改。

## 跨开发机的任务状态（state/）

任务库的权威运行数据仍是本机的 `dongos_works/.local/tasks.sqlite3`（**不进 git**，同目录下的日志、锁、作业工作副本也一样）。
为了让任何开发机在更新代码、启动协调服务后都得到同一份最新任务清单，服务把任务状态以文本形式保存在仓库内的
`dongos_works/state/`（**进 git**），并在启动时合并、每次状态变化后自动写回：

- `state/tasks/<负责人>/<编号>.json`：一个任务一个文件，键按字典序、缩进 2 空格、LF 换行。只改动的任务才会重写，不同任务的改动互不冲突。
- `state/events/<负责人>/<编号>.jsonl`：该任务的事件，一行一个 JSON，只追加；`state/.gitattributes` 让 git 用 union 合并，两台机器各自追加的行都会保留。任务时间线按事件时间排序，所以合并后顺序仍正确。
- 作业记录、全局自动化开关、日志、端口/锁和运行副本留在本机，不同步。

**启动合并规则**：快照里有而本机没有的任务直接加入；两边都有时 `rev` 大的一方获胜（`rev` 相同但内容不同，取 `updated_at` 较晚的并在同步报告里列为 diverged）；
合并绝不降低任何任务的 `rev`，也不删除任务。新克隆的仓库（没有 `.local`）启动时直接从 `state/` 重建任务库，不会再从任务书重新猜测状态。
服务运行期间用 `git pull` 带来的新文件会在下一次页面轮询时被加载，写回时也不会覆盖比本机更新的文件。

上述自动合并只适用于同一编号确实代表同一任务的情况。2026-10-20 PR#8本地同步发现CX6/CR43同号异义：同步前停止服务并完整备份，在恢复本机state、任务书及交付后隔离异机新增记录，模拟启动确认零新增、零改写，再启动服务。异机原记录仍由固定Git与备份保留；不得靠手工加rev或事件union协调不同契约，后续登记通过协调器逐项审查处理。见[本次同步报告](dongos_works/reviews/2026-10-20-pr8-merged-local-sync.md)。

典型流程（任何一台机器）：

```powershell
git pull
python coordination/coordinate.py serve        # 启动即合并 state/，之后每次状态变化自动写回 state/
# 需要提交任务状态时：
git add coordination/dongos_works/state
git commit -m "tasks: sync state"
```

- 手动同步并查看结果：`python coordination/coordinate.py state-sync`（先合并再写回，输出新增/更新/写出的文件和问题）。
- 同一任务在两台机器上各自改动，`git merge` 产生冲突标记时：保留 `rev` 更大的一方（或手工合并后把 `rev` 加 1）。带冲突标记或内容无效的文件会被**跳过且不被覆盖**，
  服务照常启动，`validate`/`status` 的 issues 里会列出该文件，修好后下一次同步自动恢复。事件日志（union 合并）不会产生冲突。
- `candidate`（隔离副本的作业编号）和作业记录只在产生它们的机器上有意义；其它机器看到该任务仍是正确的状态，但不能在本机复验那个候选副本。
- `dongos_works/index.json` 现在只是派生的汇总导出（每次状态变化仍会重写，带 `generated_at`）。它不是权威，也不参与合并；合并冲突时任选一方即可，下次导出会重写。
  只有旧版仅含 `index.json` 而没有 `state/` 的仓库，空库启动仍会要求按原流程 `recover-state`，不会静默重新导入。

## 同号异义历史的身份校正

原任务书、交付及两支原事件先按固定 Git 来源分别保全；不能按较高 rev 或事件 union 把两个契约混为一个任务。协调者可使用证据绑定的命令：

```powershell
python coordinate.py --project <项目编号> resolve-identity <任务编号> --rev <最新rev> --manifest reviews/<清单>.json --sha256 <清单SHA256> --note "原文核对结论"
```

清单需要 version=1、显式项目/任务/rev、当前契约摘要、规范任务书 SHA、至少两项原文 SHA 证据及准确的异义事件 SHA。该操作按 CAS 校验并追加审查记录，保留数据库全部原始事件及原验收；只将已确认属于另一身份的事件从本任务时间线和耗时中分开。`get_task.timing.identity_resolution` 保留分离的原事件和清单入口，状态快照携带同样的身份依据，不授予新验收或集成。服务代码升级后需在无活动作业时重启以更新 HTTP/MCP 派生统计。

## AI任务接口

把 `http://127.0.0.1:8765/api/ai` 交给AI即可发现如何发布、查看、领取、释放任务及提交交付。

- [AI调用指南](dongos_coordination/docs/AI_API.md)；在线地址 `/api/ai/guide`。
- OpenAPI 3.1：`/api/ai/openapi.json`。
- Python标准库客户端：`from dongos_coordination.client import CoordinationClient`。
- 使用显式项目URL、最新rev和领取者agent_id；写操作保留本机Origin/CSRF校验。SDK会处理令牌轮换，409需重新查询。
- 发布任务只进入todo，提交交付只进入submitted，均不会自动调用模型或自行验收。外部AI可直接使用这个接口，不依赖Cursor等工具的CLI登录。

```powershell
python coordination/coordinate.py sync      # 导入任务书和新交付
python coordination/coordinate.py validate  # 状态、依赖、文件归属校验
python coordination/coordinate.py --project dongos timing claude:C43  # 完整时间线和每轮耗时；只读，升级后无需等待服务重启
python coordination/coordinate.py doctor    # 检测可执行文件/API，不执行任务
python coordination/coordinate.py probe codex
python coordination/coordinate.py probe claude
python coordination/coordinate.py probe lmstudio
python -m unittest discover -s coordination/tests -v
node --test coordination/tests/client_api.test.js
```

Web 支持分配任务、手动领取、隔离副本执行、提交、独立定向测试、只读审查、返修、验收、集成登记及持续日志。状态每2秒更新。全局自动化默认关闭；开启后仍须逐项启用自动派单/复验，返修不会无限重试。取消的旧定时任务不会恢复。

任务页提供实时进度图：七种状态分列显示任务卡，按当前负责人、搜索词和状态筛选统计；分别显示已验收（含集成）及已集成数量。卡片标注等待的依赖和实际运行/排队的作业，点击可查看任务详情，再跳转前置任务。状态色条表示任务数量占比，不推测源码完成百分比；暂停、返修和待复验均不计入已验收。每2秒随当前项目快照更新，切换项目清除旧图；原任务表继续保留。

任务详情的“时间记录”显示发布、首次领取、每次提交完成、复验、要求返修、任务书修改及状态更新时间，并提供完整操作时间线（北京时间）。每轮实现/返修分别记录领取至提交的自然经过时长、明确暂停时长及等待领取时长；办理时长扣除明确暂停，不计提交后等待复验时间，不代表实际编辑代码或模型运行的净耗时。释放/中断结束的轮次单独标记为未提交，重新领取另记一轮。复验显示排队/开始/结束、执行时长和定向测试耗时合计；新增开始事件只对升级后启动的复验有效。历史事件缺失则显示未知，不使用导入时间冒充发布时间。HTTP任务详情及MCP get_task提供同样的timing字段；时间统计只读派生，不修改任务版本或验收证据。服务代码升级需重启协调器后生效。

页面顶部另提供“整体任务图”，展示系统 P0–P9 和语言 L0–L3 的阶段关系。点击阶段可查看已完成项、尚待完成项及证据位置；阶段结论明确标注核对日期，协作任务统计随实时快照更新，不受任务筛选影响。图源保存在各项目任务目录的 `roadmap.json`，可读的 Mermaid 版本为 `progress-map.md`；DongOS 版本见 [整体任务图](dongos_works/progress-map.md)。页面可直接下载 Markdown。切换项目时读取对应项目的图；未配置或配置错误不会阻断任务列表。阶段状态由核对证据后维护，不按组件数量自动推断整机完成。

`<项目编号>_works/.local/tasks.sqlite3` 是状态唯一写入源，`index.json` 是派生快照。每个任务具有版本号；并发旧操作会被拒绝。源码路径相对于项目源码根，`*-works/...` 映射到当前 `<项目编号>_works/`；Claude/Cursor/DeepSeek 原任务书、交付、审查完整保留。`accepted`（独立组件验收）与 `integrated`（源码已核对集成）分别记录。历史已验收任务不代表已完成整个 L3 自举。

CLI 交付保留在 `<项目编号>_works/.local/runs/<job>/workspace/`，不会自动覆盖原源码。模型退出成功、测试通过都不自动验收；必须有新鲜测试指纹和人工源码/契约审查记录。集成登记会核对原目录文件与验收指纹。不要手改索引冒充状态更新。备份时先停止服务，再保存整个 `<项目编号>_works/`（包含候选交付及日志）；仅导出索引不足以恢复候选文件。

当前适配 Codex、Claude 非交互 CLI；Cursor 编辑器与 Agent CLI 分开检测。Windows原生Cursor CLI的启动器可能不在PATH：协调器会检测 `%LOCALAPPDATA%/cursor-agent/versions/<版本>/node.exe` 与 `index.js`，直接用参数列表运行，不调用批处理或PowerShell启动器。Cursor当前仅接入只读ask审查，自动写入仍需单独验证。CLI存在、账号已授权、模型连接通过分别记录；编辑器已登录但CLI未授权时，仍可先手动领取/交付。

Cursor CLI可使用客户端的**同一个账号**，官方支持浏览器授权和API Key；当前CLI不会从客户端自动取得有效授权，需按 [官方认证说明](https://cursor.com/docs/cli/reference/authentication) 完成一次CLI授权，无需注册新账号或创建新Key。本次遵循用户要求不切换Cursor客户端账号、不复制客户端凭据。Claude已按用户选择切换官方订阅账号，2.1.302已完成固定短提示连接复验；旧网关配置备份仅保存在用户主目录，不存入项目。

路径可在 `config.json` 的 `providers.codex/claude/cursor` 中指定原生可执行文件。连接探针只发送固定短提示，不读凭据文件、不降低 CLI 权限、不指定额外模型。

## 独立运行与多项目

页面顶部支持新增/切换项目：填写名称、唯一编号和现有源码绝对路径。不会搬动新项目源码。当前项目的任务书、任务测试、各助手目录、交付、审查、索引、状态库、执行副本及日志全部放在一个 `<项目编号>_works/` 目录。同一任务编号可在不同项目复用。

```text
coordination/
  coordinate.py、dongos_coordination/、tests/   控制台自身源码/测试
  config.json                                 执行接口配置
  dongos_works/                                DongOS的全部调度文件
    project.json、index.json
    claude-works/、cursor-works/、deepseek-works/、gemini-works/、lmstudio-works/
    .local/                                   本项目状态库/执行副本/复验记录/日志
  my-app_works/                               新项目独立存放同样内容
  .local/                                    控制台服务运行信息
```

可以把协调项目单独复制运行，无须导入DongOS代码；源码位置配置在各项目 `project.json` 的 `source_root`。相对路径以该 `<项目编号>_works/` 为基准，DongOS默认 `../../code`。

在协调项目目录运行：

```powershell
python coordinate.py serve
python coordinate.py add-project my-app --name "My App" --source "D:\projects\my-app"
python coordinate.py --project my-app status
python coordinate.py --project my-app validate
# 空数据目录也可先启动Web，再新增项目
python coordinate.py --home "D:\coordination-data" serve --port 8766
```

控制台仅管理自己服务，取消的旧自动化保持取消。每个项目的自动化开关及运行记录分别保存。

## 状态库备份与恢复

`*_works/.local/` 不纳入 Git：克隆仓库不会取得 SQLite、作业日志或候选副本。任务书中的“待领取”常是发布时历史，不能据此恢复验收、集成、返修和归档事实。现在状态库缺失/为空而已有非空快照时会停止启动，保留快照，不再重导入覆盖。

启动服务、项目首次加载和手动同步前自动生成 `.local/backups/<时间-编号>/` SQLite 备份（含 events/jobs/settings）。也可执行 `python coordinate.py --project dongos backup`。备份仍在 Git 忽略目录内；迁移机器时须停止服务并保存整个 works（包括 `.local`），或另存到独立备份位置，不能用 Git 代替数据备份。

有完整SQLite备份时优先核对原库。仅剩派生快照时，人工核对逐项历史审查、验收指纹及集成实物，制作绑定快照SHA256的逐项审计JSON，再运行：

```powershell
python coordinate.py --project dongos recover-state --snapshot <原快照.json> --audit <逐项审计.json>
# 先核对预览，再使用同一组文件应用
python coordinate.py --project dongos recover-state --snapshot <原快照.json> --audit <逐项审计.json> --apply
```

恢复仅允许空库或只有导入事件且无作业的重建库；拒绝覆盖真实领取/提交等操作。应用前备份，事务内复查实物和版本，原子恢复、增加rev、记录来源、关闭自动化；不重新授予验收或伪造丢失作业。DongOS本次的逐项依据见[恢复审计](dongos_works/reviews/2026-10-19-state-recovery.md)。

本地库已有较早的真实历史、而 Git 保留了更新的完整快照时，使用 `reconcile-state` 协调历史事实，不能用重导入任务书替代。该命令要求显式项目、快照SHA256、逐项审查文件及当前全部任务的rev和原始data SHA256；拒绝覆盖快照之后的真实操作或活动作业，保留现有events/jobs。先运行预览，核对后以相同参数加 `--apply`：

```powershell
python coordinate.py --project dongos reconcile-state --snapshot <原快照.json> --audit <逐项审计.json>
```

协调前完整备份，事务内再次核对版本、历史边界及文件证据，然后增加rev、记录来源并关闭自动化。行尾差异须显式审计；已被后继任务改写的历史文件，须绑定同一快照中较晚、已集成且独立复验通过的后继指纹。此操作不重新执行或授予验收，也不补造缺失作业。2026-10-19本次依据见[状态同步审计](dongos_works/reviews/2026-10-19-status-sync-audit.json)。

## LM Studio：只接简单任务

使用本机 OpenAI 兼容 API，配置在 `config.json` 的 `providers.lmstudio`。默认 `http://127.0.0.1:1234/v1`、已加载的 `qwen/qwen3.8-27b`。不会下载、切换或卸载模型。后续可以手动换成适合小任务的模型，再重新检测。

- 只分配单个纯函数、小文档或少量文本 fixture；复杂需求由 Codex 拆分后再发布。不分配编译器/内核、跨模块重构、并发/内存管理或最终审查。
- 写入限 `<项目编号>_works/lmstudio-works/{src,docs,fixtures,deliveries}/` 中最多3个**明确文本文件（含交付）**，无通配符；说明最多3000字符、上下文最多16KiB、输出最多24KiB。
- 模型只接收任务和指定文件正文，不具备 shell、文件读取工具或自由遍历源码的能力。结构化响应经路径/数量/大小检查后写入独立副本。
- 测试由 Codex 编写，模型不能改测试。独立测试不通过则返修，通过后仍需 Codex 审查，不允许自己验收。

当前默认使用 [LM Studio 原生 Chat 接口](https://lmstudio.ai/docs/developer/rest/chat)，明确 `reasoning: off`、`integrations: []`、`store: false`；仅收集文本JSON并在写入前执行结构/路径/数量/大小检查。首次兼容接口生成曾超时，改用原生接口后连接及LM1真实交付均通过；不会以原失败作业冒充成功。控制台限制接口为 loopback，忽略系统代理并拒绝重定向。支持关闭推理的已加载模型才可使用当前适配方式。

Python子进程和CLI入口统一UTF-8，执行日志使用增量解码；中文/emoji跨读取块及日志尾部截断均有回归覆盖。服务重启后旧页面的首次403会自动刷新同源令牌并最多重试一次，CAS冲突和持续拒绝不会无限重放。

## 执行边界

Web 仅监听127.0.0.1；写操作需要同源令牌和任务版本。页面不能输入任意 shell 命令，只能选择受限 unittest 定向测试。API不提供任意文件浏览。CLI执行无 shell 插值、有限超时、可取消，重启后运行中作业标记中断而非盲目重放。

独立副本用于防止覆盖原项目，**不是操作系统安全沙箱**。测试仍以本机用户身份运行，只对可信、已审查的项目使用；不让模型运行 OS/VM、提交或推送。系统/虚拟机重型验收仍由原专用流程管理。历史回执内旧绝对路径保留用于溯源；后续构建从 `code/` 重新生成配置。
## 客户端 MCP 接入

Claude Code/VS Code、Cursor、LM Studio 和 DeepSeek Harness 可通过本地 stdio MCP 直接查看、领取和提交任务；Codex配置协调角色，可统一发布、查询、返修、复验和登记验收/集成。复用现有状态/文件指纹校验，不调用AI CLI；Cursor保持手动执行。安装和角色约定见 [MCP 使用文档](dongos_coordination/docs/MCP.md)。

```powershell
python coordination/coordinate.py mcp-config --client claude --install
python coordination/coordinate.py mcp-config --client cursor --install
python coordination/coordinate.py mcp-config --client lmstudio --install
python coordination/coordinate.py mcp-config --client deepseek --install
python coordination/coordinate.py mcp-config --client codex --install
```

先启动协调网页服务；在 coordination 目录运行时省略命令中的 `coordination/`。安装保留已有客户端配置和备份，不唤起模型或更改自动化开关。


## 任务清单、公共领取与转派

工作区默认使用精简清单，显示任务名称/编号、状态、成员和本轮经过时间；支持成员、状态、关键词、待领取/进行中/待复验快捷筛选及分页。看板、整体任务图、执行环境、动态、导出、队列和完整详情仍可展开使用。详情直接显示本轮领取、执行完成（提交）和经过时长，完整历史和每轮办理/暂停时长保留。

发布时负责人可选；未指定任务使用pool编号和pool-works范围，不因领取/转派更名或改变授权文件。符合范围的成员竞争领取，事务与版本校验保证单个胜者。任务亦可明确指派；运行中的任务先请求暂停，确认原执行者停止后才允许转派。外部客户端无进程控制能力，必须原领取者确认，或操作者实际停止后明确确认；协调器CLI采用停止后重新执行，不提供操作系统级挂起恢复。旧领取令牌、过期版本及迟到结果不能覆盖新领取轮次。

升级后需重启服务并刷新MCP客户端；未自动修改生产任务或替用户重启进程。全套隔离测试：`python -m unittest discover -s coordination/tests -v`、`node --test coordination/tests/*.test.js`。可选浏览器测试：`python coordination/tests/console_browser_smoke.py <截图输出目录>`（需Playwright及Chromium，仅创建临时测试项目；`--serve`提供临时预览）。浏览器环境不可启动时不能将静态检查当作实际视觉验收。

进程停止保证限于协调器管理的进程组，不是任意脱离进程组的后台程序的安全沙箱。Windows普通进程退出无法证明全部子进程已停止时，结果保持待确认，须人工核对并确认；不会据此解锁转派。恢复为待返修后需要重新执行。
