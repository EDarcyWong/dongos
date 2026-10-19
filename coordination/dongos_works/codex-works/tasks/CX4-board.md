# CX4 — 同步扩展有界EXEC镜像读取与内核暂存容量至2MiB

负责人：codex。状态：待领取。

L3 native semantic executable is about1.47MiB, while shell and kernel EXEC paths are capped256KiB. Raise one shared process ABI limit to bounded2MiB, size shell read buffer and kernel allocated staging pages from that same limit; retain all range/permission/zero/oversize checks. Actual unchanged shell command execution with independent IPC/filesystem/process model must cover >old cap, exact new cap, cap+1 rejected before read/execute, chunking and close/error behavior. Retain lifecycle pure-control tests; no OS/VM or full L3 claim. Verify actual kernel service leaf code generation/assembly if feasible; guest lifecycle gate remains separate.

## 可修改文件

- `services/lib/process_abi.dg`
- `services/shell/main.dg`
- `kernel/user/services.dg`
- `tests/shell_commands_probe.c`
- `tests/test_shell_commands.py`
- `tests/run_process_lifecycle_qemu.py`
- `tests/test_process_lifecycle_qemu.py`
- `codex-works/deliveries/CX4.md`

## 定向验收

- `module:tests.test_shell_commands`
- `module:tests.test_process_lifecycle_qemu`

交付：`codex-works/deliveries/CX4.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
