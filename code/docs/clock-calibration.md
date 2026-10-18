# 参考时钟校准加固

2026-10-17：`irq.platform` 已改为七次有界夹取采样，HPET 和 ACPI PM 两种真实客体均通过独立区间复算。此修改针对此前 P7 同镜像出现约 3.1 GHz 校准离群、正常值约 3.4 GHz 的实质问题；旧失败记录保留，未按预设频率或放宽帧率门槛修饰结果。

每次重装 LAPIC 计数器，在参考时钟的前后读取之间分别采样 LAPIC 和有序 TSC。等待约 10 ms 后再次夹取，显式记录八个原始值。纯策略结合计数器回绕、参考量化误差和端点夹取跨度，给出 TSC/LAPIC 的保守频率界；过宽端点、短/长区间、溢出和模糊回绕均拒绝。ACPI PM 使用精确 3579545 Hz，有效位宽由固件确定。

最多七个样本中，选择至少三个且 TSC/LAPIC 两个区间同时相交的唯一最大共识集合。多个同样大的分离集合失败关闭；中位候选收束到共同界内。至少三条合格且一致后才发布。CPUID 已提供有效 TSC 频率时保留该来源，仅用参考校准 LAPIC。没有固定 CPU 频率、取最大速率或失败时沿用陈旧频率的捷径。采样和决策均发生在现有受控初始化阶段，原 `Report` 的 192B ABI 保持不变。

原生证据：

- `build/test/clock-calibration/host/run-1eb15b7d5d2c/validation-summary.json`：3 项测试、debug/release、零跳过。每模式 2354 次区间估计、1346 次独立二维频率平面选择、2353 次真实物理频率包含检查。旧单样本实际算出 3105373100 Hz 的坏实现、删除量化界的坏实现均真正执行并被拒绝；ELF/COFF 通过，纯策略生成调用链上界 2608B。
- `build/test/p3-irq/host/run-b82ebd9b59ec/`：平台接线 3 项测试通过，两模式各 10 个硬件模型场景。包含前两个端点延迟被拒后五个正常样本通过、全部延迟时初始化失败、HPET 停滞立即超时、PM 24/32 位回绕及 deadline 排序坏实现拒绝。

真实 QEMU 使用正常 runtime7 构建 `build/test/p7-transitions/build-193421267e4b/esp`，两次均校验实际内核 RX 字节、原始布局、完整源码和产物哈希，再从物理内存读取全部样本。`tests/run_clock_calibration_qemu.py` 的 Python 整数区间/二维覆盖模型独立重算完整 24Q 结果，不调用 Dong 策略或 C 原生模型。

| 路径 | 样本接受/拒绝 | TSC Hz | LAPIC Hz | 最紧样本不确定度 | 证据 |
| --- | --- | --- | --- | --- | --- |
| HPET | 6 / 1 | 3417916818 | 62502347 | 531 ppm | `build/test/clock-calibration/qemu/run-e3223202110e/result.json` |
| 无 HPET、ACPI PM | 7 / 0 | 3418234729 | 62506752 | 726 ppm | `build/test/clock-calibration/qemu/run-03d5d857c837/result.json` |

HPET 首样本因端点跨度超过规定上限被拒，是实际发生的延迟拒绝。两次都完整复算 accepted/selected 位图、每个错误码、频率交集、中位数和实际平台频率，且源码前后一致。客体也保存了可信 ACPI FADT/DSDT 原始字节，供电源解析后续验证；保存表本身不授予寄存器写权限。

这些结果验证当前 QEMU/TCG 下的校准行为，不替代真实 TSC-deadline 硬件或 P6 Linux/KVM 的 ≤0.5 秒门槛。桌面帧率与缩放动画另由不带调试断点的实测门禁验收。
