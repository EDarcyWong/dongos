# bootstrap.nasm_symbol_address：RIP 相对内部符号地址发射

```text
module bootstrap.nasm_symbol_address;
import bootstrap.nasm_symbol as sym;     // 已集成 CR3
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NAME_LIMIT:usize=64;
pub unsafe fn emit(destination:u64, module_name:[]const u8, item_name:[]const u8, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好一行 ASCII：`lea <dest64>, [rel <symbol>]\n`。`<symbol>` 是 CR3 `nasm_symbol.encode(module_name, item_name)` 的完整结果，在 266 字节局部暂存区得到；不散列、不截断、不读取符号内容，也不用绝对地址常数。与 CR15 的基址+位移 LEA、C25 的直接调用都不同。

destination 为 0..15（rax..r15）；两个名字各 1..64 个原始字节，允许 NUL、非 ASCII 和标点。

## 检查顺序与内存

1. `INVALID`（描述符）：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；module_name、item_name、out 任一区间回绕（非空切片指针非 NULL，空 out 可为 NULL）。
2. `INVALID`（别名）：written 的 8 字节与完整 out、完整 module_name、完整 item_name 任一重叠；out 与两个完整输入任一重叠。两个输入之间允许重叠。
3. `INVALID`（参数）：destination > 15，任一名字长度为 0 或超过 64。
4. 调用 CR3 编码到局部暂存区（以上检查保证其成功，非 OK 也按 INVALID 处理），整行在 288 字节局部缓冲区组装（最长 282 字节）。
5. `CAPACITY`：行长大于 out.len。

全部通过后一次复制到 out 并写 `*written`；任何失败不改 out、written 和输入。成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_addr_emit`。
