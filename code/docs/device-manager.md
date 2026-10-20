# 设备管理与 ISA IRQ 接口

`drivers.device_manager` 是独立 CPL3 ELF。它从内核实际 ECAM 枚举接口读取设备目录，按受支持驱动策略选择设备，经 BIND 再次核对硬件身份后才发布自身 READY。init 可以据此依赖启动块设备与输入服务，再启动文件系统、shell 和合成器。

这里记录已冻结的接口、生产实现与宿主执行证据。完整客体中的 syscall、IDT、实际 IRQ、驱动撤权与恢复由系统整合验收另外确认；宿主寄存器模型不等于实际中断已经递送。

## 授权与设备目录

`lib.device_abi` 为数据模块，`lib.device` 提供 SysV 整数 syscall 封装，内核和用户共用布局。

| syscall | 操作 | 参数 |
| --- | --- | --- |
| 0x90 | ENUM | manager capability, cursor, Device*, 0, 0, 0 |
| 0x91 | BIND | manager capability, device token, role, Binding*, 0, 0 |
| 0x92 | IRQ_BIND | i8042 port capability, IRQ, self incarnation, Irq*, 0, 0 |
| 0x93 | IRQ_WAIT | IRQ token, after sequence, Irq*, flags, deadline TSC, 0 |
| 0x94 | IRQ_ACK | IRQ token, exact sequence, 0, 0, 0, 0 |
| 0x95 | REVOKE | manager capability, device token, device generation, 0, 0, 0 |

公共进程库另有0x86，以自身 endpoint capability 为首参数返回当前进程 incarnation。设备管理器的 Boot.configuration 是设备管理能力；它不直接得到 ECAM 或任意物理内存指针。Device128B：version/token/next cursor/kind/ecam/segment/bus/device/function/vendor/device id/class code/header/flags/generation/reserved，均为u64。PCI kind=1，legacy i8042 kind=2，EOF kind=0；class code 为 class/subclass/interface 拼成的24位整数。

Binding64B：version/device token/role/configuration id/generation/IRQ mask/flags/reserved。角色 BLOCK=1、TABLET=2、PS2=3、XHCI=4。当前 CPL3 manager 自动绑定前三项，XHCI matcher 供后续 USB 接线，不提前声称驱动已运行。块设备优先级与现有块服务一致：现代 VirtIO 1af4:1042、NVMe 010802、AHCI 010601；同优先级选择首次设备，其余保持未授权。VirtIO 平板为1af4:1052，PS2 只匹配内核确认的 legacy 节点。

`user.device_manager` 是内核使用的纯授权账本，最多32个设备、4个角色、2个 ISA IRQ。register只接收内核读出的原始硬件快照；BIND必须再提供一次内核重读身份，账本逐项比较位置、vendor/id、class/header后才接受。用户声称的 class 或复制出的 Device 本身从来不是授权来源。每个角色和设备只能绑定一次；身份替换、重复授权、陈旧 token 都会拒绝。真正的 BAR/DMA 发放还必须核对绑定过的 exact ECAM，不能由驱动自行选择另一个未绑定控制器。

CPL3 manager 在运行期间低频重新枚举，核对已绑定 token、generation、原始身份；设备消失或改变时请求 REVOKE。目录读取失败时先逐一撤回全部已知活绑定，再报告 manager 失败，避免因无法读取目录而留下旧 DMA 权限。撤回必须先由内核屏蔽 IRQ、关闭相应总线主控/完成安全隔离并隔离映射，再提交账本失效。账本不回收、不重用 DMA 租约，不把客体可控的“复位完成”当作安全释放证明。未完成硬件隔离应保留全部租约并报告失败。停止后的对象代际不回绕；用户不能用旧绑定重获新设备权限。

## i8042 IRQ1/12

Irq64B 为 version/token/irq/gsi/vector/generation/sequence/flags。IRQ token 属于该输入进程的能力，generation 是该进程 incarnation。IRQ1/12 固定向 BSP 递送0x51/0x5c，用户不指定目标 APIC、vector 或 IOAPIC 寄存器。sequence从0单调增长，MASKED=1、PENDING=2；重复或跨代 ACK 不会重新打开路由。

`irq.platform.route_isa` 从已验证 MADT 查找 ISO，再决定 GSI、极性与触发模式。ISA conforming flags 使用高电平有效/边沿触发；保留编码、重复覆盖、无匹配 IOAPIC、与现有路由/NMI GSI 冲突均拒绝。ISO 语义来自 [ACPI 6.6 的 MADT/MPS INTI 定义](https://uefi.org/specs/ACPI/6.6/05_ACPI_Software_Programming_Model.html)，IOAPIC mask/remote-IRR 语义参考 [Intel RTE 定义](https://edc.intel.com/content/www/it/it/design/products-and-solutions/processors-and-chipsets/comet-lake-u/intel-400-series-chipset-on-package-platform-controller-hub-register-database/1.2/redirection-table-entry-0-rte0-offset-10/)。

建立路由先 mask并读回，再写目的 APIC 并读回，再写 vector/极性/触发并读回。用户输出指针先完整验证；内核在 masked route 下提交 IRQ账本，最后 unmask并核对，才返回成功。读回容许只读 delivery-status/remote-IRR变化；写入位不符会尝试重新 mask，拒绝成功报告。

ISR顺序是屏蔽对应 IOAPIC 输入、signal单调 sequence、唤醒拥有者、LAPIC EOI；即使通知已陈旧或重复，也必须 EOI。用户先排空 i8042，再以 exact sequence ACK；内核先检查 token/owner/pending sequence，unmask读回成功后才清 pending。失败保留 pending 和 mask。撤权与进程退出先 mask，再使 IRQ token失效。普通轮询可以保留为明确回退；该接口没有宣称支持通用 MSI/MSI-X 或所有 PCI INTx。

## 宿主验证

`tests.test_device_manager` 两模式实际执行生产 manager `service_main`，验证 AHCI+NVMe选择、3种绑定、移除后1次撤回、目录读取失败后全部3次撤回；独立 C 模型验证身份、容量、输出不变、1024次 IRQ signal/wait/ACK/重新绑定，以及旧 owner/代际/sequence拒绝。两个真实坏 Dong 副本分别接受替换设备和陈旧 ACK，均必须被拒绝。

`tests.test_isa_irq` 两模式实际执行生产 IOAPIC 代码，覆盖15种多控制器、ISO、高低电平/触发、GSI/NMI冲突、读取失败、mask与目标读回、EOI场景；另移除两处真实生产读回，严格独立寄存器模型必须拒绝。原 `tests.test_irq_platform` 保留时钟、控制器身份、保留位、deadline次序全部既有模型。所有完整 OS 构建和真实 VM 启动由系统整合窗口串行执行。

## P5 恢复账本候选（尚未接入运行时）

`user.device_manager.recover` 是内核内部事务入口，不增加 syscall，也没有从
`user.device_host` 调用。它只补齐恢复时的账本提交约束；目前驱动故障后的
DMA 仍按原路径永久持有，不能据此关闭 P5 的同次启动恢复或 DMA 回收条目。

调用者必须持有内核串行化锁，并传入可信回调和精确旧设备的内核上下文，
不得接收用户提供的函数指针、上下文或“复位成功”标志。回调必须绑定旧
owner/incarnation、旧 DMA lease 与传入的旧 device token/撤权后 generation；
不得直接修改账本。事务顺序固定为：

1. `quiesce`：硬件停止并确认 DMA 已排空/完成受支持控制器复位。单独关闭
   PCI BME 或 MSI 不构成这个证明。
2. `retire`：旧 owner 的能力、映射和所有 CPU 上的调度/地址翻译引用均已退休。
3. `reclaim`：只回收上述精确旧租约，不允许接触其它 owner 的页。
4. `read`：由内核重新读取完整硬件身份；必须仍为原设备，不自动接纳替换设备。
5. 发布未绑定的新代际，并清除旧角色绑定；新 BAR/DMA/IRQ 授权仍需正常
   BIND 和硬件身份复验。IRQ serial 保留，旧 IRQ token 不会复活。

进入第一个回调前设置 `RECOVERY_HELD`。回调失败、身份改变、读取失败或
重入均不能提前发布新 token。任何可能发生了硬件副作用的失败均保持 HELD，
不自动重试、不允许同 boot 再次回收；即使最后身份读取失败前已经释放了租约，
也不把失败当作重新分配授权。达到终端 generation 前拒绝恢复，保留再次撤权空间。
旧 Table 布局保持4560字节，公共 syscall ABI 不变。

待接线工作仍包括：受支持控制器的可信停止/排空证明；与全核 owner 退休及
`user.memory` 中 pinned frame 管理一致的精确租约回收；清理 `user.devices`
与 `device_host` 的旧授权状态；驱动新代际和依赖服务恢复；同 boot 客体故障注入、
旧句柄/旧 DMA/旧 IRQ 负控与持久化回归。未实现这些回调之前不得调用此入口。

候选测试执行实际 Dong 账本，C 独立回调模型检查顺序、各阶段失败、重入、
身份替换/无效快照、输出不变、跨代旧 token 拒绝、IRQ serial 保留和代际耗尽，
并提供跳过退休/复用旧 token 的真实坏源负控。当前仅完成 debug/release 编译和
C fixture 严格语法检查；本云环境缺 NASM，native 链接执行与坏源负控尚未运行，
更不代表真实 DMA 安全证明或完整 P5 验收。
