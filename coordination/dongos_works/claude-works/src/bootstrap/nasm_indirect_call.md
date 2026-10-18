# bootstrap.nasm_indirect_call：64 位寄存器间接调用发射

```text
module bootstrap.nasm_indirect_call;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(target:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好一行 ASCII：`call <target64>\n`，寄存器编号 0..15 为 rax..r15。不是 `call [reg]`、跳转、直接符号或 ret。

只发射调用指令：callee 地址是否有效、参数/返回值 ABI、调用点 16 字节对齐、活跃调用者保存寄存器的保存都由上游负责，本组件不声称完成函数指针 lowering。rsp/rbp 作为目标只保证文本与组装正确。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：target > 15（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：行长大于 out.len。

行在 16 字节局部缓冲区组装（最长 9 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_icall_emit`。
