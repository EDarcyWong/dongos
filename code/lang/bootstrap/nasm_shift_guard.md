# bootstrap.nasm_shift_guard：完整 64 位移位计数宽度门禁

```text
module bootstrap.nasm_shift_guard;
import bootstrap.decimal_integer as dec;   // 已集成 CR4，width 与块号十进制
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(count:u64, width:u64, trap_block:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好两行 ASCII：

```text
cmp <count64>, <width十进制>
jae __dong_b<trap_block>
```

- `count` 为寄存器编号 0..15。比较完整 64 位 usize：`count >= width` 跳 trap，否则落空；绝不先截断为 CL/32 位或掩码。
- `width` 仅允许 8/16/32/64；其它（含 0/7/128/MAX）→ `INVALID`，且优先于 `CAPACITY`。
- 块号用 CR4 `decimal_integer.encode(…,64,false,…)`；`trap_block` 允许 `0..usize最大−1`，`NONE` 非法。width 数字同样经 CR4。
- 只做移位前计数门禁；不输出移位/panic，不定义 trap 块。数据寄存器与内存保持，flags 允许改变。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：寄存器 > 15、非法 width、`trap_block == NONE`（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 64 字节局部缓冲区组装（最长 45 字节：`cmp r15, 64\n` + `jae __dong_b`（12 字节）+ 20 位十进制 + `\n`），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_shift_guard_emit`。
