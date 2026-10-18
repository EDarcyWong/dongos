# AHCI 块服务与 DMA 启用边界

当前接入工作使用独立 CPL3 块服务，保留原 VirtIO 后端并优先选择它；没有现代 VirtIO 块设备时，选择 PCI class/subclass/interface 为 `01/06/01`、header0 的首个 AHCI HBA。仅为该角色授予硬件探测得到的 BAR5。文件系统、64B 块协议和两条共享通道不变。

QEMU 和 VMware SATA 均已通过真实双启动读写、FLUSH 和同盘持久化；QEMU 使用严格完成检查，VMware 使用下述精确设备身份门控的兼容策略。物理盘未验收。NVMe已在独立后端通过QEMU实际复验，见[nvme.md](nvme.md)；AHCI热插拔、多HBA自动选择、ATAPI、端口倍增、NCQ、MSI、中断式完成和错误后重新初始化仍未实现。

## 内核与驱动顺序

内核先清除 PCI I/O、memory 和 bus-master enable 并立即精确读回；失败在 BAR sizing、用户映射及句柄发布之前停止，尝试状态保持。AHCI 分支最后只启用 memory decode 并禁用 INTx，BME 保持关闭。DMA 是单独持有的连续128KiB WB/RW/NX 租约；物理地址和 CPU 指针分开，不转换任意物理地址为用户指针。

驱动完成 BIOS ownership 交接、禁用 HBA/端口中断并停止**全部实现端口**。所有 ST/FRE/CR/FR、CI/SACT 均须清零；选择首个活动 direct ATA、DET3/IPM1、signature `0x101` 的端口。写入该租约的 CLB/FB 后，通过受限 `0x65` 请求内核启用 BME。内核从授权 BAR 独立读回全部端口及可信租约基址，纯 `ahci_authority.permit` 通过后才写 PCI command，且强制写后读回。写入尝试之后，无论结果是否确定都禁止重试；失败保留所有 RAM。

顺序依据见 [Intel AHCI 1.3.1](https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/serial-ata-ahci-spec-rev1-3-1.pdf) 的 PCI command、端口命令和初始化章节。原始规范版本、打印页/PDF页及 ATA/FIS 主来源另保留于 `build/test/ahci-prototype/SOURCES.json`。

这只证明 **启用 BME 当刻** 的授权与停稳条件。驱动获得整个 HBA 的可写 MMIO 后仍可改变描述符或其他端口；当前没有 IOMMU，不能声称已将恶意驱动的后续 DMA 硬件限制在租约。它与现有 VirtIO 后端同属受信 DMA 服务边界，P9 的 DMA 重映射义务保留。

## 数据与完成契约

`ahci_core.dg` 没有硬件访问或可变全局。固定 slot0、一个 PRD、每次最多128个512B扇区，只支持 IDENTIFY、READ/WRITE DMA EXT 和 FLUSH CACHE EXT。租约全段必须低于4GiB；CLB/FB/CTBA/data 分别在 `+0/+0x400/+0x800/+0x1000`。输出包括完整32B header和144B table，先检查再发布。

严格检查 IDENTIFY 的 DMA/LBA48、有效扇区字段、正48位容量及可选 checksum；512e 可用，4Kn和旧式无效 word106 失败关闭。写入必须有 durable FLUSH EXT 路径。当前块服务不假装具备掉电事务。

每次提交清除旧 RFIS/PxIS/PxSERR/PRDBC，经设备屏障后才置 CI。完成需要 CI0、SACT0、精确字节数、干净状态和实际 D2H FIS；IDENTIFY 另支持 PIO Setup 的 E_Status 完成。错误、超时、坏完成或时钟倒退均永久 fault 并保留租约，后续操作不能复用它，release 不会被调用。

block 角色的只读128B Boot记录 `reserved3` 提供内核校准的 TSC Hz，配合 `0x73` 读 TSC 换算毫秒；shell 的同字段仍为电源能力，input 的同字段仍为显示描述符。ownership、CR/FR、命令时限分别使用真实2s、500ms、5s，不以轮询次数代替经过时间。

## 已有验证

- 正式纯核心 `tests.test_ahci`：最新4项通过，debug/release 每模式210,875次断言、134,126个身份样本和2,360个完成策略样本；枚举初始/结束/当前状态全部256个值。两个实际坏 builder 和三个放过错误完成的坏实现均被拒绝，ELF/COFF及可达栈752B通过。证据 `build/test/ahci-core/run-575be9bf0c53/validation-summary.json`；早期严格模式基线 `run-63b94b8b923e` 保留。
- 正式 `tests.test_ahci_authority`：双模式核对全部 PCI command 值、全部实现端口、可信租约、BIOS ownership、物理地址极限、稀疏 PI 和高32位基址。实际忽略其他端口的坏实现会被拒绝，ELF/COFF与单函数224B栈通过；最新证据见 `build/test/ahci-authority/run-881c4486d06b/validation-summary.json`。
- 正式适配器 `tests.test_ahci_runtime`：受限兼容策略复验 `build/test/ahci-runtime/run-487982fc0e0a`，3项通过，每模式4,726,782次断言、37个场景、39个命令；四种实际坏适配器均被拒绝，release调用始终为零。State656，策略偏移648，精确Sample偏移328。全块服务含入口可达栈3039B/16KiB，见 `build/test/ahci-integration-review/interop-state656/stack-audit.json`。纯 callback 模型不证明内核 MMIO 视图、页表、PCI 写读回或真实设备行为；早期严格模式和State648证据保留。

客体验证入口为 `python tests/run_ahci_qemu.py --reuse-esp <完成的普通runtime7构建>/esp`，只复用构建，不自动构建。数据盘独占 SATA port0，EFI卷在port1；通过 UART 发出真实 write/cat/ls/sync，核对实际 CPL3 ELF、BAR5 UC映射、32页私有 DMA、启用前全端口快照及最后 FLUSH 描述/接收 FIS，再关闭客体、独立解释磁盘并同盘重启。

2026-10-17 实际结果 `build/test/ahci/qemu/run-291b10ddedc4/result.json` 通过，构建 `build/test/ahci/builds/build-041d3a305ce1/esp`（kernel 2,047,368B，源码不变）。两个实际启动均进入桌面，分别完成3,181/3,141次块操作；UART文件内容、原始FAT两副本/clean、同盘重启、独立 ELF 权限和字节、全部DMA页及最后 FLUSH EXT 的真实 header/table/D2H 均通过。该构建原 VirtIO 后端的 S5/reset 和原盘持久化四启动回归 `build/test/p8-power/qemu/run-f4f7b951573e/result.json` 也通过。

VMware 首次真实 AHCI 尝试 `run-af593021d43e4b7c` 在 IDENTIFY 完成校验停止；精确输入诊断见 `build/test/vmware/storage-prototype/runs/run-fb363f803a13485b/ahci-diagnostic.json`。CI0、SACT0、PRDBC512、TFD40、SERR0、PxIS2；PIO Setup 为 `5f60400000000000000000000000000000020000`。唯一不满足项是保存的初始 Status.DRQ=0。SATA 的初始数据输入状态要求DRQ1；AHCI的复制规则没有保证会把这个保存字段改成终态，不能把这个差异描述为规范符合性证明。原失败和诊断均保留。

兼容策略只在实际PCI枚举的vendor/device为`15ad:07e0`、class/subclass/interface为`01/06/01`、header为0或80时选择1。这些值来自同一个获内核授权的Function，不取自VM配置或用户开关。仅IDENTIFY的PIO-only完成可接受保存的初始DRQ0或1；当前TFD、精确字节数、CI/SACT、错误/结束状态、FIS类型/方向/PMP/长度与期限等门禁保持。`poll`及`initialize`默认策略0，未知策略原子拒绝；READ/WRITE/FLUSH没有兼容放宽。VMware官方设备ID见[open-vm-tools头文件](https://github.com/vmware/open-vm-tools/blob/master/open-vm-tools/lib/include/vm_device_version.h)。

最新普通runtime7构建为 `build/test/ahci/interop-builds/build-9549eb11c983/esp`（kernel 2,047,368B，完整源码/产物哈希不变），启动镜像 `build/usb/dongos-9549eb11c983.img`。实际复验合计10次启动：

- 正式入口VMware `build/test/vmware/storage/run-0a0c0881fa0a41f1/result.json`：2次真实启动，均实际记录身份`0001060107e015ad`和策略1，完成shell写/读/列目录/同步、原盘重启后读回，独立FAT两副本及clean检查通过；两个桌面READY标记均出现。只操作新建的私有VM/磁盘副本，原镜像及源码不变，VM停止已独立确认。不据串口标记声称VMware像素、帧率或内存布局已验收。
- 迁移前原型入口VMware `build/test/vmware/storage-prototype/runs/run-5ad439c5c04441b2/result.json`：另外2次真实启动，同样通过；迁移后正式runner及依赖全在`tests/`，23项mock与再次实际双启动均通过，原记录保持。
- QEMU AHCI `build/test/ahci/qemu/run-ffa502906af2/result.json`：2次真实启动，实际全局选择及State656策略字段均为0；真实CPL3代码/页权限、BAR5、DMA租约、全端口停稳、最后FLUSH描述符/完成及原盘重启均通过。
- 同一构建原VirtIO后端的关机/重启四启动回归 `build/test/p8-power/qemu/run-026072ef1280/result.json`：实际S5/reset事件、FLUSH和原盘持久化通过。

合并输入/结果核对为 `build/test/ahci-integration-review/cross-vm-9549eb11c983/validation-summary.json`。上述结果不关闭P5通用设备生命周期、NVMe、目录/LFN，也不替代KVM或真机验收。


正式事务桥 `python -m unittest tests.test_ahci_broker -v` 已通过：测试只依赖 `tests/ahci_broker_probe.c` 与 `tests/ahci_broker_fixtures/`，动态原样提取正式 `grant` 完整函数体（本次 4,004 字节，SHA256 `933d4b28ffd85a054075c016c6c49b975af7e405f2c4e285cca9a141bb5e0e58`），并检查正式源、fixture 和编译器前后哈希不变。debug/release 每模式 290 场景、12,679 断言、4,136 条保留的原始 JSONL 事件；验证初始 PCI command 清除被忽略或精确读回变异时零 BAR 写/映射/句柄/BME 开启请求，attempted 黏滞；另覆盖 AHCI 仅 BAR5/BME 保持关闭、VirtIO 32/64 位 BAR 与 input 兼容、角色/身份/重试拒绝及部分失败。实际删掉初次读回 branch 的坏 DG 在两模式均真实命中 marker，并在首个不安全 BAR 写被独立 C 寄存器模型拒绝。ELF/COFF 实际汇编通过，最大单函数栈预留 240B；这不是完整内核调用链上界。正式路径证据为 `build/test/ahci-broker/run-be004250377c/validation-summary.json`（fixture模板使用`.dg.in`，避免伪装为完整DG源）。该桥使用明确的 typed stubs，未执行真实 ECAM/UC scratch window、页表、SMAP、完整 handles table 或 DMA allocator；日志中的 BME_ENABLE_REQUEST 是拟开启总线主控的写请求，不能当作硬件 DMA、实际 HBA 或客体验收证据。

NVMe接线后的同镜像AHCI严格模式回归为 `build/test/ahci/qemu/run-c92c22ca1997/result.json`，两个实际启动通过；VirtIO电源回归为 `build/test/p8-power/qemu/run-23e2741fa546/result.json`，四个实际启动通过。最新普通构建及完整NVMe证据见[nvme.md](nvme.md)。
