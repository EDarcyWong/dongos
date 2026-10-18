# bootstrap.nasm_block_emit：基础块标签与无条件跳转

生成单行块定义或无条件跳转。块编号十进制由只读依赖 `bootstrap.decimal_integer`（CR4）编码；标签格式与 CR10 分支目标一致。模块不导出 C 符号。

```text
module bootstrap.nasm_block_emit;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(kind:u64, block_id:u64, out:[]u8, written:*usize)u64
```

## 输入

- `kind`：仅 `0`=块定义、`1`=无条件跳转。
- `block_id`：允许 `0 .. u64::MAX-1`；`u64::MAX` 为 NONE 哨兵 → `INVALID`。

## 输出（严格单行，LF=`0x0A`）

| kind | 文本 |
| --- | --- |
| 0 | `__dong_b<unsigned-decimal>:\n` |
| 1 | `jmp __dong_b<unsigned-decimal>\n` |

只发射指定一行；不改变条件、不省略跳转、不加 section/global。调用方保证汇编单元内块 ID 唯一。

## 检查顺序

描述符与别名 → kind/NONE → CR4 栈暂存 → 总长 → `CAPACITY` → 一次写出。
