# xHCI 控制器执行器候选

当前源码已迁入正式 `services/usb/`，原候选路径与原生证据保留作历史快照；完整接口/迁移说明见 [USB 设备运行时](usb-device-runtime.md)。以下候选阶段记录不代表真实 USB 客体验收。
`services/usb/xhci_controller.dg` 是实际执行 32 位 MMIO、复位和 DMA NoOp 的正式模块，历史候选快照已保留。本轮只在宿主独立硬件模型执行；未启动 QEMU/VMware，未取得真实 USB 控制器、HID 或 U 盘验收。TRB/ring/context 三个已冻结核心的 SHA 未变。

## 接口与授权边界

`initialize(State*, Ops*, context, Setup*)` 成功前必须完成一次真实 NoOp；`noop(State*)` 随后执行另一次命令。`State` 为 1280 字节私有内存，`Setup` 为 112 字节，`Ops` 为 40 字节；最高直接栈预留 592 字节。对象及回调在控制器使用期间必须稳定、排他且互不别名。

| 回调 | 实际参数及责任 |
| --- | --- |
| read | `(context, BAR handle, offset, *u32) -> status`，只读取一个对齐 DWORD |
| write | `(context, BAR handle, offset, u32) -> status`，只写一个对齐 DWORD |
| fence | `(context, phase) -> status`，1 为发布前、2 为 cycle 发布后/门铃前、3 为 event acquire、4 为初始化 DMA 可见、5 为配置读回后/开启 BME 前；实际整合层提供相应设备内存屏障 |
| now | `(context, *u64) -> status`，返回单调 TSC；以已校准频率计算绝对截止时间 |
| enable_bme | `(context) -> status`，由内核可信接线只启用已经绑定的设备和排他 DMA 租约；没有用户自选 PA 参数 |

`Setup` 含 BAR handle/长度、DMA lease token、分别指定的 CPU VA 与 bus PA、128 KiB 长度、32–52 位物理地址宽度、controller epoch、TSC 频率/超时，以及可信设备 token、exclusive=1、interrupts_off=3、PCI command。初始 PCI command 必须 Memory Space=1、BME=0、INTx Disable=1；MSI/MSI-X 也必须已由可信授权层关闭。输入中的声明只用于合同核对，不产生设备或物理内存权限。内核必须重新核验 BDF/class/BAR、世代、租约归属、缓存类型、IRQ/MSI 状态和 BME；不能把 CPL3 填写的 exclusive/token 当成授权。

DMA 前 16 KiB 固定为 DCBAA（offset 0）、256 项命令环（4096）、256 项事件环（8192）及单项 ERST（12288）；总 128 KiB 的其余区域保留给后续设备上下文和传输。绝不把 PA 当 CPU 指针访问。该布局尚未提供任意驱动分配器。

## 实际执行顺序

先检查 BAR/地址/租约声明和能力寄存器，再发生任何 MMIO 写或 DMA 改写。当前支持 xHCI 1.0/1.1/1.2、4 KiB 页、32/64 字节上下文、最多 32 根端口、启用最多 8 个 slot、AC64 或全部 DMA 位于 4 GiB 以下。只接受隐式标准速度表的 USB2/USB3 SupportedProtocol，以及已完成 BIOS/OS 交接且 SMI 控制全零的 LegacySupport。scratchpad、未知扩展能力、显式 PSI/自定义 slot type 等明确返回 Unsupported；BIOS ownership 仍在时不会假称交接成功。

1. 清 USBCMD.RS，实际等待 USBSTS.HCH。
2. 写 HCRST，分别等待 HCRST 清零和 CNR 清零，再核对 HCH。
3. 清私有 DMA，建立命令 Link/TC、事件环和 ERST，fence phase 4。
4. 禁 IMAN.IE，配置 IMOD/ERSTSZ、ERDP、DCBAAP、CRCR 和 CONFIG；逐项读回。
5. fence phase 5，经可信 callback 开 BME，然后提交 ERSTBA，读回并检查 HSE/HCE/CNR/HCH。**ERSTBA high 写可立即触发 ERST DMA 读取，因此必须在它之前开启已受限的 BME**。这是对照 QEMU 实现补充的必要顺序。
6. 置 Run，实际等待 HCH 清零，发布真实 NoOp，发布屏障后写 DB0。
7. 从实际 event DMA 读取 cycle/type/PA/slot，消费并回写 ERDP/EHB、IMAN.IP 与 USBSTS.EINT。等待期间可接收 PortStatusChange，记录端口位图；匹配完成且主控健康后才置 READY。

所有等待均有单调 TSC 截止时间及一百万次循环硬上限。64 位 MMIO 在 AC64=1 时按低 DWORD、高 DWORD 顺序写；AC64=0 按规范只使用低 DWORD并要求全租约在 4 GiB 内。任何复位/运行/完成超时、回调或屏障失败、寄存器读回错误、坏事件都会关闭 READY、保留 held DMA 并禁止重用。模块没有“软件声明已停止所以释放”的接口；内核整合层负责隔离、停止/复位、确认设备已不再 DMA 后的安全回收。

## 复验与后续接线

`python -m unittest tests.test_xhci_controller tests.test_xhci_core -v` 本轮 4 项测试通过。控制器执行器在 debug/release 各跑 30 个独立场景、1,464,238 个断言。5 个正常场景各完成 301 次 NoOp，覆盖命令 Link 回绕、event cycle 回绕、AC64=0、64 字节 context、4 GiB 以上 DMA，以及每次命令前插入端口事件。其它场景检查 halt/HCRST/CNR/start/NoOp 超时、地址/版本/scratchpad/所有权拒绝、BME 失败、MMIO 读回/屏障失败、TSC 回退、坏完成 PA/slot 和运行 HSE。

C 硬件模型独立解释寄存器和真实 DMA 字节，停机/复位/启动必须经过多个读周期；写 ERSTBA 时真实读取 ERST，并要求 BME 已开启。5 个实际修改后的坏源码副本（删除 halt 等待、删除 reset 等待、写错 ERSTBA、延后 BME、取消完成 PA 匹配）均编译链接成功后被同一模型拒绝。源 SHA 前后相同，证据在 `build/test/p8-xhci-controller/host/run-75e4b13b1cb9/`；摘要在 `build/test/p8-xhci-candidate/controller-validation-summary.json`。

下一步由 root 在受控 xHCI 配置中准入私有 BAR/DMA 并运行本执行器，取得实际 NoOp 完成。之后才做端口复位、EnableSlot/AddressDevice、EP0 descriptor/control TD、HID 和 BOT/SCSI。上述候选不关闭 P8 真实 USB3/Hub/拔插及两台物理机验收。

依据：[Intel xHCI 1.2b 规范](https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf) §4.2、§4.9、§5.1、§5.4/5.5；[QEMU xHCI 官方源码](https://qemu.googlesource.com/qemu/+/916bf7f93793df8690f48111207961a85f5a25b1/hw/usb/hcd-xhci.c) 的 `xhci_er_reset`、oper/runtime register callbacks。AC64=0 按规范实现；当前 QEMU 标准 qemu-xhci 为 AC64=1，真实客体仍待接线。
