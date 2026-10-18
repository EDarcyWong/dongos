# 真实 BootInfo 内存准备

2026-10-17，本轮完成真实 BootInfo 的运行时地址视图、六个 IST 保护页空洞、独立新树整树审计和只读控制计划。成功标记依次为 `DONGOS_P2_STACK_READY`、`DONGOS_P2_PREFLIGHT_READY`、`DONGOS_P2_MEMORY_READY`。它们表示新栈干跑与激活前检查通过；新 CR3 尚未加载，也未执行缓存 writeback 或不返回的运行时交接。

激活策略与控制位见 [页表激活前检查](paging-preflight.md)，PA/VA 分离及显示对象见 [Runtime 地址视图](runtime-view.md)，三组异常栈见 [IST 保护页](ist-guards.md)。本页集中说明真实启动集成和各轮证据。

## 实际调用链

`kernel/memory_probe.dg` 导入原有语言探针和 `boot.memory_startup`。构建使用 `lang/examples`、`kernel`、`lang/std` 三个显式源码根；语言示例自身保持独立。内核在语言探针之后调用新入口，BSP、IF=0，只执行一次；失败输出完整 `memory_error` 和内核失败行，随后停机，不重试部分初始化状态。

1. 入口完成初始物理 BootInfo 交接校验后，将 BootInfo 指针改为 HHDM 别名，单独保存其 PA 数值；v1 内部的 PA 字段保持原值。显示和 panic 接收独立的 Runtime Display，不再把 framebuffer PA 当作指针使用。早期 panic 仍保留当前低地址启动栈的可信范围。
2. 语言探针及原有 SSE2 设置完成后，先检查 CPUID.PAT，再只读 IA32_PAT；槽 0 必须为 WB（字节 6），槽 3 必须为 UC（字节 0），缺少 PAT 或槽值不符明确拒绝。读取 CR0/CR3/CR4/EFER/RFLAGS/PAT 快照，`boot.preflight` 校验四级、非 PCID、无 global/CET 等前提，只生成未来控制值和动作掩码。
3. `cpu.capabilities.detect` 要求物理宽度为 32～52，NX 来自 0x80000001 的 EDX bit 20，不支持时拒绝。`boot.memory_resources.collect` 结合真实 BootInfo、完整 UEFI 图、链接段、CPU 表、三组 IST 与实际 workspace 建立清单；collector 失败保持整个输出不变。raw map 和 RSDP 的读取均使用 HHDM 地址。
4. 在低 4 GiB Conventional、非 runtime 区间中选择自然对齐的 4 MiB arena。`boot.arena_fit` 要求至少一个完整 64 页对齐块和共五个完整 16 页对齐块，保证页表池与新栈同时可分配。分配 order-6 的 64 页池和 order-4 的 16 页栈，追加为 kind 19、20，并核对 `free_pages + 64 + 16 == usable_pages`。新栈 PA 按 64 KiB 对齐，与页池和原 19 项资源不交叠。
5. 私有新树使用 `HHDM + pool` 作为 `WORK.space` 的表池指针。映射时逐页 query/raw walk 核 PA、权限和缓存位；随后独立遍历全部实际表与叶项，以 64 页 seen 集合拒绝环和共享子表，用严格 VA/PA/权限白名单拒绝多余 identity、内核别名或 guard 映射，并比对叶项和表数量。
6. 构造不可变 Runtime View，先把 panic 绑定到实际干跑使用的新栈 HHDM 别名，再切 RSP 执行嵌套 callback，记录 `bridge_value=0x535441434b`。返回旧栈后把panic普通栈范围清为0/0，避免跟随旧物理RBP或尚未被P1映射的未来STACK地址；IST仍可回溯，未来实际加载新CR3后才登记固定STACK；独立确认绑定、全部控制快照及旧 CR3 未变，最后输出完整报告与成功标记。

BootInfo 仍为 v1 的 160 字节，资源 Layout 保持 184 字节；新增 Runtime View 为 160 字节、Display 为 48 字节。Display 是 View 的首字段，偏移为 0。NASM 的这些类型、Report、Resource 和控制 State/Plan 偏移均由 Dong 布局清单生成。

## 完整保留与实际对象

v1 没有保存原始 `AllocatePages` 的基址/长度，例如内核在 4 MiB 分配中选择一个对齐的 2 MiB 窗口。因此本阶段保守保留资源所属的**整个 UEFI 描述符 envelope**，不猜测未交接的分配边界。固件可能合并相邻的 LoaderData，多个资源的 envelope 相同是合法情况；这些保留不能作为未来逐对象释放边界。

| kind | 资源 |
| --- | --- |
| 0 | 物理零页 |
| 1 | 包含完整 2 MiB 内核窗口的 LoaderCode envelope |
| 2～5 | BootInfo、原始图、64 KiB 启动栈、原 CR3 根所属 LoaderData envelope |
| 6～7 | GOP 帧缓冲完整容量、实际长度的 ACPI 2 RSDP |
| 8～11 | 真实链接段 text、rodata、data、BSS |
| 12～17 | GDT、TSS、IDT、DF/NMI/普通异常 IST |
| 18 | 实际 workspace：分配器/页元数据、scratch、规范化输出、清单、Space、分页 metadata，以及保存的 Layout、Runtime View 和审计状态 |
| 19 | buddy 实际取得的整个 64 页新页表池 |
| 20 | buddy 实际取得的整个 16 页新栈，64 KiB 对齐 |

BootInfo、raw map、启动栈、旧根的实际对象范围必须互不重叠，所属 envelope 则允许重合。全部物理资源要求低 4 GiB、非空、端点无溢出；kernel PA 要求 2 MiB 对齐。raw map 的步长、版本、全部描述符端点/重叠和实际存储长度都先验证。布局的四个段须连续且页对齐，所有子资源均须位于实际内核镜像内。

## 离线映射策略与边界

- 内核仅在原高半区地址映射：text RX、rodata R/NX、data/BSS RW/NX，但完整 BSS 中跳过三组 IST 的六个 guard 页。各 IST 仍有完整 16 KiB 可用区；guard 的物理页继续由整个 BSS/内核分配保留，不发布给 buddy。
- 新分配的 64 KiB 栈映射到 `[0xffff900000001000, 0xffff900000011000)`，也映射其 HHDM 别名，两者均 WB/RW/NX。STACK 地址两侧各留未映射页。
- BootInfo、raw map、旧根一页及整个新池有受限 HHDM WB/RW/NX 映射。实际 BootInfo、raw/RSDP 和页表池读取均走 HHDM；collector 中 PA 仍只是数值。禁止任何 HHDM 页包络与整个内核镜像交叠，避免重新映射 IST guard 或建立可写 text 别名。
- RSDP 的实际跨度按页包络映射 HHDM R/NX；GOP 完整容量按页包络映射 HHDM UC/RW/NX。UC 使用 PAT=0、PCD=PWT=1 选择槽 3，WB 使用槽 0；没有写 PAT 或引入 PAT bit 7/WC。GOP 包络与其他保留区相交时拒绝，避免同一页建立 WB/UC 别名。
- VA 0、内核末尾、新栈两侧及六个 IST guard 共十个空洞必须返回精确 NotMapped；其他查询错误不能充当空洞。整树审计同时拒绝任何未授权叶项，不仅抽查已知地址。

本片只生成激活计划，**尚未加载新 CR3，也未执行最终不返回交接或缓存 writeback**。运行时对象已改用 HHDM，当前实际 RSP 仍在干跑返回后的旧启动栈；后续须在明确的控制/缓存顺序下完成最终栈与 CR3 交接，并做真实权限故障验证。当前十个空洞和 W^X 是新树的离线属性，干跑不验证新树下的 guard fault。

本次正常 QEMU 实际继承 `CR0=0x80010033`、`CR4=0x668`、`EFER=0xd00`，其中 **WP/NXE 已为 1**。本阶段保持这些继承位；P1 原临时叶项仍为 RWX，因此继承控制位也不代表新树保护已生效。入口原有 SSE2 的 CR0/CR4 设置发生在 before 快照之前。控制计划拒绝 PGE、LA57、PCIDE、CET 和 IF/DF/VM 等不支持状态；actions 的 NXE/WP 位只表示未来是否需设置，缓存 writeback/invalidation 位也只表示待办。详见 [激活前检查策略](paging-preflight.md)。

能力模块返回 CPUID 枚举的原始物理宽度，没有处理配置型内存加密/密钥位等 MSR 限制。已有运行证据来自 QEMU TCG；未做真机验证。

## 独立验证与复现

```text
python -m unittest tests.test_cpu_capabilities tests.test_boot_resources tests.test_memory_qemu_result tests.test_runtime_view tests.test_ist_layout tests.test_preflight tests.test_panic_binding -v
python tests/run_memory_qemu.py --all
python tests/run_cpu_qemu.py --all
```

宿主门禁独立验证报告、资源和 runner 生命周期，QEMU 构建及进程由 mock 替代；原生探针验证 runtime/IST/preflight/panic 绑定等实际实现。CPU/资源模块另有 debug/release、ELF64/COFF、独立 C/mocked CPUID、完整失败快照/哨兵/额外容量及合并 descriptor envelope 测试。执行客体构建和 QEMU 时全部串行，避免共用构建产物。

`run_memory_qemu.py` 的门禁要求以下 **38 个 u64 字段**完整且严格有序，每行使用 `memory_<name>=0x` 加 16 位小写十六进制：

```text
physical_bits, nx, resource_count, arena_base, arena_pages,
usable_pages, free_pages, pool_physical, pool_pages, root_physical,
table_count, mapped_pages,
pat_value, stack_physical, stack_pages, stack_bottom, stack_top, bridge_value,
runtime_view, runtime_boot_info, runtime_raw_map, runtime_rsdp,
runtime_framebuffer, runtime_pool, ist_guard_pages,
cr3_before, cr3_after,
cr0_before, cr0_after, cr4_before, cr4_after, efer_before, efer_after,
rflags_before, rflags_after, planned_cr0, planned_efer, planned_actions
```

随后输出 21 个完整资源三元组，之后才可出现 STACK_READY、PREFLIGHT_READY、MEMORY_READY、PASS。门禁结合独立 ELF 符号核对链接段、CPU 子资源及六个 guard，以编译器清单核对 workspace 与 Runtime View 大小及包含关系；验证 PAT、资源隔离、页数、runtime 地址、控制值及计划掩码。映射页数下界按独立已知 VA 区间并集计算，完整 BSS 扣除六个 guard；合并 envelope 不暴露 BootInfo/raw 实际对象地址，宿主不猜测它们的页数，也不代替客体整树审计。

构建失败、超时、PANIC、缺失/多余字段不能通过。本轮 STATE 为 `build/test/memory-preflight/`，保留 `memory-startup/` 和 `memory-runtime-prep/` 原证据。每个用例有独立 NVRAM/日志和所需构建目录，no-nx/no-pat 复用 normal ESP。`--all` 串行运行以下八项，本轮均已实际通过：

| 用例 | 必须满足的结果 |
| --- | --- |
| 真实 BootInfo 正常启动 | 退出 33，21 项资源与 ELF 一致，新栈桥成功，CR3 未变 |
| test-only 错误链接布局 | 返回 0x02050005，内核明确拒绝，退出 35 |
| QEMU 关闭 NX | 实际能力检查返回 0x02060002，内核明确拒绝，退出 35 |
| test-only 错误 PAT 值 | 返回 0x02060007，内核明确拒绝，退出 35 |
| QEMU 关闭 PAT | RDMSR 之前的能力检查返回 0x02060007，退出 35 |
| test-only 错误 IST 布局 | 返回 0x02060005，退出 35 |
| test-only 在新树映射 guard | 整树审计返回 0x02060005，退出 35 |
| test-only 不支持的控制快照 | 只读策略返回 0x02080001，退出 35 |

## 本轮验证结果

本轮 **444 项宿主测试通过、零 skip**，其中系统 123 项、语言 321 项。客体门禁单独串行执行：8 个内存准备、8 个 CPU 异常、3 个镜像拒绝，合计 **19 个正式用例**符合预期；另有一次正常smoke和普通回溯范围退役修正后的正常复跑，共21次主线QEMU执行。对应native测试在修正后重跑通过，最终日志为`panic-binding-final.log`和`panic-retirement-qemu.log`。正式版构建通过，证据仅为构建，未宣称正式版启动通过。

正常客体为 1024 页 arena、64 页池、16 页新栈、剩余 944 页、17 张已用表、1160 页映射、21 项资源。新栈 callback 返回 `0x535441434b`，六个 IST guard 在新树中缺席，原 CR3 和控制配置前后不变。上文列出的控制值表明 WP/NXE 是继承的既有状态；本轮没有写入这些位。地址随固件分配变化，门禁核对关系而非固化某次物理基址。本轮证据位于 `build/test/memory-preflight/`，完整策略与边界见 [paging-preflight.md](paging-preflight.md)。

DeepSeek 验收单独记录在[激活前准备期间补交复验](../deepseek-works/reviews/2026-10-17-activation-prep-check.md)：该轮 22 项宿主通过、QEMU 执行为 0，四项仍返修；引用的 07:57 十二客体通过以未变文件 hash 为依据，属于历史证据，不混入上述 19 个正式用例。本次主线集成不替代其任务书的永久测试要求。

## 历史证据：memory-startup

最初的真实 BootInfo 基线完成 3 个内存用例、8 个 CPU 异常、篡改/截短/缺失镜像 3 个拒绝，共 14 个正式 QEMU 用例，另有一次正常 smoke。该轮测试版与正式版均构建通过，正式版仅构建。

该轮宿主为系统 99 项、语言 321 项，共 420 项通过、无 skip；系统回归排除另行串行审查的 D7 客体模块 8 项。正常 QEMU 为 40 位/NX 支持、1024 页 arena、64 页池、剩余 960 页、13 张表、136 页映射，当时尚未分配新栈。

证据保留在 `build/test/memory-startup/`：`system-host-regression.json`、`lang-regression.log`、`result.json`、`loader-regression.json`、`production-build.log`；CPU 结果在当时的 `build/test/cpu/<case>/result.json`。这些数字仅为该轮历史，不充当本轮执行。

## 历史证据：memory-runtime-prep

上一轮新栈/PAT 扩展通过 429 项不同宿主测试、零 skip：系统 106 项（35.203 秒）、语言 321 项（32.243 秒）、随后新增 arena 纯模型 2 项（1.670 秒）。arena 模型在 debug/release 各枚举 6010 组图；栈桥有真实 O0/O2 换栈/嵌套/非易失寄存器/DF 回归，UC 叶项覆盖两模式和 ELF64/COFF。系统回归排除单独实跑的 D7 九项客体测试。

该轮主线 16 个正式客体通过：5 个内存、8 个 CPU 异常、3 个镜像拒绝。arena 修复后另正常复跑一次，共 17 次主线 QEMU 执行；正式版仅构建通过。正常结果为 1024 页 arena、64 页池、16 页栈、剩余 944 页、17 张表、1154 页映射、21 项资源，PAT 为 `0x0007040600070406`，callback 为 `0x535441434b`、旧 CR3 未变。该轮没有主动加载新 CR3 或设置 NXE/WP，不能据此推断继承控制位为 0。

证据完整保留在 `build/test/memory-runtime-prep/`：`validation-summary.json`、`system-host-regression.json/.log`、`lang-regression.log`、`arena-fit-tests.log`、`result.json`、`qemu-suite.log`、`post-arena-fit-qemu.log`、`cpu-loader-regression.json/.log`、`production-build.log`。CPU 构建在 cpu 子目录，日志在 cpu-sandbox/build/test/cpu 子目录。这些结果与本轮 `memory-preflight`、DeepSeek 各轮检查分别计数。
