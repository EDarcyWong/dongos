# DeepSeek Harness MCP 配置与派单

已核对安装包内@deepseek-ai/dsh-mcp-client 0.2.1-rc.2的stdio配置，使用现有协调器安装入口，将插件insert条目写入用户desktop Cordis patch。服务为coordination-tasks，实际Python绝对路径及coordinate.py绝对路径，参数mcp --owner deepseek --url http://127.0.0.1:8765；默认worker，无管理权限。

配置：C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml。写入前原件备份，同目录coordination-backup-20261019T071949Z-f107b8；已比对托管块之外全文与原件一致，不改变账号/模型。无需把其他客户端JSON格式放入Harness。

按安装的同一命令真实启动MCP子进程，initialize/initialized、tools/list、get_workflow、list_tasks(project=dongos,status=todo)全部通过。身份deepseek、worker角色，8工具不含管理动作，能读取新D21。完整验证元数据见同名JSON。只启动本地MCP服务测试，未启动AI CLI、未代worker领取或执行任务。尚未宣称桌面进程已热加载，客户端需重载/重启后加载新profile。

D21已通过协调器发布，依赖cursor:CR28和cursor:CR14均integrated，任务为真实复用范围门禁+规范化，强制先判断再截窄，24边界及实际顺序反转坏Dong负控，仅四文件。完整原任务书deepseek-works/tasks/D21-board.md；发布回执2026-10-19-DeepSeek-D21-allocation.json。已验收/集成的D1～D20没有重置。
