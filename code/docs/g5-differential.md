# G5 完整语言差分门禁

G5 验证 Dong 原生 frontend → lower_program → nasm_program 对 v0.1
语言及 ABI 的实际执行。Python seed 仅用于构建被测编译器和独立同源对照；
被测程序不能回退到 seed，不在宿主构造目标 AST/IR，也不启动 OS/VM。
标准库和系统功能按各自任务验收。

本候选合并 G5TAG1、G5EXEC1、G5ALIGN1、G5PANIC1，以及原负责人
L3EXTUNSAFE1 的无体 extern 默认 unsafe 修复。各组件已经独立复验并验收；
候选组合、真实文件集成和集成后的复验分别登记，不以组件验收代替整体完成。

`requirements.json` 将规格要求映射到 51 个永久测试、27 个要求组。
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

G5FULL1 已经独立冷复验并验收：作业 `2619ead341924ea89cdcd4b955906d70`，51 项测试、27 组要求，零 skip，`scope_complete=true`，源码稳定。生产六模块、runner 和永久测试已实际写入主线；主线已重新冷复验并登记集成（G5INT1 rev24、G5FULL1 rev16）；最终证据见 [G5 完成回执](../../coordination/dongos_works/codex-works/reviews/2026-10-22-G5-completion.md)。

迁移后独立源码审查补充了跨模块常量枚举的tag/payload、包装前的只读指针
转换、已知错误try的终止路径，以及超大合法局部布局的FRAME原子拒绝回归。
静态枚举仅将绑定为ENUM_MEMBER的节点视作变体构造；普通常量引用继续
递归序列化。初始近u64数组超出既有2^63-1对象上限，不能作为可达溢出证据；
局部容量检查前移作为防御性边界整理，相关旧中断记录不算通过。

## 主线入口与证据

在 `code/` 运行 `python -m unittest lang.tests.test_g5_full_native`。每次运行
生成 `build/test/G5-full/run-*/full-coverage.json`，覆盖清单为
`lang/tests/g5/requirements.json`。主线直接读取 `lang/bootstrap/`，不读取
works 中的候选源码。CLI `python -m tools.g5_differential` 仍是基础矩阵，
其 `scope_complete=false` 有意保留，不能代替上述 51 项完整门禁。

闭包入口为 `python -m unittest lang.tests.test_g5_closure_native`，预算、
固定点和宿主加载限制见 [G5 编译器闭包](g5-closure.md)。
本次完整宿主语言覆盖不把历史 G6 客体证据外推到扩大后的编译器；
新源码在 DongOS 上的自编译、持久化和同盘重启须另做 G6 回归。

主线正式作业 `0856b466a4d44a13be901c02f8acff46` 已通过 full51、
closure1 和关联18共70项零skip/source stable，过程停止及退出均确认。
257项完整矩阵冻结输入及真实坏体/产物已独立复算。Windows guest
观察器复用已验收的宿主线程退出与自有ELF窗口持有桥；目标ELF和静态
指针保持原字节，C格式严格检查及失败原子性未放宽。
