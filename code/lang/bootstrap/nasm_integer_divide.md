# bootstrap.nasm_integer_divide：受控 64 位整数除法与余数

生成固定寄存器除法/余数内核。输入 `RDI`=被除数、`RSI`=除数；输出 `RAX`=商或余数。模块不导出 C 符号；无外部 Dong 依赖。

```text
module bootstrap.nasm_integer_divide;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(signed:bool, remainder:bool, out:[]u8, written:*usize)u64
```

## 输出

| signed | remainder | 文本 |
| --- | --- | --- |
| true | false | `mov rax, rdi\nmov rcx, rsi\ncqo\nidiv rcx\n` |
| true | true | 同上再加 `mov rax, rdx\n` |
| false | false | `mov rax, rdi\nmov rcx, rsi\nxor edx, edx\ndiv rcx\n` |
| false | true | 同上再加 `mov rax, rdx\n` |

只允许改 RAX/RCX/RDX/flags。调用方必须保证除数非零，且 signed 时不为 i64 最小值/-1；本组件不发射门禁。

## 检查顺序

描述符与别名 → 总长 → `CAPACITY` → 一次写出。
