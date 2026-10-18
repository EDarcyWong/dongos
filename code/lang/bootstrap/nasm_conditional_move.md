# bootstrap.nasm_conditional_move：复用谓词枚举的 64 位条件移动发射

```text
module bootstrap.nasm_conditional_move;
import bootstrap.branch_plan as bp;        // 已集成 CR6，只读引用谓词常量
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(condition:u64, destination:u64, source:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好一行 ASCII：`<cmovcc> <dest64>, <source64>\n`。condition 为 CR6 的 0..9（EQ/NE/ULT/ULE/UGT/UGE/SLT/SLE/SGT/SGE），mnemonic 依次为 cmove/cmovne/cmovb/cmovbe/cmova/cmovae/cmovl/cmovle/cmovg/cmovge。寄存器 0..15 为 rax..r15，dest==source 也照常发射。

语义：消费上游 64 位 `cmp` 留下的 flags。条件为真时复制完整的 source64，否则保留原 dest64；其它寄存器和 flags 都不变。不生成 cmp/test/setcc，不用内存操作数，选择的值不限于 bool。上游负责保证 cmp 与本片段之间没有破坏 flags 的指令。只复用 CR6 常量，不调用其规划算法。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：condition > SGE，或 dest/source > 15（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：行长大于 out.len。

行在 24 字节局部缓冲区组装（最长 16 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_cmov_emit`。
