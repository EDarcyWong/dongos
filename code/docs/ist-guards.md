# IST 栈保护页布局

三个 IST 仍分别提供 16 KiB 可用区，`cpu_df_stack_bottom/top`、`cpu_nmi_stack_bottom/top`、`cpu_exception_stack_bottom/top` 及只读的三项 trusted range 表保持原含义。每栈现在在 BSS 中显式保留前后各一页，合计六个独立 4 KiB guard 页、额外 24 KiB BSS。

| 栈 | 低 guard 页起点 | 高 guard 页起点 |
| --- | --- | --- |
| DF | `cpu_df_guard_low = cpu_df_stack_bottom - 4096` | `cpu_df_guard_high = cpu_df_stack_top` |
| NMI | `cpu_nmi_guard_low = cpu_nmi_stack_bottom - 4096` | `cpu_nmi_guard_high = cpu_nmi_stack_top` |
| EXCEPTION | `cpu_exception_guard_low = cpu_exception_stack_bottom - 4096` | `cpu_exception_guard_high = cpu_exception_stack_top` |

这些六个新符号均公开导出。相邻栈有各自的 guard 页，彼此不共享。可用栈仍为半开区间 `[bottom, top)`；TSS 的 IST1/2/3 和 panic 的 trusted ranges 仅引用实际可用区，绝不包括 guard。

`boot.memory_resources.Layout` 保持 184 字节、8 字节对齐，字段与偏移不变；其 `df/nmi/exception_stack` 仍描述可用的 16 KiB 栈。资源 kind 15～17 继续保留实际栈，六个 guard 的物理页已由 kind 11 的完整 BSS 和 kind 1 的整个内核分配 envelope 保留，不新增资源项，也不归还给 buddy。保留资源和映射资源是不同的范围。

## 纯检查 API

`boot.ist_layout` 提供两个只读函数：

```text
pub fn valid(layout: *const resources.Layout) bool
pub fn is_guard(address: u64, layout: *const resources.Layout) bool
```

非空指针必须指向完整、可读、已初始化的 Layout；空指针返回 false。函数不写输入、不解引用布局中的地址，也不依赖分配器、CPU 寄存器或活动页表。

`valid` 要求 BSS 非空且页对齐；三个可用栈恰为 16 KiB 且页对齐，各自扩展后的 `[start - 4096, end + 4096)` 全部位于 BSS 内且两两不相交。六个 guard 不得与 GDT、TSS、IDT、workspace 任一活资源相交；这四项自身也须为非空、非反向的区间。运算先验证包含与减法边界，再推导 guard 端点，避免 u64 下溢或溢出。

`is_guard` 仅对有效布局中的六个**页起点**返回 true；页内其他字节、布局无效或地址不对齐时返回 false。映射方必须先拒绝 `!valid(layout)`，再逐页跳过 `is_guard` 命中的 BSS 页；不能把无效布局的全 false 当作可映射许可。其余 BSS 以及所有实际栈页仍应为 WB/RW/NX。

布局模块只预留页和提供策略。启动集成跳过六页，并用公开 query 的精确 NotMapped 和独立 raw walk 证明空洞，同时避免其物理页被其他 HHDM 对象别名重新映射。P1 的旧映射仍包含这些页，新增 BSS 占位本身不会产生硬件 guard fault；当前启动已切到新树，EXCEPTION 低 guard 的真实 #PF 已通过独立门禁，见 [paging-activation.md](paging-activation.md)。其余五个 IST guard 的缺席由全树审计验证。

## TSS 与正常栈

当前 `cpu_init` 将 RSP0 与 IST3 都设为 `cpu_exception_stack_top`，该地址位于高半区 BSS，未引用旧低地址启动栈。当前 BSP 在 CPL0 运行，所有 IDT 门均使用非零 IST；普通新栈干跑不需要修改 RSP0。未来进入用户态或采用 IST=0 的入口时，须另行设计正常特权栈，不能把这次保持现状视为用户态支持。

AMD APM Volume 2 的 IST 说明：非零门索引选择对应 TSS IST 并载入 RSP；同一 IST 的嵌套异常可能覆盖旧帧。当前 fatal-only 入口和独立 DF/NMI 栈策略保持不变。[AMD APM Volume 2 §8.9](https://docs.amd.com/api/khub/documents/sD1_QL~h4Afq2_tvzxqqSQ/content)；Intel 同样区分特权级栈切换与非零 IST 的无条件切栈。[Intel SDM Volume 3A §7.14.4–5](https://cdrdv2-public.intel.com/843823/252046-sdm-change-document-1.pdf)

## 独立宿主验证

```text
python -m unittest tests.test_ist_layout -v
```

三项测试覆盖 debug/release、ELF64/COFF 和 native SysV。C 探针用固定六页 slot 的独立位图枚举 360 种有效布局，包含三个地址基点、全部三栈排列及不同间隔；遍历完整 BSS 的每个页起点与页内边界，要求恰好跳过六页，三栈各四个实际页全部保留。另覆盖 BSS/栈错位、大小错误、缺 guard 空间、共享 guard、区间反向与极值，以及四种活资源对六个 guard 的整页/单字节/跨边界相交。每次调用前后比较完整 Layout 及两侧哨兵。

测试还分别汇编真实 `kernel/cpu.asm` 为 ELF64 和 COFF，独立读取目标文件符号，核对六个 guard 的实际偏移、独立性、页对齐、原 16 KiB 栈大小及 trusted range 表的三项长度。未启动 QEMU 或执行特权指令；纯布局通过不替代启动集成的页表验证。
