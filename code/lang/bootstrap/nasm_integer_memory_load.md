# bootstrap.nasm_integer_memory_load：有界 NASM 整数内存装入

生成单行内存装入指令。地址操作数由只读依赖 `bootstrap.nasm_memory_operand`（CR8）编码；CR4 为其传递依赖。模块不导出 C 符号。

```text
module bootstrap.nasm_integer_memory_load;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(destination:u64, base:u64, displacement:i64, width:u64, signed:bool, out:[]u8, written:*usize)u64
```

## 输入

- `destination` / `base`：仅 `0..15`；其它 → `INVALID`。
- `displacement`：仅 i32 范围；越界不截断。
- `width`：仅 8/16/32/64。
- `signed`：决定窄装入用符号扩展还是零扩展（64 位两种相同）。

## 输出（严格单行，LF=`0x0A`）

| width | signed | 文本 |
| --- | --- | --- |
| 8/16 | true | `movsx <dest64>, byte/word <operand>\n` |
| 8/16 | false | `movzx <dest64>, byte/word <operand>\n` |
| 32 | true | `movsxd <dest64>, dword <operand>\n` |
| 32 | false | `mov <dest32>, dword <operand>\n` |
| 64 | * | `mov <dest64>, qword <operand>\n` |

`<operand>` 即 CR8 `encode(base, displacement)` 的完整结果。无原子/volatile、无 bounds check。

## 检查顺序

描述符与别名 → 寄存器/宽度/位移 → CR8 写入栈暂存 → 总长 → `CAPACITY` → 一次写出。失败不改 `out`/`*written`。
