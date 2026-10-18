# NVMe 块设备

`services/drivers/nvme_core.dg` 负责命令、PRP、Identify 和 CQ 状态机；
`services/drivers/nvme.dg` 负责受检 BAR 回调、DMA 发布、门铃、真实毫秒时限和块接口。
二者从已经通过原生复验的原型推广到正式路径，测试直接编译正式源码。
已接入内核授权和正式块服务，并通过QEMU实际读写、FLUSH、同盘双启动及独立磁盘复验。实际记录见文末；原生模型与实际执行证据分别保留。

## 接纳范围与块接口

控制器版本仅接纳 VS 1.0–1.4、NVM 命令集、4 KiB 主机页和非零 CAP.TO。
VS 2.x、CRMS/CRTO 就绪模式、非零 MPSMIN 和未知能力组合会失败。
CAP.TO 的 1–255 直接换算为 500–127500 ms，分别用于 RDY 转换；普通命令另有 5000 ms 时限。
没有用轮询次数模拟硬件超时。

仅操作 NSID 1，使用选中的 512 字节逻辑块格式，不使用 metadata、PI、共享 namespace 或 thin provisioning。
Identify Controller 的 NN 是有效 NSID 的上界，接受 1–fffffffe；它不证明只有一个活动 namespace。
NSID 1 必须通过独立 Identify Namespace 验证，所有 SQE 仍固定 NSID 0/1，不遍历或操作其他 namespace。
单次读写最多 128 个 sector，并按 Identify MDTS 收紧。只读 namespace 可读，写入会失败。

NSFEAT 仅接受 DAE 能力位 2 和 OPTPERF 建议字段 5:4，其他位保持拒绝。
DAE 表示支持返回未分配块错误，不等于启用 Error Recovery 的 DULBE；驱动没有启用该功能。
OPTPERF 的四个编码只说明推荐对齐和粒度字段是否有效，忽略这些建议不会改变本驱动的 Read/Write 字节格式。
若设备实际返回非零状态，驱动保留失败，读取输出不变并进入永久故障状态。
这不是对 controller 2.x 就绪协议或其他 namespace 功能的支持。

```text
Ops = { read:vp.Read, write:vp.Write, fence:vp.Fence,
        acquire:blk.Acquire, release:blk.Release, enable:Enable, now:Now }
Enable = unsafe fn(context:u64)u64
Now    = unsafe fn(context:u64, out_ms:*u64)u64
initialize(state:*State, bar:*const vp.Bar, ops:*const Ops, context:u64)!void
read_sectors(state:*State, lba:u64, count:usize, output:*u8)!void
write_sectors(state:*State, lba:u64, count:usize, input:*const u8)!void
flush(state:*State)!void
describe(state:*const State, output:*Info)!void
```

State 为 656 字节，Ops 为 56 字节，Info 为 56 字节。
Info 依次给出 capacity、max transfer、readonly、ready、faulted、held、completed 七个 u64。
State 中 Info 位于 0，Lease 位于 56，Bar 位于 88，Ops 指针位于 112，context 位于 120，
Admin Queue 位于 240，I/O Queue 位于 408，last CQE 16 字节快照位于 632。
编译器布局清单和独立 C 结构同时检查这些布局。
State、Ops 和输入输出使用稳定、互不重叠的借用；请求串行执行。

## DMA、授权和初始化

持有一个连续、4 KiB 对齐、低于 4 GiB 的 128 KiB 内核 lease。
Lease 分别保留 token、总线物理地址和 CPU 映射；驱动不把 PA 当作指针。

| 区域 | 相对 lease 的偏移 | 用途 |
| --- | ---: | --- |
| Admin SQ | 0000 | 64 字节 SQE，深度 2 |
| Admin CQ | 1000 | 16 字节 CQE，深度 2 |
| I/O SQ 1 | 2000 | 64 字节 SQE，深度 2 |
| I/O CQ 1 | 3000 | 16 字节 CQE，深度 2，IEN 0 |
| PRP list | 4000 | 最多 16 个有效小端 qword |
| Identify | 5000 | Controller / Namespace 共用的 4096 字节缓冲 |
| I/O data | 6000 | 最多 64 KiB 数据；纯核心另验证首 DWORD 偏移 |

先在 BME 未授权时观察 firmware 的 CC.EN / CSTS.RDY，遵守转换顺序停稳控制器。
EN1/RDY0 必须先等到 RDY1 才清 EN；EN0/RDY1 必须等 RDY0 才改队列基址。
只有 reset 前一次观察允许已完成 firmware shutdown 的 SHST2，SHST1 不支持。
reset 后及新命令阶段要求 SHST0/CFS0。

停止后清零完整 lease，初始化 CQ phase 1，配置 INTMS、CC 00460000、AQA 00010001，
ASQ=lease+0000、ACQ=lease+1000，再发布 CPU 写入并调用内核 Enable。
Enable 只有 context，没有用户提交的地址或 PCI 命令字。
内核必须从实时配置、MMIO 和自己的 lease 重建授权条件，验证 disabled/RDY0、Admin bases、
完整分区、MSI/MSI-X 禁用和独占归属后，才允许 BME。
之后 runtime 写 CC 00460001，等 RDY1，依次完成 Identify Controller、Identify Namespace 1、
Set Features Number of Queues、Create I/O CQ 1、Create I/O SQ 1，最后才发布 ready。
I/O 队列基址由受检 Admin SQE 注册，不是假想成可直接读取的 AHCI CLB 寄存器。

BAR 回调仍属于可信驱动；没有 IOMMU 时，初始化地址校验不构成对恶意 bus master 的隔离。
Release 仅为既有回调类型兼容而保留，runtime 不调用它。没有 close、复位重试或回收 API。

## 提交与完成

每个队列只允许一个在途命令。CID 从 1 增长到 65534 后耗尽，不重复使用；
软件 epoch/generation 不是 CQE 的硬件字段，也不替代停稳和内存隔离。
`Queue.next_cid` 的存储值是最后签发的 CID；下一次提交使用该值加 1。

核心返回全字节确定的 SQE、PRP 和下一门铃值。runtime 复制数据、PRP 和 SQE，
执行 release 屏障，并在写 SQ 门铃前记录已经发布。无法确认写入是否发生时不回收命令。
轮询先读取 CQ phase，匹配后 acquire 并抓取完整 CQE，再复核 status 稳定。
核心验证 CID、SQID、SQHD、phase、状态和保留字段，成功后先写 CQ head 门铃并确认健康状态，
然后才复制读数据到调用者输出或返回成功。

NVMe CQE 没有 AHCI PRDBC。Completion.bytes 是已提交命令的软件预期长度，不能作为硬件传输计数。
FLUSH opcode 00、NSID 1、不带 PRP；成功完成只表示该命令完成，不等于 controller shutdown。
超时、时钟倒退、CFS、错误完成和不确定 MMIO 都留下 held lease，并阻止后续命令和资源复用。

## 独立原生验证

运行 `python -m unittest tests.test_nvme_core tests.test_nvme_runtime -v`。
六项测试均覆盖 debug/release；生成的 NASM 还分别实际汇编 ELF64 和 COFF。
测试输出分别进入 `build/test/nvme-core/run-*/` 与 `build/test/nvme-runtime/run-*/`，
源码 hash 在前后比较，坏实现只在独立 snapshot roots 中编译，正式模块不会被替换。

NN / NSFEAT 修正后的完整六项复验耗时 39.616 秒，记录为
`build/test/nvme-core/run-b4b6d4ee7251/validation-summary.json` 和
`build/test/nvme-runtime/run-ce6bd212e3b2/validation-summary.json`。
每个模式分别检查 6521681 条断言、338116 个全字节计划、75919 个完成，
以及 3530217 条 runtime 断言、31 个回调场景、184 条实际解析命令和 74 次队列环绕。
NN 边界包括 1、2、256、65535、80000000、fffffffe 的成功及 0 / ffffffff 的原子拒绝；
NSFEAT 包括全部 256 个值与 readonly 0/1 的组合，接受的能力不改变命令字节。
runtime 模型默认报告 NN256、NSFEAT34；错误 Controller 场景独立报告 NN0。
原逐字推广结果保留在 `run-df6f1b0a8fb2` / `run-629eb2e9a009` 中。

两种模式的 runtime 直接调用链上界为 2048 字节，含原生 probe 为 2176 字节，
没有可变全局区和 SIMD 指令。该上界没有包含实际块服务调用者、函数指针回调和 syscall bridge；
集成后必须加上这些路径，不能把组件数字当作完整服务栈证明。

核心 oracle 验证 SQE / PRP 全字节、1024 个首数据偏移、1–128 sector、Identify、
队列环绕、CID 耗尽、过期 ticket、错误状态和失败输出原子性。
runtime C 模型解释真实编译代码发布的 SQE 和 PA，独立检查 BME 前队列配置、CAP.TO、
CC/RDY 时序、门铃、CID/phase、PRP、错误读输出和持久化 FLUSH 模型。
实际执行的坏实现包括错误 NLB、忽略旧 phase、允许 NN0、允许 thin namespace、
提前 Enable、错误 CQ head、释放故障 lease 和固定 500 ms 就绪超时。
这些都是原生回调验证，不包含实际 PCIe/MMIO、内核授权或 guest 启动证据。

## 规范与 QEMU 源码核对

初始化顺序、CAP.TO、CC/CSTS、NN 和 DULBE 对照
[NVM Express 1.4c](https://nvmexpress.org/wp-content/uploads/NVM-Express-1_4c-2021.06.28-Ratified.pdf)
第 44、47–50、163、186、212、294–300 页。
当前字段还对照
[NVM Command Set 1.3](https://nvmexpress.org/wp-content/uploads/NVM-Express-NVM-Command-Set-Specification-Revision-1.3-Ratified-2026.07.31.pdf)
第 85、94 页 NSFEAT / OPTPERF，及
[Base 2.4](https://nvmexpress.org/wp-content/uploads/NVM-Express-Base-Specification-Revision-2.4-Ratified-2026.07.31.pdf)
和
[PCIe Transport 1.4](https://nvmexpress.org/wp-content/uploads/NVM-Express-NVMe-over-PCIe-Transport-Specification-Revision-1.4-Ratified-2026.07.31.pdf)
的 SQE、CQE、PRP 和门铃定义；使用这些定义不代表实现完整 2.x 控制器协议。

本机 QEMU 报告 `11.0.0 (v11.0.0-12122-ga4bb4b10c9)`。
按实际 commit 下载并保存的官方
[ctrl.c](https://github.com/qemu/qemu/blob/a4bb4b10c9/hw/nvme/ctrl.c)、
[ns.c](https://github.com/qemu/qemu/blob/a4bb4b10c9/hw/nvme/ns.c) 和两个头文件
hash 见 `build/test/nvme-qemu-source-review/sources.json`。
该实现 VS/VER 10400、NN256、SQES66、CQES44、VWC7；默认 namespace 的 NSFEAT34
是 DAE 和 OPTPERF 能力。NN / NSFEAT 的修正遵循字段语义，不篡改虚拟设备报告或加入不存在的版本选项。
controller 的 `drive` 隐式 NSID1 是 private；独立 `nvme-ns` 设备默认 shared=true，
不能把二者默认设置混为同一种布局。

## 内核与块服务接线

块服务优先选择现代VirtIO块设备，其次选择PCI class/subclass/interface为`01/08/02`、header0或80的首个NVMe控制器，最后回退AHCI。EFI的SATA盘不会抢占NVMe数据盘。三种后端保留各自State、Ops、Info和完成协议，文件系统的64B消息及共享通道不变。

内核grant先清I/O、Memory、BME并精确读回，再有界遍历PCI capabilities，以16bit控制字写入停用MSI/MSI-X并读回。仅探测和授予NVMe BAR0，启用Memory及INTx Disable，BME仍关闭。驱动停稳控制器、取得128KiB独占连续DMA、清队列、屏蔽中断并配置Admin基址后，通过受限syscall `66`请求启用；它没有用户地址或队列参数，只接受block角色的配置RW能力。

内核在读取INTMS前再次确认MSI/MSI-X停用；从实际BAR0读取CAP/VS/CC/CSTS/INTMS/AQA/ASQ/ACQ，与自己的租约、CPU地址位数和BAR范围构成128B可信快照。纯`nvme_authority.permit`通过后，才执行一次BME写入和读回；不确定写入也永久记为已尝试，保留所有DMA，不允许重试。完整授权边界和native负控见[nvme-authority.md](nvme-authority.md)。这不是IOMMU对恶意DMA的硬件隔离。

完整块服务的debug/release可达栈均为3143B/16KiB，包含实际入口、syscalls.asm桥及全部14个Ops/PCI间接调用；ELF64/COFF均实际汇编。证据 `build/test/nvme/integration-review/run-24eb1c394e6e/stack-audit.json`，独立接线审查未发现阻断问题。

## 实际读写、FLUSH及同盘重启

普通runtime7构建：`build/test/nvme/builds/build-43bb9b12df32/esp`，kernel为2,080,136B；源码及全部构建产物指纹保持不变。普通GPT启动镜像：`build/usb/dongos-43bb9b12df32.img`。实际客体是本机QEMU11/TCG、q35、4vCPU、2GiB；EFI保留SATA固件盘，NVMe连接新建64MiB数据镜像。未使用物理盘。

正式入口：

```powershell
python tests/run_nvme_qemu.py --selftest
python tests/run_nvme_qemu.py --reuse-esp build/test/nvme/builds/build-43bb9b12df32/esp
```

最终结果 `build/test/nvme/qemu/run-27bfff24d772/result.json`：两个实际启动均通过。首轮UART真实执行`write PROBE.TXT ...`、`cat`、`ls`、`sync`；确认停止后独立读取原始FAT。第二轮使用同一数据盘执行读回、列目录、同步，不预填probe、不通过QMP注入磁盘或电源操作。39B唯一载荷相同，两个FAT副本一致且clean；第二轮结束后的整盘SHA256与首轮同步后完全相同：`f8b316848b8ef6b26a2616171881482e2a833a1ee4839e0766cf14b16d87ffdd`。

两轮分别完成3181/3141次块操作。取证核对实际五个ELF的可执行字节与权限、10个栈guard、实际BACKEND/SELECTED_KIND3、BAR0 UC/RW/NX、全部32页DMA WB/RW/NX、BME前可信Header，以及真实I/O SQ中NSID1 FLUSH SQE和DMA CQE。最后CID分别3181/3141，SQHD/SQID/phase/status及保存的CQE均一致。NVMe CQE没有传输字节计数；软件预期bytes未被当作硬件PRDBC。

隔离检查遍历其他服务全部有效USER叶，按物理区间排除块DMA别名，也独立核对输入服务自己的4页DMA及其隔离。页表读取只允许各进程32页私有池和独立从内核View核验的64页共享池；逐级计算USER可访问性，覆盖1GiB/2MiB叶，不跳过高地址分支。内核View的真实字节、编译布局及UART池记录交叉匹配。该检查证明实际CPU用户映射隔离，不替代IOMMU。

之前两次失败保留为失败：`run-010bc41a00e5`把输入服务同VA不同PA的独立DMA误判为共享；`run-f0827109ccbe`的取证器只允许私有池，未覆盖继承的内核页表。两个客体都已执行写/读/sync，但当时未满足完整验收，未改记PASS。修复仅在取证脚本；生产镜像与驱动源码未改。最终28项纯自测覆盖物理别名、共享池、逐级USER、边界、环、PAT、View/UART变异和清理失败，证据 `build/test/nvme/runner-selftest/run-2313d4147e31/validation-summary.json`。两次旧失败均已确认停止，最终两个启动也已确认停止。

同一构建的后端回归均通过：AHCI严格模式两启动 `build/test/ahci/qemu/run-c92c22ca1997/result.json`；VirtIO S5/reset、FLUSH和原盘持久化四启动 `build/test/p8-power/qemu/run-23e2741fa546/result.json`。本批共有8次完整通过的实际启动，另有上述2次取证失败调查启动，不能把它们合并为10次全通过。

当前验收覆盖NSID1、512B扇区、轮询及普通文件工作负载。1–128 sector、跨页PRP等由独立机器码模型验证，本次实际文件流程没有单独发起128-sector RPC，因此不宣称完成最大传输的硬件专项。物理NVMe、VMware NVMe、热拔插、IRQ完成、多队列、队列退休/回收、2.x就绪模式和真实掉电事务仍需各自验证。通用设备管理、完整P5与P0–P9没有因本子项完成而全部关闭。

最终合并复核记录：`build/test/nvme/integration-review/final-43bb9b12df32/validation-summary.json`。独立重核1182份物理取证文件的长度/SHA、实际runner输入及构建指纹，重新读取原始FAT并保留两次调查失败状态；8次完整通过启动与2次调查启动分别计数。
