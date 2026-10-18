# bootstrap.nasm_bounds_guard：无符号数组/切片边界门禁

```text
module bootstrap.nasm_bounds_guard;
import bootstrap.decimal_integer as dec;   // 已集成 CR4，块号十进制
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(index:u64, length:u64, trap_block:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好两行 ASCII：

```text
cmp <index64>, <length64>
jae __dong_b<trap_block>
```

- `index`/`length` 为寄存器编号 0..15，允许相同。`cmp` 按无符号比较：`uint64(index) >= uint64(length)` 时跳 trap，否则落空。
- 高位值仍按无符号比较（例如 `index=2^63`、`length=MAX` 合法落空），不把所有高位值当 signed 负值拒绝。
- 块号用 CR4 `decimal_integer.encode(trap_block,64,false,…)` 在局部暂存区编码，标签形式与已集成 CR10 的 `__dong_b<十进制>` 一致。`trap_block` 允许 `0..usize最大−1`，`NONE` 非法。
- 只做 usize 元素索引相对元素数检查；不计算地址、不检查切片/指针有效性，也不定义 trap 块/panic。只改 flags，所有数据寄存器与内存保持。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：寄存器 > 15、`trap_block == NONE`（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 64 字节局部缓冲区组装（最长 45 字节：`cmp r15, r15\n` + `jae __dong_b` + 20 位十进制 + `\n`），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_bounds_emit`。
