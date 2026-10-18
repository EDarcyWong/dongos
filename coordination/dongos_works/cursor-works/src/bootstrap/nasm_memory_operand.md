# bootstrap.nasm_memory_operand：NASM 基址加有符号位移操作数

生成受限的 NASM 内存操作数文本（单一 64 位基址 + 可选有符号位移）。绝对值十进制由只读依赖 `bootstrap.decimal_integer`（CR4）编码，本模块不另写十进制算法。无大小前缀、LF、NUL；不支持索引/比例/RIP/符号。模块不导出 C 符号。

```text
module bootstrap.nasm_memory_operand;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn encode(base:u64, displacement:i64, out:[]u8, written:*usize)u64
```

## 输入

- `base`：仅 `0..15`，依次为 `rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15`；其它 → `INVALID`。
- `displacement`：仅 `[-2147483648,2147483647]`（i32 全范围）；越界 → `INVALID`，不截断。先检查有界再求绝对值；负值幅度用无符号 `wrapping_sub`（含 `-2147483648` → `2147483648`）。

## 输出格式

成功时严格为（括号内空格不可增减）：

| 条件 | 文本 |
| --- | --- |
| `displacement == 0` | `[<reg>]` |
| `displacement > 0` | `[<reg> + <十进制>]` |
| `displacement < 0` | `[<reg> - <绝对值十进制>]` |

例：`base=5, displacement=-8` → `b"[rbp - 8]"`。

## 检查顺序

1. `written` 非空、8 字节对齐、区间不回绕。
2. `out` 完整声明区间不回绕（空 `out` 可为 NULL）。
3. `written` 的 8 字节与完整 `out` 不重叠。
4. `base` / `displacement` 规则；不合法 → `INVALID`。
5. 非零位移时经 CR4 得到十进制长度并求总长；溢出 → `INVALID`。
6. `out.len` 不足 → `CAPACITY`。`INVALID` 先于 `CAPACITY`。
7. 成功一次写出；失败不改 `out` / `*written`。

CR4 先写入栈上暂存，再复制到用户 `out`，避免子调用失败留下半成品。
