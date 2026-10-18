# bootstrap.sysv_integer_args：SysV 整数参数位置规划

只规划 x86-64 SysV 中 **INTEGER 类**参数的位置，不支持 SSE/浮点、超过两个机器字的聚合、返回值和 varargs，不代表完整 ABI。

```text
module bootstrap.sysv_integer_args;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const REGISTER:u64=0; pub const STACK:u64=1;
pub struct Location { pub kind:u64, pub index:usize }     // 16 字节
pub struct Result { pub used:usize, pub stack_bytes:usize } // 16 字节
pub unsafe fn plan(kinds:[]const u8, out:[]Location, result:*Result)u64
```

- `kinds[i]=0`：一个 u64/i64/指针机器字；`kinds[i]=1`：含两个 INTEGER 机器字的聚合；其它值 `INVALID`。
- 按参数顺序输出展开后的每个机器字。`REGISTER` 的 index 0..5 依次为 RDI、RSI、RDX、RCX、R8、R9；`STACK` 的 index 是从第一个栈参数槽起的字节偏移，按参数/字顺序每字递增 8。
- 双字聚合需要同时剩余两个寄存器，否则两个字整体上栈，**不占用**剩下的那个单寄存器，之后的标量仍可使用它（例如 5 个标量、1 个聚合、1 个标量：聚合在栈 0/8，最后的标量在 R9）。
- `result.used` 为机器字总数，`result.stack_bytes` 为栈字节数向上取整到 16。空输入成功，`used=0, stack_bytes=0`。

## 检查顺序与内存

1. `INVALID`（描述符）：`result` 非空、8 字节对齐；`out` 8 字节对齐；长度乘法和端点不溢出；`out`、`result` 彼此不重叠，也不与 `kinds` 重叠；空切片可为 NULL。
2. `INVALID`（数据）：第一遍扫描全部 kinds，任何非 0/1 的值；机器字数或栈字节数（含取整）溢出（实际不可达，但先比较再相加）。
3. `CAPACITY`：`out.len` 小于机器字总数。

第一遍只读不写；全部通过后第二遍按同样规则写出。非 OK 不改变 out 和 result；成功只写 `out[0..used)` 和 result，out 尾部不变。O(kinds.len)，无分配、无全局可变状态、无 OS 调用。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_sysv_plan`。
