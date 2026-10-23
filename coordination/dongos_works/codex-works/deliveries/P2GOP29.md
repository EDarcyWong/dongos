# P2GOP29 交付

任务：`dongos/codex:P2GOP29`，实施依据最新 rev2 完整任务书。仅修改任务声明的
六个路径；由 root 协调器提交及独立复验，执行方未修改任务状态。

已实施：

- `kernel/entry.asm` 内永久 64B 对齐的 32B Gate 和固定 SysV getter；writer
  只原子修改 word，局部 helpers 不增加可选 CACHE/Domain 外部依赖。
- 普通和 panic renderer 最外圈一次 enter/leave，拒绝在读取几何/GOP 前返回；
  invalid geometry 也释放已取得的 writer，普通绘图返回值和保存寄存器保持。
  leave 执行 SFENCE，允许 close/closing 后已有 writer 退出。
- host 验证直接抽取真实 renderer/Gate/rodata、真实 cache Gate 原子函数。
  独立 C oracle 检查受 guard RAM、NOACCESS、布局、计数、关闭互操作、字形和
  ABI；O0/O2 共 16 个正常/实际坏体执行。完整生产 entry 的六个 runtime 级别
  各有 ELF64/COFF 仅汇编检查。
- 文档记录唯一启动期 memory_active_probe 调用点与 C/D 后续真实 ledger、poll
  mux、固定 Gate 绑定、生产 reader 链接等只读接线设计。

静态检查：已人工对照 Gate ABI 0/8/16/24、renderer 全部出口、helper clobber、
SysV 栈对齐、panic 原串口/重入路径、真实源码抽取边界、负控的正常失败要求及
声明文件范围；`git diff --check` 用于空白检查。最终源码 SHA 由交付消息另附。

明确未执行：任何 Dong/C 编译、汇编、测试、VM、OS、任务状态变更、提交或验收。
没有当前执行证据可用于声称测试通过；新 harness 会由 root 独立运行并保存
源码/工具前后 SHA、raw 命令、对象和 EXE 哈希。

限制：Gate 不等于用户 compositor 已 capture；宿主 RAM 不证明真实 NMI/WC
硬件排序、AP/guest 结果。全内核链接后的 2MiB 预算和后续 C/D 工作区预算仍需
wholebuild 独立验证。失败时不能清零 writer 强行重开 Gate。其它 B/C/D 服务、
memory、build、panic、IDT 和原失败证据均未修改。


## AI交付 2026-10-22T21:45:39+00:00 · codex-mcp-daece153b59c4bd5

P2GOP29六路径完成。root及独立只读审查实际核production Gate/getter/完整screen-panic-text-hex调用覆盖、所有出口leave+SFENCE、SysV寄存器/栈、先Gate后geometry、永久32B align64/epoch ABI、无optional CACHE extern及启动probe前置；未见确定阻断。测试真实production slices/rodata+真实cache Gate，O0/O2各1正常+7实际坏体，共16native计划，另6runtime×ELF/COFF共12完整entry仅汇编；NOACCESS敏感路径前先独立RAM反控、坏体只接受rc1 oracle而非crash。完整src/tools/rawcmd/output/object/EXE SHA与late稳定性assert。实现者未编译测试/VM。root另在SMP27 v2不可变快照fresh full runtime7构建已实际成功，entry字节与本交付SHA50b61f...完全相同，raw1966480B/余130672B/285artifacts；这仅构建诊断，不代替本组件独立门禁。等待正式三模块复验；不宣称真实NMI/WC/capture或P2/C/D通过。
