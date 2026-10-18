# USB 设备枚举、boot HID 与 BOT

`services/usb/` 已包含正式 TRB/ring/context/controller/descriptor，以及本轮新增的 `transport.dg`、`enumerate.dg`、`hid_boot.dg`、`bot.dg`。迁移保留了 `build/test/p8-xhci-candidate/` 的历史源码和原生证据。本轮没有运行虚拟机；真实 MMIO 服务权限、通用控制器命令/控制与批量执行器、USB 事件共享及块服务仍由 root 接入，不能据此关闭 P8 客体或硬件验收。

## 传输合同

`transport.Ops` 为 56 字节，包含 reset_port、command、control、bulk、recover_endpoint、now、fence 七个回调。`Buffer` 分别包含 bus PA、CPU VA、实际长度；回调不得把 PA 当 CPU 指针。所有对象、数据和租约在完成前必须稳定、排他，普通进程不能自选物理地址或角色。

| 回调 | 输入及完成责任 |
| --- | --- |
| reset_port | 根端口编号、绝对 TSC deadline，返回真实 connected/speed；执行 PORTSC 正确的 reset/状态确认，不能只报告策略成功 |
| command | 实际 `xhci_trb.Command`、deadline，返回 completion slot；执行命令环、匹配完成及 DMA 输入上下文可见性；EnableSlot 返回 1–255，其它命令必须返回原 slot；整合层再限制为已启用 slot 范围 |
| control | slot、私有 EP0 Producer、**实际 56B ControlPlan（Setup/Data/Status TRB）**、Buffer、deadline、actual 输出；actual 只计数据阶段，不把 8B Setup/Status 算入；无数据请求必须 actual=0 |
| bulk | slot、USB endpoint address、私有 Producer、Buffer、deadline、actual 输出；返回实际 USB 字节数，不把设备相关处理字节数混入；生产 xHCI 接线须编码 Normal TRB 并使用同一环的发布/匹配完成 |
| recover_endpoint | slot、USB endpoint address（0 表示 EP0）、Producer、deadline；必须实际完成 xHCI ResetEndpoint/SetTRDequeue、处理旧事件并恢复软件环一致性后才返回 0，不能仅清软件 pending/fault |
| now / fence | 单调原始 TSC；DMA/设备内存实际屏障，含编译器屏障 |

回调状态：0 成功、1 STALL、2 Timeout、3 未知 I/O 故障、4 拔出、5 不支持；其它值为协议错误。Deadline 按校准频率计算，每阶段最多 5 秒；回调负责实际等候、截止时间与硬件完成，不得阻塞无界。控制和批量回调成功时必须设置 actual 且不超过 Buffer；不能通过假完成清掉仍由设备拥有的 DMA。

## 直连根端口枚举

`enumerate.Setup` 96B，`State` 1784B；State 必须先全零。初始化检查 BAR 之外的私有 DMA 区域、地址宽度、CPU/总线对齐与 DCBAA 不重叠、频率/timeout/epoch，随后持有 DMA。任何后续错误保留 held、关闭 READY，交给外层隔离和安全回收。

实际调用顺序为 reset_port → EnableSlot → 写私有 DCBAA/EP0 InputContext → AddressDevice → GET_DESCRIPTOR(Device,8) → 必要时 EvaluateContext 只加 EP0 flag=2 更新 MaxPacket → Device18 → Configuration9/完整配置 → SET_CONFIGURATION → ConfigureEndpoint → HID SET_PROTOCOL(0)。Boot keyboard 还要求 SET_IDLE(0)；boot mouse 的 SET_IDLE 是可选项，本模块不会要求它。

每设备固定 32 KiB 私有 DMA 工作区，另借用控制器 DCBAA；在 128 KiB 控制器租约中可从 16 KiB 起顺序放三个实例。

| 设备工作区偏移 | 用途 |
| --- | --- |
| 0 | 32/64B InputContext（33 项） |
| 4096 | Output DeviceContext |
| 8192 | EP0 256 项传输环 |
| 12288 / 16384 | IN / OUT 256 项传输环 |
| 20480 | 最多 4096B descriptor/control 数据 |
| 24576 | 可供 BOT 使用的独立 512B scratch |
| 28672 | 可供小批次块读写使用的独立 4096B 数据 |

当前每设备只选择一个 boot HID 或 BOT interface，多个复合 interface 明确拒绝；descriptor 层本身仍可解析复合配置。Hub、非零 altsetting、UAS、USB3 burst/streams 等尚未支持。QEMU 默认 SS storage 的 burst=15 会明确拒绝，不能忽略该字段后加载不完整上下文。第一轮实际存储可在受控 USB2 root 配置协商 HS，再扩展 USB3。

## boot HID 与 input4

`hid_boot.Keyboard` 120B，`Mouse` 8B；调用前必须成功 SET_PROTOCOL(0)。键盘处理 8B boot report，转换为与既有 `input.events` 相同的 Linux evdev KEY、修饰键/锁定状态、按下/释放；重复相同报告不制造假按键。显式 `repeat` 供系统按自己的 TSC repeat 策略产生 value=2。六键 rollover/error、重复 usage、短报告和队列空间不足会清该设备状态并产生 LOST。鼠标接受 boot 前三个字节，输出有符号 x/y 与三按钮 KEY；附加 wheel/report-protocol 字段不作已支持声明。

每设备必须有自己的私有事件 Queue。LOST 会清该队列并表示释放该设备状态；合入 input4 需保留来源/每设备 held 状态或按键引用计数，不能让 USB release 清掉 PS/2 仍按住的同键。F12 映射为既有 evdev 88，可走现有 console 逻辑。

HID 空闲 NAK 正常，中断 IN TD 可以长期在途。不能套用 BOT 同步 bulk timeout 来判定键鼠空闲故障，也不能为了返回 WouldBlock 清 pending。实际控制器需 posted interrupt TD、非阻塞 event poll、完成后解码并重新投递；拔出/硬件错误才进入隔离。

## BOT/SCSI

`bot.Setup` 120B，`State` 232B。只处理 LUN0、单在途命令、单调非零 32 位 tag；不会在 tag 耗尽后复用。初始化实际 GET_MAX_LUN；合法 STALL 时显式调用 recover_endpoint(address=0)，确认 EP0 Producer 恢复才采用 LUN0。随后执行 READ CAPACITY(10)。支持 512–4096B 的 2 次幂 block size；READ CAPACITY 的 0xffffffff sentinel 明确要求未实现的 16 字节容量命令。

`read_write` 编码 READ10/WRITE10，一批 1–8 个块、32 位 LBA，并验证容量、完整 Buffer、64KiB 边界、与 scratch/三条环的物理和 CPU 别名不相交。`synchronize` 编码 SYNCHRONIZE CACHE(10)，不用假写入或主机缓存状态替代。每次实际发送 31B CBW，必要的数据阶段，再读 13B CSW；检查签名、精确 tag、长度、status、residue 范围与 relevant bytes 不超过已传输实际字节。

Residue 是设备**处理/相关**字节的缺口，可能与 USB actual 不同：DATA-IN 可含 padding，DATA-OUT 可以完整接收后只部分处理。本模块允许 actual 大于 relevant；status=1 返回 CommandFailed，合法短处理/短数据返回 Short，不能据此宣称完整块 I/O 成功。初始化失败仍关闭 READY。普通运行中的合法 CommandFailed/Short 不假冒 Phase Error 或强制设备复位；调用方必须把错误反馈给文件/块客户端。

STALL、坏 CSW 或 Phase Error 可走显式 `recover`：BOT class reset → CLEAR_FEATURE(IN halt) → 硬件恢复 IN → CLEAR_FEATURE(OUT halt) → 硬件恢复 OUT，并核对各 Producer。Tag 不回退。Timeout、拔出、未知 I/O、回调协议错误和 tag 耗尽保留 held 且禁止该 USB 级恢复；必须由外层确认控制器/设备停止及旧 DMA 已失效。任何情况下模块都不释放租约。

## 已执行复验与入口候选

独立 C 硬件模型读取真实 DCBAA/InputContext、ControlPlan TRB、CBW/CDB/CSW 与数据 Buffer。覆盖有界 deadline、EP0 MaxPacket 更新、非零 interface、鼠标不接受 SET_IDLE、HID 全 256 modifiers/六键/释放/锁定、65,536 对有符号鼠标坐标及按钮；BOT 包括实际容量/读写/同步、合法短写、padding/部分处理 residue、坏 tag/CSW/phase、GET_MAX_LUN STALL/EP0 恢复、runtime STALL 恢复、timeout/disconnect/IO 隔离。七个真实坏源码副本分别漏 SET_PROTOCOL、Evaluate、signed 坐标、CSW tag、residue边界、class reset 与 timeout 禁重用；必须先编译链接成功再被同一模型拒绝。

正式路径联合复验命令 `python -m unittest tests.test_xhci_core tests.test_xhci_controller tests.test_usb_descriptor tests.test_usb_device -v` 共 8 项通过，耗时 116.979 秒。debug/release 每模式合计 2,067,051 次正向断言、18 个真实坏源码负控；设备运行时为 39 个独立场景、323,407 次断言。四套证据分别为 core `run-8cc1be282aad`、controller `run-8dfc34622472`、descriptor `run-144b819d4a1c`、device `run-8b392097ae7a`，各位于对应 `build/test/p8-*/host/`。所有输入 SHA 前后一致，正式源码与历史候选快照相同；总摘要在 `build/test/p8-xhci-candidate/production-validation-summary.json`。

根整合所需最小接口为：独立 XHCI catalog/slot 与既有 config/DMA 句柄；0x60/61/62/63 读配置/授 BAR0/映射/取 128KiB DMA；新增 0x67 同 NVMe 0x66 形式的可信 BME 门控。内核复核绑定设备身份、BAR、租约/代际、INTx/MSI/MSIX 均禁、HCH/CNR/地址寄存器正确后才开启 BME；此时 ERSTBA 尚为零，下一步提交 ERSTBA 会立即取 ERST。错误/退出继续隔离持有 DMA。

`build/test/p8-xhci-candidate/services/drivers/xhci_service.dg` 是独立 CPL3 **NoOp-only** 入口候选，尚未迁入正式 drivers 或加入 bundle/build。它沿用 Boot.reserved0/1/2 的 ECAM base/first/last 与 reserved3 的 TSC Hz，扫描 xHCI、复用现有 BAR/DMA ABI，要求可信 syscall 0x67 后完成三次实际 NoOp，再发布 `DONGOS_XHCI_NOOP_READY`。不将此标记当成 HID/MSD 就绪。两模式已独立汇编链接 ELF；release 305488B、debug 337152B，最大直接栈预留 784B，证据 `build/test/p8-xhci-service/run-936696dfcee8/summary.json`。服务尚未实际执行，0x67 仍是显式整合依赖；它是 builtin 驱动候选，不能冒充受 256KiB 上限约束的 ordinary EXEC 程序。

规范依据：[USB-IF HID 1.11](https://www.usb.org/sites/default/files/hid1_11.pdf) 的 boot 格式/可选鼠标请求，[USB-IF BOT 1.0](https://www.usb.org/sites/default/files/usbmassbulk_10.pdf) 的 CBW/CSW、residue 与恢复，以及 [Intel xHCI 1.2b](https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf) 的实际上下文/命令完成合同。真实 USB 硬件与 guest 证据仍待 root 后续接入。
