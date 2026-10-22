# L3SYSVASM1 — [L3A] 原生汇编器接续SysV链接名的NASM符号转义

负责人：codex。状态：待领取。

codex:L3SYSV1为extern/export的合法ASCII链接名统一输出NASM $转义，原生汇编器旧word/identifier尚不接受。补齐原生汇编器$identifier解析/符号查找归一化，使普通/转义拼写指向同一标签、全局声明和重定位/直接call正确，不把$rax当寄存器，不允许重复符号或未定义符号，不增加外部链接能力。普通现有导出名继续可用。新增小型真实Dong assembler桥，debug/release输出ELF，宿主按PT_LOAD映射执行，独立常量oracle检验返回42；验证escaped/plain混用、call/rel/dq、保留原始源、guard/失败输出原子性及重复/坏符号拒绝；不运行OS/VM。仅write_paths，不修改native compiler桥或语义ABI，不提交推送。

## 可修改文件

- `lang/bootstrap/native_assembler.dg`
- `lang/bootstrap/native_assembler.md`
- `lang/tests/test_l3_escaped_symbols.py`
- `codex-works/deliveries/L3SYSVASM1.md`

## 定向验收

- `module:lang.tests.test_l3_escaped_symbols`

交付：`codex-works/deliveries/L3SYSVASM1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
