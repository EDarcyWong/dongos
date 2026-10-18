# bootstrap.nasm_compare_emit：64 位比较生成规范 bool

```text
module bootstrap.nasm_compare_emit;
import bootstrap.branch_plan as bp;        // 已集成 CR6，只读引用谓词常量
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(condition:u64, left:u64, right:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好三行 ASCII：

```text
cmp <left64>, <right64>
<setcc> al
movzx rax, al
```

condition 沿用 CR6 编号 0..9：EQ/NE/ULT/ULE/UGT/UGE/SLT/SLE/SGT/SGE，对应 setcc 为 sete/setne/setb/setbe/seta/setae/setl/setle/setg/setge。寄存器编号 0..15 为 rax..r15。cmp 在覆盖 AL 之前执行，所以 left/right 为 RAX 也正确；结果 RAX 严格为 0 或 1，只改 RAX 和 flags。仅 64 位整数寄存器，无内存、浮点或窄值。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：condition > SGE，或 left/right > 15（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本先在 48 字节局部缓冲区中组装（最长 36 字节，长度计算不可能溢出），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。不重写 CR6，无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_compare_emit`。
