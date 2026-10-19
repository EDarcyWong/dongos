# bootstrap.nasm_memmove：聚合赋值的 overlap-safe memmove 发射

```text
module bootstrap.nasm_memmove;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(forward_block:u64, end_block:u64, out:[]u8, written:*usize)u64
```

依赖已集成 `bootstrap.decimal_integer`（CR4）。`forward_block` 与 `end_block` 必须不同且均非 `NONE`；本组件在输出中**定义** `__dong_b<F>` / `__dong_b<E>`，调用方须全局唯一保留这两个编号。

固定运行时：`RDI`=dst、`RSI`=src、`RCX`=count，入口 `DF=0`。允许任意重叠；是非重叠 COPY 的必要补充。`count==0` 允许 NULL 指针，不访问内存、不计算倒退地址。

精确文本（F/E 为 CR4 规范十进制）：

```text
test rcx, rcx
jz __dong_b<E>
cmp rdi, rsi
jbe __dong_b<F>
lea rsi, [rsi + rcx - 1]
lea rdi, [rdi + rcx - 1]
std
rep movsb
cld
jmp __dong_b<E>
__dong_b<F>:
rep movsb
__dong_b<E>:
```

- count0：RDI/RSI/RCX 保持；非零且 dst≤src：前拷贝，指针各前进 count，RCX=0；dst>src：反拷贝，指针各为原地址−1，RCX=0。
- 所有出口 DF=0。只 RDI/RSI/RCX 与 flags 可变；RAX 及其它 GPR 保持。
- 无 call/libc。最大块号 20 位时最长 263 字节；512 字节局部 scratch，不可只用 256。

## 检查顺序与内存

1. `INVALID`：written NULL/未 8 对齐/8 字节回绕；out 区间回绕；written 与完整 out 重叠。
2. `INVALID`：块号为 NONE 或两者相同（容量为 0 时也先 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

失败不改 out/`*written`；成功只写精确前缀。无分配、无全局可变状态、无 OS 调用；不导出 C 符号（测试 wrapper 可导出）。

## 原生观察契约（R1）

主原生使用正式 Dong 实际产出。精确断言 count0 指针保持、前向入口+count、反向入口-1（仅整数比较）。观察 RAX/RDX/R8–R10/R12–R15；观察器地址保存在 callee-saved RBX。负控含精确指针终值坏 Dong；好坏两侧实际产出与相同输入。
