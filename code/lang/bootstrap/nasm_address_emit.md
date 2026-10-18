# bootstrap.nasm_address_emit：NASM 基址位移地址生成

生成单行 `lea`，把 base+displacement 地址装入 64 位目的寄存器。地址操作数由只读依赖 `bootstrap.nasm_memory_operand`（CR8）编码；CR4 为其传递依赖。模块不导出 C 符号；不复制 CR8 的操作数格式实现。

```text
module bootstrap.nasm_address_emit;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(destination:u64, base:u64, displacement:i64, out:[]u8, written:*usize)u64
```

## 输入

- `destination` / `base`：仅 `0..15`；其它 → `INVALID`。
- `displacement`：仅 i32 范围；越界不截断。

## 输出（严格单行，LF=`0x0A`）

`lea <dest64>, <operand>\n`

`<operand>` 即 CR8 `encode(base, displacement)` 的完整结果。位移 0 或 `destination==base` 仍发射。只改 destination，不改 flags、不读取地址所指内存；无缩放索引/RIP/符号重定位。

## 检查顺序

描述符与别名 → 寄存器/位移 → CR8 写入栈暂存 → 总长 → `CAPACITY` → 一次写出。失败不改 `out`/`*written`。INVALID 优先 CAPACITY。
