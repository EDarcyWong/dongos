# bootstrap.nasm_direct_call：复用内部符号编码的直接调用发射

```text
module bootstrap.nasm_direct_call;
import bootstrap.nasm_symbol as sym;     // 已集成 CR3
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NAME_LIMIT:usize=64;
pub unsafe fn emit(module_name:[]const u8, item_name:[]const u8, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好一行 ASCII：`call <symbol>\n`，其中 `<symbol>` 是 CR3 `nasm_symbol.encode(module_name, item_name)` 的完整结果（`__dong_m<hex>_n<hex>`），在 266 字节局部暂存区得到，不另行散列、截断或转义。不输出 extern/global/section/ret，也不做间接调用或尾调用。

两个名字各 1..64 个原始字节（不是 UTF-8 字符数），允许 NUL、非 ASCII 和标点。调用方负责 callee 的定义或链接、参数传递、调用点 16 字节栈对齐以及保存活跃的调用者保存寄存器；本组件不做参数或栈帧 lowering。

## 检查顺序与内存

1. `INVALID`（描述符）：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；module_name、item_name、out 任一区间回绕（非空切片指针必须非 NULL，空 out 可为 NULL）。
2. `INVALID`（别名）：written 的 8 字节与完整 out、完整 module_name、完整 item_name 任一重叠；out 与两个完整输入任一重叠。两个输入之间允许重叠。
3. `INVALID`（长度）：任一名字长度为 0 或超过 64。
4. 调用 CR3 编码到局部暂存区（以上检查保证其成功，非 OK 也按 INVALID 处理）。
5. `CAPACITY`：`5 + 符号长度 + 1`（至多 272，无溢出可能）大于 out.len。

全部检查通过后才写 out 和 `*written`；任何失败不改 out、written 和输入的任何字节。成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_call_emit`。
