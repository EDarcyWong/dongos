# DongOS：x86-64 汇编 PC 操作系统架构与推进计划

- 版本日期：2026-10-17
- 负责人：cdH
- 当前阶段（2026-10-17）：**P0/P1、L1和P2核心/P3已验收；P4百万IPC、P5持久化、P6四核/TLB及P7桌面里程碑保留。新增七样本时钟校准已由HPET/PM真实客体独立复算；GPT/ESP启动镜像已由QEMU实际从USB启动到桌面。窗口缩放功能、反向打断、半透明边框及SSE2回退已通过真实客体；当前200%拖动60.0216FPS/最慢7.0423ms。精确遮挡将四窗DPI移动帧降至约16–23ms，仍不宣称动画恒定60Hz。Q35关机/重启四次启动和原盘持久化通过，两个恶意服务的21项权限负控通过；dongfmt与VS Code高亮已交付。** 原生/客体证据分别见 `docs/clock-calibration.md`、`docs/usb-boot-image.md`；窗口过渡的性能优化、独立应用生命周期、P2扩展、PCID/init、AHCI/NVMe及P6余项继续承担交付义务。用户已明确本轮完成P0–P9，P10另定；完整未关闭项和外部验收条件见 `docs/remaining-plan.md`。本机VMware16现已通过IOAPIC、P3/P6四核/TLB、五服务装载、AHCI双启动shell读写/FLUSH及原盘持久化；QEMU AHCI严格模式两启动及同镜像VirtIO电源四启动回归也通过（含正式runner再验共10次实际启动，见docs/vmware-validation.md与docs/ahci.md）。FAT32目录/LFN正式接线完成：全树分配审计、UTF-8路径、创建/读写/追加/截断/删除、实际NVMe FLUSH与同盘双启动通过，见docs/fat32.md；NVMe现已正式接入：QEMU实际写/读/FLUSH、同盘双启动及完整USER映射隔离复验通过；同镜像AHCI两启动和VirtIO电源四启动回归通过，见docs/nvme.md。KVM和真机标准不替换。
- 在线版本（可编辑、可评论）：https://claude.ai/code/artifact/88664644-09d5-4088-8ef5-cf9773cf0347
- 本文件是在线版本的文本快照，供后续开发和其他会话读取。两者不一致时，以最近修改的为准，并同步另一份。
- 本地进展（2026-10-16）：P0 已在 Windows 原生 NASM 3.02 + lld-link 19.1.5 + QEMU 11.0.0 / EDK II 上通过自动验收；L0 首版规格已写入 `lang/spec.md`。本轮未同步在线快照，也未触发远程 CI。
- 继续推进（2026-10-16）：P1 的镜像读取/校验/解压、GOP/ACPI/内存图、退出固件、自建页表和高半区内核输出已在同一环境实测。L1 已有可运行的标量子集，并在内核中核对 Dong 函数返回 42 和 55；完整 L1 仍未完成，暂不进入 P2。
- L1 后续进展（2026-10-16）：已支持所有整数宽度、结构体/固定数组、裸指针、unsafe、布局内建与 JSON 导出；新增切片、显式源码根模块图、SysV 双字/栈参数和 SysV/Win64 标量外调。透明类型别名、命名常量与布局计算、高对齐局部/临时存储均已验证；全局 var 与聚合/字符串/对象地址常量已接通数据节、BSS 和完整 64 位重定位。wrapping、非对齐、volatile、顺序一致原子内建、编译器屏障和八条受限 asm 指令已实现。BootInfo 已迁入共享 Dong 模块，NASM 定义由编译器布局生成，P1 实启核对内存探针 373、切片/ABI 探针 765、别名/常量探针 282、对齐探针 458、全局探针 436 和内存内建探针 719。函数指针、间接调用和 Win64→SysV 回调桥接已实现，P1 探针 761 通过；方法、其余控制流、错误处理与 defer 已完成编译器侧验收，P1 探针 75 通过。标准库 D1～D4 已交付复验，完整 L1 等待 DeepSeek 的 D5 独立回调 ABI 补测、D6 测试 ABI 修正与总验收。

- 最新验收（2026-10-17）：DeepSeek D5 独立汇编回调补测与 D6 测试 ABI 返修均复验通过，D1～D6 全部验收。`python tools/build.py test` 通过 32 项系统测试、321 项语言/标准库测试，共 353 项宿主测试，以及 5 次 QEMU 启动。L1 达到本地总验收门槛，D7 独立特权 QEMU 探针、D8 P2 伙伴分配器已分配给 DeepSeek，状态待领取；未执行远程 CI 或真机测试。

- P2 CPU 与交付复验（2026-10-17）：私有 GDT/TSS/IDT、DF/NMI/普通异常三组 IST 和寄存器/回溯 panic 屏已接入并完成本地验收。统一回归通过 58 + 321 = 379 项宿主测试，以及 P0/P1 5 次启动和 CPU 八种故障注入，共 13 次 QEMU；正常生产镜像与 panic 画面均已核对。DeepSeek D7/D8 的既有测试通过，但审查发现 D7 验收误通过/旧结果残留及 D8 错误码/覆盖缺口，已下达 R1；新分配 D9 内存图规范化、D10 固定对象缓存，见 deepseek-works。

- P2 离线页表（2026-10-17）：新增 mm.paging 与专用错误模块，四级 48 位 canonical、32～52 位物理地址、外部对齐表池和元数据；支持单页映射/撤销/改权限/查询、空中间表回收及失败前后完整状态不变。独立 C 原始页表遍历和 2500 步模型、debug/release、ELF64/COFF 均通过；本轮执行 63 项系统宿主测试和 321 项语言测试，共 384 项。当前只构建离线私有树，不接活动 CR3、不改 P1 大页、不声称硬件 W^X 已启用；D8/D9 复验后再集成。原定时复验已按用户要求取消，目前由手动指令触发。

- DeepSeek 后续复验（2026-10-17，上一轮）：D7 正向双模式 QEMU、10 项解析测试，D8/D9/D10 各 2 项宿主测试均通过；独立负控仍发现 D7 错硬件目标被接受、D8 必需失败/合并补测漏检、D9 交付测试实际 scratch 越界，及 D10 漏地址区间溢出预检/payload 测试。分别追加 D7 R2、D8 R2、D9 R1、D10 R1，见 `deepseek-works/reviews/2026-10-17-D7-D9-recheck.md` 与 `2026-10-17-D10.md`。D8/D9 生产实现的额外模型未发现功能缺陷，但尚不满足交付验收。本轮不重跑全项目，不修改活动内核或页表。

- DeepSeek 第二轮返修复验（2026-10-17）：D7/D8 R2、D9/D10 R1 的正向定向测试均通过。D8 两旧负控已被拒绝，D9 已修 scratch 容量并加入逐页多图模型/D8 耗尽联调，D10 地址溢出及失败状态不变有效；D7 清理覆盖失败返回值使原坏 CR3/MSR 仍 PASS，D8 剩余失败快照、D9 output/尾部保护及 D10 NULL/payload/padding 验证仍有实证缺陷。继续原任务 D7/D8 R3、D9/D10 R2，不新增 D11，见 `deepseek-works/reviews/2026-10-17-D7-D10-round2.md`。未修改活动内核/页表或运行全项目回归。

- DeepSeek 第三轮及补交复验（2026-10-17）：D7/D8 R3、D9/D10 R2 定向测试通过；旧主要负控已被拒绝。01:55补交的 D7 RBX/恢复、D8持有后发布、D9raw长度及D10旧内容保护已确认；当时剩余项继续原修订补交，证据 `deepseek-works/reviews/2026-10-17-D7-D10-round3-supp.md`。未改活动内核/页表，未做全项目回归。

- DeepSeek 手动检查（2026-10-17）：定时任务取消后按用户指令复验。D7 套件16项（含3个QEMU负控）及正常debug/release通过，D8/D9/D10各2项通过；独立mock仍证实D7三负控可把构建失败当通过，另三项仍有真实失败分支/全调用字节保护漏检。已认可CR3写前校验、更多输入矩阵/快照/尾余量等进展，继续D7/D8 R3、D9/D10 R2；最新记录 `deepseek-works/reviews/2026-10-17-manual-check.md`。未改正式实现/测试或活动内核，未跑全项目回归。

## 目录

1. 结论：改用 x86-64
2. 平台与默认选择
3. 总体架构
4. 安全设计
5. 快速启动设计
6. 界面设计
7. 内核与服务细节
8. 工程规范（汇编与 Dong）
9. 自研语言 Dong
10. 推进计划
11. 风险与对策
12. 立即开始的下一步

## 1. 结论：改用 x86-64

建议改用 x86-64。决定性的是两点：

- 你要在真机上跑，而按公开文档就能驱动的 ARM PC 几乎不存在；x86-64 PC 随处可得。
- 你现在在虚拟机里开发，而在普通 x86 电脑上，x86-64 虚拟机接近原生速度，ARM 虚拟机只能靠纯软件模拟，慢很多。

你提的三项要求（安全、启动快、界面美观）两种架构都能做到，分不出胜负。

唯一的例外：如果你的开发机是 Apple Silicon 的 Mac 或 ARM 笔记本，虚拟机这一条反过来，届时需要重新权衡。

| 对比项 | ARM64 | x86-64 | 结论 |
| --- | --- | --- | --- |
| 真机可得性 | 骁龙 X 笔记本的键盘、触控板、显卡、电源管理缺公开文档 | 任何带 UEFI 的 PC 都能启动，NVMe、AHCI、xHCI、键盘控制器都有公开规范 | x86-64 明显更好 |
| 虚拟机开发 | 在 x86 电脑上只能软件模拟 | KVM、VirtualBox、VMware、Hyper-V 硬件虚拟化，接近原生 | x86-64 更好 |
| 资料与社区 | 有，但偏嵌入式和 Linux | OSDev Wiki、Intel/AMD 手册、大量业余系统可参考 | x86-64 更好 |
| 安全特性 | PAN、PXN、指针认证 PAC、分支目标 BTI | NX、SMEP、SMAP、UMIP、CET 影子栈与 IBT、IOMMU、TPM | 基本持平 |
| 启动速度 | UEFI | UEFI | 持平，取决于自己的设计 |
| 界面 | 真机只有 UEFI 帧缓冲，NEON 软件渲染 | 真机同样只有 UEFI 帧缓冲，AVX2 软件渲染 | 基本持平 |
| 汇编难度 | 指令定长、寄存器多、历史包袱少 | 变长指令，需处理 GDT/TSS 等历史结构 | ARM 更好 |

针对三项要求做了三个设计调整：

- **安全**：内核改为微内核。
- **启动快**：自写无菜单的 UEFI 引导器，并行启动服务。
- **界面美观**：增加独立的合成器和抗锯齿字体方案。

## 2. 平台与默认选择

开发与调试用 QEMU + OVMF（UEFI 固件），阶段性地在 VirtualBox 或 VMware 里复测，最后从 U 盘在真机启动。下表任何一项都可以改。

| 项目 | 默认选择 | 理由 |
| --- | --- | --- |
| 指令集 | x86-64（长模式），最低要求 x86-64-v2（SSE4.2、POPCNT），有 AVX2 时自动启用 | 2010 年后的 PC 都满足；AVX2 用于界面渲染加速 |
| 编写语言 | 自研系统语言 Dong（编译成 NASM 汇编）；引导器入口、中断入口、上下文切换等少量底层代码手写汇编；宿主机上的构建工具和第一版编译器用 Python | 写得快、读得懂，最终产物仍是可审查的汇编 |
| 汇编器 | NASM（Intel 语法）+ lld-link（引导器）/ ld.lld（内核与程序） | NASM 资料最多；lld 能直接输出 UEFI 需要的 PE32+ |
| 开发虚拟机 | QEMU 8 + OVMF，`q35` 机型，Linux 上开 KVM、Windows 上开 WHPX | 可接 gdb 单步、可打印中断日志 |
| 复测虚拟机 | VirtualBox 或 VMware，开启 EFI | 提前发现只在 QEMU 里正常的问题 |
| 启动方式 | 仅 UEFI，不支持传统 BIOS；自写无菜单引导器 `BOOTX64.EFI` | 少一整套 16/32 位启动代码，启动更快，并能接入安全启动 |
| 硬件发现 | ACPI（MADT、MCFG、FADT、HPET）+ PCIe | PC 的标准描述方式 |
| 内核形态 | 微内核：内核只管内存、线程、IPC、中断、句柄；驱动、文件系统、界面都是用户态服务 | 一个驱动出错不会拖垮整台机器，汇编内核也更小、更好审查 |
| 内存 | 4 级页表、48 位地址、4 KB 页（大块用 2 MB 页），内核在最高 2 GB | 所有 x86-64 CPU 都支持 |
| 多核 | SMP，用 ACPI MADT 找核，INIT-SIPI 唤醒 | 启动和界面都能并行 |
| 程序格式 | ELF64；系统调用用 `syscall` 指令和自定编号 | 微内核调用很少，不再沿用 Linux 编号 |

## 3. 总体架构

系统是微内核结构：特权级 0 只跑一个小内核，驱动、文件系统、合成器都是特权级 3 的普通进程，彼此通过 IPC 通信。这是安全要求带来的最大变化：一个驱动的漏洞或崩溃只影响它自己。

分层（从上到下，箭头方向为调用方向）：

| 层 | 特权级 | 组成 |
| --- | --- | --- |
| 应用 | 3 | 桌面与任务栏（任务栏、启动器）；终端与 shell（命令行）；文件管理器；编辑器与设置 |
| ↓ IPC 消息 + 共享内存 | | |
| 系统服务（各自独立的地址空间） | 3 | 合成器（窗口、字体、动画、指针）；文件系统（FAT32，按句柄授权访问）；服务管理器 init（并行启动，崩溃自动重启）；存储驱动（virtio-blk、AHCI、NVMe）；输入与 USB 驱动（PS/2、xHCI、HID）；设备与电源（PCIe 枚举、ACPI 关机） |
| ↓ syscall 入口 | 边界 | 只接受句柄，每次调用都检查权限 |
| 微内核 | 0 | 内存与页表；线程调度；IPC；中断转发；句柄与权限 |
| ↓ 硬件 | | x86-64 CPU（NX、SMEP、SMAP、CET）· PCIe 设备 · IOMMU 限制驱动的 DMA · UEFI 帧缓冲 |

启动链：UEFI 安全启动 → 引导器校验 SHA-256、随机化内核基址 → 内核 → init 并行拉起服务。

代价是多一次进程间通信：大数据（窗口画面、磁盘块）一律走共享内存，消息只传通知和小参数，性能在 P4 就会实测。

## 4. 安全设计

安全靠三层保障：只启动签过名的代码、每个程序只拿到被授予的权限、CPU 硬件强制内存和控制流规则。前两层从 P4 起就是架构的一部分，不是后加的。

### 信任链

- UEFI 安全启动：用自己的密钥签名 `BOOTX64.EFI`，在虚拟机和真机固件里导入公钥（P9）。
- 引导器对系统镜像算 SHA-256，与编译进引导器的期望值比对，不符就拒绝启动。CPU 支持 SHA 指令时用硬件加速。
- 内核加载服务时同样校验哈希，哈希表随镜像一起被签名。

### 隔离与权限

- 微内核：驱动、文件系统、合成器都跑在特权级 3，各有独立地址空间，崩溃后由服务管理器重启。
- 句柄即权限：进程只能操作手里的句柄（进程、内存对象、IPC 端点、中断、设备寄存器区间），句柄带读/写/传递权限位，不存在“超级用户绕过一切”。
- 驱动的 DMA 用 IOMMU（Intel VT-d / AMD-Vi）限制在分配给它的内存内（P9）。

### 内存与控制流保护

- W^X：没有任何页同时可写可执行，数据页一律加 NX。
- CR4 打开 SMEP、SMAP、UMIP：内核不能执行或意外访问用户页，用户态不能读描述符表。
- 用户指针只通过 `copy_from_user` / `copy_to_user` 访问：先检查范围，再在 `stac` / `clac` 之间拷贝。
- 每个内核栈和用户栈下方留一个不映射的保护页，溢出即缺页。
- 地址随机化：引导器用 `rdseed` / `rdrand` 随机选择内核基址，用户程序的栈、堆、加载地址也随机。
- 控制流：`FUNC` 宏在每个函数入口放 `endbr64`，CPU 支持 CET 时打开影子栈和间接跳转检查。
- 浮点与 SIMD 状态在每次切换时用 `xsave` 立即保存（不用延迟保存，避免 LazyFP 一类泄漏）。其余推测执行漏洞按 Intel/AMD 公布的缓解指南处理。

## 5. 快速启动设计

目标是在 KVM 虚拟机里，从固件交出控制权到桌面画出第一帧不超过 0.5 秒；固件自身的自检时间不归我们控制。做法是少做事、不空等、能并行就并行。

1. **引导器（目标 ≤ 100 ms）**：没有菜单和倒计时。只读一个文件 `DONGOS.IMG`（内核 + 启动必需的服务 + 字体和壁纸，LZ4 压缩）。沿用固件已设好的分辨率，不切换显示模式，屏幕不闪。取内存图、帧缓冲、ACPI 入口后退出固件服务，建好页表跳进内核。进内核前先画出启动标志，用户不会看到黑屏。
2. **内核（目标 ≤ 100 ms）**：不用旧式 PIT 定时器忙等。TSC 频率优先从 CPUID 直接读，读不到再用 HPET 量 10 ms。各个处理器核并行唤醒。
3. **服务管理器**：按依赖图并行拉起服务。显示、输入、合成器先启动，存储、网络在后台接着启动。
4. **桌面第一帧**：用镜像自带的资源立即画出，不等磁盘。需要磁盘的内容就绪后再刷新。

每个阶段用 TSC 打时间戳写入启动日志，P6 起把“启动到桌面的耗时”纳入自动测试，变慢即报警。

## 6. 界面设计

没有显卡驱动也能做得好看：所有画面由一个合成器服务用 CPU 合成，关键是只重绘变化的区域、用 SIMD 指令、写显存用写合并方式。显卡加速超出汇编项目的可行范围，不列入计划。

- **合成器**：每个窗口是一块与应用共享的 32 位 ARGB 缓冲区。合成器在内存里双缓冲，只处理脏矩形，再用 `movntdq` 等非临时写指令拷到显存。显存页用 PAT 设为写合并（WC），这一项对速度影响最大。
- **视觉效果**：Alpha 混合、圆角、预先生成的九宫格软阴影、半透明任务栏。毛玻璃模糊作为可选项，只在性能允许时开启。
- **动画**：由定时器驱动，目标 60 帧每秒，带缓动曲线；窗口打开和关闭有淡入淡出与缩放。
- **字体**：用开源的思源黑体（Noto Sans CJK SC，SIL OFL 授权）。构建时在宿主机上用 Python + FreeType 预光栅化成 8 位灰度字形图集，字号 14 / 16 / 20 / 28 px，收 ASCII 和 GB2312 全部 7445 个字符。运行时只做 Alpha 混合，得到抗锯齿文字。每个字号未压缩约在 1.5–6 MB 之间，压缩后放入镜像。
- **高分辨率**：按屏幕分辨率选择 1×、1.5×、2× 缩放，字体用对应字号的图集，不做位图拉伸。
- **主题**：颜色、圆角、间距、动画时长统一写在 `include/theme.inc`，提供浅色和深色两套。
- **输入响应**：输入服务通过共享环形缓冲区把事件交给合成器；鼠标指针最后绘制并保存底图，移动指针不必重绘窗口。
- **桌面程序**：任务栏、终端、文件管理器、文本编辑器、设置，共用一套汇编控件库（按钮、输入框、列表、滚动条）。

## 7. 内核与服务细节

内核只提供六类机制，其余功能都由用户态服务通过 IPC 提供。

### 虚拟地址布局

| 虚拟地址范围 | 用途 |
| --- | --- |
| `0x0000_0000_0000_0000` – `0x0000_0000_003F_FFFF` | 不映射，捕获空指针 |
| `0x0000_0000_0040_0000` – `0x0000_7FFF_FFFF_FFFF` | 用户空间（每进程一套，基址随机化） |
| `0xFFFF_8000_0000_0000` – `0xFFFF_BFFF_FFFF_FFFF` | 全部物理内存的线性映射（不可执行） |
| `0xFFFF_C000_0000_0000` – `0xFFFF_DFFF_FFFF_FFFF` | 内核堆与内核对象 |
| `0xFFFF_E000_0000_0000` – `0xFFFF_EFFF_FFFF_FFFF` | 设备寄存器（不缓存）与帧缓冲（写合并） |
| `0xFFFF_FFFF_8000_0000` – 末尾 | 内核镜像与每核内核栈（基址在此 2 GB 内随机） |

### 内核机制

- **内存**：物理页伙伴分配器（4 KB–4 MB）、内核定长对象缓存、页表管理；用 PCID 避免切换地址空间时刷整个 TLB。
- **线程与调度**：每核一个运行队列，32 级优先级；界面与输入线程优先级最高，保证操作顺滑；时钟用 LAPIC 的 TSC-deadline 模式，按需定时而不是固定节拍。
- **IPC**：同步短消息（不超过 64 字节，直接在寄存器中传递）+ 共享内存传大数据 + 异步通知。消息可以携带句柄，用来把权限转给别的进程。
- **中断**：内核接住硬件中断，屏蔽后以通知的形式发给持有该中断句柄的驱动服务。
- **句柄**：每进程一张句柄表，句柄带权限位，可复制、降权、关闭。
- **时间**：单调时钟和墙上时间（从 CMOS RTC 读一次后用 TSC 推算）。

### 系统调用

用户程序执行 `syscall`：`rax` 放编号，参数依次放 `rdi rsi rdx r10 r8 r9`，返回值在 `rax`，负数为错误码。内核入口先 `swapgs` 切到每核数据。第一版约 20 个调用：

| 类别 | 调用 |
| --- | --- |
| 进程与线程 | `proc_create` `thread_create` `thread_exit` `yield` `sleep` |
| 内存 | `vm_map` `vm_unmap` `vm_protect` `mem_create`（可共享的内存对象） |
| IPC | `ipc_call` `ipc_reply_wait` `ipc_send` `notify` `wait` |
| 句柄 | `handle_dup` `handle_close` |
| 设备（仅驱动） | `irq_bind` `io_map` `dma_alloc` |
| 其他 | `clock_get` `debug_log` |

### 用户态服务

| 服务 | 职责 | 第一批支持的硬件 |
| --- | --- | --- |
| 服务管理器 `init` | 按依赖图并行启动、分发句柄、崩溃重启 | 不适用 |
| 设备管理 | 枚举 PCIe、按设备号启动驱动 | PCIe ECAM |
| 存储驱动 | 块设备读写 | virtio-blk、AHCI、NVMe |
| 输入驱动 | 键盘与鼠标事件 | PS/2（i8042）、virtio 平板、USB HID |
| USB | 主控制器与设备枚举 | xHCI |
| 文件系统 | 目录、文件、权限 | FAT32（与 EFI 分区共用），以后可加自有格式 |
| 合成器 | 窗口、字体、动画、指针 | UEFI GOP 帧缓冲 |
| 电源 | 关机与重启 | ACPI FADT 与 `\_S5` |

## 8. 工程规范（汇编与 Dong）

汇编与自研语言混合的项目，成败取决于纪律：统一的调用约定、单一来源的结构体偏移、每个函数写清楚输入输出和破坏的寄存器。

### 目录结构

```text
dongos/
├── Makefile
├── lang/          spec.md（语言规格）  dongc/（编译器）  std/（标准库）  tests/
├── boot/          efi_main.asm  fs.dg  gop.dg  paging.dg  sha256.dg  lz4.dg
├── kernel/
│   ├── arch/      entry.asm  switch.asm  gdt.dg  idt.dg  apic.dg  smp.dg  cpu.dg
│   ├── mm/        pmm.dg  slab.dg  vmm.dg  fault.dg
│   ├── task/      thread.dg  sched.dg  elf.dg
│   ├── ipc/       ipc.dg  handle.dg  notify.dg
│   ├── sys/       syscall.asm  syscall.dg  usercopy.asm
│   └── lib/       string.dg  printk.dg  list.dg  spinlock.dg  panic.dg  acpi.dg
├── include/       macros.inc  cpu.inc  theme.inc（供手写汇编使用）
├── services/      init/  devmgr/  storage/  input/  usb/  fs/  compositor/  power/
├── apps/          shell/  terminal/  files/  editor/  settings/  taskbar/
├── assets/        字体图集、壁纸、图标（由 tools/ 生成）
├── tools/         mkimage.py  rasterize_font.py  gen_offsets.py（从 Dong 结构体导出汇编偏移）  sign.py
└── tests/         run_qemu.py（启动 QEMU，比对串口输出与启动耗时）
```

### 寄存器约定

引导器调用 UEFI 时必须用微软 x64 约定（参数 `rcx rdx r8 r9`，调用前留 32 字节影子空间）。内核和用户程序一律用 System V AMD64 约定：

| 寄存器 | 用途 | 谁来保存 |
| --- | --- | --- |
| rdi rsi rdx rcx r8 r9 | 第 1–6 个参数 | 调用者 |
| rax | 返回值 | 调用者 |
| r10 r11 | 临时（`syscall` 会改写 rcx 和 r11） | 调用者 |
| rbx rbp r12–r15 | 长期变量 | 被调用者 |
| rsp | 栈顶，`call` 前 16 字节对齐 | 被调用者 |
| xmm / ymm | 内核不使用；用户态由 `xsave` 保存 | 不适用 |

每核数据用 `gs` 段基址，用户态线程局部存储用 `fs`。

### 宏与书写规则

- `FUNC name` / `ENDFUNC`：生成 `global`、符号类型和大小，并在入口放 `endbr64`。
- `PROLOGUE` / `EPILOGUE`：建立 `rbp` 帧并保存列出的被调用者寄存器，panic 时沿 `rbp` 链打印调用回溯。
- 一律 `default rel`（RIP 相对寻址），代码位置无关，内核基址才能随机化。
- Dong 类型声明和编译器布局器作为结构体布局的唯一来源，`tools/gen_offsets.py` 已能从布局清单生成 NASM 定义，禁止维护第二张偏移表。BootInfo 已迁入这条生成链；UEFI 协议布局暂集中在 `include/uefi.inc`，待语言模块/外部 ABI 完善后迁移。
- 命名：模块前缀（`pmm_alloc`、`ipc_call`），局部标签用 `.` 前缀。
- 每个函数头注释固定五行：功能、输入、输出、破坏的寄存器、可否在中断中调用与要求持有的锁。

### 构建、运行与测试

- `make`：汇编全部源文件，链接出 `BOOTX64.EFI` 和 `DONGOS.IMG`，放进 `build/esp/` 目录。
- `make run`：QEMU + OVMF，`-machine q35 -smp 4 -m 2G`，把 `build/esp` 当作 FAT 磁盘挂上；有 KVM 时加 `-enable-kvm`。
- `make debug`：加 `-s -S`，用 `gdb` 连 `:1234`；查异常时加 `-d int -D qemu.log`。
- `make usb`：生成可直接写入 U 盘的 GPT + FAT32 磁盘镜像（纯 Python 制作并独立核验，不需要 root；不依赖 mtools）。
- `make test`：内核带 `selftest` 参数启动，串口输出 `PASS`/`FAIL` 和启动耗时；GitHub Actions 每次提交自动跑。

## 9. 自研语言 Dong（工作名）

Dong 是一门系统编程语言，编译器 `dongc` 把它翻译成 NASM 汇编，再由 NASM 生成机器码。这样保留了“整个系统都落到可读汇编”的初衷，又让大部分代码写得更快更顺手。只有引导器入口、中断与系统调用入口、上下文切换等少量代码仍手写汇编。

### 设计目标

- **高效**：提前编译，没有垃圾回收和运行时；抽象不带额外开销；任何函数都能对照生成的汇编检查。
- **方便**：类型推导、模块、方法、`defer`、错误返回值，不写头文件。
- **安全**：切片默认边界检查，调试版整数溢出报错，未初始化变量编译报错；裸指针运算和内联汇编只能写在 `unsafe` 块里。v1 不提供所有权、借用或生命周期检查，因此不承诺内存安全或无数据竞争。
- **兼容**：v1 实现 System V AMD64 的整数/指针与特定双字值子集，外部调用先限于标量；结构体和数组经显式指针传递。UEFI 边界显式使用 Microsoft x64。完整 C ABI 留待后续，不能把当前子集视为完整 C 兼容层。

L0 首版规范见 `lang/spec.md`，包括分号、词法块 `defer`、v1 类型与 ABI 限制、标准库范围、诊断和 L1 验收清单。以下为概览，细节以该规格为准；当前编译器实现范围见 `lang/README.md`。

### 语言要点

| 特性 | 写法 | 说明 |
| --- | --- | --- |
| 变量与类型推导 | `let n = 10`、`var buf: [512]u8` | `let` 不可变，`var` 可变 |
| 基本类型 | `u8`–`u64`、`i8`–`i64`、`bool`、`*T`、`[]T` | 切片带长度 |
| 结构体与方法 | `struct Page { addr: u64 }`、`fn (p: *Page) zero()` | 可加 `packed`、`align(4096)`，直接描述页表项和描述符 |
| 带数据的枚举 | `enum Event { Timer, Key(u8) }` | `match` 必须覆盖所有情况 |
| 错误处理 | `fn alloc() !*Page`、`try alloc()` | 错误是返回值，没有异常 |
| 资源清理 | `defer lock.release();` | 所属词法块退出时逆序执行 |
| 汇编与外部函数 | `unsafe { asm { cli } }`、`extern fn memcpy_avx2(...)` | 只在 `unsafe` 中允许 |
| 中文 | 标识符可以用中文，关键字为英文 | 注释和命名更易读 |

示例（物理页分配）：

```text
module mm.pmm;

import sync.spin;

// lock、free_list 和 Page 是项目模块接口示意。

// 分配一个 4 KB 物理页；内存不足时返回错误
pub fn alloc_page() !*Page {
    lock.acquire();
    defer lock.release();
    let page = free_list.pop() orelse return error.OutOfMemory;
    unsafe { page.zero(); }
    return page;
}
```

### 编译器 dongc 的三个版本

1. **v1（宿主机，Python）**：词法、语法、类型检查，直接生成 NASM 汇编。代码生成用最简单的方案，先保证正确。用 Python 是为了最快拿到可用的编译器，v3 会去掉这个依赖。
2. **v2（优化）**：加入 SSA 中间表示、寄存器分配、常量折叠、内联、死代码删除；输出调试信息，gdb 可以按源代码单步。
3. **v3（自举）**：用 Dong 重写 dongc，在 DongOS 上编译自己。从此系统可以在自身上继续开发。

配套工具：格式化工具 `dongfmt`、VS Code 语法高亮、标准库 `std`（字符串、容器、格式化、IPC 封装、控件库）。

## 10. 推进计划

开发分 11 个阶段：P5 结束时有可用的命令行系统，P7 出桌面，P8 上真机，P9 完成安全加固。安全的基础部分（NX、SMEP/SMAP、句柄权限、微内核隔离）在 P2 和 P4 就已完成，P9 只补需要真机配合的部分。每个阶段只有一条验收标准，不过不开始下一阶段。

另有一条与系统并行的语言线 L0–L3（见下文）。L1 必须在 P2 开始前完成：从 P2 起，除入口和上下文切换等少量代码外，内核、服务、应用都用 Dong 编写。

| 大阶段 | 阶段 | 内容 | 验收标准 |
| --- | --- | --- | --- |
| 打基础 | P0 工具链与 UEFI 入口 | NASM、lld、QEMU + OVMF | 独立串口 hello 与自动验收已在 Windows TCG 实测 |
| 打基础 | P1 引导器 | 读镜像、取帧缓冲与内存图、建页表 | 内核在屏幕和串口输出，启动标志可见 |
| 打基础 | P2 CPU 与内存 | GDT/IDT、缺页、分配器、NX/SMEP/SMAP | 故意缺页显示 panic 屏，保护位全开 |
| 打基础 | P3 中断与线程 | ACPI、APIC、TSC 定时、调度、xsave | 内核线程按时间片交替运行 |
| 可用系统 | P4 用户态与 IPC | syscall、ELF、句柄、IPC、init | IPC 往返 100 万次无错并记录耗时 |
| 可用系统 | P5 基础服务 | PCIe、键盘、存储驱动、FAT32、shell | shell 写入的文件重启后仍在 |
| 可用系统 | P6 多核与快速启动 | SMP、并行启动服务、启动计时 | KVM 下引导器到 shell 不超过 0.5 秒 |
| 图形桌面 | P7 图形桌面 | 合成器、字体、主题、动画、鼠标 | 1080p 下拖动窗口保持 60 帧 |
| 真机与加固 | P8 USB 与真机 | xHCI、HID、U 盘镜像、ACPI 关机 | 真机从 U 盘启动到桌面 |
| 真机与加固 | P9 安全加固 | 安全启动签名、IOMMU、CET、随机化 | 开安全启动可启动，模糊测试 24 小时无崩溃 |
| 持续完善 | P10 持续完善 | 网络、声音、中文输入、更多应用 | 按需迭代，无固定终点 |

下面是每个阶段的任务清单，做完一项就把 `[ ]` 改成 `[x]`。

### 语言线 L0–L3

| 阶段 | 内容 | 验收标准 | 与系统阶段的关系 |
| --- | --- | --- | --- |
| L0 语言规格 | 语法、类型、调用约定、标准库范围 | 规格覆盖内核需要的全部写法 | 与 P0–P1 并行 |
| L1 编译器 v1 | Python 实现，生成 NASM 汇编 | 测试集全部通过，编译出的内核模块能启动 | P2 开始前完成 |
| L2 编译器 v2 | 优化与调试信息 | 关键基准与手写汇编的差距在 20% 以内，gdb 能按源码单步 | 与 P3–P6 并行 |
| L3 自举 | 用 Dong 重写编译器 | 在 DongOS 上编译自身，产物与宿主版一致 | P5 之后 |

- [x] L0：写首版语言规格 `lang/spec.md`（后续需 L1 的 ABI 探针和编译测试反馈）
- [x] L1：dongc v1 词法与语法分析
- [x] L1：类型检查与 NASM 代码生成（编译器侧语言功能）
- [x] L1：编译器测试集，接入 `make test`
- [x] L1：六个标准库全部交付及本地总验收（2026-10-17，353 项宿主测试及 5 次 QEMU 启动通过）

L1 当前进展：`lang/dongc/` 已拆成共享 AST、前端、布局、模块加载、声明依赖、语义和代码生成模块，支持全部整数宽度、局部变量/确定初始化、if/while、短路和各位宽整数检查、普通/packed/align 结构体、固定数组、指针/unsafe、显式转换、布局内建及 JSON 输出。支持切片/UTF-8 字符串、显式源码根导入/可见性、透明类型别名和显式整数/bool 常量；数组长度、重复次数和对齐可使用命名常量与布局内建，并检查依赖环、可见性和局部遮蔽。高对齐局部与临时值采用动态对齐，栈参数、嵌套调用、寄存器保留和最坏帧边界均有独立验证。SysV 支持双字传参/返回/整项落栈，以及 SysV/Win64 标量外调；输出仍为 NASM ELF64。`lang/tests/` 已接入统一测试。P1 内核已执行 42/55 的标量探针、BootInfo 指针读取、结果 373 的内存探针、结果 765 的跨模块切片/ABI 探针、结果 282 的别名/常量探针和结果 458 的高对齐栈探针。

BootInfo 的唯一字段定义在共享模块 `lang/examples/boot/abi.dg`，编译器导出布局，再生成 NASM `struc`；没有第二张手写偏移表。类型布局支持 4096 对齐，局部/临时存储超过 16 对齐时动态对齐栈，保留原帧指针读取传入栈参数；4096 字节最坏栈帧上限包含保存寄存器、动态填充和最大出参区。全局 var 必须显式初始化，全零对象进入 BSS；const 具有只读存储，支持聚合、字符串、对象/字段/元素地址和静态切片，链接重定位使用完整 64 位。4096 对齐全局对象不占局部帧预算，静态物化数据总量当前限制为 16 MiB。wrapping 内建在 debug/release 及编译期按确定位宽取模；非对齐/volatile 支持八种整数，u32/u64 原子固定顺序一致性并返回旧值，参数从左到右单次快照。compiler_fence 无 CPU 指令，受限 asm 每块一条白名单指令，全部内存内建和 asm 均要求显式 unsafe 块。函数指针为精确 ABI/unsafe 签名的非空 8 字节代码指针，可保存在静态对象中、传参和返回；间接调用先快照接收者再求参数，并要求显式 unsafe。Win64 回调通过独立汇编入口保护 RDI/RSI 与 XMM6～XMM15，再重排参数进入 SysV 函数体；桥接及函数体联合计入 4096 字节最坏栈限制，目标须提供 SSE2 执行状态，不生成 SEH。切片没有生命周期/逃逸分析，外部接口限标量/指针。编译器侧方法、局部 const、noreturn、for/loop、枚举/match、可选值、错误传播与 defer 均已实现；双字 ABI 扩展到所有相应类型，静态初始化与模块可见性亦有验证。标准库 D5 的回调 ABI 补测及 D6 的测试 ABI 修正现已复验通过，完整 L1 达到本地门槛，可以开始 P2。

上一轮验收（2026-10-16 至 2026-10-17 初次审查）：`python tools/build.py test` 通过 32 项系统/工具测试、317 项语言/标准库测试，共 349 项宿主测试，以及 P0 回归和 P1 正常/篡改/截短/缺失 5 次 QEMU 启动。新增 25 项语法/布局、16 组语义/模块、5 项后端及3项独立 C/NASM 原生测试，覆盖显式/接收者方法调用、for 范围/数组/切片单次求值与视图、局部常量、noreturn 与短路路径、枚举/匹配、所有标量载荷的可选值/错误结果表示及双字 ABI。defer 覆盖正常、return、break、continue、try 传播、参数延迟读取、返回值保存后清理和 panic 不清理；语义对抗复现已修复不可达 break、延迟枚举布局与 noreturn 表达式求值顺序。P1 新增 `DONGOS_L1_FEATURES_OK: 75`，正常版画面已更新，最后一行 y=444，适配最低 640×480。DeepSeek 的 core.mem/core.int/core.slice/sync.spin 八项测试已独立复验并进入完整回归；标准库源码未由 Codex 修改。清单已迁到 `deepseek-works/`，新增 D5 格式化及 D6 体系结构包装器任务书。D5/D6 随后均交付，各两项定向测试通过；D5 尚缺原任务要求的独立汇编回调 ABI 验证，D6 独立 Win64 哨兵复现了测试观察器调用约定错误，已分别下达补测和修正任务并保留审查记录。编译器侧 L1 功能已完成，完整 L1 等待标准库剩余交付及总验收；本轮未执行远程 CI 或真机测试。
2026-10-17 复验：D5 的独立 NASM 回调、双字返回和不同错误号传播已通过；D6 的观察器显式 SysV 声明已修复并复验。完整回归为 32 + 321 = 353 项宿主测试，以及 5 次 QEMU 启动全部通过。上述上一轮待办现已关闭；六个标准库达到本地 L1 门槛。D7/D8 新任务书、文件归属与实际验收要求见 `deepseek-works/`；D7 补硬件特权实测，D8 提供纯 Dong 的 P2 分配器，均尚待领取。

- [x] L2：SSA 中间表示、寄存器分配、常见优化（2026-10-18 受控标量/指针后端：循环phi合并/并行复制、比较分支、常量提升、有序内存地址/读取合并；388项语言回归、16项O1原生ABI及17服务叶构建通过；原固定五项安静性能均≤1.20，见docs/language-l2-l3.md。未支持函数保留L1，不声明所有函数均优化或新OS客体回归已通过）
- [x] L2：调试信息与 gdb 源码级调试（DWARF4；18项宿主/真实GDB验证源码断点、单步、变量、跨调用/Win64/高对齐展开与遮蔽；ELF调试节非ALLOC且text逐字不变，见 docs/language-l2-l3.md。未据此声明客体内核源码调试已复验）
- [ ] L3：用Dong重写dongc并在DongOS上自举（C29及CR16～CR19已集成、主线16+2组合共18项0skip通过，C29/CR16待修已闭，CR19门禁另派Claude C31，见docs/bootstrap-backend-components.md；C26～C28已集成、主线12+1真实移位/条件选择/间接调用组合共13项通过0skip，C29后续已真实复验并集成，见docs/bootstrap-backend-components.md；CR11～CR15已集成，主线15+1栈帧/内存组合共16项通过0skip、来源稳定，历史CR11/12/13返修闭合，见docs/bootstrap-backend-components.md；C22～C24已集成并完成真实算术组合、主线13项通过0skip，见docs/bootstrap-backend-components.md；追加try/orelse/控制转移语义，96个案例两模式、相关7项通过0skip，见docs/l3-tagged-flow.md；CR8～CR10独立后端模块已集成、主线9项通过0skip，D20已集成、正式/主线同4项通过0skip；CR11端点补交已在本轮真实复验并集成，见docs/bootstrap-backend-components.md；追加原生内存内建语义，85个案例两模式、相关6项通过0skip，见docs/l3-memory-intrinsics.md；2026-10-18追加原生切片语义，37个正反案例两模式、相关语义定向9项通过0skip，见docs/l3-slice-semantics.md；L3已接入原生运行时类型与流程语义子集；此前443项语言回归通过、0skip及当时源码hash稳定属于历史回执，本轮未重跑完整回归。Claude C1～C12、DeepSeek D1～D13及Cursor CR1已独立验收；C7～C12/CR1已接入主线模块和永久测试，并完成两模式原生组合验证，见docs/bootstrap-backend-components.md。完整标签/方法/错误码语义、目标I/O、后端/CLI及真正自举仍待完成，见 docs/language-l2-l3.md）
- [x] 工具：`dongfmt`、VS Code 语法高亮；正式目录15项测试通过，161个DG文件语义/token/注释保留及幂等性、实际TextMate/Oniguruma和离线VSIX验证通过，见 docs/dongfmt.md

### P0 工具链与 UEFI 入口

- [x] 准备 P0 必需工具 NASM、lld-link、QEMU、UEFI 固件；Windows 可执行 `tools/setup_windows.ps1`，复用现有 make/gdb
- [x] USB 镜像工具补齐：纯 Python GPT/FAT32 制作与独立解析承担此流程，替代 mtools；7 项宿主测试及实际 USB 固件启动通过，见 docs/usb-boot-image.md
- [x] 建仓库与当前阶段目录，Makefile 提供 `make` / `run` / `debug` / `test` / `doctor`
- [x] `p0/efi_main.asm` 独立 COM1 输出 hello 和 `DONGOS_P0_PASS`，保留 UEFI 屏幕输出
- [x] 配好 GitHub Actions 和无界面 TCG 自动启动验收（本地已通过，远程工作流尚未执行）

2026-10-16 本地验收记录：Windows、NASM 3.02、lld-link 19.1.5、QEMU 11.0.0 + 自带 EDK II 固件，q35 / 4 核 / 2 GiB / TCG。`make PYTHON=python test` 通过 7 个宿主测试和 QEMU 实启，退出码为 33。另已核对正常版屏幕 hello、正常版持续停留、GDB 远程暂停响应，以及故意设短超时会失败并清理 QEMU。日志和结果在 `build/test/`，屏幕截图在 `build/screen-check/screen.png`。约 1.6 秒是包含固件的宿主进程耗时，不是 P6 的启动指标；Linux CI、其他虚拟机与真机尚未验证。

### P1 引导器

- [x] 用 UEFI 文件协议读入 `DONGOS.IMG`，有界 LZ4 解压，整文件 SHA-256 与编入 EFI 的期望值比对
- [x] 取 GOP 帧缓冲信息与校验后的 ACPI 2 RSDP，直接绘制启动标志
- [x] 取最终内存图并调用 `ExitBootServices`，失效密钥仅在预分配缓冲区中重取并重试
- [x] 建 4 级页表（高半区内核 + 低 4 GiB 恒等/HHDM），切换 CR3 和自有栈，按 `BootInfo` ABI 跳入内核
- [x] 内核侧串口（0x3F8）与独立帧缓冲文字输出

P1 已验证正常启动、载荷篡改、镜像截短和镜像缺失；后三种必须在退出固件之前拒绝。测试版首轮故意传入无效的内存图密钥，已确认真实的重取图/退出固件重试路径。统一 `make PYTHON=python test` 已通过 28 项系统/镜像测试、15 项语言测试和 5 次 QEMU 启动；随后增加 NASM 保留字导出的回归测试，语言测试已单独复测至 16 项全通过，共 44 项宿主测试。其中包括实际执行 SHA-256/LZ4 汇编、独立的标量 ABI 探针和分进程 panic 检查。

镜像/交接契约见 `docs/image-format.md` 与 `docs/boot-protocol.md`。当前内核物理分配、帧缓冲和启动分配限于低 4 GiB，镜像仅包含不超过 2 MiB 的内核，内存图容量 64 KiB；LZ4 编码器为纯 literal block，尚无压缩率收益。P1 临时页表仍为 supervisor RWX，正式权限、零页不映射和保护页属于 P2；不能把 P1 的成功视为安全加固已完成。日志在 `build/test/p1/`，正常画面截图在 `build/screen-check/p1/screen.png`。本轮没有执行远程 CI 或同步在线快照。

### P2 CPU 与内存

- [x] GDT、TSS（含 DF/NMI/普通异常三组独立 IST）、256 项 IDT；当前仅 BSP，IF 保持关闭
- [x] 终止异常处理与 panic 屏：全部通用寄存器、错误码、CR2、受限调用回溯；八种 QEMU 注入通过
- [x] 物理页伙伴分配器、内核对象缓存：BSP单页buddy→活动RW/NX映射→定长槽→全空撤销/失效→归还已接通，见 `docs/page-cache.md`
- [x] 离线 4 KiB 页表核心：map/unmap/protect/query、原子失败、空表回收，独立原始页项与模型验证
- [x] 独立宿主内存链路：规范化图→buddy→离线页表，资源保留、物理地址交接、失败回滚与所有权释放
- [x] 真实BootInfo/链接资源与CPU能力接入：21项保留资源、低4GiB单arena/新表池，私有离线树实启核对且CR3保持原值
- [x] 激活前新栈/PAT准备：UC叶项、GOP/RSDP受限别名、64KiB新栈真实干跑、arena同时容纳表池和栈预检
- [x] 激活前Runtime/IST/审计：高半区视图、退役旧可信栈、六guard、整树白名单与只读控制计划，444宿主/19主线QEMU通过
- [x] 私有树激活：不返回CR3/固定栈交接、缓存维护及寄存器读回，新根下零页/RO/NX/普通栈guard/IST guard真实故障验收
- [x] BSP本地活动WB/NX数据页：原子map/protect/replace/unmap，INVLPG/完整CR3失效后才回收表槽，预热故障与缺失效负控验证
- [x] 在活动新树验证NX/WP/W^X，硬件A/D变化后仍核对完整映射白名单
- [x] 按CPU能力启用SMEP、SMAP、UMIP：五模型门控/真实读回、AC清零与后续supervisor内存路径
- [x] USER/CPL3权限专项：SMEP/NX区分、SMAP读写与AC对照、五条UMIP拒绝/关闭后实际结果；12项权限QEMU通过，见 `docs/user-permissions.md`
- [x] P2核心阶段验收：当前正式版实启、全保护位640×480真实缺页panic，50项主线及9项包装器补验通过，524项同源宿主证据复用；扩展清单仍未完成，见 `docs/p2-acceptance.md`

#### P2扩展（SMP已通过，其余四项保留）

- [ ] 动态执行别名策略：仍属P2扩展，先建立物理别名W^X/所有权及撤权同步契约，P4代码加载前复核；活动API当前仍拒绝USER/EXEC
- [ ] 大页/拆分：仍属P2扩展，独立实现2MiB/4KiB转换、失败不变、失效及回收；当前私有树只用4KiB页
- [ ] PCID生命周期与精确失效：关联P4多地址空间，启用前验证tag复用；当前PCIDE关闭
- [x] SMP shootdown：runtime6 四核共享内核根，BSP 单写者等待全部 AP IPI 应答后回收；真实陈旧映射反例通过，PCID/PGE 关闭
- [ ] PAT写合并：本次明确排期为图形阶段使用WC前完成，先验证PAT/MTRR、缓存类型迁移及冲突别名；当前保留WB/UC、不改PAT

SMP一项已按独立客体验收，其余四项继续承担交付义务；核心阶段验收不将它们视为已实现或删除范围。原单一阶段标准仍为“故意缺页显示panic屏，保护位全开”；范围及依赖见 `docs/p2-acceptance.md`。

P2 CPU 基础实现：私有高半区 GDT/TSS/IDT，三组各 16 KiB 的 IST；正常启动在 Dong 探针前输出 `DONGOS_P2_CPU_READY`。异常保存完整 184 字节上下文，经有界串口和最低 640×480 的 GOP panic 屏报告，生产版停机；测试版以 37 区分正常成功和引导失败。回溯只读已知栈区间，最多 16 帧，重入只给最简标记。早期独立故障构建验证 INT3、UD2、#GP、#PF、坏 RSP、真实 #DF、除零和坏 RBP；后续新树权限与保护页验收见 `docs/paging-activation.md`。IRQ递送、生产用户进程/可返回用户异常和多核尚未实现；隔离CPL3权限测试已完成。

2026-10-17 宿主内存集成：真实 memory_map/phys_buddy/paging 同图编译，独立 C 逐页模型与原始 PTE 遍历验证保留区、动态连续表池、4 GiB 以上 PA、W^X 策略、页表 OOM 不变、别名解除及显式释放。新增 3 项测试通过（24 个正向场景、六次有效交接负控），相关三模块 6 项回归通过；debug/release 与 ELF64/COFF 均覆盖。详见 `docs/memory-integration.md`。仍是离线模型，不替代 D8/D9 原任务验收，也未接真实 BootInfo/CPU 能力、CR3 或硬件权限。

首次真实启动准备已完成：共享160字节BootInfo ABI不变，完整保留资源所属UEFI描述符envelope、链接段/CPU表与IST、实际workspace和新表池；读取真实CPUID能力，管理一个低4GiB对齐4MiB arena，从buddy持有64页池构建私有页表。420项宿主测试（99系统、321语言）、14个正式QEMU用例（3内存准备、8CPU异常、3镜像拒绝）通过，另正常smoke和正式构建通过。新树CR3未激活，GOP/RSDP/完整旧表区未映射，仍需激活前映射/PAT、栈切换桥和IST保护。见 `docs/boot-memory.md`；集成通过不替代DeepSeek任务验收。

上一轮新栈/PAT准备完成：新资源共21项，64页池+16页新栈，GOP UC/RSDP等HHDM别名、真实PAT WB0/UC3检查；在旧CR3下以新栈HHDM真实执行嵌套callback。候选arena预检同时容纳表池与栈，独立6010图/模式核对。429项不同宿主测试（106系统+321语言+2新增arena模型）和16个主线QEMU用例（5内存+8CPU+3镜像）通过，另一次arena修复后正常复跑及正式版构建通过；日志 `build/test/memory-runtime-prep/validation-summary.json`。当时尚未加载新CR3或修改继承的NXE/WP位，legacy物理指针、IST保护和实际权限故障留待后续，详见 `docs/boot-memory.md`。

### P3 中断与线程

- [x] 解析 ACPI：RSDP → XSDT → MADT、HPET、MCFG、FADT（低4GiB、有界清单；558宿主、4配置实启及35项P2回归通过，见 `docs/acpi-discovery.md`）
- [x] LAPIC 与 IOAPIC，屏蔽旧式 8259（真实UC映射、全pin屏蔽及QMP控制器状态复核）
- [x] TSC 校准与 TSC-deadline 定时（能力门控deadline实现/独立native寄存器模型；TCG实测为HPET或PM参考加LAPIC one-shot回退，真实deadline硬件待补）
- [x] 线程结构、上下文切换（含 `xsave`）、优先级调度、自旋锁、等待队列（BSP两忙线程真实抢占，各64tick；XSAVE/FXSAVE两配置，见 `docs/interrupt-runtime.md`）

### P4 用户态与 IPC

- [x] `syscall`/`sysret` 入口、`swapgs`、`copy_from_user` / `copy_to_user`（真实CPL3、完整范围/所有权预检后经supervisor别名拷贝；SMAP保持开启，见 `docs/user-runtime.md`）
- [x] 地址空间与 PCID，ELF64 加载器，用户栈与地址随机化（受控BSP：事务装载/销毁、独立根与双guard、RDSEED/RDRAND门控布局；QEMU原始页表/跨代VA及VMware十次PCIDE保留通过。AP用户调度与每CPU回收仍归P6，见docs/process-integration.md）
- [x] 句柄表与权限位（代际、关闭、降权复制、实际越权/失效句柄拒绝）
- [x] 同步 IPC、共享内存对象、异步通知（两个独立CR3真实call/reply_wait、共享物理页和通知位；通用服务接线继续P5）
- [x] 用户库（Dong类型化封装及SysV `syscalls.asm` 桥，履行libasm接口范围）、服务管理器 `init`、IPC 压测程序（百万真实往返、就绪/依赖/退出/有限重试，正式能力附带、通知和共享对象的正常内核CPL3复验通过；见docs/init-lifecycle.md、docs/process-integration.md）

P4压测里程碑：XSAVE/FXSAVE均完成1,000,000次实际CPL3往返、2,000,015次系统调用；首配置记录46.202672108秒（TCG），生产入口1,000轮与实际坏响应客体拒绝通过。正式通用IPC附带权限、通知对象和共享页API现已由R5正常内核实际补齐，证据为 `build/test/integration-promotions/p4-p5-r5-normal-actual-acceptance.json`；旧runtime计数器不替代这些接口。R6 init发起的首次跨AP启动与当前GUI输入集成回归仍归P6/P7，不据此提前关闭其剩余门禁，见docs/process-integration.md。

### P5 基础服务

- [ ] 设备管理：受控32项PCIe ECAM目录、独立devmgr/四角色匹配、寄存器句柄、IRQ1/12及AHCI单MSI、owner退出撤权均已实测；同boot通用设备恢复与DMA安全回收/重授权仍待完成（故障时持有DMA，不冒充已恢复，见docs/process-integration.md）
- [x] 键盘驱动（i8042，独立CPL3、Set2/RESEND/错误字节与有界回退、IRQ1/12 owner/incarnation/sequence ACK；实际40次控制台循环及400+IRQ通过，见docs/process-integration.md）
- [x] 存储驱动：virtio-blk → AHCI → NVMe（受控子集的实际读写/FLUSH与同盘双启动均通过；NVMe为NSID1/512B轮询，AHCI另有VMware双启动，见 docs/nvme.md、docs/ahci.md。通用设备生命周期和物理盘另验）
- [x] FAT32 文件系统服务（根目录8.3、子目录/LFN/UTF-8、按文件能力授权/代际/退出drain与FS重启撤权，实际读写/FLUSH及同盘双启动通过；全树审计、66个写/FLUSH故障点及GUI文件持久化通过。不承诺journal、rename或任意断电恢复，见docs/fat32.md、docs/process-integration.md）
- [x] shell 与常用命令，在 VirtualBox / VMware 里复测（路径/目录/文件操作、ps/run/wait/kill/磁盘ELF执行/故障隔离及电源命令；最终AHCI在VMware五组十次启动完成实际写/读/FLUSH/原盘重启及PCID生命周期。受支持设备范围见docs/process-integration.md）

### P6 多核与快速启动

- [x] INIT-SIPI 唤醒从核、每核数据、核间中断与 TLB 广播失效（四 vCPU 实测与省略 INVLPG 反例通过，见 docs/smp-runtime.md）
- [x] 每核运行队列与负载均衡（实际CPL3 AP抢占/迁移、GPR/AVX状态、跨代回收、tickless及IPI唤醒；R5正向/无效返回隔离/省略xstate负控共六次实际启动，见docs/process-integration.md）
- [ ] 服务依赖图与并行启动
- [x] 启动计时日志纳入自动测试，4 核压测（真实封存时间线独立复算及四核用户负载；TCG只作诊断，不替代下项KVM性能）
- [ ] Linux/KVM 引导器至 shell ≤0.5秒的原阶段性能验收（当前Windows/TCG及VMware证据不替代）

### P7 图形桌面

- [x] 合成器：窗口缓存、脏矩形、能力门控AVX2非临时呈现与SSE2回退；1080p实际拖动60Hz门禁通过（见docs/graphical-desktop.md）
- [x] 字体预光栅化脚本与抗锯齿文字渲染（英文 + GB2312，7541 glyph；16/20/24/28/32px五字库随bundle装载，按DPI选择真实字号）
- [x] 圆角/阴影、TSC定时淡入淡出与100/125/150/175/200%启动DPI缩放（六客体与原生复验通过）
- [x] 运行时100/125/150/175/200%DPI重配：Settings焦点下 -/= 切换，真实只读字库与布局同步更新（五次设置客体、27项宿主检查和六配置回归通过，含175%一次定向复测；原失败保留）
- [x] 明暗主题与双槽偏好持久化：T切换、S保存、R读取，DESK0.CFG/DESK1.CFG校验、同盘重启和损坏回退（同盘重启、坏新槽/双坏槽及只读保存失败实启通过；不承诺物理掉电FAT原子性）
- [x] 窗口缩放过渡动画（显示/隐藏居中缩放、五档DPI过渡/反向及点击拖动打断、真实中间GOP像素、SSE2回退复验通过；200%拖动60.0216FPS/最慢7.0423ms。四窗DPI移动帧仍约16–23ms，未声称动画恒定60Hz，见docs/graphical-desktop.md）
- [x] 鼠标：PS/2 与现代VirtIO平板实际PCI/DMA双队列；校准/独立授权/回绕及真实输入复验通过
- [x] 控件库、任务栏、终端、文件管理器、编辑器、设置的受控完整应用行为（四个独立CPL3应用，实际文件/程序命令、脏文档确认、主题/DPI持久化与同盘双启动通过，见docs/process-integration.md）
- [x] 图形应用独立进程与启动、退出、崩溃恢复生命周期（四个独立根/ELF、正常退出/受控终止重启，以及有效窗口下真实UD2、旧租约/映射撤销和新进程恢复均通过，见docs/process-integration.md）

### P8 USB 与真机

- [x] xHCI 驱动、USB 键盘鼠标、U 盘（受控direct-root/HID boot/BOT子集：共存与i8042关闭各同盘双启动，真实键鼠消费、USB主盘FAT读写/FLUSH/重启回读及完整DMA隔离通过；Hub/热插拔/物理设备另验，见docs/process-integration.md）
- [x] `make usb` / `python -m tools.build_usb` 生成 GPT/ESP/FAT32 普通启动镜像，QEMU 实际 USB 固件引导到桌面通过；Python 制作流程替代此处 mtools 依赖，实际写盘/真机另验（见 docs/usb-boot-image.md）
- [x] ACPI 关机（`\_S5`）与 FADT 重启（当前受控Q35 IO执行器；静态AML/GAS校验、四次真实启动及FLUSH/原盘持久化、两恶意服务21次实际权限拒绝通过。其它硬件/MMIO/动态AML与通用设备退休另验，见docs/power-management.md）
- [ ] 在至少一台台式机和一台笔记本上实测

### P9 安全加固

- [ ] 用自己的密钥签名引导器，在 OVMF 与真机固件导入公钥
- [ ] IOMMU 限制驱动 DMA
- [ ] CET 影子栈与间接跳转检查，内核基址随机化
- [ ] 系统调用与 IPC 模糊测试工具

### P10 持续完善

- [ ] 网卡驱动与精简 TCP/IP
- [ ] 声卡（HD Audio）
- [ ] 中文输入法、完整 ACPI（睡眠、电池）、更多应用

## 11. 风险与对策

换到 x86-64 后，最大的风险从“真机驱动不动”变成了“工作量和真机差异”，两者都能靠阶段验收和早上真机来控制。

| 风险 | 后果 | 对策 |
| --- | --- | --- |
| 汇编代码量大、易出错 | 寄存器被意外改写、栈不对齐，问题难定位 | 微内核控制内核规模；统一宏和函数头注释；每模块配自测；小步提交 |
| 微内核 IPC 开销拖慢界面 | 窗口拖动卡顿 | 大数据走共享内存不走消息；短消息寄存器传递；P4 就测 IPC 往返耗时 |
| 软件合成带宽不足 | 4K 屏幕动画掉帧 | 脏矩形、写合并显存、AVX2；毛玻璃等重效果可关 |
| 真机与虚拟机差异 | 虚拟机里正常，真机启动失败 | P5 起每个阶段都在 VirtualBox/VMware 复测；串口之外把日志画在屏幕上 |
| 笔记本触控板走 I2C-HID | 内置触控板不可用 | 先支持 USB 鼠标；内置键盘多数仍兼容 i8042 |
| ACPI 完整解释器（AML）工作量大 | 关机、电池、睡眠做不全 | 先只解析 `\_S5` 做关机，重启用 FADT 重置寄存器；完整 AML 放到 P10 |
| 安全启动密钥管理 | 真机上无法开启安全启动 | 开发期关闭安全启动；P9 在固件里导入自己的公钥 |
| 范围膨胀 | 永远做不完 | 每个阶段的验收标准不过，不开始下一阶段 |
| 自研语言拖慢系统进度 | 编译器 bug 与系统 bug 难以区分，系统开发等编译器 | v1 只求正确；特性以 L0 规格为准，不边写系统边加特性；编译器有独立测试集；可随时查看生成的汇编 |

DeepSeek 07:57补交复验：29项永久定向测试、十二个串行QEMU符合预期；D7正确读/写CR3+ret 8均已拒，剩negative runner自身永久回收验证。D9随机raw、D10三类失败快照已有效；原非对齐raw、size0/meta8失败等调用共同保护仍漏检，D8无新完成项。继续D7/D8 R3、D9/D10 R2，无新修订/矩阵或D11。证据 `deepseek-works/reviews/2026-10-17-progress-0757.md`。

激活前离线准备本轮完成：444项宿主（123系统+321语言）、19个正式QEMU用例（8内存预检+8CPU异常+3镜像拒绝），另1次smoke与普通回溯范围退役修正后的正常复跑，正式版仅构建通过。Runtime高半区视图、六个真实IST guard页、旧物理栈可信范围退役、表池HHDM软件视图、全树白名单raw审计及控制状态计划均接入；CR3/CR0/CR4/EFER/PAT在准备与干跑前后不变。正常固件已开启NXE/WP，本轮不写这些位；P1宽权限叶仍不能提供新树的权限保护。新CR3尚未加载，下一步不返回栈交接、缓存策略过渡、实际NXE/WP读回和新树异常验收，见 `docs/paging-preflight.md` 与 `build/test/memory-preflight/validation-summary.json`。

DeepSeek最新独立验收（14:19）：D10最后原4096B边界当前192 count后193立即BG、194才alloc，永久两项通过、零skip；唯一旧坏写控制debug/release均构建成功、实际hit1后立即拒绝，恢复未执行，2拒绝/0漏检，无QEMU/全回归。D10原有限剩余全部关闭，D1～D11现均已验收；不加接口/矩阵/修订或新编号，见 `deepseek-works/reviews/2026-10-17-acceptance-1419.md`。旧记录均保留，P2整体仍在推进。

私有树激活本轮完成（2026-10-17）：460项不同宿主测试（137系统+323语言/标准库，零skip）、24个正式QEMU用例（13内存+8早期CPU+3镜像拒绝），另1次正常smoke，实际25次QEMU全部串行通过；正式版仅构建通过。新CR3/固定栈不返回交接、两次WBINVD及NXE/WP保留位读回、Runtime/GOP访问、允许合法A/D的活动树审计已接入；新根零页/RO/NX/普通栈guard/IST guard分别产生精确#PF与四帧诊断。旧38项快照仍只描述提交前，新增14项activation报告证明提交后状态。P1 GOP此前已为UC，文档中WB→UC假设已更正；PAT/MTRR与旧资源归属不变。记录 `docs/paging-activation.md`、`build/test/memory-activation/validation-summary.json`。活动树修改/TLB回收、SMEP/SMAP/UMIP、大页/PCID/PAT扩展仍待实现。

本地活动数据页修改本轮完成（2026-10-17）：474项不同宿主（151系统+323语言，零skip），26个正式QEMU（15内存+8早期CPU+3镜像拒绝）全部通过；另1次smoke通过、2次省略INVLPG/完整CR3失效的坏客体被门禁拒绝，实际共29次QEMU全部串行。表数17→20→17，A→B读写与三表两轮回收复用正确，回调期间metadata2隔离且失效返回后才可分配；预热后RO降权/unmap产生精确#PF。原38+14字段保留，新增18项mutation读回；正式版仅构建通过。范围仅BSP、WB/NX数据页，不释放buddy/BSS/旧资源。证据 `docs/active-paging.md`、`build/test/memory-mutation/validation-summary.json`，整体位置见 `docs/progress-map.md`。

DeepSeek 12:45只读状态核对：D9/D10/D11有12:3x局部补测，生产源码未变，没有新的完整补交完成状态。D9原raw双端/紧邻guard、D10若干失败/正文、D11独立尾位/真实0/1/奇地址等新增代码先待独立复验；原共同保护仍未齐，仍按原R2/原补测清单完成，不重复实现新增代码。记录 `deepseek-works/reviews/2026-10-17-status-1245.md`，本次状态核对无测试/负控/QEMU。

## 12. 立即开始的下一步

CPU能力硬化本轮完成（2026-10-17）：SMEP/SMAP/UMIP在首次活动Context绑定前按CPUID启用，保留其它CR4位并核对真实读回；入口/终止异常清AC，三处内存策略同步拒绝AC。492项不同宿主测试（169系统+323语言、零skip）及33项正式QEMU通过：五能力模型、15内存、两项全特性活动故障、八早期CPU和三镜像拒绝。省略MOV CR4的临时坏副本因真实读回不符退出35并被门禁拒绝；另保留五次首轮串口宏格式错误的拒绝记录，实际客体共39次，全部串行。正式版仅构建通过；user页SMEP/SMAP拦截和CPL3 UMIP尚未实测，不代表P2整体完成。证据 `docs/cpu-hardening.md`、`build/test/cpu-hardening/validation-summary.json`。

内存/对象缓存活动集成本轮完成（2026-10-17）：新增 `mm.page_cache.Owner` 将真实buddy单页、精确PA范围的活动Context及fixed_cache连接；同步回调重入Busy，活对象拒绝销毁，撤销/完整本地失效/表页回收后才归还物理页；清理失败保留lease，重试路径两模式已验证。生产启动实际运行64槽耗尽/复用和两轮页归还，buddy944→943→944、表17→20→17，两个INVLPG、两个CR3失效、累计退休6；已销毁窗口精确#PF通过。510项不同宿主（187系统+323语言、零skip），36个正式QEMU（新增3个cache、15内存、5硬化模型、2全特性活动故障、8早期CPU、3镜像拒绝）全部通过；另提前归还物理页的隔离坏客体退出35并被拒绝，实际37次客体串行。正式版构建通过且无故障助手；未启动正式版。证据 `docs/page-cache.md`、`build/test/cache-lifecycle/validation-summary.json`。

USER/CPL3权限专项本轮完成（2026-10-17）：仅测试镜像建立独立USER RX/RW-NX页和shadow GDT，以真实CPL0访问及IRETQ进入CPL3复验SMEP、SMAP、UMIP。SMEP与NX同号#PF按raw PTE区分；SMAP有AC=1真读写与AC=0拒绝/关闭放行；五条UMIP各精确#GP0，关闭后五条实际结果正确并在专用HLT终止。524项不同宿主（201系统+323语言、零skip）和15个正式QEMU（12权限+3缓存回归）通过；错误NX/清USER/错误CPL三个真实坏客体全部拒绝。另保留一次首轮SMSW报告宽度失败，实际19次QEMU串行；修正后正式矩阵全部通过。正式版与正常P1测试装载字节均与上轮相同、无权限助手，正式版未启动。证据 `docs/user-permissions.md`、`build/test/permissions/validation-summary.json`。

P2核心阶段本轮验收通过（2026-10-17）：原标准“故意缺页显示panic屏，保护位全开”由当前正式版实启、全保护位下cache-unmap真实PF画面及50项完整主线客体达成。另补跑原九项真实QEMU包装器测试，八坏实现均拒绝、正常实现通过；与同211个源码哈希的524项已验宿主证据合计533项不同测试、零skip。正常与PF两次图像观察均在640×480完成并与串口/ELF/QMP寄存器绑定；首轮GOP配置失败另存，实际62次客体全部串行。正式版装载字节与前轮一致且无测试助手。见 `docs/p2-acceptance.md`、`build/test/p2-acceptance/validation-summary.json`。

P0、P1、L1及P2核心标准已通过本地验收，当前进入P3。首步为安全读取ACPI拓扑：在旧P1物理映射退役前完成解析，将结果复制到内核BSS，在私有CR3与全保护位下继续使用；下一步为LAPIC/IOAPIC及8259屏蔽，再实现定时中断和线程切换。此时仍保持IF=0，P3“内核线程按时间片交替运行”的阶段标准尚未完成。P2五项扩展继续未完成：动态执行别名与大页保留P2归属，PCID/SMP/WC分别关联地址空间、AP共享根和图形启用前条件。DeepSeek D1～D11均已独立验收，无待返修项或新编号。未执行远程CI、真机或性能阶段验收。

- [x] 准备 Windows 原生 P0 工具链；Linux/CI 使用发行版软件包
- [x] 建立 Git 仓库，已配置远程 `origin`
- [x] 跑通 P0（独立串口、屏幕、正常/测试构建、调试入口）
- [x] 确认当前开发环境为 Windows PowerShell，本轮使用 QEMU TCG
- [x] P1：冻结启动信息结构和 `DONGOS.IMG` 格式，实现读取、校验、GOP 与内存图交接并实启
- [x] L1 起步：词法/语法和整数函数子集，生成 ELF64 汇编并在 P1 内核调用
- [x] L1 内存访问：窄整数、结构体/固定数组、指针与 unsafe、布局导出及独立执行测试，P1 内存探针通过
- [x] L1 切片/模块/调用：跨模块类型与可见性、双字/栈参数、SysV/Win64 标量外调，P1 探针 765 通过
- [x] L1 别名/标量常量：跨模块透明别名、编译期整数/bool 常量、命名长度/重复次数/对齐/布局依赖，P1 探针 282 通过
- [x] L1 高对齐栈：局部/临时对象动态对齐、传入栈参数与寄存器恢复、完整最坏帧预算，P1 探针 458 通过
- [x] L1 全局存储：显式初始化 var、只读聚合/字符串/对象地址常量、静态切片和高半区 64 位重定位，P1 探针 436 通过
- [x] L1 硬件内建：wrapping 常量/运行时、非对齐和 volatile、u32/u64 顺序一致原子、compiler_fence 与受限 asm，四线程竞争及 P1 探针 719 通过
- [x] L1 函数调用：函数指针/静态函数地址、间接调用、完整 Win64→SysV 回调桥接、联合栈预算与独立寄存器探针，P1 探针 761 通过
- [x] L1 剩余语言功能：方法、局部 const、noreturn、for/loop、枚举/match、可选值、错误传播与 defer，独立 ABI/清理探针及 P1 探针 75 通过
- [x] L1 标准库总验收：DeepSeek D1～D6 已全部复验；353 项宿主测试及 5 次 QEMU 启动通过，记录见 `deepseek-works/reviews/2026-10-17-D5-D6-recheck.md`
- [x] D7：R3验收，17项宿主及三个旧negative runner变体确认最后外围断言有效；客体六文件hash不变，沿用既有硬件证据
- [x] D8：R3验收，最后holes OOM完整Allocator/metadata快照及四次相关坏写拒绝，算法/已闭六组不变
- [x] D9：原R2最后即时FCHK有效，坏写两模式均在恢复前拒绝，13:09正式验收
- [x] D10：原R2最后4096B边界count后即时BG通过14:19复验，两模式旧坏写均在恢复前被拒，原有限剩余全部关闭
- [x] D11：原有限剩余全部关闭，0/1即时正文/actual odd前guard/MAX返回点及文档通过13:40验收
- [x] P2活动对象缓存集成：真实buddy页与活动RW/NX槽缓存，非空销毁拒绝、回调重入、失效后归还、清理失败保留/重试及最终精确#PF；510宿主/36正式QEMU通过，1提前释放坏客体拒绝
- [x] P2 独立内存集成探针：图规范化→buddy→离线页表及资源/所有权模型，3 项新测试、6 项模块回归通过
- [x] P2 真实内存与激活前准备：Runtime高半区视图、六IST guard和整树/控制预检，444宿主及19主线QEMU用例通过，旧CR3继续使用
- [x] P2 私有树激活：新CR3与固定栈实际启用，五类权限/guard故障通过，当前进度见 `docs/paging-activation.md`
- [x] P2 活动WB数据页与本地TLB：474宿主、26正式QEMU及两次缺失效拒绝通过，失效后表槽回收复用；见 `docs/active-paging.md`
- [x] P2 CPU能力硬化：492宿主、五能力模型及原门禁共33正式QEMU通过，实际CR4/AC读回与缺写负控有效；见 `docs/cpu-hardening.md`
- [x] P2 USER/CPL3权限专项：524宿主、12权限与3缓存回归QEMU通过，错误NX/USER/CPL三个真实坏客体拒绝；见 `docs/user-permissions.md`
- [x] P2核心阶段验收：正式实启/全保护缺页画面与50项主线客体通过，9包装器补验关闭排除项；5项扩展继续未完成，见 `docs/p2-acceptance.md`

OVMF 文件名各发行版不同（旧版是 `OVMF_CODE.fd`），请按本机 `/usr/share/OVMF/` 下的实际文件名替换。

2026-10-17 P7桌面核心里程碑（本轮扩展前历史记录）：生产版1920×1080，按客体完成TSC统计的120次真实PS/2拖动呈现为59.9546 FPS（60Hz目标）、最慢8.8647ms；松开鼠标额外帧明确排除。输入、编辑器真实落盘、窗口隐藏/任务栏恢复、6301页RAM及五个ELF/10用户guard/在线四核TLB域复验通过；12原生测试、旧1000轮IPC兼容及真正省略YMM保存的坏客体拒绝通过。总记录`build/test/p7-desktop/validation/validation-summary.json`，详见`docs/graphical-desktop.md`。P6通用多核调度/DAG/KVM快启及P7平板/高DPI/动画等详细项仍未关闭。

2026-10-17 P7扩展复验：VirtIO平板与100/125/150/175/200%启动DPI、淡入淡出完成。六个真实客体全部通过，120次位移均对应120次呈现，59.9466～59.9985 FPS，最慢8.7117ms；27原生测试零skip，实际DMA/只读字库/动画中间及结束像素、72点任务栏焦点复验通过。总记录`build/test/p7-extensions/validation-summary.json`；主题持久化、运行时DPI重配、缩放过渡、独立应用生命周期及P6余项仍保留。

2026-10-17 P7运行时设置完成：五次正式设置客体通过五档运行时缩放、明暗切换、S/R、同盘重启、新槽损坏回退、双坏槽采用启动默认、只读盘保存失败保留当前外观及编辑内容；确认缓存处理完成、页表META/RAM用量不变、2048页只读字库与四核TLB确认。27项宿主检查零skip，六种桌面配置通过，运行时200%的120次实际呈现为59.9420FPS、最慢8.7174ms。正式共12次启动、11个场景通过：175%首次单窗口时钟校准离群失败，原镜像一次定向复测59.9415FPS通过，失败记录和原阈值保留。总记录`build/test/p7-settings/validation-summary.json`。128B双槽偏好经校验、FLUSH及完整回读后发布，不承诺FAT物理掉电原子性。P7缩放过渡/独立应用、P6调度/DAG/KVM快启及单窗口时钟校准抗抖动继续保留。


2026-10-17 FAT32目录/LFN接线完成：全树两遍有界审计、逐组件UTF-8路径、创建/读写/追加/截断/删除、跨扇区/簇LFN及客户端私有IPC通道正式接入。QEMU/NVMe实际目录写入、FLUSH和同盘双启动通过；同镜像桌面设置5启动、AHCI2启动、VirtIO电源4启动回归均通过，本轮共13次实际启动。主机66个写/FLUSH故障点、真实坏实现负控和v2服务协议测试通过。最终复核196个构建输入、6142个物理读取文件与完整FAT树；证据 `build/test/fat-paths/integration-review/final-0eb2e28973e5/validation-summary.json`，接口/边界见 `docs/fat32.md`。文件句柄授权、通用生命周期/恢复及图形应用路径交互仍保留，不提前关闭完整P5/P0–P9。
