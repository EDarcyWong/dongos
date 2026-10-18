# P6 AP 调度：按需计时与体积优化候选

候选位于 `build/test/p6-runtime-tickless/`，独立于历史冻结的
`build/test/p6-runtime-candidate/`。未改生产树，未执行 AP、QEMU 或 VMware。
完整私有栈、xstate、CR3、优先级、迁移与 arena 集成约束继续见
`docs/p6-runtime-candidate.md`。此候选仍只支持 CPL0 AP 线程；现有 BSP 用户服务
`CURRENT`、用户 GS/TSS、SYSCALL、跨核 PCID 回收还不能并发使用。

## 行为

- 域锁内完成运行队列变更和竞争者判断：当前 CPU 有 RUNNING 线程，且存在其
  affinity 包含该 CPU、优先级不低于当前线程的 READY 线程时才需要 quantum。
  只把判断结果放到该 CPU 的 `timer_need`；解锁后不再扫描可变运行队列。
- 空域、空闲 CPU、单独运行的最高优先级线程，以及最后一个线程 BLOCK/EXIT
  都停止本地计时器。不会靠周期中断发现新工作。
- start、admit、wake、affinity、priority、rebalance 向可接收工作的 CPU 发出实际
  reschedule IPI；空闲 AP 可以通过现有有界 steal 获取其他队列中的 eligible 线程。
  修改发生于锁内，IPI 于解锁后发送；本地 IF=0 使待决 IPI 在停表后仍会被处理。
- ASM 的 timer mode=0 先 mask LVT timer，再清 initial count；只有当前 CPU
  CPUID 声明 TSC-deadline 才清 IA32_TSC_DEADLINE，避免无能力 CPU 访问该 MSR。
  `timer_armed=2` 表示初始硬件状态尚未确认，第一次停表仍会执行硬件取消。
  之后为 0=停止、1=已 arm。硬件停表或 IPI 失败都保留全局 fail-stop。

`sched.multicore.Engine` 仍为 12,960B，Cpu 为 552B、Thread 为 64B；移除只用于
初始化的巨大 `EMPTY Engine` 常量，以显式逐 CPU / 线程循环初始化所有字段。
结构审计、代际、32 优先级、FIFO、affinity、steal 和 rebalance 校验均保留。
适配器 Cpu 新增本地计时状态，现为 160B；Domain 仍为 112B。metadata 需要
83,264B，加模板及备份仍由 arena 的 21 页容纳，没有新增大块 BSS。

## 验证

`python -m unittest tests.test_parallel_tickless -v`

最终证据：`build/test/p6-tickless-native/run-485a3db2866b/validation-summary.json`。
debug/release 均执行实际 Dong 队列和适配器，只有硬件边界回调为 mock：
104,826 项常规调度断言、559 项停表 / 最后 BLOCK / 最后 EXIT / IPI 唤醒断言，
以及独立 stack/root/frame/arm/stop/kick 故障场景。10 种实际坏源码变体均被拒绝：
漏存/恢复 xstate、临界区错误释放、漏 scheduler-stack/root 检查、丢 IPI、漏 arm、
空闲仍 arm、漏 stop、只给原 CPU 发 IPI。

同一 variant 的真实队列原生测试证据为
`build/test/p6-runqueue/run-6770ee8200be/validation-summary.json`，每模式
108,770 项断言、30,000 次模型转换和 3 种坏源码拒绝。现有真实 paging / arena
builder 复验为 `build/test/p6-builder-native/run-21ff904508aa/validation-summary.json`，
含双 guard 撤权、确认 barrier、晚失败保持及 3 种坏源码拒绝。三个 ASM 均汇编为
ELF64 / COFF64，实际 builder 全模块图在 debug / release 编译通过。

## 体积

`build/test/p6-size-tickless/no-wrapper-size.json` 对同一生产依赖图分别编译空入口和
实际 `parallel_boot.dg`，没有测试 wrapper：release DG 增量 text=55,392B、
rodata=1,000B、data=0、BSS=55B，共 56,447B；比旧冻结 DG 小 11,168B。
加实际 arch/probe ASM 和 AP bootstrap 相对生产的增量 text=1,179B、rodata=4B、
BSS=128B，总估算增量 **57,758B**。这是目标文件 section 之和；最终 PE/ELF
链接、对齐与 2MiB 启动窗口仍须串行完整构建核实。

源文件 SHA 与全部证据入口在候选 `manifest.json`。旧冻结源码与历史证据保留。
