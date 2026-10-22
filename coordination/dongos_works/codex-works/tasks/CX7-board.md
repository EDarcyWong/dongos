# CX7 — [L3] 编译器专用64KiB受保护栈配置与装载入口

负责人：codex。状态：待领取。

用户已要求协调者选择栈约束，选择仅编译器专用64KiB，普通进程仍16KiB，两侧guard，全部映射来自既有64MiB共享arena。实现窄profile及内核可信专用stage入口，容量预检和ELF guard碰撞覆盖完整16页，stage失败回收保持。不得扩大arena、暴露用户自选栈大小或赋予额外权限。独立审查+真实编译debug/release测试、边界与旧4页坏实现负控；本项只是专用装载能力，真实编译器启动/自举另需集成。

## 可修改文件

- `kernel/user/compiler_stack.dg`
- `kernel/user/memory.dg`
- `tests/test_compiler_stack.py`
- `docs/l3-compiler-stack.md`
- `codex-works/deliveries/CX7.md`

## 定向验收

- `discover:tests:test_compiler_stack.py`

交付：`codex-works/deliveries/CX7.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
