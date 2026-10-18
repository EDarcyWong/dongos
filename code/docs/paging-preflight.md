# 页表激活前准备

本文保留激活前阶段的历史记录。当前启动已接入新根与永久换栈，最新实现和验收见 [paging-activation.md](paging-activation.md)。

2026-10-17，本轮已完成真实 BootInfo 的 Runtime 地址视图、三组 IST 保护页布局、私有页表全树审计、控制寄存器快照和未来切换计划。正常客体依次输出 `DONGOS_P2_STACK_READY`、`DONGOS_P2_PREFLIGHT_READY`、`DONGOS_P2_MEMORY_READY` 和测试 PASS。**新 CR3 尚未加载；本轮通过的是激活前准备与原 P1 地址空间下的干跑。**

本页描述本轮状态。之前 [boot-memory.md](boot-memory.md) 记录的字段数、IST 状态和验证次数属于此前阶段；本轮寄存器是否已启用 NXE/WP，以下面的实际快照为准。

启动仍只运行 BSP、保持 IF/DF 清零、只初始化一次，失败明确报告并停机。`memory_startup` 收集真实 UEFI 图和链接资源，在低4GiB内选择可同时容纳64页表池与16页普通栈的4MiB arena；全部原有保留资源、旧栈、旧页表及固件分配 envelope 继续持有。21项资源的编号及归属规则保持原含义，不把合并的 UEFI envelope 当成独立对象的释放边界。正常报告满足 `944 + 64 + 16 = 1024`，没有释放旧栈。

Runtime 迁移保留 BootInfo v1 的160字节物理语义，原 PA 字段不变。入口用单独保存的物理基址收集资源，BootInfo 本身及 raw map、RSDP、GOP、表池的软件访问全部使用受限 HHDM 别名；`Space` 的虚拟表缓冲也使用 HHDM，物理池基址仍独立保存。Runtime View 位于内核高半区 data/BSS，大小160字节，首字段是偏移0、大小48字节的 Display。具体字段和纯数据校验见 [runtime-view.md](runtime-view.md)。

CPU 故障注入发生在完整内存准备之前，因此早期显示使用独立的 `earlyDisplay`；准备成功后，正常屏幕和 panic 使用 `RuntimeView.display`，不再通过 BootInfo 的物理帧缓冲字段写屏幕。panic先登记旧物理启动栈，再登记新栈干跑的HHDM范围。干跑结束后以`panic_init(Display,0,0)`停用普通栈回溯：旧RBP和当前P1尚未映射的未来STACK地址均不再被接受，三个IST范围仍有效。Runtime只保存未来STACK的计划边界，须在真正加载新CR3后才登记为可读范围。native测试实际验证退役旧范围、拒绝未映射未来范围、保留IST以及后续登记的完整边界；这不等于已经完成永久换栈。

普通新栈有16页，未来固定 VA 为 `[0xffff900000001000, 0xffff900000011000)`，两侧各留一页空洞；HHDM 别名供当前栈桥干跑及管理使用。栈桥实际切换 RSP、执行嵌套 SysV callback、核对对齐和返回值，随后恢复原栈。不能依靠这个会返回旧 RSP/RBP 的桥直接执行永久激活。

三组 IST 分别保留16KiB可用区，并各自显式预留低、高两个独立4KiB guard，共六页。链接 BSS 映射逐页跳过这些真实占位页，而非仅检查栈边界地址；TSS 的 IST top 与 panic trusted ranges 只包含可用栈。完整窗口互不重叠，guard 不覆盖 GDT/TSS/IDT/workspace，仍由整个 BSS/内核 envelope 持有。布局、符号和纯模型验证见 [ist-guards.md](ist-guards.md)。当前 P1 活动映射仍覆盖这些页，因此本轮没有验证硬件 guard fault。

私有新树保持内核 text RX、rodata R/NX、其余实际 data/BSS RW/NX；没有 identity 映射或可写内核 text 别名。GOP 为 HHDM UC/RW/NX，RSDP 为 HHDM R/NX，其余所需管理对象为受限 WB/RW/NX。PAT 槽0要求WB、槽3要求UC；本轮不改 PAT。映射策略和缓存位编码见 [paging.md](paging.md)。

最终审计从物理根经 HHDM 读取原始页项，不依赖 `Space` 的私有 metadata 来决定树结构。它遍历全部512项的每一层，逐叶对照独立 VA/PA/权限/缓存 allowlist；以64槽 `seen` 表拒绝环和跨分支共享子表，并把实际访问的表数、叶数与构建结果核对。这样可以拒绝多余 identity/别名映射及 guard 被重新映射，而不只是验证已知成功路径。`mapped-guard` 用例真的向新树注入 guard 叶，最终 raw 审计捕获它并返回 `0x02060005`。

本轮控制快照位于原有 SSE2 ABI 探针配置之后；此前对 EM/TS/MP、OSFXSR/OSXMMEXCPT 的设置继续保留。预检阶段只读取 CR0/CR3/CR4、EFER、RFLAGS、PAT，再生成纯数据计划：CR0/CR3/CR4/EFER/PAT 前后必须完整相等；RFLAGS 的 IF/DF/VM 必须不变且为0，普通算术标志允许变化。策略要求 PE/PG/PAE/LME/LMA 已满足，CD/NW/PGE/LA57/PCIDE/CET 为0，拒绝超出当前四级、非PCID换栈策略的状态。控制位、TLB 和缓存迁移的硬件依据见 [Intel SDM Volume 3A，第4章及第12章](https://cdrdv2-public.intel.com/825758/253668-sdm-vol-3a.pdf)。

本次正常客体的完整原始结果见 [normal/result.json](../build/test/memory-preflight/normal/result.json)：

| 项目 | 实际值 |
| --- | --- |
| 物理地址宽度 / NX 支持 | 40位 / 1 |
| arena / 可用 / 空闲页 | 1024 / 1024 / 944 |
| 表池 / 普通新栈页 | 64 / 16 |
| 新池及根 PA / 新栈 PA | `0x00400000` / `0x00440000` |
| 实际已用表 / 映射页 | 17 / 1160（`0x488`） |
| 资源数 / IST guard 页 | 21 / 6 |
| PAT | `0x0007040600070406` |
| CR0 前后 | `0x80010033` / `0x80010033` |
| CR4 前后 | `0x668` / `0x668` |
| EFER 前后 | `0xd00` / `0xd00` |
| planned_cr0 / planned_efer / planned_actions | `0x80010033` / `0xd00` / `4` |

**本次固件继承状态中的 CR0.WP、EFER.NXE 已经为1，本阶段没有写入它们。** `planned_actions=4` 表示仍需在未来执行缓存写回/失效与缓存策略迁移，不能理解为已加载新根，也不能声称此前这些位一直为0。计划规则为 `planned_cr0 = before.cr0 | 0x10000`、`planned_efer = before.efer | 0x800`；actions 的掩码1、2分别表示尚需设置NXE、WP，掩码4始终保留缓存迁移要求。即使NXE/WP已开，旧 P1 映射仍不是新树的页级权限和保护页布局。

串口在 STACK_READY 之前完整输出38个固定顺序字段，全部为 `memory_<key>=0x` 加16位小写十六进制；字段分组如下，随后才是21个完整 `kind/base/length` 三元组：

```text
physical_bits,nx,resource_count,arena_base,arena_pages,usable_pages,free_pages,
pool_physical,pool_pages,root_physical,table_count,mapped_pages,pat_value,
stack_physical,stack_pages,stack_bottom,stack_top,bridge_value,
runtime_view,runtime_boot_info,runtime_raw_map,runtime_rsdp,runtime_framebuffer,
runtime_pool,ist_guard_pages,cr3_before,cr3_after,
cr0_before,cr0_after,cr4_before,cr4_after,efer_before,efer_after,rflags_before,rflags_after,
planned_cr0,planned_efer,planned_actions
```

宿主 gate 要求字段/标记完整有序且仅出现一次，拒绝未知项、截断、PANIC、错误退出码和旧成功日志。它独立读取 ELF 段与六个 guard 符号，并读取编译器布局清单核对 workspace/View 大小，验证 Runtime VA 的归属和别名关系、完整 guard 窗口互斥、控制快照及计划。最低映射页数按已知 VA 并集计算并扣除六个 BSS guard；BootInfo/raw 仅按实际已知地址及最小可证明跨度计入，不猜合并 envelope 的全部映射数。客体全树 raw 审计承担完整映射集合校验。

本轮8项内存客体全部通过，CPU能力负例复用 normal ESP，其余注入分别构建；每项独立保存NVRAM、串口和结果，构建与 QEMU 全部串行：

| case | 必须观察到的结果 |
| --- | --- |
| normal | 完整预检报告，退出33，CR3不变 |
| bad-layout | `memory_error=0x02050005`，退出35 |
| no-nx | `memory_error=0x02060002`，退出35 |
| bad-pat | `memory_error=0x02060007`，退出35 |
| no-pat | CPUID拒绝后不读PAT，`memory_error=0x02060007`，退出35 |
| bad-ist-layout | 无效IST布局，`memory_error=0x02060005`，退出35 |
| mapped-guard | 实际污染新树后被审计拒绝，`memory_error=0x02060005`，退出35 |
| bad-controls | 仅污染快照、不改真实CR4，`memory_error=0x02080001`，退出35 |

完整回归还包含8项CPU异常（int3、ud2、gp、pf、bad-stack、double-fault、divide、bad-frame），均按fatal诊断退出37；3项镜像篡改/截短/缺失拒绝均退出35。合计19个正式客体用例，加上一次正常smoke和普通栈退役修正后的正常复跑，本轮实际执行21次QEMU，全部串行。八项异常运行在原P1根下，不能充当新根权限或IST guard故障验证。

宿主共444项通过、零skip：123项系统测试用时44.094秒，321项语言/标准库测试用时33.393秒。普通栈退役逻辑修正后，另重跑对应native测试并复跑正常客体，正式版也重新构建通过。系统发现132项，明确排除需独立QEMU执行的 `test_std_arch_qemu_negative` 9项，未计为这444项的通过结果。正式版构建通过，仅构建，没有把测试版退出当成正式版实际启动；正式ELF不含 `memory_test_map_guard` 测试注入helper。运行时间是宿主测试进程耗时，不是内核启动性能。

本轮证据集中在 `build/test/memory-preflight/`，保留此前 `memory-runtime-prep/` 与 `memory-startup/` 证据：

- [result.json](../build/test/memory-preflight/result.json)：8项内存客体聚合结果；各case子目录保留独立结果、ELF、串口和QEMU日志。
- [system-host-regression.json](../build/test/memory-preflight/system-host-regression.json) 与 [system-host-regression.log](../build/test/memory-preflight/system-host-regression.log)：123项系统宿主结果和排除清单。
- [lang-regression.log](../build/test/memory-preflight/lang-regression.log)：321项语言/标准库宿主结果。
- [cpu-loader-regression.json](../build/test/memory-preflight/cpu-loader-regression.json) 与 [cpu-loader-regression.log](../build/test/memory-preflight/cpu-loader-regression.log)：8项CPU异常和3项镜像拒绝结果。
- [production-build.log](../build/test/memory-preflight/production-build.log)：最终正式版构建日志。
- [panic-binding-final.log](../build/test/memory-preflight/panic-binding-final.log)、[panic-retirement-qemu.log](../build/test/memory-preflight/panic-retirement-qemu.log)：退役旧范围且尚不信任未映射未来范围的最终复验。

未来真正激活必须另设可验证的切换边界，不能把 PREFLIGHT_READY 当成已完成这些动作：

1. 进入不返回的高半区 handoff，保证执行代码、Runtime、显示、CPU表与IST在切换窗口内可达；提前在寄存器中准备新root PA、固定guard栈顶、入口与Runtime参数，但此时不能把RSP切到旧树未映射的固定STACK，也不能把它登记为可读回溯范围。任何路径都不能返回旧RSP/RBP或loader返回槽。现有可返回栈桥保留为干跑接口。
2. 再核对实际控制状态与新树，必要时按计划设置NXE/WP并读回，保留其他位；维持本策略的PGE/PCIDE前提并明确旧TLB/分页缓存失效过程。完成缓存writeback/invalidation与单一缓存别名策略，不能把改PTE或单独MOV CR3视为缓存数据已写回。后续复核确认P1已为GOP的2MiB PDE设置PCD/PWT，在PAT3=UC的既定前提下GOP此前已经是UC，不能称作WB→UC；具体更正见当前激活记录。
3. 在两棵树均可达的高半区代码中加载新CR3，紧接着更新RSP、清除旧RBP链，二者之间不执行依赖旧栈的CALL/PUSH/POP或栈内存访问；异常/NMI仍走两树共同保留的IST及当前停用的普通回溯边界。确认新根和固定栈可达后才登记该栈范围，在其上执行嵌套调用和Runtime/GOP访问，证明不依赖identity映射及旧栈。旧资源继续保留，资源释放不由这次准备结果授权。
4. 在新根下独立触发并核对零页访问、只读页写入、NX页取指和IST guard故障，验证异常上下文、panic显示及可信回溯边界。只有这些实际客体门禁通过，才能声明新树权限和保护页在硬件上生效。

这些后续动作尚未实现或执行；本页不改变当前启动流程、寄存器或资源所有权。
