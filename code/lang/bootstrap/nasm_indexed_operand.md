# bootstrap.nasm_indexed_operand：NASM 缩放索引地址操作数

```text
module bootstrap.nasm_indexed_operand;
import bootstrap.decimal_integer as dec;   // 已集成 CR4
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn encode(base:u64, index:u64, scale:u64, displacement:i64, out:[]u8, written:*usize)u64
```

成功时 out 前缀是一个 ASCII 操作数（无 LF/NUL）：

```text
[<base64> + <index64>*<scale>]               ; displacement == 0
[<base64> + <index64>*<scale> + <disp>]      ; displacement > 0
[<base64> + <index64>*<scale> - <|disp|>]    ; displacement < 0
```

- base 为 0..15；index 为 0..15 但不能是 4（RSP），12（R12）合法；base==index 合法。
- scale 只能是 1/2/4/8，scale=1 也写出 `*1`；displacement 必须在 i32 范围内。
- scale 和位移数字由 CR4 `decimal_integer.encode` 写入局部暂存区（负位移取补得到绝对值，可表示 2^31）。
- 不支持无基址、RIP、符号、段前缀或 addr32 形式；不修改 CR8 的 base+disp 操作数或 CR15 LEA 接口。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：base/index 越界、index==RSP、scale 不是 1/2/4/8、位移超出 i32（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 48 字节局部缓冲区组装（最长 `[r15 + r15*8 - 2147483648]` 为 26 字节，这是固定的充分界限），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_indexed_encode`。
