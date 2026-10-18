# P3 ACPI 发现与持久拓扑副本

本轮实现 P3 的 ACPI 发现子项：在旧 P1 映射仍可读取固件 RAM 时验证 RSDP/XSDT 及相关表，把有限容量的纯值 Inventory 复制到常驻内核 BSS，再切换私有 CR3。后续路径读取 BSS 副本，不扩大 P2 的固件映射白名单。本轮不配置 LAPIC/IOAPIC/PIC、不启动 AP、不启用 IRQ 或定时器，也不执行 AML、切换 ACPI 模式或访问表中描述的设备寄存器；整个 P3 尚未完成。

## 解析器与支持边界

[firmware.acpi](../kernel/firmware/acpi.dg) 的接口为：

```dong
pub type Reader = unsafe fn(context: u64, physical: u64, length: usize) *const u8;
pub unsafe fn discover(reader: Reader, context: u64, rsdp: u64, out: *Inventory) !void;
```

Reader 必须返回完整、稳定、可读的请求范围，或返回 null；回调上下文、输入表和输出/临时存储不得重叠。物理地址始终为 u64 数值，不能截断成 u32 或直接当作可解引用指针。解析器每次先检查范围，再请求最小头部，核对声明长度后重新请求完整正文。单次请求/单表上限为 1 MiB，所有受支持的物理范围均非零且终点不超过 4 GiB。该上限是当前 DongOS 的平台边界，不是 ACPI 对 64 位表地址的普遍限制。

RSDP 要求 revision≥2、正确签名、首20字节 checksum 和完整声明长度的 extended checksum；不回退到 RSDT。XSDT 使用非对齐 little-endian 读取，检查36字节头、完整 checksum、8字节 entry 整除及最多64个 entry。`table_count` 表示 XSDT entry 数，包含未知 SDT，不包含 RSDP/XSDT 自身。未知 SDT 也先验证完整范围、长度和 checksum，再忽略其内容；重复物理 entry、重复根引用或重复必需表会拒绝，失败不发布部分输出。

| 内容 | 当前契约 |
| --- | --- |
| MADT / `APIC` | 当前 x86 profile 必需且唯一；至少一个 CPU 记录和一个 IOAPIC，支持类型0/1/2/3/4/5/9/10，合法未知类型按长度跳过 |
| CPU | 最多16条；保留 LAPIC/x2APIC 来源、完整 UID/APIC ID 和原 flags，包括 disabled/online-capable 记录；UID与APIC ID分别查重，不把记录数当作已启动 AP 数 |
| IOAPIC / ISO / NMI | 分别最多8/16/16条；保存地址、GSI、ISA覆盖与独立NMI类型，拒绝歧义重复、截断条目及保留的极性/触发编码2 |
| LAPIC override | 最多一条，覆盖 MADT 头中的32位 LAPIC 地址；地址只保存，不启用 x2APIC 或访问 MMIO |
| FADT / `FACP` | 必需且唯一；至少116字节已知前缀，扩展字段按完整长度存在性读取；非零 X_DSDT 优先于 legacy DSDT，仅保存地址，不解析 AML |
| HPET | 可选，缺失时相关值为零；当前 Inventory 只有一组 HPET，第二张返回 Capacity，而非声称规范禁止多张 HPET |
| MCFG | 可选，最多8个 allocation；44字节、零 allocation 的合法表保留 MCFG PA，`mcfg_count=0`，与整表缺失区分 |

FADT 保存 SCI、boot architecture、fixed flags、legacy PM timer、扩展 PM timer GAS、reset GAS/value 等原始信息。GAS 的有效访问范围按 bit width/offset 和 access-size 的完整访问单元计算；IO端点不越过64 KiB，system-memory范围不越过当前4 GiB边界。非零 PM timer 扩展寄存器为32位、offset0，实际计数位数仍由 FADT 的24/32位标志描述。reset_supported 时校对完整8位 reset 字段，但不执行 reset。

HPET 历史 GAS 中的 width/offset/第四字节按原值保存，不强制 width64/access4；当前只支持 system-memory 地址，验证1 KiB对齐及完整范围、页保护低四位。MCFG 允许非零 segment 和非零起始 bus，检查1 MiB对齐、bus范围、完整 ECAM 端点及冲突；ECAM基址对应bus0，实际区间按起止bus偏移形成。上述设备地址均未被当作 ACPI RAM 读取，也不证明设备寄存器已经核验或可用。

错误码位于 [acpi_errors.dg](../kernel/firmware/acpi_errors.dg)，依次区分 InvalidRange、Unreadable、BadSignature、BadLength、BadChecksum、Unsupported、Duplicate、Capacity、Malformed、MissingRequired（`0x03010001`～`0x0301000a`）。未知表类型、保留高位与合法追加尾字段不能被误写成一律无效；当前有限 profile 的限制与规范事实分开记录。

## 旧映射读取与 BSS 生命周期

[boot.acpi_startup](../kernel/boot/acpi_startup.dg) 提供 `prepare(info)`、`inventory_pointer()` 和 `report(out)`；`prepare_with(reader,context,rsdp)` 使用同一发布路径，供独立 native 回调验证。`prepare` 在 `dong_memory_startup` 和原内存预检成功之后、首次 CR3/永久换栈之前调用，不打印成功报告、不改 CPU 控制位或资源表。

正式 Reader 先校验 BootInfo-v1、descriptor version1及整个最终 UEFI raw map：非空且不超过64 KiB，stride≥40且8字节对齐、长度整除，所有描述符页对齐、页数非零、乘法/端点不溢出、全图无重叠。随后每个请求只有在 **ACPI Reclaim(9)/NVS(10)、无 Runtime 属性的描述符完整连续覆盖** 时，才返回旧 `HHDM+PA`。描述符可无序，表可非页对齐或跨相邻有效描述符；洞、错误类型、MMIO、runtime、零地址及越界请求均拒绝，RSDP也走相同限制。[UEFI GetMemoryMap](https://uefi.org/specs/UEFI/2.11/07_Services_Boot_Services.html#efi-boot-services-getmemorymap) 定义描述符布局和类型；这里的低4GiB白名单是本项目接入策略。

Inventory 固定 **2456字节、8字节对齐**，包含全部标量、三个 GAS 和有限数组，未用槽为零。候选和最终副本均在私有 BSS，回调期间 BUSY 阻止重入观察或发布；只有完整发现成功才复制并置 READY。成功后为一次性准备，重复返回 AlreadyPrepared；首次准备失败不置 READY，已发布副本在任何拒绝中保持不变，report 的 Busy/NotReady 保持输出全部字节不变。适配层错误为 InvalidBootInfo、InvalidMap、NotReady、Busy、AlreadyPrepared（`0x03020001`～`0x03020005`），解析错误保留原码。新根下只读持久副本，不保留 raw map、Reader context 或固件正文借用。两模式实际汇编调用链（含 Reader 回调）在宿主门禁中限制为4096字节以内。

本轮不把 ACPI Reclaim/NVS 交给 buddy，也不因“已经复制”释放它们。DSDT引用、AML、休眠和NVS生命周期仍有后续依赖。

## 报告与原启动链

`boot.acpi_startup.Report` 为固定顺序24个 u64，**192字节、8字节对齐**：

```text
rsdp xsdt madt fadt hpet mcfg
table_count cpu_count ioapic_count iso_count nmi_count mcfg_count
lapic_address madt_flags fadt_flags boot_arch
pm_timer_block pm_timer_length pm_timer_32bit
hpet_gas_info hpet_address pm_timer_gas_info pm_timer_address steps
```

`gas_info = address_space | bit_width<<8 | bit_offset<<16 | access_size<<24`，对应 address 单列；`steps=7` 表示完整解析、持久发布及报告可用。完整 Inventory 包含报告未展开的记录，不能只用这24字段代替其全部内容。

正常路径在原 `DONGOS_P2_CACHE_READY` 和既有 cache-unmap/permission 终止分支之后，输出严格 `acpi_<field>=0x` 加16位小写hex字段，再输出 `DONGOS_P3_ACPI_READY`、原 MEMORY_READY/PASS。准备失败输出明确 `acpi_error` 后走 kernel_fail；旧内存预检错误仍保持原发生位置和错误含义。旧 P2 门禁只投影完整、精确的可选 ACPI 结构，ACPI的新语义由独立门禁负责，不伪造旧字段、READY或成功退出。

## 独立验证

[原始字节参考解析器](../tests/acpi_reference.py) 不调用 Dong 实现。[run_acpi_qemu.py](../tests/run_acpi_qemu.py) 在实际链接的 CPL0 HLT 停机后，通过 QMP 读取原物理 BootInfo、UEFI map 和固件表；参考解析同样受 ACPI RAM 范围限制，保存每个物理块的PA、长度、文件及hash。验证包括：

- 原 cache/hardening/memory 完整门禁、真实 CPUID/CR4 及原资源/归还账本。
- 独立固件解释与24字段串口逐项一致；实际 BSS Report192字节与串口一致。
- 导出的 Inventory 指针落在真实 ELF 的保留 BSS，完整2456字节（含未用槽）与参考结果一致。
- 实际 CPU 拓扑及显式 HPET 配置一致；最终 CR0/CR3/CR4/EFER等于原已验证读回，IF/DF/VM/AC策略保持，精确链接 RIP、CPL0、HLT=1。

配置包含正常 `q35` 四CPU、`one-cpu`、`no-hpet` 和正式 `production`。正式版不是 test exit33：PASS后在真实HLT观察并由宿主QMP退出；它允许实际0～7次EBS retry，适配预期前缀而不修改原串口字节。QEMU配置的CPU数量只用于核对固件拓扑，不代表已实现多核启动。

宿主方面，[解析器探针](../tests/test_acpi.py)、[启动适配探针](../tests/test_acpi_startup.py) 和[门禁测试](../tests/test_acpi_qemu_result.py) 分别检查 packed表/checksum与失败不变、独立排序区间模型与持久复制/Busy、原始字节参考/格式/ELF/宿主失败行为。debug/release、ELF64/COFF及实际 native 拒绝控制都有各自证据；宿主 Reader 不冒充执行真实 HHDM 或设备访问。

```powershell
python -m unittest tests.test_acpi tests.test_acpi_startup tests.test_acpi_qemu_result -v
python tests/run_acpi_qemu.py --all --timeout 60
```

三个隔离坏客体见[一次性负控脚本](../build/test/p3-acpi/negative_guests.py)：真实 RSDP checksum 改坏应早期报 BadChecksum，RSDP指向MMIO应报 Unreadable，真实 BSS CPU数量加一应被独立物理参考拒绝。构建失败、无实际执行、超时或宿主错误不能计作负控成功。

## 当前证据状态

**本里程碑已验收，最终证据见 [validation-summary.json](../build/test/p3-acpi/validation-summary.json)。** 235项系统加323项语言/标准库，共558项不同宿主测试通过、零skip。四项ACPI配置均实际启动并通过；35项P2集成回归（15内存、5能力、3缓存、12权限）通过，全部串口/ELF由当前门禁重新解析。三个真实坏客体按预期有效拒绝。最终汇编含Reader的完整早期调用链为3520字节。

合计39项正式客体、3项坏客体，另保留GAS边界修正前的一次成功smoke和一次无HPET参数失败：本轮共44次QEMU进程启动，其中43次进入内核。无HPET首轮因当前QEMU不接受`-no-hpet`而未启动客体；原始目录与四项首轮汇总完整保留，改用已核实的`q35,hpet=off`后单项重验通过。该选项是558项宿主结束后唯一正式源码变化，受影响的15项门禁测试已重跑通过；重复执行不加入不同测试总数，其他225个源码哈希与宿主快照一致。构建/客体均串行，源码和共享正常镜像在35项回归期间保持不变。

历史 P2 中，[九项 std-arch 实际客体](../build/test/p2-acceptance/std-arch-summary.json) 已独立执行；它们曾从纯宿主发现列表明确排除，不能重复当作本轮新增宿主通过。当前仅完成 ACPI发现与持久复制链路，不宣称整个P3、中断递送、AP启动、定时、线程、远程CI或真机验收。

## 规范依据

[规格审计](../build/test/p3-acpi/spec-audit.md) 区分了规范事实、字段布局和当前支持策略，并保留来源清单/头文件hash。主要依据为 [ACPI 6.6 第5章](https://uefi.org/specs/ACPI/6.6/05_ACPI_Software_Programming_Model.html)、[UEFI 2.11 x64平台](https://uefi.org/specs/UEFI/2.11/02_Overview.html#x64-platforms)与前述 GetMemoryMap；packed布局交叉核对 [EDK2 Acpi66.h](https://github.com/tianocore/edk2/blob/master/MdePkg/Include/IndustryStandard/Acpi66.h)及[官方 MCFG 声明](https://github.com/tianocore/edk2/blob/master/MdePkg/Include/IndustryStandard/MemoryMappedConfigurationSpaceAccessTable.h)。HPET表的历史GAS和设备块语义采用 [Intel HPET 1.0a §3.2.4](https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/software-developers-hpet-spec-1-0a.pdf)与[EDK2 HPET声明](https://github.com/tianocore/edk2/blob/master/MdePkg/Include/IndustryStandard/HighPrecisionEventTimerTable.h)。MCFG属于PCI Firmware规范；未获得PCI-SIG受限全文，不声称已通读该全文或实现完整PCI枚举。
