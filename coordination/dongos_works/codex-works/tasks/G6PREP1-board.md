# G6PREP1 — 扩大G5编译器的新G6宿主准备与源码绑定复验

负责人：codex。状态：待领取。

用户继续推进G5之后的新G6。本项只完成当前扩大编译器的可复验宿主准备：在协调器隔离副本中用当前源码新生成release完整固定点fixture，fresh构建production runtime5/compiler_job/test=False内核与controller/fs/block，调用现有runner.load_inputs+verify_frozen绑定所有真实源码和启动产物；seed_disk写入fresh SOURCES/SEED并用真实FAT解析逐字读回，两份stage ELF相同且在既有2MiB/512KiB/56MiB/64KiB边界内。保留带SHA的产物与命令/工具日志，设置guest_executed=false，不以宿主落盘声称guest FLUSH/双启/退休通过。扩展宿主准备永久测试，异常启动fixture/启动产物必须失败且不得调用QEMU；修正compiler-job契约与最新进度中的G5旧状态和47.25MiB/8.75MiB分区，历史G6与新准备分开。禁止启动OS/VM/AI CLI或commit/push；协调角色审查源码、契约和独立定向零skip/稳定结果后登记本地集成并同步工作区进度。

## 可修改文件

- `tests/test_compiler_job_preparation.py`
- `docs/l3-compiler-job.md`
- `docs/l3-compiler-job-host.md`
- `docs/l3-native-selfhost-progress.md`
- `codex-works/reviews/2026-10-23-G6-preparation.md`
- `codex-works/reviews/2026-10-23-G6-preparation.json`
- `codex-works/deliveries/G6PREP1.md`

## 定向验收

- `module:tests.test_compiler_job_preparation`
- `module:tests.test_compiler_guest_runner`
- `module:tests.test_fat32_allocation`
- `module:tests.test_compiler_job_launch`
- `module:tests.test_compiler_stack`

交付：`codex-works/deliveries/G6PREP1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
