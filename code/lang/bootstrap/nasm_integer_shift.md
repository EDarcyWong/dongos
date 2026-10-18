# bootstrap.nasm_integer_shift：64 位立即数移位发射

生成单行立即数移位。计数字面量由只读依赖 `bootstrap.decimal_integer`（CR4）编码。模块不导出 C 符号。

```text
module bootstrap.nasm_integer_shift;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(operation:u64, destination:u64, count:u64, out:[]u8, written:*usize)u64
```

## 输入

- `operation`：仅 `0`=shl、`1`=shr、`2`=sar。
- `destination`：仅 `0..15`。
- `count`：仅 `0..63`；越界 → `INVALID`（不静默掩码）。

## 输出

`<mnemonic> <dest64>, <count十进制>\n`（count=0 仍发射）。

## 检查顺序

描述符与别名 → 操作/寄存器/计数 → CR4 栈暂存 → 总长 → `CAPACITY` → 一次写出。
