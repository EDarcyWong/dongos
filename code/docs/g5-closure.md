# G5 有界编译器闭包

本任务验证完整编译器自身的实际纯 Dong 编译闭包，不启动 OS/VM。
硬约束保持为：56 MiB arena、64 KiB 调用栈、最多 512 KiB 源目录包和
2 MiB ELF。debug/release seed 分别构建同一编译器；编译器再原生编译同一
完整源码，两个阶段的 ELF 必须逐字节相同，两种 seed 模式的结果也须相同。

最终语言候选扩大后，原 profile 的 115000 AST 节点不足。真实探针显示
49 模块使用 177359 tokens、115973 nodes、842 types；该探针仅用于诊断，
不计为固定点成功。候选将 token/node 池调整为 190000/118000，保留
56 MiB 总额，前端分配为 57745296 字节。

随后实际运行发现后端分区放不下保留图、IR 和 NASM 文本池。
当前候选在原 arena 内以前 47.25 MiB 供保留图/后端工作区，余下
8.75 MiB 供 NASM 输出；后端池为 640 functions、126000 instructions、
14000 arguments 和 9150000 text bytes。不扩大硬约束，不跳过容量检查。

生成的整程序 guard 现在按语言契约调用目标 panic。pure job 在最终目标
NASM 中检测准确的外部 panic 声明，仅在需要时提供实际不返回的目标退出
实现。若源码已有 panic 定义，保留它的实现。配套 native_assembler 仅允许
在同一最终汇编文本中已有真实定义的 extern，未解析符号仍必须报错。
没有宿主 AST/IR 构造、产物修补或 seed 回退。

永久测试复制只读闭包及声明的候选模块到本次全新构建目录，保存原始
输入和阶段产物。继续执行既有 32 项原子预检、真实语义拒绝、后端容量拒绝、
启动桥寄存器检查及两个阶段的完整 ELF 固定点。所有输入在结束时重新
取哈希，任何变化、异常、超时、skip 或不同产物都不能算通过。

迁移前失败和中断的编号保留在交付记录，本机未迁入其 ignored build 产物。
本机已重新冷构建并完成协调器独立复验；既有迁移记录不充当本机通过证据。
作业 `cbf9efdf4bda4b3b9892141d4baa6dbe` 通过 1 项测试、零 skip，源码稳定。
两模式四份 ELF 均为 2,046,376 字节并逐字节相同，SHA256 为
`2bda587a6842913879eb6bf0445202066adb68baef06d06593ff0f3ee787defa`。
49 模块源码包为 491,683 字节，156 项冻结输入一致；独立审查已解包核对。
生产模块已实际写入主线，主线已重新冷复验并登记集成（G5CLOSURE1 rev21、G5INT1 rev24）；证据见
[G5 完成回执](../../coordination/dongos_works/codex-works/reviews/2026-10-22-G5-completion.md)。

## 主线执行与宿主地址空间

在 `code/` 运行 `python -m unittest lang.tests.test_g5_closure_native`。
测试直接复制当前主线 49 模块，保存 `frozen-inputs.json`、每模式 receipt、
源码包与 stage1/stage2 ELF。独立门禁重新构建，不复用开发诊断对象。

Windows 宿主观察器以 0x10000000 装载，CRT worker 等待原线程真正退出，
并预留 ELF 的 0x400000 两 MiB 地址窗；映射前仅释放自己的预留，
小 ELF 释放后立即重新持有窗口。实际 ELF 仍以原地址执行，静态指针
不重定位、不修补。G5HOST2 独立复验包含占窗/去掉持有的真实坏宿主，
不是捕获地址冲突后伪造成功。先前失败作业和诊断仍保留。

本范围为宿主纯编译作业；没有运行 OS/VM，不增加历史 G6 客体的证明范围。

最新主线独立作业 `0856b466a4d44a13be901c02f8acff46` 的闭包
检查已通过：1项零skip，四份完整ELF与已验收候选逐字节相同，
49条源码包记录及149项冻结输入逐项独立复算一致。整个主线70项
门禁已通过，source_stable/process_stopped/execution_exited均true。
