# xHCI 内核 BME gate 候选

2026-10-18更新：本模块已迁入正式 `services/drivers/xhci_authority.dg`，真实kernel syscall67已调用。完整USB首启动`usb-runtime/qemu/run-291dbcf8b5b7`在controller phase6被gate拒绝；只读诊断`run-b70f73b79ba5`保存了完整128KiB内核DMA快照、16项interrupter及扩展链。独立比较DMA每字节与精确初始布局相同、全部interrupter符合合同；USB2为4端口，后随count0/start1的USB3项。内核旧规则拒count0，与已修正的controller预检不一致。

正式规则现允许`1 <= first <= MaxPorts+1`且`count <= MaxPorts+1-first`；空范围覆盖零端口，实际端口仍须完整、无重叠覆盖，其余name/version/slot/保留位/链检查保留。正式默认路径原生复验`p8-xhci-authority/run-80187ab3b033/validation-summary.json`通过：两模式各8612检查，另七类真实坏源码各两模式拒绝，包括旧拒空规则、缺覆盖和缺重叠；计16次native执行。原测试默认旧候选路径也已改为正式源码，独立候选可显式环境变量覆盖。修后真实启用/枚举/读写仍待当前新构建复验，不能将native或这次失败采样称作USB成功。

下文保留最初候选的合同和历史证据；“尚未迁入”与“尚未调用”的旧时间状态以本段更新为准。

纯模块 `build/test/p8-xhci-candidate/services/drivers/xhci_authority.dg` 尚未迁入 production。它不读取 MMIO、不改 PCI、不启动 DMA、不释放租约，只接受**内核独立构造且稳定的**权限/寄存器/DMA快照；成功返回 planned PCI command（原值 | 4）。客户端 `controller.Setup` 或 CPL3 提供的 Header 不得直接作为输入。

`Header` 248B，`Bounds` 64B，`Registers` 48B，单项 `Interrupter` 40B，`Extension` 48B。`shape(Header*,Bounds*)` 先验证授权/布局并给出安全读取边界；`permit(Header*,Registers*,Interrupter slice,Extension slice,DMA slice)` 重新验证 shape，再检查精确初始配置和 DMA。输出仅成功时改变。两个函数都要求输入、输出及快照内存合法、稳定、互不别名；Header/lease 身份信息必须来自内核 handle/设备 ledger/分配器，而非调用参数中的用户声明。

## 内核调用顺序

1. 验证 syscall 0x67 只含 caller-owned CONFIGURATION cap、其它参数为零，拥有 XHCI 管理角色且匹配已绑定 BDF；取 caller slot/incarnation、binding token/role/owner/incarnation、DMA token/owner/incarnation、BAR/lease 排他归属及映射性质。拒绝已经尝试过 BME 的同实例。
2. 锁定设备/租约并阻止同 owner 的其它执行上下文修改 MMIO/DMA；重读 identity/class/header、PCI command 和 MSI/MSIX。BAR 为已映射 UC、排他 grant；DMA 为该实例排他私有 NX（允许受控内核 alias），全跨度可在内核安全读取。单 CPU 用户线程在 syscall 中暂停不自动替代未来 SMP owner 冻结。
3. 有界读取 CAPLENGTH/HCIVERSION、HCSPARAMS1/2、HCCPARAMS1、DBOFF、RTSOFF、PAGESIZE，再调用 shape。**先检查边界再读**其它 MMIO；不能先对未验证 offset 做 volatile_load，随后才调用纯策略。
4. 根据 Bounds 读实际 operational registers、全部报告的 interrupters 和扩展链。每个扩展头的下一项/长度也先检查 BAR 边界；最多 64 项；不能按用户自报链读取。快照数组放内核预留/动态分配的私有存储，不能把最多 1024 项 interrupters 和 64 项 extension 放 4KiB 内核栈；也可以显式把支持数量限制为可容纳的控制器子集。
5. 在内核 owned alias 中读取稳定 DMA（slice 长度必须完整 128KiB，当前 permit 只检查初始可达前 16KiB），调用 permit。成功后先将 per-instance `attempted` 永久置 1，再写 PCI command并读回。读回/写入不确定也不允许再次 enable；可尝试关闭 BME，但继续隔离并保留 RAM/句柄所有权。
6. 成功返回后服务提交 ERSTBA，继而 Run/NoOp。ERSTBA high 可立即 DMA 读取 ERST，因此 gate 要求它此时仍为零；绝不能为了“地址全配置”提前写 ERSTBA 后才开启 BME。旧 epoch/退出/拔出走外层隔离，不能信用户“已 reset”而 free。

## 精确允许条件

Header 要求 owner/incarnation 非零，binding 和 lease 的 owner/incarnation 都相等；binding role=4、token 非零、排他 BAR/lease、UC BAR、私有 NX lease、attempted=0、实际 class=0x0c0330、type0 header。PCI command 的 I/O=0、Memory=1、BME=0、INTx Disable=1；MSI 和 MSI-X 都已关闭。物理宽度 32–52 位，BAR power-of-two 4KiB–256MiB、页对齐、不跨 CPU 物理范围且不与精确 128KiB、页对齐 lease 相交。AC64=0 时整个 lease 在 4GiB 内。

只支持 xHCI 1.0/1.1/1.2、4KiB page、最多 32 ports、1–1024 interrupters、最多启用 8 slots、无 scratchpad。分别验证 operational+port span、**完整 runtime/interrupter span**及全部 advertised slot doorbells 的 BAR 边界与互不重叠。扩展链只允许已完成 OS ownership/BIOS-clear/SMI-zero 的单个 LegacySupport，以及标准隐式速度 USB2/USB3 SupportedProtocol；拒绝未知能力、自定义 slot/显式 PSI、重叠或未覆盖的端口范围。无协议表控制器目前也明确拒绝。

Registers 要求 USBCMD=0、USBSTS 仅允许 HCH=1 与可选 PCD（拒绝 HSE/HCE/CNR/EINT 等）、DNCTRL=0、DCBAAP=lease、CRCR=lease+4096|RCS、CONFIG=min(MaxSlots,8)。primary interrupter IE=0、IMOD=0、ERSTSZ=1、ERSTBA=0、ERDP=lease+8192；其余所有 interrupters 必须复位为零。允许 primary IP=1，因为它不启用中断。

DMA 前 16KiB 必须恰好为：空 DCBAA、空命令/event 环，command[255] 为正确环内 Link/TC 且 cycle 未发布，ERST[0] 指向 lease+8192、size=256、保留位零，其余字全零。策略不把用户 descriptor 中的 PA 当 CPU地址，不扫描非初始可达工作区。测试还将这些固定 offsets 与正式 `usb.xhci_controller` 常量相互核对。

此 gate 只核对**初始准入状态**。开启 BME 后可写 DMA/寄存器的驱动和真实设备仍需受控代码、生命周期隔离及后续 IOMMU；不能把初始快照通过宣称为恶意 DMA 硬件隔离。BME 期间始终保留 lease，真正回收另需实际停机、旧事件/DMA 失效及所有 alias 生命周期证明。

## 复验

`python -m unittest tests.test_xhci_authority -v` 两项通过（6.211秒）。debug/release 各执行 8600 次独立检查，翻转 owner/世代/权限、全部 16 项 interrupter 字段、2048 个初始 DMA qword、控制寄存器，以及尺寸/边界/扩展链/输出保持。两种目标 object 格式均汇编。4 个真实坏源码副本放行旧 ERSTBA、忽略 binding owner、错误 Link PA、只查 primary interrupter，编译链接后均被独立模型拒绝。

最大单函数直接栈 560B；含 saved RBP、return address、外调栈参数的完整直接调用链 1328B（panic 路径另计）。没有 privileged 指令或 MMIO/PCI 执行。证据位于最新 `build/test/p8-xhci-authority/run-*/summary.json`，源码 SHA256 为 `b88aa30ac96dbc072104dd8c63bbea82de64282ac0aadccbfce3207717edc46a`。尚未实际调用 kernel gate 或运行 guest。

依据：[Intel xHCI 1.2b](https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf) §4.2、§4.9、§5.1/5.4/5.5，及 [QEMU xHCI](https://qemu.googlesource.com/qemu/+/916bf7f93793df8690f48111207961a85f5a25b1/hw/usb/hcd-xhci.c) 的 reset 和 ERSTBA 激活行为。与正式控制器合同配套，但允许内核更严格拒绝不支持的硬件子集。
