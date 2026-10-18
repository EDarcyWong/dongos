# D6 — DeepSeek 新任务

负责人：DeepSeek。状态：已验收（Codex，2026-10-17）。

## 最新验收结论

Windows 测试观察器的 SysV 声明已修正并复验，原问题关闭。D5/D6 定向 4 项通过，完整回归通过 353 项宿主测试和 5 次 QEMU 启动，见 [复验记录](../reviews/2026-10-17-D5-D6-recheck.md)。特权操作的真实执行另交 D7；下方保留历史返修要求，不代表仍待处理。

## Codex 复验与返修要求

独立复跑 `python -m unittest lang.tests.test_std_arch -v`，2 项通过（1.310s）。包装器本体暂未发现功能缺陷，但测试中的 Windows 调用边界不符合 ABI，D6 暂不作最终验收。

- `lang/tests/test_std_arch.py` 的 C 探针将 `arch_regcheck` 声明为普通 C 函数，Windows 默认使用 Microsoft x64；对应 NASM 观察器按 SysV 编写并清零 RDI/RSI，违反 Microsoft x64 对这两个非易失寄存器的保存要求。
- 将该声明改成与汇编一致的显式 SysV ABI（例如 `extern int DG arch_regcheck(void);`），或提供完整 Microsoft x64 桥接。重新执行 debug/release 原生测试及 ELF64/COFF 组装。
- 在 `deliveries/D6.md` 追加修复和实际验证记录，保留原交付内容；修复后将状态更新为“已修正，待 Codex 复验”。审查详情见 [D6 审查记录](../reviews/2026-10-16-D6.md)。

## D6：实现 `arch.x86_64`

提供受审查的外部汇编函数声明和对应 NASM 实现，至少包括以下能力；链接名加统一 `dg_arch_` 前缀，不使用编译器保留前缀。

- `in8/out8`：u16 端口和 u8 数据；仅允许特权调用环境。
- `read_cr3/write_cr3`、`read_msr/write_msr`：显式整数参数/返回，说明特权、保留位、页表/CPU 状态由调用方负责。
- `read_tsc`：返回 u64；说明读取本身不等于序列化屏障。
- `cpuid(leaf:u32,subleaf:u32,out:*CpuId)`：通过指针写入四个 u32 字段，保持 SysV 非易失寄存器，尤其 RBX。CpuId 使用公开字段并核对布局，不按值跨函数传递。
- CPU 屏障可作为薄封装提供；不引入自动 CPU 特性调度、SIMD 算法、系统调用入口、线程切换或设备发现。

所有声明标记 unsafe，汇编写明输入、输出、破坏寄存器及特权前提。ELF64/COFF 都要组装；宿主只执行允许在用户态运行的 CPUID/TSC 等探针，检查寄存器保留和返回布局。特权指令不得在宿主用户态执行；需要的 QEMU 探针可作为独立 `std_arch_probe.*` 交付，写清尚未执行的部分，不修改现有 P1 或将编码检查称为特权实测。



## 执行与交付约束

- 完整协作边界与通用验收要求见 [总清单](../deepseek-work-list.md)；只修改本任务分配的标准库、测试与说明文件。
- 不修改 `lang/dongc/`、P1 内核或构建入口；发现编译器缺陷时提交最小源码和实际诊断。
- 真实运行 debug/release 原生测试及 ELF64/COFF 组装；未执行的部分明确列为未验证。
- 完成后新增 `deepseek-works/deliveries/D6.md`，记录文件、命令、结果与限制，再更新本任务和总清单状态。
- 不覆盖其他任务或既有交付记录，不提交或推送。
