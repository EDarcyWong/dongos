# DongOS 工作区

原 DongOS 项目与本地协作控制台已分开：

```text
dongos/
├─ code/                 DongOS 源码、语言、工具、项目测试与原构建产物
│  ├─ lang/ kernel/ services/ tools/ tests/
│  └─ README.md PLAN.md
├─ coordination/         独立的本地 Web 与协同项目
│  ├─ dongos_coordination/  后端、队列、CLI 适配与 Web 静态文件
│  ├─ tests/               控制台定向测试
│  ├─ dongos_works/        DongOS任务书、任务测试、交付、审查、索引、运行记录
│  │  ├─ claude-works/ cursor-works/ deepseek-works/ gemini-works/ lmstudio-works/
│  │  ├─ project.json index.json
│  │  └─ .local/           本项目状态库、执行副本、日志（Git忽略）
│  ├─ <项目编号>_works/     新项目的全部调度相关文件
│  └─ .local/              服务自身运行信息
├─ .github/              工作区 CI，DongOS命令在code中执行
└─ dongos.code-workspace  VS Code 双项目工作区
```

启动本地控制台（Python 3.12+，无需安装依赖）：

```powershell
python coordination/coordinate.py serve
```

打开 <http://127.0.0.1:8765>。功能与CLI说明见 [协同项目](coordination/README.md)。

DongOS 编译与测试在 `code/` 内运行：

```powershell
cd code
python tools/build.py doctor
```

原项目说明见 [code/README.md](code/README.md)，计划见 [code/PLAN.md](code/PLAN.md)。迁移保留原源码、构建产物和历史交付；历史回执里的绝对路径保留原样，不以重写路径破坏其hash。
