# USB 描述符解析候选

当前源码已迁入正式 `services/usb/`，原候选路径与原生证据保留作历史快照；完整接口/迁移说明见 [USB 设备运行时](usb-device-runtime.md)。以下候选阶段记录不代表真实 USB 客体验收。
`services/usb/descriptor.dg` 处理真实 GET_DESCRIPTOR 取得的字节切片。它已迁入正式源码，仍未产生任何 USB 硬件验收；EP0 传输、SET_CONFIGURATION/SET_PROTOCOL 和运行时 HID/BOT 服务仍需接入。

| 接口 | 合同 |
| --- | --- |
| `packet0(bytes,speed)` | 可从首 8 字节验证 EP0 packet；speed 使用 xHCI 标准 1=full/2=low/3=high/4=super |
| `device(bytes,speed,*Device)` | 精确 18 字节 DeviceDescriptor，验证速度/packet、配置数、拒绝 Hub；输出 96 字节 |
| `configuration_bytes(first9)` | 安全取得 9–4096 字节总配置长度，先给 EP0 完整传输分配有界缓冲 |
| `configuration(bytes,speed,*Configuration)` | 要求切片长度精确等于总长度，遍历实际 interface/HID/endpoint/SS companion，输出至多 8 个 Binding；输出共 544 字节，每个 Binding 64 字节 |
| `language(bytes,preferred)` | 验证 LangID 字符串描述符，优先选指定语言，否则第一语言 |
| `string_utf8(bytes,out)` | 两遍验证 UTF-16LE、surrogate 和容量，再转 UTF-8；拒绝输入/输出重叠，返回实际字节数，不附 NUL |

仅选择 HID boot subclass=1 的 keyboard(protocol 1)/mouse(protocol 2)，以及 mass-storage subclass=6/SCSI、protocol=0x50/BOT。HID 必须有一个 Interrupt IN、有效 HID report 长度和足够 packet；BOT 必须有 Bulk IN/OUT 各一个。按速度核对 packet/interval，拒绝端点零、保留位、重复 endpoint、重复 interface、声明数量不符、截断和越界。HID boot 服务仍须发 SET_PROTOCOL(0)，不能直接按 boot 布局解释默认 report protocol。

所有接口失败时保持用户输出不变。配置解析在临时结果完整通过后才提交；字符串转换先验证整个输入及输出容量再写入。数据及输出必须稳定，不能由别的线程/设备并发改写。UTF-8 返回值可以包含 U+0000；调用方必须按返回长度使用，不能当未验证 C 字符串。字符串 descriptor 0 是 LangID 表，必须走 `language`，不能当普通 UTF-16 文本。

当前有界子集拒绝非零 alternate setting、低速 bulk、isochronous、USB3 burst/stream、多 packet transaction、非标准 SS companion。支持 composite 的多个 boot/BOT interface，但不能把“支持 boot”当成已支持任意 HID report descriptor。第一轮 USB storage 可先验证 USB2/HighSpeed。QEMU 默认 SuperSpeed storage 的 bMaxBurst=15 当前明确拒绝；不能忽略它后声称完整 USB3。固定 `xhci_context` 编码器尚未提供 MaxBurst/stream，需统一扩展才可放行。

`python -m unittest tests.test_usb_descriptor -v` 两项测试通过。debug/release 各执行 134,475 次检查、65,415 个 Unicode scalar 样本及所有单独 surrogate；11 个有效速度/类别组合、逐字节截断、256 种 terminal descriptor 长度、复合接口、非法 packet、alternate setting、SS companion 和输出保护均有检查。独立 C 参考编码器比较真实 UTF-8 字节。四个实际坏源码副本分别删除跨 interface 重复 endpoint 检查、descriptor 长度边界、SS burst/stream 检查及 surrogate 配对检查；全部编译链接后被同一测试拒绝。

证据：`build/test/p8-usb-descriptor/host/run-edddc2ac2844/`；摘要：`build/test/p8-xhci-candidate/descriptor-validation-summary.json`。源码 SHA256 为 `3829eaed549ed38d2ad5ba1e4c619c0895d14ebe3023481d6da73dc8388028dc`，两模式最大直接栈预留 1376 字节。原先 xHCI ring/TRB/context/controller 候选未改。

依据：[USB-IF HID 1.11](https://www.usb.org/sites/default/files/hid1_11.pdf)、[USB-IF BOT 1.0](https://www.usb.org/sites/default/files/usbmassbulk_10.pdf) 以及 [QEMU HID](https://raw.githubusercontent.com/qemu/qemu/master/hw/usb/dev-hid.c)/[存储](https://raw.githubusercontent.com/qemu/qemu/master/hw/usb/dev-storage.c) 的标准 descriptor 字段。原生 fixture 按这些接口的 FS/HS 参数构造；SS MaxBurst=0 fixture 是受控合成配置，并非默认 QEMU SuperSpeed 存储。
