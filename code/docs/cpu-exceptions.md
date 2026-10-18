# P2 BSP CPU 表与终止异常诊断

内核现在在执行 Dong 探针前安装自己的 GDT、TSS 和 256 项 IDT。此阶段只运行启动处理器，保持 IF=0；所有异常终止当前启动，不尝试恢复或返回。P1 引导器、镜像格式和 BootInfo ABI 保持现有契约。

本文保留早期 CPU 基础阶段的实现与当时验收范围。当前版本已激活私有页表和 guard，接通 buddy/对象缓存及 CPU 硬化，并完成隔离 CPL3 权限验证；最新正式启动、全保护位真实缺页画面及阶段状态见 [P2阶段验收](p2-acceptance.md)。下文“尚未激活/后续”的描述对应早期历史，不代表当前状态。

后续[CPU硬化](cpu-hardening.md)按能力启用SMEP/SMAP/UMIP。异常入口在保存完整原始上下文之后、调用诊断之前，使用PUSHFQ/AND/POPFQ清实时AC；保存的RFLAGS仍保留被中断状态。该序列在无SMAP能力时也有效，不会因无条件CLAC导致#UD。当前没有可恢复的user-copy窗口或CPL3异常返回协议。

## 描述符与栈

实现位于 `kernel/cpu.asm`，共用常量和异常布局位于 `include/cpu.inc`。

| 内容 | 当前设置 |
| --- | --- |
| GDT | 40 字节；null、64 位代码 0x08、数据 0x10、16 字节 TSS 描述符 0x18 |
| TSS | 104 字节；I/O bitmap 基址为 104，超出 limit 103；LTR 后类型为 busy |
| IDT | 256 × 16 字节；present、DPL 0 的 64 位 interrupt gate |
| IST1 | 双重故障，独立 16 KiB 栈 |
| IST2 | NMI，独立 16 KiB 栈 |
| IST3 | 其余入口，独立 16 KiB 栈 |

表、处理器入口和三组栈均在高半区内核镜像内，BSS 由现有 ELF 物化流程初始化；它们随整个内核物理范围保留。`cpu_validate` 用 SGDT/SIDT/STR 和实际内存核对当前表、TSS 状态、全部门、段选择子及 IF/DF，成功后输出 `DONGOS_P2_CPU_READY`。

三栈各有前后独立4KiB guard占位，新离线树跳过六页；P1活动大页仍映射这些物理页，因此本阶段不声称硬件guard fault已经生效。布局和集成验收见 [IST保护页](ist-guards.md)与[激活前检查](paging-preflight.md)。

TSS.RSP0 暂指向异常栈顶。进入用户态前需换成对应线程的内核栈；本轮没有用户态、IRQ 控制器、调度器或中断返回路径。

## 异常上下文

64 位硬件帧中的 SS/RSP、RFLAGS、CS、RIP 均按 8 字节读取。带硬件错误码的向量为 8、10、11、12、13、14、17、21、29、30；其他入口补零，再压入向量编号。不能用 `int n` 模拟带硬件错误码的异常。

公共入口保存全部通用寄存器并尽早读取 CR2，形成固定 184 字节 `ExceptionContext`。布局为 CR2、R15～R8、RDI、RSI、RBP、RDX、RCX、RBX、RAX、vector、error、RIP、CS、RFLAGS、原 RSP、SS。在清除 DF、保持 IF=0 并对齐栈后，按 SysV 调用 `kernel_exception_panic`。

架构依据：[Intel SDM 卷 3，异常与中断章节](https://cdrdv2-public.intel.com/868137/325462-089-sdm-vol-1-2abcd-3abcd-4.pdf)、[AMD APM 卷 2，第 8 章](https://docs.amd.com/api/khub/documents/sD1_QL~h4Afq2_tvzxqqSQ/content)。双重故障属于 abort，测试不依赖它保存的 RIP 精确定位原指令。

## 诊断与停机

`kernel/panic.asm` 输出完整串口记录：`DONGOS_P2_PANIC`、上下文地址、IST 分类、全部寄存器和控制字段，以及最多 16 条地址。回溯第一项为保存的 RIP；后续只读取已登记的正常启动栈或一组 IST 栈内、8 字节对齐且严格递增的 RBP 链。每次读取前检查完整两个 qword 的范围和整数溢出，不跨栈追踪、不读返回地址指向的内存。

串口轮询有界，超时后停止重试。重入只输出 `DONGOS_P2_PANIC_REENTERED` 后停机，不继续遍历或绘图。panic保存独立RuntimeDisplay*，GOP地址已转换为HHDM；原BootInfo的物理字段不再被renderer解引用。准备阶段先登记旧正常栈，再登记实际干跑的HHDM新栈；结束时停用普通回溯范围，拒绝旧低地址RBP及旧树未映射的未来STACK地址，IST范围仍有效。固定新栈只在未来真正加载新CR3后登记。`test_panic_binding.py`实际验证旧范围退役、完整两qword边界及IST guard排除。GOP panic 屏显示全部通用寄存器、vector/error、RIP/RSP/CR2、段/标志及前四条回溯，适配最低 640×480。正常构建持续 CLI/HLT；测试构建使用独立退出码 37，区别于正常成功 33 和引导失败 35。

早期屏幕记录：`build/screen-check/p2/panic.png`。该图来自旧树下的真实非法指令异常（vector6），640×480，不作为当前缺页验收。最新活动根下、保护位全开的真实 vector14 画面见 [page-fault-screen/screen.png](../build/test/p2-acceptance/page-fault-screen/screen.png)；两次采图均移除 debug-exit 设备，使原测试内核停留在最终 HLT。

## 验收命令

```text
python tests/run_cpu_qemu.py --all
python tests/run_cpu_qemu.py --case double-fault
python -m unittest tests.test_cpu_qemu_result -v
python tools/build.py test
```

八个独立注入为 INT3、UD2、无效段选择子 #GP、读取未映射 4 GiB 的 #PF、坏 RSP 时 UD2、#GP 交付再故障形成 #DF、除零、损坏 RBP 链。每项重新构建内核、镜像和匹配哈希的 EFI，产物隔离在 `build/test/cpu/<case>/`，故障注入源码不会链接进普通构建。

运行器同时检查退出码、完整且有序的阶段行、向量/错误码、CR2、保存的寄存器、原栈、上下文 IST 范围和回溯。除双重故障外，故障 RIP 与 ELF 符号对照。任何正常 PASS、重入、缺字段、损坏/重复字段或超时都算失败。结果保存于 `build/test/cpu/result.json`；统一验收还保留 P0 和 P1 镜像拒绝用例。

## 早期验收时的边界（历史）

现有页表仍为 P1 的低 4 GiB 恒等/HHDM 和高半区临时 RWX 映射，零页仍映射，IST 尚无保护页。正式 W^X、保护页、NX/SMEP/SMAP/WP、物理页分配器、对象缓存、用户态和多核异常状态均属于后续工作。NMI 门已安装和检查，本轮自动注入不包含外部 NMI 的硬件递送。

## 本轮实测记录（2026-10-17）

`python tools/build.py test` 完整通过：58 项系统/工具测试和 321 项语言/标准库测试，合计 379 项；P0/P1 的 5 次启动及本节 8 次真实 CPU 异常注入共 13 次全部通过。完整日志 `build/test/p2-full-test.log`，逐项结果 `build/test/cpu/result.json`。正常生产构建已重新生成，实际完成 CPU 表检查和完整 L1 链后保持运行，无注入和 panic；正常画面与 640×480 panic 画面均已目视检查。

本轮还读入了 DeepSeek D7/D8 的初始测试，它们虽然通过但有单独的审查返修要求，见 `deepseek-works/reviews/2026-10-17-D7-D8.md`；不以统一测试通过替代这些任务的最终验收。未执行远程 CI 或真机测试。
