# DongOS 源码目录

本目录即原 DongOS 项目根，编译/测试均在这里执行。上级 `coordination/` 为独立协同项目，优先通过 `coordination-tasks` MCP 获取项目/任务最新状态和任务书；工具不可用时使用 coordination HTTP API/协调CLI，`../coordination/dongos_works/index.json` 为只读派生索引。源码路径相对于本目录，`*-works/` 映射到 `../coordination/dongos_works/`。仅修改任务授权的文件，保留交付和审查历史；执行者不自行验收，Codex协调角色依照上级AGENTS的独立复验/集成流程管理。不自行提交或推送。

CLI隔离副本中的当前目录同样是源码根；不要通过旧绝对路径访问原项目。测试命令由协调器运行，不启动 OS/VM。
