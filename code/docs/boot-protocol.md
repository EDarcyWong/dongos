# P1 启动交接 ABI v1

状态：已在 QEMU q35 / EDK II、4 核、2 GiB 内存、TCG 上实测。此文描述当前交接实现；内核已接入 P2 的私有 GDT/TSS/IDT、终止异常诊断和真实 BootInfo 的离线内存准备，活动页表与硬件保护仍待切换。

## 启动链

`BOOTX64.EFI` 从自身所在设备的文件系统根目录读取 `DONGOS.IMG`，验证长度、头和整文件 SHA-256，解压内核，取得 GOP、ACPI 2 RSDP 和内存图。引导器分配完资源、关闭文件并绘制启动标志后，取得最新的内存图密钥并调用 `ExitBootServices`。

若固件因密钥失效返回 `EFI_INVALID_PARAMETER`，只用已有缓冲区重新取图并重试，最多 8 次；期间不分配内存或调用设备协议。成功后仅使用自己的代码、页表、栈、串口和帧缓冲；不再调用固件服务。

镜像字节格式见 [image-format.md](image-format.md)。本阶段仅包含平坦内核载荷；构建系统先链接 `kernel.elf`，再按 ELF 的 `PT_LOAD` 段生成含零填充 BSS 的载荷。ELF 入口固定为 `0xffffffff80000000`。镜像与 EFI 必须一起更新，否则校验失败。

## BootInfo

字段布局唯一来源为共享模块 [lang/examples/boot/abi.dg](../lang/examples/boot/abi.dg) 的 Dong `BootInfo` 声明；编译器导出 `dong_layout.json`，`tools/gen_offsets.py` 再生成 NASM 定义，由 [include/bootinfo.inc](../include/bootinfo.inc) 包含。全部字段均占 8 字节，共 160 字节；数值为小端，类型中的地址字段保存物理地址，P1 也可经恒等映射直接访问。

| 偏移 | 字段 | 含义 |
| --- | --- | --- |
| 0 | magic | 字节串 `DONGBOOT` |
| 8 | version | 1 |
| 16 | size | 160 |
| 24 | flags | bit 0：已成功退出固件服务 |
| 32 | memory_map | 最后一次成功获取的原始 UEFI 内存描述符数组 |
| 40 | memory_map_size | 有效数组字节数 |
| 48 | descriptor_size | 每项字节跨度，不能固定按 40 字节遍历 |
| 56 | descriptor_version | 当前要求 1 |
| 64 | framebuffer_base | GOP 物理基址 |
| 72 | framebuffer_size | 固件报告的缓冲区容量 |
| 80、88 | width、height | 有效宽、高 |
| 96 | stride | 每扫描行的像素数 |
| 104 | pixel_format | UEFI 0：RGB 字节顺序；1：BGR 字节顺序 |
| 112 | rsdp | 已校验 20 字节及扩展校验和的 ACPI 2 RSDP |
| 120、128 | kernel_physical、kernel_size | 解压目标及实际载荷大小 |
| 136 | pml4_physical | 自建页表根 |
| 144、152 | stack_physical、stack_size | 64 KiB 内核栈 |

内存图包含上述分配及 EFI 镜像自身；在 P2 真正接管、复制必要数据之前，不得回收这些区域。不要把 `EfiLoaderData` 一概视为立刻可释放。

当前已从真实交接图收集完整分配描述符 envelope、链接段、CPU 表/IST、workspace、新页表池和新分配栈共 21 项保留资源。v1 未提供原始 AllocatePages 边界，所以保守保留整个所属描述符；新 accessor 不改变 160 字节 ABI。详见 [真实内存准备](boot-memory.md)。 内核另建Runtime高半区视图，BootInfo及其PA字段保持原值；显示/panic与页表软件访问不再解引用这些低地址。新树的六个IST保护页和整树预检见 [激活前检查](paging-preflight.md)。

## 内核入口与地址空间

引导器关闭可屏蔽中断，加载自己的 GDT 和临时空 IDT，切换 CR3，设置内核栈，以 `rdi=BootInfo*` 跳入内核。`rsp % 16 == 8`，栈上有一个停机返回地址，方向标志清零。普通内核函数遵循 SysV；UEFI 调用与解压/哈希助手遵循 Microsoft x64。内核入口随后安装自己的高半区 GDT、TSS 和全部 256 项 IDT，使用双重故障、NMI 和普通异常三组独立 IST 栈；IF 保持关闭。表核验通过输出 `DONGOS_P2_CPU_READY`，异常诊断与验收见 [cpu-exceptions.md](cpu-exceptions.md)。

| 虚拟范围 | P1 映射 |
| --- | --- |
| `0` 到 `4 GiB` | 物理地址恒等映射 |
| `0xffff800000000000` 起的 `4 GiB` | 同一物理范围的 HHDM 别名 |
| `0xffffffff80000000` 起的 `2 MiB` | 2 MiB 对齐的内核物理区域 |

使用 4 级页表、2 MiB 叶页和 supervisor 映射。切换时清除 CR4.PGE，避免遗留固件 global TLB 项。帧缓冲覆盖的叶页及其别名设为默认 PAT 下的 UC；写合并留到 P2。**P1 临时映射允许读写和执行，也映射了零页；P2 必须替换为保护后的正式映射。**

内核检查 BootInfo 版本、尺寸、退出标志、CR3、高半区执行地址和 HHDM 别名，再调用 Dong 生成的加法/求和函数核对 42、55。随后 Dong 函数通过 `*const BootInfo` 调用共享模块读取实际交接数据，并执行结构体/数组/packed/窄整数转换/指针别名/聚合复制探针，核对结果 373。跨模块切片窗口/修改/求和、切片整项落栈、UTF-8 字符串，以及 SysV/Win64 各 8 个标量参数的外调核对 765，外部助手独立实现于 `kernel/abi_probe.asm`。`boot.constants` 的别名/常量/布局核对 282，`alg.aligned` 的局部/临时对象对齐及栈参数核对 458。`boot.state` 核对跨模块全局读写、只读聚合复制、UTF-8/NUL、静态切片、4096 对齐 BSS、自引用和完整高半区地址，结果 436。`alg.intrinsics` 核对 wrapping 常量、非对齐和 volatile 访问、u32/u64 原子的模加法及 CAS 成败、编译器屏障和受限 CPU 屏障，结果 719。`alg.functions` 核对高半区静态函数表、全局与返回函数指针、两种 ABI 八参数间接调用，以及 Win64 回调进入 SysV 函数体，结果 761，输出 `DONGOS_L1_FUNCTIONS_OK: 761`，随后执行下述语言探针。屏幕全部文字仍适配最低 640×480。原子探针只使用普通 RAM；此处尚无调度器；异常可报告完整寄存器、CR2、受限回溯和 GOP panic 屏后停机，不支持恢复。

Win64 回调的显式汇编桥接保存 RDI、RSI 和 XMM6～XMM15，再重排参数调用 SysV 函数体，返回时完整恢复。内核在该探针前清除 CR0.EM/TS、设置 CR0.MP 及 CR4.OSFXSR/OSXMMEXCPT，明确提供 SSE2 保存/恢复需要的执行状态。普通 Dong 函数体仍不生成 SIMD；此项不包含 P2 的任务状态管理、每线程扩展状态保存或异常处理。桥接不提供 SEH 展开，异常不得穿越 Dong 栈。

函数指针探针之后调用 `alg.l1`，检查结果 75 并输出 `DONGOS_L1_FEATURES_OK: 75`。该探针执行真实的 `try` 失败传播和成功返回清理、方法、局部常量、for/loop、枚举匹配与可选回退，再绘制最终画面和报告 PASS；没有依赖标准库。最后一行文字在 y=444，仍适配最低 640×480。编译器与六个基础标准库已另行通过 L1 本地总验收；P2 当前继续推进 CPU、内存和保护机制。

目前在语言探针和最终画面之间还有真实内存准备：读取 CPUID、规范化一个低 4 GiB arena、分配新表池、构建并核对离线页表，输出 `memory_*` 数值/资源清单与 `DONGOS_P2_MEMORY_READY`。汇编独立确认 CR3 前后相同；旧 P1 映射继续服务当前执行。新树保留了全部资源，但尚非可直接激活的完整地址空间。

## 当前支持边界与验收

- 必须有 ACPI 2 表和 GOP RGB/BGR 32 位帧缓冲；不支持 bitmask / BLT-only。
- 引导器、启动分配、RSDP、完整帧缓冲范围必须在低 4 GiB，超出明确失败。
- 内核载荷最多 2 MiB，镜像最多 4 MiB，内存图预留 64 KiB；超出明确失败。
- 内核画面要求至少 640×480；最大宽高 8192，最大 stride 16384。保持固件当前模式，不主动切换分辨率。
- LZ4 编码器当前写合法的纯 literal block，没有压缩率优化；引导端解码器支持完整的有界重叠复制。

`python tools/build.py test` 执行宿主测试、语言测试、P0 回归及 P1 正常/篡改/截短/缺失四种启动。失败镜像必须在退出固件之前拒绝。日志在 `build/test/p0/normal/` 与 `build/test/p1/<case>/`，正常版截图在 `build/screen-check/p1/screen.png`。宿主进程耗时含固件，不能代替 P6 计时。

测试版的第一次 `ExitBootServices` 故意传入按位取反的无效密钥，必须报告一次 `DONGOS_P1_EBS_RETRY`，再取内存图并成功退出。正常构建没有该注入；这项测试不通过分配额外内存制造密钥失效。

P2 CPU 异常注入作为统一验收的后续步骤执行，每个用例使用独立的内核/EFI/ESP，日志与结果在 `build/test/cpu/`；正常镜像不包含注入。
