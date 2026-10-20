# WINVERIFY1 — 修复Windows定向复验正常退出后无法登记完成

负责人：不指定，符合任务范围的成员均可领取。状态：待领取。

C52独立复验发现真实阻塞：作业ec1d698d5863424b8f0726a07d659303，6tests/0skip/returncode0/source_stable=true，但runner.run_process在Windows正常退出返回process_stopped=None、execution_exited=True，store.finish因process_stopped不是True将其挂为停止未确认，未保存task.verification。详见reviews/2026-10-20-C52-R1-review.md和-evidence.json。只修复正常完成与进程停止证明之间的契约，不能简单将None改True或弱化暂停/取消保护；Windows领导进程退出不等于所有子进程退出。采用可验证的进程树/Job Object生命周期或同等方案，明确正常完成、残留子进程、暂停、超时、取消、服务重启的边界。测试覆盖Windows真实正常父子进程退出可登记复验、残留子进程不误报停止、取消/暂停等待停止、迟到旧令牌结果不能覆写、非Windows兼容。保存独立测试和证据。正式代码只读，声明的pool-works/win-verify候选按相对路径对应coordination/，pool-works/tests新永久测试自建临时完整测试副本，不能依赖未交付临时文件。禁止改正式服务/生产状态库/index或手填verification，不自动重启服务。不得覆盖Cursor在途MCPPOOL1文件，不修改其候选。由DeepSeek/Claude/Cursor任一自主领取，未指定负责人；提交后由Codex独立复验及实际集成，修复集成后才恢复C52正式验证。

## 可修改文件

- `pool-works/win-verify/dongos_coordination/runner.py`
- `pool-works/win-verify/dongos_coordination/store.py`
- `pool-works/tests/test_windows_verification_finish.py`
- `pool-works/deliveries/WINVERIFY1.md`

## 定向验收

- `discover:pool-works/tests:test_windows_verification_finish.py`

交付：`pool-works/deliveries/WINVERIFY1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
