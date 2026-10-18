# P3 中断、定时与抢占线程

2026-10-17，P3 原阶段标准“内核线程按时间片交替运行”已通过本地验收。目标继续推进至 P7；P4 用户态/IPC 正在接入。结果见 [validation-summary.json](../build/test/p3-runtime/validation-summary.json)，ACPI 发现见[前一里程碑](acpi-discovery.md)。

## 实际行为

`python tools/build.py run --runtime-level 3` 在原内存/缓存诊断链后进入 BSP 运行时。单独的 UC、supervisor RW/NX 设备窗口映射来自 ACPI 的 LAPIC、IOAPIC、HPET/PM timer，拒绝与普通 RAM、runtime 描述符、保留资源和其它设备页冲突。旧 WB 数据页 API 没有放宽。生产中的所有页表修改在独占 BSP、IF=0 时完成，先失效再回收；P2 全树初始审计的生命周期在移交前结束。

8259 双片 IMR 均设为 ff；所有 IOAPIC redirection entries 先屏蔽。LAPIC 核对 APIC_BASE、BSP/ID、版本和 LVT 数量，屏蔽非计时器入口后启用合法 spurious vector ff。每次 IRQ 使用 vector40、IST0，让挂起帧留在所属线程栈；原致命异常的三个专用 IST 保持原职责。spurious 不发送 EOI，真正 timer IRQ 重装定时器后发送一次 EOI。

时钟优先读取完整 CPUID15 比率，否则以 HPET 或 ACPI PM 参考校准 TSC；LAPIC count 模式也独立校准。具备能力时实现 TSC-deadline，LVT MMIO 与 deadline WRMSR 之间有 MFENCE；TCG 此轮实际未提供该能力，四个客体都使用已校准的 one-shot 回退。真实 deadline 路径尚待有能力的环境实测，有限 native 寄存器模型已核对该路径及省略 MFENCE 的坏实现。

两条忙循环线程由真实 10ms IRQ 抢占，没有 yield。129 个 tick 中两个 worker 各获得64个，发生65次切换，最后回到原 bootstrap 栈。所有 GPR、x87、MXCSR 和16个 XMM 状态均保存/恢复；XSAVE 仅启用 x87/SSE、XCR0=3，缺 XSAVE 时使用 FXSAVE。每条线程16KiB栈的上下两页 guard 都撤销映射，返回帧核对所属栈、内核 RIP/CS/SS 和 flags。优先级/量子、嵌套禁抢占、IRQ-safe 锁与 FIFO 等待/代数唤醒另由独立 native 模型覆盖，见[scheduler.md](scheduler.md)。

当前 runtime3 是有界验收入口：完成线程证明后停 timer、IF=0，再返回原 PASS/HLT。后续用户进程和服务由 P4 入口接入；没有将此诊断循环当成持续运行的桌面。

## 验证与证据

四项正式配置为普通四核、无 HPET、无 XSAVE 和正式镜像。每项通过原 ACPI 物理清单及完整 P2 生命周期验证，并在实际链接 HLT 后核对：

- 192B controller 报告、240B scheduler 报告、448B engine 与原串口一致。
- 原始物理页表遍历证明设备叶精确 UC/RW/NX/supervisor，四个 guard 不存在，worker 栈精确 WB/RW/NX。
- QMP `info lapic` 的计时器已屏蔽、count为0、ESR为0、ISR/IRR为空；`info pic` 的24个 IOAPIC pin 与两个8259均屏蔽。
- worker 正计数、各64tick、零 GPR/xstate 错误，129次状态恢复；受保护控制位保持。

本阶段新增受影响的10项宿主测试全部通过，零跳过。另有首次真实 smoke 和首次独立 snapshot，合计6次实际客体，全部串行。旧 runtime0 重建后的装载内核字节与前轮完全相同，因此前轮35项 P2 客体证据仍对应相同运行程序，没有重复声称本轮又跑35次。

首轮源码清单误收了所有 `include/*.inc`，并发开发中的 P4 `user_context.inc` 导致清单总标志为 false；四项客体本身均通过。审计确认该头文件未被任何 P3 输入引用，其余实际输入哈希稳定；修正仅涉及永久 runner 的依赖清单，所有验证函数 AST 相同，原结果/前后哈希完整保留。构建阶段的 extern 语法、错误码重名和局部 ELF 符号重名均已修正，它们没有执行客体，也未被算作有效负控。

```powershell
python -m unittest tests.test_device_policy tests.test_irq_platform tests.test_sched tests.test_runtime_qemu_result -v
python tests/run_runtime_qemu.py --all
python tools/build.py run --runtime-level 3
```

## 来源

控制器、IRQ帧、XSAVE 和 SYSRET 后续边界采用 [Intel SDM](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)；LVT 项数与屏蔽向量核对 Vol3A §13.4.8/§13.5.1/§13.5.2，设备内存采用现有 PAT WB0/UC3 的独占映射策略。本轮没有启动 AP、实现用户进程或声称达到 P6/P7 的性能标准。
