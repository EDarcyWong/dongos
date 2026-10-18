# NVMe Bus Master 授权策略

`services/drivers/nvme_authority.dg` 是内核开启 PCI Bus Master 前的纯策略。它只读取内核提供的可信快照，不执行 MMIO、PCI 配置、DMA、内存分配、释放或回调。`permit(header:*const Header)!u16` 成功返回保留其它 PCI command 位并置 BME 的目标值；所有拒绝返回 `Denied=0x0522_0001`。输入保持不变，策略本身不修改任何外部状态。

`Header` 为 128 字节，16 个字段依次均为 `u64`：

| 字段 | 可信来源与约束 |
| --- | --- |
| cap, version, physical_bits | 实际 BAR0 的 CAP/VS 和内核 CPU 能力；调用正式 `drivers.nvme_core.limits`，深度固定 2，接纳其 NVMe 1.0–1.4、4KiB、NVM Command Set 子集 |
| bar_bytes | 内核实际探测并完整授权的 BAR0 范围；包括最后一个 I/O CQ1 doorbell 的完整 dword |
| lease_physical, lease_bytes | 内核独占、完整映射并保留的 4KiB 对齐 128KiB lease；PA 非零，整个范围低于或恰好终止于 4GiB |
| pci_command | 内核读取的 16 位 command；I/O decode=0、Memory=1、BME=0、INTx Disable=1，其余位保留 |
| cc, csts, intms | 实际寄存器；分别精确等于 `00460000`、`0`、`ffffffff` |
| aqa, asq, acq | 实际寄存器；分别精确等于 `00010001`、lease PA、lease PA+`1000` |
| msi_disabled, msix_disabled | 内核遍历真实 PCI capabilities、禁用后读回得到的证据；缺少对应 capability 时也由内核确认；值精确为 1 |
| lease_exclusive | 内核的实际角色、lease token、唯一取得路径和保留所有权共同保证的证据；值精确为 1 |

这些来源必须由内核建立。服务不能上传快照、选择队列 PA、PCI command 或自行声称已停用中断。内核仍须对 BME 进行一次性、不可重复的写入和实际读回；即使操作失败也必须保留 lease，并阻止不确定状态下的重试与释放。

策略独立检查固定的七个半开区域，均完整落入 lease 且两两不重叠：Admin SQ `[0000,1000)`、Admin CQ `[1000,2000)`、I/O SQ `[2000,3000)`、I/O CQ `[3000,4000)`、PRP list `[4000,5000)`、Identify `[5000,6000)`、I/O data `[6000,17000)`。数据保留 17 个页面，可容纳最大 128 sector 加首个页面内最多 4092 字节偏移。固定 core 常量也须与这些区域一致。doorbell 步长来自 CAP.DSTRD；要求 BAR 长度至少 `1000 + 3 * stride + 4`。

这证明的是开启 BME 当时的可信配置、所有权与固定协议布局。I/O SQ/CQ 随后由正式 core 的 Create Queue 命令在 Admin 队列注册；硬件没有对应的可读基址寄存器供该策略提前核对。它不建立 IOMMU 隔离，也不限制已取得整个 BAR/DMA 写权限的恶意服务或恶意设备。FLUSH 成功也不代表 Controller Shutdown 完成或 DMA lease 已可回收。

接口与寄存器语义依据 [NVM Express 1.4c](https://nvmexpress.org/wp-content/uploads/NVM-Express-1_4c-2021.06.28-Ratified.pdf) §3.1、§7.6。其 §3.1.3 的 INTMS 31:0 为读回当前屏蔽状态的字段；配置 MSI-X 时访问 INTMS 未定义。因此 MSI-X 停用和读回须发生在服务访问 INTMS 之前，而非只在最后授权时补记一个标志。版权 © 2007–2021 NVM Express, Inc.

原生复验命令：

```powershell
python -m unittest tests.test_nvme_authority -v
```

独立 C oracle 在 debug/release 各执行 770,448 个快照检查，覆盖全部 PCI command、Admin SQ/CQ 深度字段、CAP.MQES、VS 次版本空间、全部 CAP.TO/DSTRD、全部 lease 长度边界、字段高位和随机物理范围。失败时验证输入与输出哨兵完全不变；实际 guard pages 位于输入和输出末端。三个实际编译执行的坏策略分别忽略 INTMS、接受 lease 外的 Admin SQ、漏掉最后一个 doorbell，均由指定负控捕获。

最新证据保存在 `build/test/nvme-authority/run-b929dc5ef9ae/validation-summary.json`；源码指纹未变化，ELF64/COFF 均实际汇编。正常策略调用链含返回地址和保存 RBP 共 592B，排除不可返回的外部 panic 实现；整份生成模块最大单帧 448B（包含编译器输出的未被策略调用的 core 函数）。正式策略 SHA256 为 `b9005802d8a6c39273f34abaa64709d13bca6abd95f4e00e3c01fa20b575ac0a`，依赖正式 core SHA256 `be7f06028a34055f82ad22889a34d14b9a041f3d46461e5dfecf190e66e6b62c`。此前 `run-a894f872edee` 使用旧 Identify 语义的 core，保留为历史证据。该证据只包含原生纯策略复验，不声称真实控制器、客体读写或重启已通过。

正式 PCI broker 的额外复验为 `python -m unittest tests.test_nvme_broker tests.test_ahci_broker -v`。NVMe 测试原样提取 `kernel/user/devices.dg` 的完整 1390B `interrupt_caps` 和 4272B `grant`，分别记录字节范围、完整源码 SHA 和函数 SHA；仅外围 MMIO、16-bit PCI control、映射和 capability 安装使用明确的 typed stubs。独立 C 配置空间模型在 debug/release 各执行 131,601 个场景，覆盖全部 65,536 种 MSI 和 MSI-X control、48 节合法链和循环链、坏指针、重复 capability、MSI/MSI-X 各自写不清时的实际读回，以及失败后 sticky grant。实际 PCI control 只允许 16-bit 写；Status 和 capability header/next 不得变化。初次 PCI command 清除读回失败时，没有 capability、BAR、映射或 handle 写入尝试。

四个实际编译执行的坏 broker 分别跳过 capability 禁用、跳过 control 读回、用 32-bit 错写 capability、跳过初次 command 读回，均被独立模型在危险的后续事务处捕获。正常模型 ELF64/COFF 均实际汇编，生成最大单帧 240B，证据为 `build/test/nvme-broker/run-3b66ceab0ee8/validation-summary.json`。AHCI/VirtIO 原 C 模型保持不变，回归证据 `build/test/ahci-broker/run-c9ab08428dba/validation-summary.json`（290 个场景、12,679 个断言/模式）。这三个原生测试联合通过，20.281 秒，正式源码指纹均未变化；它们不执行实际 UC scratch window、页表、SMAP 或完整 capability table 实现。
