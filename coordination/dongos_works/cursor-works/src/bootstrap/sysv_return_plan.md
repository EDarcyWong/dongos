# bootstrap.sysv_return_plan：SysV INTEGER 返回值扩展规划

仅为 Dong x86-64 System V ABI 的 INTEGER 类返回值做有限元数据规划：占用机器字数、有效位宽、后端统一值表示的高位扩展约定。不支持浮点/SSE、大聚合、sret、Win64、可变参数；不冒充完整 ABI 分类器。

```text
module bootstrap.sysv_return_plan;
pub const OK:u64=0; pub const INVALID:u64=1;
pub const NONE:u64=0; pub const ZERO:u64=1; pub const SIGN:u64=2;
pub struct Plan { pub words:usize, pub width_bits:usize, pub extension:u64 }
pub unsafe fn plan(kind:u64, out:*Plan)u64
```

`Plan` 固定 24 字节、8 字节对齐。单字结果约定在 RAX；`INTEGER_PAIR` 低/高字在 RAX/RDX。BOOL 输入在上游已规范化为 0/1；本组件不读取返回值本身。

## kind → Plan

| kind | 名称 | words | width_bits | extension |
| --- | --- | --- | --- | --- |
| 0 | VOID | 0 | 0 | NONE |
| 1 | BOOL | 1 | 8 | ZERO |
| 2 | U8 | 1 | 8 | ZERO |
| 3 | I8 | 1 | 8 | SIGN |
| 4 | U16 | 1 | 16 | ZERO |
| 5 | I16 | 1 | 16 | SIGN |
| 6 | U32 | 1 | 32 | ZERO |
| 7 | I32 | 1 | 32 | SIGN |
| 8 | U64 | 1 | 64 | NONE |
| 9 | I64 | 1 | 64 | NONE |
| 10 | PTR | 1 | 64 | NONE |
| 11 | INTEGER_PAIR | 2 | 64 | NONE |

其它 `kind` → `INVALID`，`out` 全文不变。

## 检查顺序

1. `out` 非空、8 字节对齐、完整 24 字节区间不回绕（端点有效）。
2. `kind` 属于上表；否则 `INVALID`，不写。
3. 成功时写全部三个字段。

无分配、无全局可变状态、无 OS/文件 I/O、无寄存器发射。模块不导出 C 符号；测试经临时 wrapper 调用。扩展约定是后端统一值表示，不宣称 SysV 标准要求所有窄返回必须清高位。
