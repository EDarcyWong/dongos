# xHCI 传输核心候选实现

当前源码已迁入正式 `services/usb/`，原候选路径与原生证据保留作历史快照；完整接口/迁移说明见 [USB 设备运行时](usb-device-runtime.md)。以下候选阶段记录不代表真实 USB 客体验收。
正式源码位于 `services/usb/`，历史候选及证据保留在 `build/test/p8-xhci-candidate/`。已完成实际 MMIO/NoOp 执行器和设备枚举/HID/BOT 的原生复验，见 [控制器执行器](xhci-controller.md) 与 [USB 设备运行时](usb-device-runtime.md)；仍未取得真实客体 USB 执行证据。不得据此关闭 PLAN 的 P8 驱动/真机条目。

实现依据 [Intel xHCI 1.2b 规范，625472](https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf) 的环、TRB、上下文和控制传输定义。当前范围有意有界：每环一个在途提交、单内存段、16至256个TRB、单次最多8个TRB、直连根端口、非Hub、无stream/isochronous/USB3 burst。BSP及DMA权限须由系统整合层提供。

| 模块 | 实际提供的接口 |
| --- | --- |
| `usb.xhci_trb` | 16B TRB布局；NoOp/EnableSlot/DisableSlot/AddressDevice/ConfigureEndpoint/EvaluateContext命令；Normal与Setup/Data/Status控制传输；命令/传输/端口/主控事件解码 |
| `usb.xhci_ring` | producer初始化、纯plan、fence/cycle最后发布、Link/TC回绕、匹配完成；event消费者cycle回绕、ERDP与单段ERST |
| `usb.xhci_context` | 32/64B InputContext；根端口Slot、EP0及单packet bulk/interrupt endpoint；DCI与USB轮询间隔换算 |

## DMA 与发布合同

CPU pointer与总线physical分别传入，绝不把PA转为可访问指针。Region检查32至52位地址范围、长度减法边界、alignment及申请区域；单TRB数据不得跨64KiB，环段/上下文不得跨4KiB。初始化和所有unsafe参数都要求调用者拥有稳定、互不别名的私有对象与DMA范围；全局租约排他性、缓存类型及与其它设备/进程的隔离由内核授权层核验。

producer先纯编码Plan，预检失败不改变状态、DMA或输出。publish重新核对完整Plan，再把全部TRB以反向cycle写入，调用fence阶段1。之后才发布Link和后续TRB，最后发布第一TRB并调用fence阶段2。调用者在publish成功之后才能敲doorbell。回调重入被Busy拒绝，防止同一环在半提交时被再次修改。

命令或整个控制序列只有一个在途提交；transfer仅最后TRB可以IOC，短包中间事件仍保留pending，等终结Status事件才完成。完成检查controller epoch、软件generation、提交TRB的精确物理位置、slot/endpoint与残余长度。出现错误完成、写屏障失败或读回不一致时标fault，保持held/pending，禁止再次提交；本模块不提供凭软件声明归还DMA的接口。预检失败与发布后的硬件故障有不同副作用合同，不能称后者完全回滚。

event consumer先检查cycle再读DMA payload，fence阶段3后重读control确认稳定。消费event不重写设备拥有的TRB，只推进软件head/CCS，调用者据ERDP接口更新硬件。当前不接受EventData cookie事件，也不把cookie当PA。Ring generation用于软件请求关联；xHCI命令事件本身没有软件CID，不能据此宣称可以识别控制器恶意伪造的、在TRB物理位置再次复用后内容完全相同的历史完成。DMA恶意设备隔离仍属于IOMMU整合义务。

上下文输入在所有校验完成后才写入，预留字段全零；EP0默认控制类型、CErr、packet与dequeue cycle有明确编码。配置只支持普通bulk/interrupt，拒绝低速bulk、非法packet/interval和与上下文相交的ring。USB SET_ADDRESS通过AddressDevice命令执行，控制TRB编码器拒绝直接发送该标准USB请求。

## 独立执行测试

`python -m unittest tests.test_xhci_core -v` 自动选择候选源码，迁入生产后改用生产路径。debug/release均实际执行同一Dong源码，独立C“硬件”只读取真实DMA TRB字节，检查cycle可见性、Link/TC、环和事件回绕、输入/输出32/64B上下文及保留字节、控制短包与最终完成。屏障三个位置故障、重入、坏指针/世代/完成、篡改Plan、计数耗尽和lease保留均有检查。

两个真实坏副本分别清除Link的TC位和移除发布前fence；同一独立模型必须在两模式中拒绝。测试保存源SHA、编译/汇编/链接/执行命令与结果，候选源码尚无真实控制器或CPL3 USB服务验收。

## 接入顺序

1. 内核给独立USB服务发放所绑定的xHCI BAR和排他的DMA租约，验证停机/复位与bus-master状态；禁止普通程序自选控制器角色或物理地址。
2. 有界解析CAPLENGTH/HCSPARAMS/HCCPARAMS/DBOFF/RTSOFF、BIOS/OS handoff、scratchpad和PAGESIZE，建立DCBAA、命令环与event环；先做真实NoOp命令完成。
3. 端口复位、EnableSlot、AddressDevice和EP0 GET_DESCRIPTOR，再配置HID/bulk endpoint；按SupportedProtocol核对端口speed语义。
4. 以实际USB键盘/鼠标产生输入事件，USB mass storage通过BOT/SCSI接块接口；对实际USB盘做文件读写、FLUSH和同盘重启。
5. 再验证Hub/USB3设备组合、拔插、故障撤权与安全回收。至少一台台式机和一台笔记本仍需实际硬件验收，VM不能替代。

P6剩余依赖是实际AP运行队列/迁移/抢占、多进程CR3/xstate一致性、并行服务启动和统一计时/压力；原Linux/KVM≤0.5秒门槛仍保留。这里的USB核心不改变该阶段状态。
