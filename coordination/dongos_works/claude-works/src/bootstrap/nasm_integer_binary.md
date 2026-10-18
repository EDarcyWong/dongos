# bootstrap.nasm_integer_binary：显式 wrapping 的 64 位整数二元发射

```text
module bootstrap.nasm_integer_binary;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const ADD:u64=0; pub const SUB:u64=1; pub const AND:u64=2; pub const OR:u64=3; pub const XOR:u64=4; pub const IMUL:u64=5;
pub unsafe fn emit(operation:u64, destination:u64, source:u64, out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好一行 ASCII：`<mnemonic> <dest64>, <source64>\n`，mnemonic 依 operation 0..5 为 `add/sub/and/or/xor/imul`。寄存器编号 0..15 为 rax, rcx, rdx, rbx, rsp, rbp, rsi, rdi, r8..r15。dest==source 不省略。不含 section/global/标签/注释/NUL，单字节 LF。

语义：结果模 2^64，只改 dest 和 flags，不读写内存。**不**承担 Dong debug 模式的溢出检查，只能用于明确允许 wrapping 的路径，不能当作全部整数运算的后端。无除法、移位、立即数和浮点。

## 检查顺序与内存

1. `INVALID`：`written` 为 NULL、未 8 字节对齐、8 字节区间回绕；out 区间回绕（空 out 可为 NULL，非空必须非 NULL）；written 的 8 字节与**完整声明的** out 重叠（包括 out 未使用的尾部）。
2. `INVALID`：operation > 5，或 destination/source > 15（即使 out 容量为 0 也先报 INVALID）。
3. `CAPACITY`：行长大于 `out.len`。

行先在 16 字节局部缓冲区中组装（最长 `imul r15, r15\n` 为 15 字节，长度计算不可能溢出），全部检查通过后一次复制到 out 并写 `*written`。失败不改 out 和 written 的任何字节；成功只写 `out[0..written)` 和 `*written`，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_binary_emit`。
