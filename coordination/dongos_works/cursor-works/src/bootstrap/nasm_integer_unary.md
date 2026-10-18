# bootstrap.nasm_integer_unary：64 位整数一元与零比较发射

生成 wrapping `neg`、按位 `not`，或把同一寄存器与零比较后写成 0/1。模块不导出 C 符号；无外部 Dong 依赖。

```text
module bootstrap.nasm_integer_unary;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(operation:u64, register:u64, out:[]u8, written:*usize)u64
```

## 输入

- `operation`：仅 `0`=wrapping neg、`1`=bitwise not、`2`=零比较取反；其它 → `INVALID`。
- `register`：仅 `0..15`。

## 输出（严格 ASCII + 单字节 LF）

| op | 文本 |
| --- | --- |
| 0 | `neg <reg64>\n`（一行） |
| 1 | `not <reg64>\n`（一行） |
| 2 | `test <reg64>, <reg64>\nsete <reg8>\nmovzx <reg64>, <reg8>\n`（三行） |

op2 结果落在同一 `register`：输入 0 → 1，其它 64 位模式 → 0。只改目标寄存器及允许的 flags。`neg` 为模 2^64（含 i64 最小值位模式）。

## 检查顺序

描述符与别名 → 操作/寄存器 → 总长 → `CAPACITY` → 一次写出。失败不改 `out`/`*written`。
