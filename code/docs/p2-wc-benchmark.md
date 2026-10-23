# P2 有界 GOP UC/WC 采集门禁

这是独立的性能采集准备工作。已验收的 EXEC/WC owner、生产启动路径和装载 ABI
不因本门禁修改。真实物理机尚未采样；P2 的物理 WC 吞吐外部门禁仍未完成。
TCG、WHPX、KVM、VMware 的周期数均属于虚拟环境，不能证明物理 WC 性能。

`mm.wc_benchmark.measure` 消费正常 `mm.paging.Space`、真实 GOP 子窗口、TSC
频率和调用者提供的备份。窗口不超过 65,536 字节，8 字节对齐；先完整校验范围、
备份容量及与 Config/Report/Space/页表池/metadata 的不重叠关系，再逐页 query
物理地址和精确 WRITE|UNCACHED 或 WRITE|WRITE_COMBINING 权限。只接受普通
4KiB 叶项，并把每个实际原始 PTE 保存到报告。无效输入在任何窗口、备份或报告
写入前拒绝；unsafe 调用者仍负责提供可访问且独占的对象存储。

同一个 `wc_benchmark_trial` 汇编体向窗口写入 `PATTERN xor qword_index`。
每种状态运行七次，CPUID/RDTSC/LFENCE 序列化起止边界，结束先 SFENCE，再 CPUID/RDTSC/LFENCE，
将 WC store 完成计入周期数。每次测量后，独立 restore 汇编逐字节复制原备份，
SFENCE 后由 Dong 逐字节比对整个窗口并检查备份内 guard，成功才发布该 sample。
周期数包含循环、SFENCE 和序列化开销。报告记录原始七项周期数、实际根、范围、
频率、query flags、原始 PTE、模式、恢复次数和 guard；不把 cache 名称字段当作
PAT/MTRR 的实际效果证明。试验不配置 PAT/MTRR，不自建 framebuffer 别名。

备份由既有 `boot.service_memory` arena 在私有启动 overlay 中分配；最大需求
65,552 字节，按页向上取整为 17 页。生产模块只有 712 字节 Pair 报告，无 64KiB
静态备份。调用者必须在采样期间停止其它 framebuffer 写者；本接线发生在原
`smp.alias_memory.cache_run` 内、用户调度和 compositor 发布之前。

准备与构建均从 `code/` 执行：

```powershell
python -m tests.p2_wc_stage --output build/test/p2-wc-stage/review-1
python -m tests.p2_wc_stage --output build/test/p2-wc-stage/build-1 --build
```

默认只复制当前完整源码，不运行编译器、OS 或 VM。准备器仅修改私有副本的两个
原文件：给 `alias_memory.dg` 导入 benchmark/时钟，在真实 WC bind/migration 前
采 UC、迁移完成并重读真实硬件 mailbox 后采 WC；给 `alias_memory.asm` 追加同一
timing helper。真实全 GOP owner、原 bind/迁移/封存顺序和全读者回读保留。窗口
大小、地址、模式、备份和 TSC 频率在前后相同。工具保存唯一可重推的 `overlay.diff`、
原始/私有输入 SHA、真实命令及原始构建日志；明确 `--build` 才在 fresh Python
进程中调用私有源树原 `tools.build.build(runtime_level=7,test=True)`，产出实际
ELF、DONGOS.IMG、SERVICES.BIN 和 EFI。原生产 manifest 不覆写成自造来源声明。
重验会从当前原始源重新推导精确 overlay，拒绝仅重写 staged manifest 的额外修改。

完成构建后的默认 runner 仍只核来源：

```powershell
python -m tests.run_p2_wc_benchmark --reuse-esp build/test/p2-wc-stage/build-1/image/esp
```

仅协调者在独立审查与宿主门禁后，依据用户 P2 授权明确执行：

```powershell
python -m tests.run_p2_wc_benchmark --reuse-esp build/test/p2-wc-stage/build-1/image/esp --execute
python -m tests.run_p2_wc_benchmark --replay build/test/p2-wc-guest/run-<id>/result.json
```

执行器只用 QMP stop/cont、寄存器查询与 pmemsave 读回，不补写 RAM、寄存器或
成功标志。复用 P2 alias 的完整页表、EXEC owner、全 GOP WC owner、全部读者
真实 PAT/MTRR/mailbox 和封存 oracle，再独立核 benchmark Pair、UC/WC 原始 PTE、
最终实际 WC 页表及 arena backup guard。UC 原始叶项是在迁移前由 source-bound
生产 benchmark 采入；最终 GOP 已由 compositor 接管，runner 不把此后像素变化
当作采样期间的恢复失败，也不把一个 `restored=true` 字段当作独立物理证明。

原始 UART、物理 dump、顺序 manifest、ABI/ELF、副本 SHA、源码/工具/磁盘前后
SHA 和子进程停止记录一同保留。replay 对每次读取的地址、长度、角色、原始文件
SHA 重算所有结果。缺原始数据、错误来源、仅布尔 `passed`、损坏 PTE/PAT 或
未清理进程均不得作为成功采集。文件 SHA 绑定字节，不认证外部记录的作者。
本 runner 的所有结果强制 `physical_wc_performance=false`、
`physical_gate_complete=false`；`passed` 只表示这次虚拟采集的一致性。

宿主门禁：

```powershell
python -m unittest tests.test_p2_wc_benchmark -v
```

该模块还执行一次真实 fresh runtime7 构建，并通过真实 identity CLI 核验产物、
完整来源、工具及明确三个构建回执文件，再实际篡改私有命令回执证明被拒绝。
它会生成启动镜像，但仍不执行 OS/VM；不使用伪造 ELF 或完成标志代替构建。

它在 debug/release 中编译真实 Dong paging/benchmark，分别组装 ELF64、COFF64，
在本地正常 RAM 运行真实 timing/restore 汇编。独立 C 检查整个窗口、外 guard、
备份、报告、真实 PTE、七次周期和非法范围/容量/cache/PA 的失败原子性。实际
跳过 restore、实际多写一个 qword 的两个坏汇编必须正常构建并运行，分别被
`window-restored` 与 `write-window-guard` 精确拒绝；崩溃、编译失败、超时不能
替代成功负控。缺工具即失败，零 skip。测试不会自动启动 VM。

宿主页表是实际 Dong 软件页表，宿主 RAM 的硬件 cache type 明确为 unknown。
因此宿主测试只证明有界写入、恢复、计时与报告契约；不将逻辑 UC/WC PTE 或某个
周期比值冒充实际 UC/WC 吞吐。物理机验收还需独立记录实际固件/CPU、PAT/MTRR、
完整 GOP 所有权、相同采样模式与原始结果，并明确排除虚拟化；未有此证据前保持
物理性能门禁未完成。

## R1 实际构建与来源拒绝记录

2026-10-23 协调器在隔离快照
`coordination/dongos_works/.local/runs/32bfd154494945e5b718667278c52299/workspace`
运行了实际 `python -m tests.p2_wc_stage --build --output build/test/p2-wc-real-build/current-r1`。
实际构建进程正常退出 0，`kernel.bin` 为 2,006,736 字节，源码与工具前后 SHA
稳定；没有启动 VM。原始材料保留在该隔离目录的
`build/test/p2-wc-real-build/current-r1/`：

- `wc-source.json`：真实构建回执；其中 `built=true` 仅记录链接完成。
- `build-command.json`、`build.stdout`、`build.stderr`：真实命令和原始构建输出。
- `image/kernel.bin`、`image/kernel.elf` 及其它真实启动产物。

随后实际 identity 命令退出 1，报
`ValueError: complete actual artifacts/tools/raw build logs required; flags alone are insufficient`。
根因是构建完成阶段使用 `glob('build.*')`，仅枚举了 `build.stdout` 和
`build.stderr`，遗漏带连字符的 `build-command.json` 的 SHA。命令文件实际存在，
identity 正确拒绝缺失来源绑定；本次结果不能算完整门禁通过。该 identity 失败的
stdout/stderr 仅在协调器的工具记录中，未另存独立磁盘日志，本文不补造日志文件。

R1 修复改为明确枚举上述三个回执，保留 identity 原门槛，并增加实际 fresh
构建→identity 的永久宿主门禁。这项返修的通过情况以随后协调器独立复验为准，
不将旧 R1 构建改写成通过记录，也不改变物理 WC 性能尚未实测的结论。
