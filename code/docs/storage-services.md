# 独立用户服务与实际持久化

后续进展（2026-10-17）：FAT32已接入子目录、UTF-8长文件名与路径协议v2，并通过实际NVMe读写/FLUSH及同盘双启动。文件客户端分为shell/FS的0x50000000与桌面/FS的0x52000000两组独立64KiB通道，FS/block为0x51000000；kernel accepted-ticket peer决定通道，不信任请求内的caller。详见[目录/LFN验收](fat32.md)。下文最初三服务记录保留。

后续进展（2026-10-17）：正式块服务现优先VirtIO，其次NVMe，再回退AHCI。三后端均有实际读写/FLUSH和同盘双启动，AHCI另有VMware复验；NVMe最新内核授权、DMA/队列取证与证据见[nvme.md](nvme.md)，AHCI见[ahci.md](ahci.md)。下文保留最初三服务与VirtIO接线记录。

2026-10-17。`runtime_level=5` 从 ESP 的独立 `SERVICES.BIN` 装入三个 PIE：shell、FAT32 服务、现代 VirtIO 块驱动。各自拥有 CR3、用户栈、代际句柄表和64B端点；shell→FS→块驱动的嵌套调用经过真实 SYSCALL/SYSRET。两条独立64KiB共享通道传输文件/扇区数据，文件系统和设备协议代码运行在 CPL3。

`ServiceHandoff v1` 是独立96B扩展，入口通过 RSI 交接，不改变160B BootInfo v1。固件读取有界服务包、分配128MiB额外RAM和交接页；内核复制前验证整页 EfiLoaderData 所有权，再检查实际对象不重叠和全部包哈希。额外RAM的当前分配器只递增，失败后不回收半成品。旧2MiB内核镜像上限保留。

设备授予来自实际 MCFG 和 PCI BAR 探测。ECAM 的低地址 ReservedMemoryType 例外仅限固件给出的配置窗口；高地址保留PCI窗口仅限所选硬件 BAR、CPU物理位宽和非RAM/非runtime范围。驱动实际使用一个4KiB低BAR和一个位于 `0xc000000000` 的16KiB高BAR，用户映射全部 UC/RW/NX。配置、MMIO、DMA、控制台及IRQ拥有独立句柄种类，不允许以普通共享内存句柄冒充。

DMA以独立 WB/RW/NX、连续128KiB持有块支撑队列和64KiB数据区。当前驱动生命周期结束前保留该物理块；内核尚不提供可回收的 DMA release，所以不能据此声称已经支持驱动崩溃后的自动重启。库中坏完成/超时的租约保留规则继续有效。

正式客体测试 `tests/run_services_qemu.py` 使用真实 TCP UART 交互与独立 raw 磁盘，先执行：

```text
write PROBE.TXT DongOS persistent shell 2026-10-17
cat PROBE.TXT
ls
sync
exit
```

关闭第一个虚拟机后，重新启动同一盘并执行 `cat`、`ls`、`exit`。两次分别完成3181/3127次同步调用、8016/6770次系统调用，错误数均为0。宿主独立解释磁盘 BPB、目录及簇链，核对34字节文件、两份FAT相等和clean位；文件SHA-256为 `51d927be82eef864035f12b1fcb1c673d57e43ffe62ceb617c79c18bc423ff57`。

每次正常HLT后另做111次物理读取：复核原固件ACPI、P3报告/控制器、三个私有表池、实际用户代码字节、代码/数据权限、六个用户和两个syscall栈guard、只读启动能力页、两条共享通道、全部RAM持有记录、64位BAR UC叶及DMA页。实际队列请求头最后为 FLUSH(type4)，状态字节为0。退出由宿主在真实正常HLT和物理检查后 QMP quit，不伪造客体退出33。

证据保存在 `build/test/p5-storage/qemu/run-58600e4c6590/`，两次实际启动均通过且整个检查期间源码哈希不变。之前的配置区类型拒绝、64位BAR限制和Windows stdio输入超时诊断记录保留在 `build/test/p5-services/`；TCP UART解决了宿主文本管道的输入/换行问题。

定向宿主验证：EFI实际装载helper24场景通过；资源模型debug/release各32案例（4成功、28完整不变拒绝）；新增设备句柄种类按全部1..255权限掩码检验；UI主题/控件/真实像素及四个实际坏实现也已通过。所有这些是组件或本里程碑验收。

尚未关闭完整P5：i8042实际接线、AHCI/NVMe、子目录/LFN写入、另一虚拟机复测、通用进程/驱动恢复仍待完成。当前继续P6多核与P7实际图形桌面；P6原KVM性能和P7原1080p/60fps标准保留。
