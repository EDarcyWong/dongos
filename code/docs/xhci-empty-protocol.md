# xHCI 空 SupportedProtocol 范围

实际首轮 QEMU xHCI 启动在 precheck 返回 `0x08110002`，phase0、held0，尚未启用 BME。只读 BAR 取证保留于 `build/test/p8-xhci/qemu/run-822f626b7974/failure-capabilities.json`：USB2 项 `0x02000402 / USB / range0x401`，后接 USB3 项 `0x03000002 / USB / range1`。后者 count 为0，旧实现直接拒绝。

[QEMU 官方 xHCI 实现](https://raw.githubusercontent.com/qemu/qemu/master/hw/usb/hcd-xhci.c) 在端口数量为0时仍发布对应协议项；USB2 offset 为 USB3 端口数加1，USB3 offset 为1。因此空区间也可能位于控制器端口范围的末端加1。

候选仅修改 `precheck` 的范围条件：`1 <= start <= MaxPorts+1`，`count <= MaxPorts+1-start`。非空区间仍完全位于真实端口内；空区间不进入映射循环，不写入任何 `protocols[]` 项。协议名称、major、PSI/保留位、slot、next 链及所有其它 controller 函数保持原有校验。

候选与精确 SHA 位于 `build/test/p8-zero-protocol-candidate/promotion.json`。`tests.test_xhci_empty_protocol` 使用真实 precheck 和独立 C MMIO 模型，逐字复刻客体 BAR；两种编译模式20个寄存器场景与7种实际坏源码，共54次执行通过。覆盖 USB2/USB3 双向零端口、空区间不授权、错误名称/major/slot/范围、链截断及输出不提前发布。模型禁止写寄存器、启用 BME或修改 DMA 缓冲区。

既有 `tests.test_xhci_controller` 通过 `DONGOS_XHCI_CONTROLLER_ROOT` 指向该候选，原30个 reset/start/NoOp/MMIO/错误场景在 debug/release 共60次执行全部通过，前后源码指纹一致。回归目录记入同一 manifest。

这是候选原生验证，尚不能替代推广后的真实 QEMU xHCI 启动复验。
