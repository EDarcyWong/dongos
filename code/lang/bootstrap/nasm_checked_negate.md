# bootstrap.nasm_checked_negate：signed i64 一元负号溢出门禁

```text
module bootstrap.nasm_checked_negate;
import bootstrap.decimal_integer as dec;   // 已集成 CR4，块号十进制
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(destination:u64, trap_block:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好两行 ASCII：

```text
neg <dest64>
jo __dong_b<N>
```

- `destination` 仅 `0..15`（rax..r15）；其它编号 INVALID。
- 只处理 signed i64：`i64::MIN` 溢出跳 trap，其它落空；两路径目的寄存器均为模 2^64 负值。
- 仅 `destination`/flags 改变；无 scratch、标签定义或 panic。不覆盖 unsigned/narrow，不改 CR16 wrapping 一元组件。
- `trap_block` 允许 `0..usize最大−1`，`NONE` 非法；标签数字仅复用 CR4。

## 检查顺序与内存

1. `INVALID`：written 描述符/对齐/端点；out 区间回绕（空 out 可为 NULL）；written 与完整声明 out 重叠。
2. `INVALID`：`destination > 15` 或 `trap_block == NONE`（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 48 字节局部缓冲区组装（最长 40 字节：`jo __dong_b` 为 11 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_checked_neg_emit`。
