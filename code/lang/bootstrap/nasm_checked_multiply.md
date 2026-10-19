# bootstrap.nasm_checked_multiply：固定寄存器 64 位乘法溢出门禁

```text
module bootstrap.nasm_checked_multiply;
import bootstrap.decimal_integer as dec;   // 已集成 CR4，块号十进制
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(signed:bool, trap_block:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好三行 ASCII：

| signed | 文本 |
| --- | --- |
| true | `mov rax, rdi\nimul rax, rsi\njo __dong_b<N>\n` |
| false | `mov rax, rdi\nmul rsi\njc __dong_b<N>\n` |

- 运行时固定输入：`RDI=a`、`RSI=b`。溢出跳 trap，否则落空；两路径 `RAX` 均为积的低 64 位。
- signed：仅 `RAX`/flags 改变，`RDX` 保持；unsigned：另 `RDX`=无符号积高 64 位。`RDI`/`RSI` 及其余 GPR 保持。
- 乘法除 CF/OF 外算术 flags 未定义；不定义 trap 块/panic。这是 debug checked 路径原语，不替代 wrapping/窄值/完整语言 lowering。
- `trap_block` 允许 `0..usize最大−1`，`NONE` 非法；标签数字仅复用 CR4。

## 检查顺序与内存

1. `INVALID`：written 描述符/对齐/端点；out 区间回绕（空 out 可为 NULL）；written 与完整声明 out 重叠。
2. `INVALID`：`trap_block == NONE`（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 64 字节局部缓冲区组装（最长 59 字节：`jo __dong_b` 为 11 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_checked_mul_emit`。
