# bootstrap.nasm_variable_shift：64 位 CL 可变移位发射

```text
module bootstrap.nasm_variable_shift;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const SHL:u64=0; pub const SHR:u64=1; pub const SAR:u64=2;
pub unsafe fn emit(operation:u64, destination:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好一行 ASCII：`shl|shr|sar <dest64>, cl\n`。寄存器编号 0..15 为 rax..r15。不装入或保存 RCX，不发射立即数移位（与 CR17 的常量 count 接口不同）。

语义（x86-64 硬件）：上游把计数放进 RCX，有效计数是 CL 的低 6 位；结果为低 64 位。SHL 丢弃高位，SHR 补 0，SAR 按补码保留符号。dest 为 RCX 也合法，移位前的 CL 决定计数，结果写回 RCX。其它寄存器不变，flags 按硬件规则改变。语言层的移位范围/溢出检查仍由上游负责，不能因硬件会掩码就省略。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：operation > 2 或 destination > 15（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：行长大于 out.len。

行在 16 字节局部缓冲区组装（最长 12 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_shift_emit`。
