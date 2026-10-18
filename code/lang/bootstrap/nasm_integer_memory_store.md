# bootstrap.nasm_integer_memory_store：有界 NASM 整数内存存储

生成单行内存存储指令。地址操作数由只读依赖 `bootstrap.nasm_memory_operand`（CR8）编码；CR4 为其传递依赖。模块不导出 C 符号。

```text
module bootstrap.nasm_integer_memory_store;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(source:u64, base:u64, displacement:i64, width:u64, out:[]u8, written:*usize)u64
```

## 输入

- `source` / `base`：仅 `0..15`。
- `displacement`：仅 i32 范围。
- `width`：仅 8/16/32/64；写出源寄存器的低 width 位。

## 输出

严格单行：`mov <size> <operand>, <source-width-reg>\n`（LF=`0x0A`）。

| width | size | 源寄存器 |
| --- | --- | --- |
| 8 | byte | al…r15b（低 8 位名） |
| 16 | word | ax…r15w |
| 32 | dword | eax…r15d |
| 64 | qword | rax…r15 |

`<operand>` 即 CR8 `encode(base, displacement)`。不改任何寄存器；无原子/volatile。

## 检查顺序

描述符与别名 → 寄存器/宽度/位移 → CR8 栈暂存 → 总长 → `CAPACITY` → 一次写出。失败不改 `out`/`*written`。
