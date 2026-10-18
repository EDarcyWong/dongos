# P6 AP 抢占、迁移与按需计时的实际接线候选

2026-10-18实际更新：`p6-live/qemu/run-dbf1d9f7cc2e`同盘两次启动及`run-8cb80c430436`省略xstate真实负控均通过，见`build/test/integration-promotions/p6-live-actual-acceptance.json`与[集成记录](process-integration.md)。每次61份AP物理读取、六线程GPR/XMM/guard（旧配置XCR0=3）、真实迁移和各CPU masked LAPIC/停表已复核；后续三服务写读/FLUSH/同盘重启也通过。旧配置256帧不足已调512并通过四组回归；两处检查器错误（有效USER祖先和stateless HMP的CPU选择）修后完整重跑，旧失败保留。下文“未运行完整OS/VM”是最初候选交付时的记录，现由上述实际证据补充；生产AP用户调度仍未据此验收。

候选为 `build/test/p6-live-integration-candidate/`，原生证据与 SHA 入口为该目录的
`manifest.json`。没有写生产源码，没有链接完整 OS，也没有运行 QEMU/VMware。
完整 Dong 图 debug/release 编译及五个 ASM 的 ELF64/COFF64 汇编通过，证据为
`build/test/p6-live-native/run-f47455e3103a/validation-summary.json`。首次尝试的
完整生成内核 ASM 超过 90 秒限时，保留在 run-e6b9fa0e3572，未计为通过。

## 实际接线

- `smp_probe.dg` 引入真实队列、arena builder 和 `parallel_live` 门禁。
- AP bootstrap 增加 timer 0x40 / reschedule 0xf3 的 IST0 gate，空闲循环先执行
  tickless stop，保留原 SmpContext256 / GS、ping/stop/TLB handler。
- `smp_runtime.asm` 在原 SMP/TLB gate 成功后调用新门禁，失败不继续用户服务。
- `parallel_live.asm` 在每个 AP 的首次 scheduler-stack 入口上，以该 AP 的
  divide-by-16 LAPIC 倒计数对既定 TSC 参考独立校准 10ms。测量期间 LVT masked，
  有有限轮数，零/stuck/溢出结果拒绝；不会把 BSP LAPIC 频率当作 AP 实测。
- 新 live 门禁调用于 BSP/IF0，Report 与 Timer 数组共两页 arena。队列/适配器
  metadata 仍为 21 页，线程与 scheduler 栈仍使用带双 guard 的独立 arena 栈。
  退休前在队列锁内归档实际最后 Frame 指针及 token；RAM 保持到物理复验。

门禁按次序验证：每 AP 两个无 yield 忙循环线程真正收到 timer 并轮换；开启
affinity 后让最后 AP 的本地线程退出，迫使它 steal 其他 AP 的普通保存帧；
所有线程退出；空域连续 50ms 无调度 ticks；复用 token 槽并用真实 IPI 唤醒单个
线程，其忙循环推进而无额外 quantum；最后退出。线程检查各自 GPR、XMM0/15
以及实际 XCR0=7 时的高 YMM15。报告计数区分真正 timer vector 和 reschedule IPI。

这仍是 **三个 AP 上的普通 CPL0 线程**，BSP 继续既有 CPL3 服务。它没有把用户
`CURRENT` 放到 AP，也没有完成多核用户态；相应所有权/回收协议候选另见
`docs/p6-user-smp-candidate.md`。

## 构建与运行入口

以下脚本默认只准备隔离快照，不执行构建或 VM：

```text
python build/test/p6-live-integration-candidate/tools/build.py
python build/test/p6-live-integration-candidate/tests/run_parallel_qemu.py
```

构建器核对被覆盖的四个生产基底 SHA，然后在输出目录复制实际 kernel union。
修改基底变动时明确拒绝覆盖，需先审查 rebase。原 production tools.build 保留
loader/services 工具；适配器把 Dong kernel root 和所有 kernel ASM 路由到该
union，生成实际 Report offsets，并向链接列表加入 parallel / probe / live 三个
对象。所有实际 union 输入及候选 SHA 都写入 `p6-live-source.json`。不扩大原
2MiB image 限制。

主任务可串行显式执行：

```text
python build/test/p6-live-integration-candidate/tools/build.py --build --output build/test/p6-live-positive
python build/test/p6-live-integration-candidate/tests/run_parallel_qemu.py --execute --reuse-esp build/test/p6-live-positive/esp
python build/test/p6-live-integration-candidate/tools/build.py --build --parallel-case omit-xstate --output build/test/p6-live-negative
python build/test/p6-live-integration-candidate/tests/run_parallel_qemu.py --execute --negative-xstate --reuse-esp build/test/p6-live-negative/esp
```

正向 runner 保留旧 SMP/TLB 物理复验与 FAT 同盘两次启动。它另外读取实际 Report、
真实 Engine / FIFO / generation、线程栈与 guard、最后硬件 GPR Frame、XMM/YMM
快照，以及各 AP 的实际 masked LVTT 和零倒计数。所有 arena PTE 必须确为该
arena 的物理 RAM、WB/RW/NX supervisor；拒绝只看串口标记。旧 AP idle RIP oracle
改为候选真实导出的 `smp_ap_idle_after_hlt`，没有伪造符号偏移。VM 与 QMP 清理
仅针对本脚本启动的进程。

负控只省略调度器 save/restore，且必须 P1 test。runner 要求实际 worker 错误、
真实 timer 命中与物理 Probe done=2，不能用启动失败、panic 或超时代替成功的
反例。两个 runner 都检查实际构建 artifact SHA 及保存 union 未变。

## 预算与待实测项

相同依赖图、无测试 wrapper 的 release DG 增量为 text=71,296B、rodata=1,024B、
BSS=64B，共 72,384B。三个新 ASM 合计 text=1,960B、rodata=527B、BSS=128B，
连同 bootstrap/smp_runtime 相对当前生产的差量，全部目标文件 section 增量为
**75,048B**。完整链接的布局/对齐和最终 2MiB 边界仍需
主任务核实。当前生产约 2,014,600B；若后续 compositor 改 arena 后允许 STATIC4
缩为 STATIC3，可另外释放 128KiB，但本候选没有擅自进行该修改。

idle-drain 已经主任务批准合入：在原 20 秒截止内寻找完整 50ms 无 ticks 窗口，
允许旧 affinity IPI 尾部自然排空。周期 timer 始终不能取得该窗口，最终物理
HMP LVTT mask/one-shot/count0 检查保留。delay 先检查 TSC 回退再作无符号差，
避免回退短路成“已完成等待”。历史修正与旧 manifest 保留。

`build/test/p6-idle-drain-native/run-f1b07c01e6f1/validation-summary.json` 独立提取
实际 timed/healthy/delay/settle_idle 源码并运行真实 Domain；只有时钟、异步
AP ticks 和 worker 读取边界为 mock。debug/release 各通过 quiet、一次迟到
IPI、持续 ticks 20 秒超时、worker 错误、TSC 回退和已失败域六种场景。
五种实际坏源码（漏全局截止、错把迟到 IPI 当安静、漏 worker 错误、漏回退检查、
忽略 failed 域）在两种模式均被拒绝。持续 ticks 的正常模型执行 20,022 次
时钟读取，有限 guard 也确保故意漏 deadline 的坏实现被拒，未依赖 host 超时。

原生结构/oracle/路由测试：

```text
python -m unittest tests.test_parallel_live_integration tests.test_parallel_idle_drain -v
```

现有所有证据都标明 actual_ap_or_vm_executed=false。只有实际正向、保存状态的
硬件负控、持久存储回归通过后，才能验收这里的 AP 调度门禁。
