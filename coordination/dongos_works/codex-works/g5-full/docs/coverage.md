# G5 最终组合候选

G5 验证 Dong 原生 frontend → lower_program → nasm_program 对 v0.1
语言及 ABI 的实际执行。Python seed 仅用于构建被测编译器和独立同源对照；
被测程序不能回退到 seed，不在宿主构造目标 AST/IR，也不启动 OS/VM。
标准库和系统功能按各自任务验收。

本候选合并 G5TAG1、G5EXEC1、G5ALIGN1、G5PANIC1，以及原负责人
L3EXTUNSAFE1 的无体 extern 默认 unsafe 修复。各组件已经独立复验并验收；
候选组合、真实文件集成和集成后的复验分别登记，不以组件验收代替整体完成。

`requirements.json` 将规格要求映射到 47 个永久测试、27 个要求组。
完整结果为每次新运行的 `full-coverage.json`；只有所有要求对应测试均实际
通过、无 skip、无已知缺口、native ELF 通过且源文件稳定，才置
`scope_complete=true`。测试异常、超时、取消及不受支持都不能算通过。

覆盖包括整数/转换/检查/wrapping、指针和函数值、数组/结构体/全局及静态
重定位、模块可见性、slice/optional/result/enum 的表示和 SysV pair ABI、
方法选择与求值次序、初始化流、for/match/try/orelse/defer、noreturn 清理、
Win64 shadow space/栈参数/非易失 GPR 与 XMM6–15/DF、对齐及总栈预算、
各宽度 volatile/非对齐访问、四线程原子竞争、asm 白名单、panic 的精确
种类/行号/文件及不执行清理、正式诊断和失败输出原子性。

所有正向执行均使用真实 NASM 产物和独立 C/汇编观察器。完整 ELF 由同一次
冷构建的 Dong native_assembler 生成，经 kernel ELF validator 验证并在原始
0x400000 地址执行；目标源码显式提供 panic 实现，静态指针不重定位或修补。

组件复验分别构建单一缺陷的坏编译器。最终组合测试另从本轮源码实际构建
一个含六个明确缺陷的编译器，供六个互相隔离的输入复用：optional 标签、
XMM15 恢复、局部地址、panic 种类、全局地址和窄写入。输入避免触发其它
缺陷；每个独立 oracle 都须观察到预期的正常执行错误或精确 panic 差异。
原始及变异源码、真实驱动/object 哈希、进程返回码和产物哈希均保存。
另以缩小实际 C 调用者 instruction pool 制造真实 CAPACITY 失败，验证把
seed 成功替代 native 失败的坏 runner 会被来源检查拒绝。

静态数组可以大于 4 KiB；类型的 word 数与局部存储的栈预算分开检查。
局部 slot 分配仍拒绝超预算对象，静态全局量/常量及其索引、指针使用
真实大数组执行回归，不能把静态对象错误地当作栈分配拒绝。

Windows 长路径和 CRLF 属于测试承载边界；测试使用短目录及文本/实际
文件哈希各自一致的比较。失败证据保留。编译器自身闭包和 bounded pure
compiler_job 固定点须另做实际回归；本文件不将尚未完成的检查声明为通过。

当前仍在最终候选开发复验阶段，尚未集成。
