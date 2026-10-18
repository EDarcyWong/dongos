# bootstrap.nasm_checked_add_sub：64 位加减溢出分支发射

```text
module bootstrap.nasm_checked_add_sub;
import bootstrap.decimal_integer as dec;   // 已集成 CR4，块号十进制
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const ADD:u64=0; pub const SUB:u64=1; pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(operation:u64, signed:bool, destination:u64, source:u64, trap_block:u64,
 out:[]u8, written:*usize)u64
```

成功时 out 前缀恰好两行 ASCII：

```text
add|sub <dest64>, <src64>
jo __dong_b<trap_block>      ; signed：有符号溢出（OF）
jc __dong_b<trap_block>      ; unsigned：进位/借位（CF）
```

- 块号用 CR4 `decimal_integer.encode(trap_block,64,false,…)` 在局部暂存区编码，标签形式与已集成 CR10 的 `__dong_b<十进制>` 一致。trap_block 允许 0..usize最大−1，NONE 非法。
- trap 标签不由本组件定义，由上游拥有唯一块号并提供处理块。算术与条件跳转之间不插入任何指令。支持 dest==source；只改 dest 和 flags。
- 只处理 64 位整数加减的机器溢出分支，不含乘法、窄值、浮点，也不等于完整 panic 处理；与 C23 的显式 wrapping 组件分开维护。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：operation > 1、寄存器 > 15、trap_block == NONE（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 64 字节局部缓冲区组装（最长 45 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_checked_emit`。
