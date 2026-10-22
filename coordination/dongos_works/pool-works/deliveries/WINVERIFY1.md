# WINVERIFY1 交付：Windows 定向复验正常退出后可登记完成

领取：2026-10-20，Claude（agent_id=claude-worker-winverify1），pool:WINVERIFY1 rev1→rev2。

## 根因

`Runner.run_process` 在 Windows 上只能确认领导进程退出，`tree_stopped` 依赖 `taskkill` 的结果，正常完成时没有 taskkill，所以 `process_stopped=None`。`Store.finish` 把任何非 True 视为停止未确认，不保存 `task.verification`，作业保持 running（C52 作业 ec1d698d…）。

## 修复（只改 `pool-works/win-verify/dongos_coordination/runner.py`，`store.py` 无需修改，未提供候选）

- 新增 `WindowsJob`：用 ctypes 创建 Windows Job Object，`KILL_ON_JOB_CLOSE`，不设置任何 breakaway 标志。
- 领导进程以 `CREATE_SUSPENDED` 创建，先放入作业再 `NtResumeProcess`，所以所有后代从第一条指令起都是作业成员，且无法脱离作业（测试已用 `CREATE_BREAKAWAY_FROM_JOB` 验证被拒绝）。
- 完成证明：`tree_stopped` 在 Windows 上要求领导进程已退出且作业活动进程数为 0；查询失败（None）不算证明。
- 残留后代：领导进程退出后作业仍非空，按取消处理：`TerminateJobObject` 并等待清空，该次复验不通过，但停止已证明，不进入停止未确认。
- 取消/超时：`terminate` 对作业调用 `TerminateJobObject` 并等待活动数为 0，再记录 `coordination_tree_terminated`；无作业时仍走原 taskkill 路径。
- 无法放入作业时不启动执行（进程仍处于挂起状态即被杀死）。创建作业失败则回退到原行为：完成保持未证明，不弱化暂停/取消保护。
- 作业句柄仅在证明清空后关闭；未证明的进程保留在 `self.processes`，`close()` 仍可终止。
- 服务重启：新服务没有句柄，`store.recover` 仍将作业置为 interrupted 并要求外部确认，行为不变。非 Windows 路径未改动。

## 实际测试

```text
cd coordination/dongos_works
python -m unittest discover -s pool-works/tests -p test_windows_verification_finish.py -v
```

结果：**11 项通过，0 失败，0 skip**（连续两次：45.2 秒、31.8 秒），Windows 11，Python 3.13.7。测试每次把官方 `dongos_coordination` 复制到临时目录并改名为独立包，再覆盖候选文件，因此不触碰正式包、服务和状态库，也不依赖未交付的临时文件。全部使用真实子进程。

覆盖：
- 正常的父子进程退出后 `process_stopped=True`，`finish` 保存 `verification`，作业 completed；
- 领导进程退出后残留的子进程：被终止、证明停止、该次复验不通过，子进程确已消失；
- 作业对残留成员计数，领导进程退出不算证明，终止后计数为 0；
- 子进程无法脱离作业；
- 取消和暂停会等待整个进程树停止，暂停在证明停止之前保持 submitted，之后才变 paused/confirmed；
- 迟到的旧令牌结果不覆盖 `verification`，并记录 stale_result_ignored；
- 服务重启后仍需外部确认；
- 作业创建失败时 `process_stopped=None`，`finish` 要求停止确认，且不保存 verification；
- 仅在 Windows 分支调用 `WindowsJob`，非 Windows 平台导入模块不触及 Win32。

**负控**：把候选 `runner.py` 换回官方原文后同一测试 11 项中 8 项失败（含 `test_normal_parent_and_child_exit_records_verification` 和残留子进程用例），证明测试能复现 C52 阻塞；随后已恢复候选，SHA 前后一致。

另外把候选覆盖到官方副本后，既有 `tests.test_coordination.RunnerTests`（含此前失败的 `test_implementation_real_process_collects_isolated_delivery`）以及 `test_mcp` 中此前失败的两项（deepseek handoff、codex 协调器）均通过；用官方 runner 它们仍失败。这是在临时副本中运行的，未改官方目录。

## SHA256

- 候选 `runner.py`：`40504e6f0ca2beca2d6e1a08b9c91735d978529854c575f3a4590cc325b08abe`
- 测试：`90d953a072d6ed9398b647f423efadf7dd2b5a245a7c0828aad8d929d5cc60dd`
- 基线官方 `runner.py`：`45cf1a2de23f9aeb790da1ca1f9ba0b40f1534a28afc91c3326d0a781ed630cd`；`store.py`：`00c74c157dcf617b7cc48591a7095e9ab65c0b8d67369f209481e83187348200`（未改）

## 限制

- 未改正式服务、状态库、index，未手填 verification，未重启服务；C52 的正式复验需 Codex 集成本修复、重启服务后再排队。
- 作业对象只在本服务存活期间提供证明；重启后仍需外部确认。
- 脱离作业的进程无法产生（breakaway 被拒绝），但不防御另一个会话/用户对本进程树之外的进程操作。
- 只在 Windows 实测；POSIX 路径未改动，仅通过既有测试集在 Windows 上运行，未在 Linux 运行。
- 未提交 git，未自行验收或集成。

## Codex 按用户明确授权接续的集成适配

用户要求直接修复任务内容并完成正式复验/验收。已将候选runner.py真实复制到coordination/dongos_coordination/runner.py（SHA256 40504e6f0ca2beca2d6e1a08b9c91735d978529854c575f3a4590cc325b08abe），正式服务已通过shutdown接口停止后隐藏启动新进程1388。集成前无运行/排队作业；原文件备份coordination/.local/WINVERIFY1-integration/runner-before.py。

测试集成适配：取消“正式源码必须与候选不同”假设，改为精确验证临时副本加载候选文件；沿祖先定位只读正式协调依赖包，以兼容正式隔离副本路径；依赖包所有Python文件前后SHA必须一致。仍在临时包与临时数据库运行，全部11项真实父子进程、Job Object计数、无法脱离、暂停取消、旧令牌、重启保守恢复及无Job回退保护均保留。未弱化任何停止证明或验收条件。以下以新正式作业结果为准，不沿用首轮目录错误的0tests结果。
