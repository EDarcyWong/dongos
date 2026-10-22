# DongOS

本轮17份缺失任务书、CX6同号异义和CX14/CX15旧状态均已处理完成。CX14 integrated rev7，CX15 integrated rev8；CX6 integrated rev9，已恢复读取器契约，分离5条原NASM事件，耗时恢复为1轮/265秒，原始事件全部保留。协调器issues=0；核对时间2026-10-22T09:18:41+08:00。

当前MCP快照共164项活动任务：19 accepted、140 integrated、3 submitted、1 in_progress、1 rework。本轮同时观测到其它客户端新增5项并行任务，其状态按实时MCP继续变化，本轮没有接管或改动它们。

当前阶段范围见[整体任务图](../coordination/dongos_works/progress-map.md)和[剩余清单](docs/remaining-plan.md)。P2 EXEC/WC与有限G5已集成，完整G5、P5安全恢复和硬件/外部验收继续推进。

以下保留原有记录；其中日期、任务数量、机器路径和“当前/下一步”均属于各自历史检查点，最新状态以上述记录及协调器为准。

DongOS 是一个面向 x86-64 PC 的操作系统项目，目标是安全、快速启动和图形桌面。采用 UEFI 引导与微内核架构，主体使用自研语言 Dong（编译为 NASM 汇编），少量底层入口手写汇编。

当前开发优先级（2026-10-18）：推进L3自举。L2循环与普通指针内存优化已通过固定五项性能门槛，真实GDB源码调试已复验。L3已接入原生运行时类型与流程语义子集；443项语言回归通过、0skip，源码hash稳定。Claude C1～C6及DeepSeek D1～D13已独立验收，Cursor CR1字节常量任务已发布。完整标签/方法/错误码语义、目标I/O、后端/CLI及真正自举仍待完成；范围及证据见[语言线记录](docs/language-l2-l3.md)。

当前已实启 **P7 的 1920×1080 图形桌面核心**，支持 VirtIO 平板、五档运行时 DPI、主题持久化及窗口缩放过渡。反向和拖动打断、半透明边框、SSE2/FXSAVE 回退均已实际复验。200%拖动为60.0216 FPS、最慢7.0423ms；四窗口 DPI 移动帧约16–23ms，尚未达到恒定60Hz。七样本 HPET/PM 时钟校准已替换早期单窗口实现，见[桌面记录](docs/graphical-desktop.md)和[时钟记录](docs/clock-calibration.md)。

P4百万次IPC、P5持久化与P6四核/TLB里程碑保留。新增可引导 GPT/ESP 镜像、Q35 S5/重启及21项电源权限负控已通过；[dongfmt 和 VS Code 高亮](docs/dongfmt.md)已交付。NVMe 已通过[QEMU实际读写、FLUSH与同盘双启动](docs/nvme.md)，同镜像AHCI与VirtIO回归通过。AHCI 已通过 QEMU 严格模式与 VMware 的真实双启动shell读写、FLUSH及原盘持久化，见[跨 VM 记录](docs/vmware-validation.md)；FAT32 子目录与长文件名已完成[实际 NVMe 读写、FLUSH 和同盘双启动](docs/fat32.md)，支持中文、emoji、空格路径及 shell cwd。本轮目标为 P0–P9；独立应用生命周期、通用多核调度、文件句柄授权、KVM和真机等余项见[完整清单](docs/remaining-plan.md)，P10另定范围。

启动桌面（默认保留数据盘）：

```powershell
python -m tools.run_desktop
# 200%默认缩放；有效的磁盘偏好优先，--ps2 可选择鼠标回退
python -m tools.run_desktop --scale 200
```

聚焦设置窗口后，`-` / `=` 在五档缩放间循环，`T` 切换完整明暗主题，`S` 保存、`R` 读取磁盘设置。启动优先选择数据盘上有效且序号最新的 `DESK0.CFG` / `DESK1.CFG`，两槽均无效时采用镜像的 `--scale` 默认；`--scale` 不能覆盖有效的已保存偏好。默认数据盘仅在不存在时创建，重启保留文件。

Display版本3通过只读128B描述符共享当前指标；五个真实字号字库一起打包，切换固定8MiB字体孔径并等待四核TLB确认。每槽偏好为128B，保存经校验、FLUSH和完整回读后发布序号，保留旧有效槽；不承诺FAT在物理掉电时的原子性。早期设置门禁为 `build/test/p7-settings/qemu/run-25bd369c2690/result.json`，其首次175%时钟离群失败和同镜像复测均保留；后续时钟加固与窗口过渡证据见上述记录。

## 文件说明

- `PLAN.md`：完整的架构与推进计划（在线可编辑版：https://claude.ai/code/artifact/88664644-09d5-4088-8ef5-cf9773cf0347）
- `p0/efi_main.asm`：P0 验收代码，UEFI 应用，打印 `DongOS: hello, x86-64 UEFI!`
- `p0/build_and_run.sh`：P0 构建与运行脚本
- `boot/efi_main.asm`：P1 引导器；`boot/image.asm`：SHA-256 与 LZ4
- `kernel/entry.asm`：内核交接、映射检查、串口及正常/panic 画面；`kernel/abi_probe.asm`：独立 ABI 助手
- `kernel/cpu.asm`、`include/cpu.inc`：P2 GDT/TSS/IDT、独立 IST 和异常上下文；`kernel/panic.asm`：有界诊断与回溯
- `kernel/cpu/hardening.dg`、`kernel/cpu_hardening.asm`：SMEP/SMAP/UMIP能力门控、实际启用与读回；见 `docs/cpu-hardening.md`
- `kernel/mm/paging.dg`、`active_paging.dg`：四级4KiB离线核心、活动原子修改与同步失效/回收；契约见 `docs/paging.md`、`docs/active-paging.md`
- `kernel/memory_probe.dg`、`kernel/boot/`、`kernel/cpu/capabilities.dg`：真实启动资源与 CPU 能力收集，构建并核对私有新页表
- `tests/test_memory_integration.py`：内存图→buddy→离线页表的独立宿主模型，资源与生命周期见 `docs/memory-integration.md`
- `tools/gen_offsets.py`：从 Dong 布局 JSON 生成 NASM 结构体，BootInfo 不再手写偏移
- `tools/build.py`：跨平台构建、运行、调试与依赖检查入口
- `tools/syscall_corpus.py`：P9 syscall/IPC 离线语料生成、严格校验及有限减小；用法见 [语料格式](docs/syscall-corpus.md)
- `tests/run_qemu.py`：无界面 QEMU 启动验收；`tests/run_cpu_qemu.py`：独立 CPU 异常注入验收
- `tests/run_memory_qemu.py`：15项串行门禁，核对真实资源、激活/活动修改读回及静态与预热后的权限故障
- `tests/run_hardening_qemu.py`：五种CPU能力组合的独立门禁，已接入P1完整test入口
- `tests/run_cache_qemu.py`：buddy/活动单页对象缓存生命周期与最终撤销故障门禁
- `kernel/permission_test.asm`、`tests/run_permission_qemu.py`：仅测试版链接的USER映射/CPL3探针及十二项独立权限门禁
- `lang/spec.md`：Dong v0.1 规格；`lang/dongc/`：当前 L1 子集编译器
- `deepseek-works/`：DeepSeek 标准库任务索引、独立任务书、交付与验收记录
- `docs/boot-protocol.md`、`docs/image-format.md`：当前交接与镜像格式；`docs/cpu-exceptions.md`：P2 异常处理
- `.github/workflows/ci.yml`：Linux CI 构建与启动验收

计划的在线快照地址保留在 `PLAN.md`，本地状态以仓库和可重现测试为证据；在线版本需要另行同步。

## 工具链

需要 Python 3.10+、NASM、LLVM 的 `lld-link` 和 `ld.lld`、QEMU x86-64 和匹配的 UEFI 固件。Python 脚本仅使用标准库，Makefile 是可选入口。

Ubuntu / Debian：

```sh
sudo apt install python3 nasm lld qemu-system-x86 ovmf make mtools gdb gcc
make doctor
make test
```

Windows PowerShell：

```powershell
powershell -File tools/setup_windows.ps1
python tools/build.py doctor
python tools/build.py build
python tools/build.py test
```

Windows 可使用 [NASM](https://www.nasm.us/)、[LLVM](https://releases.llvm.org/) 和 [QEMU 官方下载页指向的 Windows 发行版](https://www.qemu.org/download/#windows)。脚本查找环境变量、PATH、项目 `.tools/` 下的便携工具，以及 Visual Studio 自带的 x64 `lld-link.exe`。`.tools/` 不入库。

`setup_windows.ps1` 固定版本并校验下载哈希，将 NASM、QEMU 和固件免安装解包到 `.tools/`（约 1.2 GB），不改系统 PATH。LLVM 链接器复用已有安装，缺少时脚本给出安装地址。也可自行准备依赖，跳过此脚本。

| 环境变量 | 用途 |
| --- | --- |
| `NASM`、`LLD_LINK`、`LD_LLD`、`QEMU` | 指定对应可执行文件，值内无需额外引号 |
| `OVMF_CODE`、`OVMF_VARS` | 同时指定一套匹配的固件代码与变量模板 |
| `OVMF_DIR` | 在指定目录内查找匹配固件 |
| `PYTHON` | Makefile 与兼容 shell 脚本使用的 Python 命令 |

默认识别 `/usr/share/OVMF/` 下的 4M / 旧版固件，以及 QEMU Windows 包 `share/` 中的 `edk2-x86_64-code.fd` + `edk2-i386-vars.fd`。每次启动复制变量模板到 `build/`，不会改写原始固件。当前使用关闭安全启动的固件，签名留待 P9。

## 构建、运行与调试

| 操作 | Make | Python（Windows 用 `python`） |
| --- | --- | --- |
| 检查依赖 | `make doctor` | `python3 tools/build.py doctor` |
| 构建 UEFI 应用 | `make` | `python3 tools/build.py build` |
| 启动图形窗口 | `make run` | `python3 tools/build.py run` |
| 暂停并等待 GDB | `make debug` | `python3 tools/build.py debug` |
| 全部验收 | `make test` | `python3 tools/build.py test` |
| 创建新的 USB 启动镜像 | `make usb USB_IMAGE=build/usb/dongos.img` | `python3 -m tools.build_usb --output build/usb/dongos.img` |

USB 镜像含 GPT、FAT32 ESP 和完整桌面启动文件，已通过 QEMU 从 xHCI USB 介质启动到桌面；产物只创建为新的普通文件。用户文件仍走现有数据盘，操作系统 USB 驱动及实际写盘/真机验收继续推进，见 [USB 镜像记录](docs/usb-boot-image.md)。

默认构建和运行 P1，产物为 `build/esp/EFI/BOOT/BOOTX64.EFI` 与 `build/esp/DONGOS.IMG`，中间文件位于 `build/p1/`，包括 `kernel.elf`、含零填充 BSS 的 `kernel.bin`、哈希 manifest 和汇编清单。修改内核后必须同时更新 EFI 和镜像。

BootInfo 的唯一字段定义在共享模块 `lang/examples/boot/abi.dg`。构建以 `lang/examples` 为显式源码根加载模块图，先导出 `dong_layout.json`，再生成 `bootinfo_layout.inc`，引导器与内核共同包含该文件；布局、切片、unsafe 与当前编译器限制见 [lang/README.md](lang/README.md)。

加 `--stage p0` 可单独构建/运行 P0，产物位于 `build/p0/esp/`。旧命令 `sh p0/build_and_run.sh` 保持运行 P0。宿主测试可单独执行 `python3 -m unittest discover -s tests` 和 `python3 -m unittest discover -s lang/tests`。

默认 `q35`、4 核、2 GiB 内存和 TCG 软件模拟，没有硬件虚拟化权限也能启动。交互运行可指定 `--accel kvm`（Linux）或 `--accel whpx`（Windows），无图形环境可加 `--headless`。

```sh
python3 tools/build.py run --headless
python3 tools/build.py debug
# 另一个终端启动 gdb 后执行：
# target remote localhost:1234
```

调试模式加上 `-s -S`，CPU 从固件入口暂停；GDB 端口为 1234，异常日志位于 `build/run/p1/qemu.log`。引导器是固件重定位的 PE 应用，可结合实际加载地址、`efi_main.map` 与 NASM 清单查看；P1 内核固定链接到 `0xffffffff80000000`，可在 GDB 加载 `build/p1/kernel.elf` 的汇编符号。当前没有 Dong 源码级调试。

## 自动验收

`make test` 与 `python tools/build.py test` 调用同一入口：宿主和语言测试、P0/P1、CPU异常、内存/活动页表、硬化、缓存、权限专项与P3 ACPI四配置门禁。测试版在各runner独立目录构建，QEMU串行使用无界面TCG。以下为P1/L1前缀；其后还需完整P2字段与阶段标记、24项ACPI字段及`DONGOS_P3_ACPI_READY`，最终才到`DONGOS_P2_MEMORY_READY`和`DONGOS_P1_PASS`。精确协议由各runner验证：

```text
DONGOS_P1_START
DONGOS_P1_IMAGE_OK
DONGOS_P1_READY
DONGOS_P1_EBS_RETRY
DONGOS_P1_EBS_OK
DONGOS_P1_KERNEL_HIGH_OK
DONGOS_L1_PROBE_OK: 42
DONGOS_L1_MEMORY_OK: 373
DONGOS_L1_SLICE_ABI_OK: 765
DONGOS_L1_CONSTANTS_OK: 282
DONGOS_L1_ALIGNMENT_OK: 458
DONGOS_L1_GLOBALS_OK: 436
DONGOS_L1_INTRINSICS_OK: 719
DONGOS_L1_FUNCTIONS_OK: 761
DONGOS_L1_FEATURES_OK: 75
```

测试内核随后向 `isa-debug-exit` 写入 `0x10`，QEMU 返回 `33`。篡改、截短和缺失镜像必须分别输出哈希、长度和打开失败诊断，返回 `35`，且不得到达退出固件或内核标记。每个用例检查完整行、顺序、退出状态和 60 秒超时。正常构建不访问退出设备，保留内核画面。COM1 是当前固定调试设备，真机差异留待设备发现阶段处理。

测试版第一次退出固件时故意传入一个无效密钥，要求出现一次 `EBS_RETRY` 后重新取图并成功退出，以覆盖真实的重试路径。正常版不注入错误密钥。

日志与结果位于 `build/test/p0/normal/`、`build/test/p1/<case>/`，各有串口、QEMU 输出与结果 JSON。记录时间含固件，不能作为 P6 启动性能指标。正常 P1 画面已实测，截图在 `build/screen-check/p1/screen.png`。

当前 P1 边界为：低 4 GiB 启动分配和帧缓冲、最大 2 MiB 内核、64 KiB 内存图，以及 GOP RGB/BGR 且至少 640×480。LZ4 编码器暂用纯 literal block，解码器支持重叠复制；目前没有压缩率收益。P1临时页表允许读写执行；P2启动随后切到W^X和guard生效的私有树，旧资源仍保留。完整交接契约见 [docs/boot-protocol.md](docs/boot-protocol.md)。

GitHub Actions 在 Ubuntu 上执行相同验收，保存串口日志，失败时保留构建产物。工作流已配置，远程执行状态以 GitHub Actions 结果为准。

## 下一步

P3已进入ACPI发现与持久拓扑阶段，下一步为LAPIC/IOAPIC与旧8259屏蔽，之后推进TSC校准、定时中断、线程上下文与调度；当前IF仍关闭，尚未达到P3时间片线程验收标准。P2核心已验收、五项扩展继续保留未完成。见[ACPI记录](docs/acpi-discovery.md)、[P2阶段验收及剩余任务](docs/p2-acceptance.md)与[整体进度图](docs/progress-map.md)。以下保留此前各轮实现和验收记录。

离线 4 KiB 页表模块已实现 map/unmap/protect/query，支持失败不变、空表回收和 NX/权限校验，见 [docs/paging.md](docs/paging.md)。此前页表模块一轮通过 63 项系统宿主测试与 321 项语言测试，共 384 项；模块未接活动 CR3，该轮未重跑不受影响的 QEMU 启动链。

独立 P2 内存集成探针已接通内存图规范化、伙伴分配器和离线页表，验证保留资源、4 GiB 以上地址、权限、失败回滚与显式释放。新增 3 项集成测试及 6 项相关模块回归通过，包含两模式/三 seed 共 24 个模型场景和六次交接负控。复现 `python -m unittest tests.test_memory_integration -v`，详见 [内存集成记录](docs/memory-integration.md)。

私有树激活及BSP本地活动数据页修改已完成：原子发布/CAS保留硬件A/D，叶修改后INVLPG，中间表撤链后保持隔离，完整CR3失效后才回收。预热后RO降权/unmap的真实故障与省略失效的坏副本均经独立门禁验证。复现 `python tests/run_memory_qemu.py --all`，详见[活动页表记录](docs/active-paging.md)。随后已完成SMEP/SMAP/UMIP能力策略及内存分配/缓存集成；动态执行别名、大页、PCID、SMP shootdown及PAT扩展继续后续实现。

P2 CPU 基础设施和终止异常诊断已通过 379 项宿主测试和 13 次 QEMU 启动，见 [docs/cpu-exceptions.md](docs/cpu-exceptions.md)。统一 `test` 入口包括八种真实 CPU 异常注入；可单独运行 `python tests/run_cpu_qemu.py --all`。

L1 编译器、六个基础标准库和原内核探针已通过本地总验收，见 [复验记录](deepseek-works/reviews/2026-10-17-D5-D6-recheck.md)。D1～D11现已全部验收：14:19复验确认D10最后一处count后即时BG有效，永久2项通过、零skip，唯一旧坏写控制在debug/release均立即被拒绝，2拒绝/0漏检。原有限剩余全部关闭，见[最新验收](deepseek-works/reviews/2026-10-17-acceptance-1419.md)及[任务索引](deepseek-works/README.md)。本轮已另行完成活动内核集成，定时检查保持取消。

12:45/12:53历史进度与复验记录保留；主线回归不替代DeepSeek原任务负控验收。

开发阶段、语言设计和各阶段验收标准见 [PLAN.md](PLAN.md)。
