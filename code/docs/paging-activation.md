# 私有页表激活与永久换栈

本文保留首次激活阶段的实现和验收记录。当前启动在ACTIVATION_READY之后还执行[活动页表修改与TLB门禁](active-paging.md)，通过MUTATION_READY后才进入正常MEMORY_READY/PASS。

2026-10-17，内核已在完成准备和干跑后，实际加载 P2 私有 CR3，并以不返回的 handoff 永久切到固定虚拟栈。`DONGOS_P2_PREFLIGHT_READY` 仍只表示切换前检查通过；新增 `DONGOS_P2_ACTIVATION_READY` 才表示新根、普通栈、Runtime 访问、显示访问和活动树审计全部通过。正常路径随后绘屏并输出 MEMORY_READY 与 PASS。本文记录当前实现；[paging-preflight.md](paging-preflight.md) 的“尚未激活”结论属于此前阶段。

本阶段仍只运行 BSP，正常启动维持 IF/DF/VM 为 0，保留四级分页，要求 CR4.PGE/PCIDE/LA57/CET 为 0。全部原有保留资源、旧物理栈、旧页表与固件分配 envelope 继续持有；没有释放、重新分配或回收旧启动资源。普通新栈继续为 16 页，固定范围是 `[0xffff900000001000, 0xffff900000011000)`，两侧各有一页不在场 guard；它的受限 HHDM 管理别名也继续存在。资源编号、归属与页面计数规则沿用 [boot-memory.md](boot-memory.md)、[runtime-view.md](runtime-view.md) 和 [ist-guards.md](ist-guards.md)。

实现入口见 [kernel/entry.asm](../kernel/entry.asm)、[kernel/memory_runtime.asm](../kernel/memory_runtime.asm)、[kernel/boot/activation.dg](../kernel/boot/activation.dg) 与 [kernel/boot/memory_startup.dg](../kernel/boot/memory_startup.dg)。准备阶段先核验 CPU 能力、PAT 与控制寄存器，构造私有树、执行原有可返回栈桥，随后停用普通栈回溯范围。旧栈上的帧不能继续成为可信回溯来源，尚未映射的固定栈也不能提前登记。提交前再次执行完整离线树审计并读取实际控制状态，确认它与初始快照的 CR0/CR3/CR4/EFER/PAT 完整一致，IF/DF/VM 仍为 0。原始 UEFI map 的首个字在此时保存，供切换后实际读取 Runtime 别名核对。

`memory_activate` 是专用的不返回汇编边界。输入寄存器依次为 RDI=新根 PA、RSI=固定栈顶、RDX=高半区 continuation、RCX=RuntimeView 指针、R8=planned CR0、R9=planned EFER。它先把这些值保存到不会被 WRMSR 的 EAX/EDX/ECX 操作破坏的寄存器，再完成以下顺序：

1. 写入保留其余位的 `planned_efer = before.efer | 0x800`，确保新树 NX 叶项生效；写入 `planned_cr0 = before.cr0 | 0x10000`，启用 supervisor write protection。
2. 在保留其余 CR0 位且 NW=0 的前提下设置 CD=1，进入 no-fill 阶段，执行第一次 `WBINVD`。
3. 执行相邻的 `MOV CR3,new_root` 与 `MOV RSP,fixed_top`，随后清零 RBP。两条 MOV 之间没有 CALL/PUSH/POP，也没有任何旧栈内存操作。
4. 执行第二次 `WBINVD`，恢复 planned CR0，使 CD/NW 均为 0，保留 WP；通过 JMP 进入高半区 continuation。路径不会恢复旧 RSP/RBP，也不会访问 loader 的返回槽。

固定栈顶按 16 字节对齐。continuation 用零返回槽和零 RBP 建立终止帧，之后所有普通 SysV CALL 的调用点 RSP%16=0、被调函数入口 RSP%16=8。它此时才把固定栈登记为 panic 可读范围，核对绑定，读取活动控制寄存器，实际执行固定栈上的嵌套调用，并检查 BootInfo、raw map 与 RSDP 的 Runtime 地址。GOP 探针保存一个像素、写入 `0x0055aa33`、读回并恢复原值；只有这些实际访问成功后才登记对应 token。最后进行活动树全树审计和纯数据 readback 校验，再输出激活报告。

两树共同映射高半区内核代码、Runtime、GDT/TSS/IDT、panic 数据和三个 IST 可用栈。#DF 使用 IST1、NMI 使用 IST2，其余向量使用 IST3。IF=0 不屏蔽 NMI；CR3 已更新而 RSP 尚未更新的短窗口仍可通过这些共同保留的 IST 进入 fatal 诊断。此窗口的普通回溯范围为空，panic 不会尝试解引用旧栈或未来普通栈。新树继续只映射 IST 可用页，并跳过六个独立 guard 页。

缓存处理依据 [Intel SDM Volume 3A，253668-093US，September 2026](https://cdrdv2-public.intel.com/929359/253668-093-sdm-vol-3a.pdf) §5.10.4.1、§14.5.3、§14.12.4：在 PCIDE/PGE 均为 0 时，MOV CR3 清除旧的普通 TLB 与分页结构缓存；它不替代数据缓存写回。CD=1/NW=0 后的 WBINVD 用来写回并失效已有缓存，第二次 WBINVD 在切换后、恢复正常缓存模式前执行。CD 只是 no-fill 控制，不能据此宣称全物理内存已经成为 UC。PAT 和 MTRR 完全不修改，页级缓存类型及别名限制继续见 [paging.md](paging.md)。

必须纠正此前“P1 framebuffer 为 WB、P2 改为 UC”的笼统表述：[boot/efi_main.asm](../boot/efi_main.asm) 已给覆盖 framebuffer 的全部 2 MiB PDE 设置 PCD/PWT，identity 与 HHDM 使用同一组 PDE；在本阶段已经验证 PAT 槽 3 为 UC 的前提下，P1 GOP 已经是 UC。P2 使用 4 KiB UC/RW/NX framebuffer 叶项，移除 identity 别名。两次 WBINVD 是此次提交实际执行的保守缓存维护，不能作为此前 GOP 确为 WB 的证据，也不声称完成了 PAT/MTRR 重编程。P2 不允许同一物理页同时具有冲突缓存类型；GOP 的完整页 envelope 与其他保留对象相交时在构建阶段拒绝。

离线与活动审计共用从原始根出发的独立 allowlist，遍历每层全部 512 项，拒绝环、共享子表、额外 identity/可写 text 别名、被重新映射的 guard、异常权限与缓存编码，并核对叶数和已用表数。离线树从未被硬件使用，因此要求原始项严格匹配，连 A/D 也不能被预先加入；活动树只允许处理器增加非叶 A 位、叶 A/D 位，其余地址、权限、缓存位及全部允许映射集合仍须完全匹配。该区别避免把硬件正常置位误判为页表污染。

串口保留原来的 38 个 `memory_<key>=0x` 加 16 位小写十六进制字段，以及随后 21 组完整的 `kind/base/length`。这些全部发生在提交之前，所以其中的 `cr3_before == cr3_after`、CR0/CR4/EFER 不变与 PREFLIGHT_READY 都只描述准备阶段：

```text
physical_bits,nx,resource_count,arena_base,arena_pages,usable_pages,free_pages,
pool_physical,pool_pages,root_physical,table_count,mapped_pages,pat_value,
stack_physical,stack_pages,stack_bottom,stack_top,bridge_value,
runtime_view,runtime_boot_info,runtime_raw_map,runtime_rsdp,runtime_framebuffer,
runtime_pool,ist_guard_pages,cr3_before,cr3_after,
cr0_before,cr0_after,cr4_before,cr4_after,efer_before,efer_after,rflags_before,rflags_after,
planned_cr0,planned_efer,planned_actions
```

PREFLIGHT_READY 后至 ACTIVATION_READY 前，连续输出新增的 14 个 `activation_<key>=0x` 加 16 位小写十六进制字段；Report 大小 112 字节、对齐 8，字段偏移依次为 0～104：

```text
cr3,cr0,cr4,efer,pat,rflags,entry_rsp,entry_rbp,rsp,rbp,
nested_value,display_value,runtime_value,cache_steps
```

`activation_cr3` 必须等于新根且不同于旧根；CR0/EFER 必须等于保留其余位的计划，CR4/PAT 不变。entry_rsp 必须等于固定栈顶，entry_rbp 必须为 0；嵌套调用的 rsp/rbp 必须完整位于固定栈内并满足 ABI 对齐。成功 token 分别为 `nested_value=0x414354495645`、`display_value=0x0055aa33`、`runtime_value=0x52554e54494d45`。`cache_steps=31` 表示本次路径已执行 EFER 写入、WP 写入、首次 no-fill/WBINVD、新根换栈和第二次 WBINVD/CR0 恢复五个步骤；它与只表示“尚需动作”的 `planned_actions` 含义不同。宿主 gate 独立检查字段布局、固定顺序、唯一性、阶段相邻性及完整标记序列，拒绝旧日志、截断、未知项和错误退出码。

新树下的五个测试在 ACTIVATION_READY 后输出 ACTIVATION_INJECT，再触发真实 #PF。每项均要求 vector=14、CS=8、SS=0x10、CR2/RIP 与 ELF 中的独立目标符号一致，测试版 fatal 退出码为 37；不能出现正常 MEMORY_READY/PASS：

| case | 实际操作 | #PF error | CR2 / 关键上下文 |
| --- | --- | --- | --- |
| null-page | 读取地址 0 | `0x00` | CR2=0，普通固定栈帧保持可读 |
| ro-write | 向 rodata 目标写一字节 | `0x03` | CR2=rodata 目标；证明 CR0.WP 下 supervisor 写被拒绝 |
| nx-fetch | JMP 到 data 中的 `RET` 字节 | `0x11` | CR2=RIP=data 目标；证明 NX 取指保护 |
| stack-guard | 把 RSP 放到普通栈下界并执行 PUSH | `0x02` | CR2=`0xffff900000000ff8`，保存的故障 RSP=`0xffff900000001000` |
| ist-guard | 读取 EXCEPTION IST 的低 guard | `0x00` | CR2=`cpu_exception_guard_low`；故障处理使用相邻可用 IST |

五项的完整 184 字节 ExceptionContext 都必须落在 EXCEPTION IST 可用范围内，归一化 context%16=8。注入器先给通用寄存器设置已知值并置 DF=1；gate 核对保存的全部 GPR、RFLAGS.IF/VM=0 与 DF=1，而实际异常入口清 DF 后调用 panic。普通故障的保存 RSP=RBP；普通栈 guard 测试例外地保留上述边界 RSP，RBP 链仍在栈顶附近。回溯至少包含三帧，前面依次为故障 RIP、`memory_activation_test_mid_return`、`memory_activation_test_inject_return`，最多 16 帧且后续地址必须落在已链接 text 内。IST guard 测试证明该 guard 确实不在场且 IST 诊断可用，不模拟 IST 自身溢出的嵌套故障。

原有八项 CPU 异常探针仍在完整内存准备之前注入，运行于旧 P1 根；它们继续用于早期异常诊断回归，不能替代这里的权限/guard 测试。七个准备阶段拒绝用例仍须在激活之前返回规定 memory_error 并退出 35，不得产生 activation 或 panic 字段。

正常 smoke 和正式 normal 用例已实际通过：新根 `0x00400000`，entry_rsp=`0xffff900000011000`、entry_rbp=0，嵌套 rsp=`0xffff900000010fb8`、rbp=`0xffff900000010fe0`；CR0=`0x80010033`、CR4=`0x668`、EFER=`0xd00`、PAT=`0x0007040600070406`、RFLAGS=`0x46`，三个 token 正确且 cache_steps=31，测试版退出 33。当前 normal 使用17张表、映射1161页，arena仍为空闲944页+64页表池+16页普通栈，资源21项。这次继承状态的 NXE/WP 已经为 1，实际 handoff 仍按保留位计划写入并读取结果。

复现命令为 `python tests/run_memory_qemu.py --all`。构建与 QEMU 逐项串行，CPU 能力负例可复用正常 ESP，各次运行使用独立 NVRAM、串口、QEMU 日志和结果。证据目录为 [build/test/memory-activation/](../build/test/memory-activation/)，聚合结果位于 [result.json](../build/test/memory-activation/result.json)，单项结果位于对应 case 子目录。宿主耗时包括构建和固件启动，不能作为内核启动性能。

本轮最终回归全部通过，汇总及编译源文件SHA-256见 [validation-summary.json](../build/test/memory-activation/validation-summary.json)：

| 验证 | 实际结果 |
| --- | --- |
| 系统宿主 | 137项通过、零skip，53.797秒 |
| 语言/标准库宿主 | 323项通过、零skip，39.886秒 |
| 不同宿主测试总数 | 460；重复的定向复跑不重复计数 |
| 内存QEMU | 13项：normal、七个预检拒绝、五个新根故障，全部通过 |
| 早期CPU QEMU | 原八种fatal诊断全部退出37并通过独立上下文gate |
| 镜像拒绝QEMU | 篡改、截短、缺失三项全部退出35且未进入内核 |
| 正式客体用例 | 24项；另1次正常smoke，实际共25次QEMU，全部串行 |
| 正式版 | 构建通过，ELF含实际激活入口且不含三种测试注入helper；仅构建，未启动正式版 |

系统宿主发现146项，明确排除需实际启动QEMU的 `test_std_arch_qemu_negative` 九项；它们未计入460项通过结果。该套件属于DeepSeek独立探针，本轮没有重做其任务验收。原始宿主结果/排除清单见 [system-host-regression.json](../build/test/memory-activation/system-host-regression.json)、[日志](../build/test/memory-activation/system-host-regression.log)及[语言日志](../build/test/memory-activation/lang-regression.log)。新native测试在debug/release、ELF64/COFF核对Report布局，独立C模型遍历全部栈偏移并破坏原始页项，确认只容许合法A/D变化且其余污染被拒绝。

内存客体的各项原始报告见上述聚合结果；五个新根故障均产生四帧受限回溯。[cpu-loader-regression.json](../build/test/memory-activation/cpu-loader-regression.json)和[日志](../build/test/memory-activation/cpu-loader-regression.log)记录其余11项客体；[production-build.log](../build/test/memory-activation/production-build.log)记录正式构建。[handoff-listing.txt](../build/test/memory-activation/handoff-listing.txt)保留NASM机器码清单，可核对两次WBINVD及相邻CR3/RSP指令。

QEMU TCG验证了控制流、寄存器读回、页权限和诊断，尚无真机或远程CI结果。活动树仍只在提交前构建，后续修改所需TLB失效、跨核shootdown和安全回收尚未接入；本轮不释放旧启动资源。下一步先定义并验证活动树map/protect/unmap与TLB生命周期，再推进大页、PCID及PAT写合并。
