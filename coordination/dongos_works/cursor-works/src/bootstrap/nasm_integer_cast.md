# bootstrap.nasm_integer_cast：NASM 整数截断与符号规范化

生成单行寄存器间截断/符号扩展指令，把 `source` 低 `width` 位解释为目标整数并得到规范 64 位零/符号扩展结果。模块不导出 C 符号；无外部 Dong 依赖。

```text
module bootstrap.nasm_integer_cast;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(destination:u64, source:u64, width:u64, signed:bool, out:[]u8, written:*usize)u64
```

## 输入

- `destination` / `source`：仅 `0..15`；其它 → `INVALID`。
- `width`：仅 8/16/32/64。
- `signed`：决定窄宽度用符号扩展还是零扩展（64 位两种相同）。
- `source` 原 64 位可任意；不依赖高位已清零。

## 输出（严格单行，LF=`0x0A`）

| width | signed | 文本 |
| --- | --- | --- |
| 8/16 | true | `movsx <dest64>, <source-low8/16>\n` |
| 8/16 | false | `movzx <dest64>, <source-low8/16>\n` |
| 32 | true | `movsxd <dest64>, <source32>\n` |
| 32 | false | `mov <dest32>, <source32>\n` |
| 64 | * | `mov <dest64>, <source64>\n` |

`destination==source` 仍生成该行。这是显式 cast 位模式组件，不改 flags，除 dest 外不改其它寄存器；不代替编译期常量越界或调试算术溢出诊断。

## 检查顺序

描述符与别名 → 寄存器/宽度 → 总长 → `CAPACITY` → 一次写出。失败不改 `out`/`*written`。INVALID 优先 CAPACITY。
