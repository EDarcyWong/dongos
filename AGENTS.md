# 工作区协作

- 本工作区分为 `code/`（DongOS）和 `coordination/`（本地协作控制台）。根据任务进入对应目录；原来以项目根为基准的编译/测试命令现在在 `code/` 内运行。
- 优先通过 `coordination-tasks` MCP 查询项目、任务、最新 rev 和原任务书；工具暂不可用时使用 coordination HTTP API/协调CLI，`coordination/dongos_works/index.json` 仅作只读派生索引。源码路径相对于 `code/`，`*-works/` 映射到 `coordination/dongos_works/`；状态由协调器统一写入，不手改数据库/index.json。
- Codex 的 MCP 配置使用 `--owner codex --role coordinator`，默认查看所选项目的全部负责人，可发布任务、记录返修、暂停/恢复、排队定向复验、读取日志和登记验收/集成。变更必须显式项目及最新 rev；验收前实际审查源码/契约/测试并通过独立复验，集成前完成真实文件集成。其它客户端使用 worker 角色；Cursor保持手动执行，不通过管理工具自动启动AI CLI。
- 各任务只修改声明的文件。其它实现由原负责人返修；审查者写审查结果，独立验收后由Codex集成。`accepted` 与 `integrated` 分开。
- CLI派单在协调器生成的独立副本中执行；不访问原目录，不自行提交、推送、运行OS/VM或标记验收。不要修改协调器数据库/索引来跳过复验。
- 用户明确授权的范围优先于上述日常分工。当前用户要求的目录迁移与协同控制台开发属于工作区级维护，不受旧的组件文件归属限制。
- DongOS 最新派单偏好见 `coordination/dongos_works/ALLOCATION.md`：新增开发主要给 Cursor（客户端手动执行），DeepSeek 少量且先完成在途任务，LM Studio 同时最多一项最简单任务；Claude 额度不足期间不新增任务。不要为凑数量重复已验收组件或抢占已领取任务。
