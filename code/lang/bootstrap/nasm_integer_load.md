# bootstrap.nasm_integer_load：NASM 定宽整数常量装入 64 位寄存器

生成 `mov <reg64>, <立即数十进制>\n`。立即数文本由只读依赖 `bootstrap.decimal_integer`（CR4）编码，本模块不另写十进制算法。模块不导出 C 符号。

```text
module bootstrap.nasm_integer_load;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(register:u64, raw:u64, width:usize, signed:bool, out:[]u8, written:*usize)u64
```

## 输入

- `register`：仅 `0..15`（rax…r15）；其它 → `INVALID`。
- `width`：仅 8/16/32/64；窄 `raw` 必须 `< 2^width`，不截断。
- `signed`：交由 CR4 按该宽度补码解释；i64 最小与 u64 最大均可编码。

## 输出

严格为 `mov <reg>, <CR4 规范十进制>\n`（LF=`0x0A`）。无内存/符号/浮点，不插入 section/global/ret。

## 检查顺序

描述符与别名 → 寄存器/宽度/窄 raw → CR4 写入栈暂存 → 总长 → `CAPACITY` → 一次写出。失败不改 `out`/`*written`。
