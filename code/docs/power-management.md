# ACPI 关机和重启

shell 新增 `shutdown` 和 `reboot`：先完成文件系统 FLUSH，再使用 shell 独占的电源能力调用 `0x78`。其它服务不持有该能力。内核同时检查当前进程、句柄种类/写权限/对象及同步 IPC 完成状态；无效或不支持的计划在端口写入前拒绝。执行后若仍返回，向调用者报告错误，不把“已发出写入”当作成功。

早期启动在原固件映射仍有效时，通过一次受限 Reader 收集并重新验证 RSDP/XSDT/FADT/DSDT/SSDT。持久状态仅保存计划值和错误；窗口消费时清零 BootInfo/map 身份，不保留 Reader 或固件切片。采集失败禁用电源操作，正常启动继续。

当前执行器明确限定 Q35：FADT reset 为 I/O `0xcf9` 的 8 位写，S5 为 I/O `0x604` 的 16 位 PM1a 控制。静态 AML 解析器有界遍历命名空间，隔离方法/缓冲区载荷，拒绝动态求值、歧义 `_S5`、不匹配 GAS 和不支持的硬件缩减模式。S5 要求 SCI_EN 已置位，两次 RMW 保留睡眠字段外的控制位。其它平台地址/MMIO/SMI 交接仍需独立授权和实现。

实际客体证据：

- 构建：`build/test/p7-p8-integration/build-e988c629592f`，完整源码/产物指纹保持一致。
- `build/test/p8-power/qemu/run-ade7a9653793/result.json`：4 次实际 QEMU 启动，关机和重启均通过。
- 关机观察到 QMP `SHUTDOWN`，`guest=true, reason=guest-shutdown`，随后实际状态为 shutdown；RAM 中请求计数 1、action 2。实际 VirtIO 请求头 type 4、完成状态 0，完成计数从 3169 到 3171。
- 重启观察到 QMP `RESET`，`guest=true, reason=guest-reset`，随后重新进入内核、5 个私有服务和桌面；重新读取原磁盘中的 NOTE 文件。
- 两条路径均保留串口中 `DONGOS_POWER_SYNCED` 先于对应内核请求标记的证据。未用 QMP 复位/关机或 debug-exit 代替客体电源操作。

复现：

```powershell
python tests/run_power_qemu.py --reuse-esp build/test/p7-p8-integration/build-e988c629592f/esp
```

实际权限负控为 `build/test/p8-power/permissions/run-bf4141101654/result.json`：两个独立恶意 compositor/shell ELF，生产内核和其它 bundle 项完全不变，分别执行 8/13 次无权限或无效动作请求。逐项精确错误码、实际用户 ELF 和内核代码、页权限、能力表、内核错误计数均通过；请求计数/最后动作保持零，未出现客体 RESET/SHUTDOWN。早期 Reader 身份字段也实际读回全零。首轮 `run-50d0c835dc9c` 因检查器错误地要求所有上级页项 USER=0 而中止，保留原结果；修正为逐层有效权限、仍严格核对 supervisor RO/RX 叶项后重跑通过。该失败客体实际已启动一次，旧结果中的零次计数未覆盖原始启动日志。

```powershell
python tests/run_power_permissions_qemu.py --reuse-esp build/test/p7-p8-integration/build-e988c629592f/esp
python -m unittest tests.test_power tests.test_power_runtime -v
```

正式原生 7 项检查通过，固定实际 Q35 ACPI 样本于 `tests/fixtures/acpi-q35/`；独立 C/AML 模型覆盖 GAS、源表身份、完整失败不变、精确端口操作顺序和实际坏实现。生产特权汇编另行组装。当前 QEMU 没有精确 PM1/CF9 写值 trace，实际电源事件与原生 I/O 模型分别保留其证据范围。设备 DMA 租约未在此路径回收；通用设备退休、真实硬件关机及 VMware 电源兼容仍待后续验证。
