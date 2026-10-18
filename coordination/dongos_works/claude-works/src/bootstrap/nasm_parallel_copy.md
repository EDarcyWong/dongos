# bootstrap.nasm_parallel_copy：复用消环规划的 8 槽 GPR 并行复制发射

```text
module bootstrap.nasm_parallel_copy;
import bootstrap.parallel_moves as pm;        // 已集成 C9
import bootstrap.nasm_integer_cast as cast;   // 已集成 CR14
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const SLOTS:usize=8;
pub unsafe fn emit(moves:[]const pm.Move, out:[]u8, written:*usize)u64
```

固定 8 个值槽依次为 `[rax, rcx, rdx, rsi, rdi, r8, r9, r10]`；Move.dst/src 是槽号 0..7，不是全局寄存器编号。临时槽 8 固定映射到 R11，不能出现在输入中；RSP/RBP/被调用者保存寄存器不在映射内。

- 调用 C9 `schedule(moves, 8, 局部 Move[16], 局部 work[8], &used)` 得到确定的顺序（不重写消环算法），对每一步调用 CR14 `nasm_integer_cast.emit(destreg, srcreg, 64, false, …)` 得到 `mov <dst>, <src>\n`，按顺序精确拼接，不加标签或其它文本。
- 最多 8 个输入；重复 dst（含重复的自复制）INVALID，重复 src 合法，自复制按 C9 消除。空输入或全为自复制时 OK，written=0，不写 out。
- 执行后有 dst 的值槽按并行语义更新；R11 的最终值不作规定；其它 GPR 与 flags 不变。

## 长度证明

C9 保证输出步数 `used ≤ 2*moves.len ≤ 16`；更精确地，步数 = 非自复制移动数 + 非平凡环数 ≤ 8 + 4 = 12。每行最长为 `mov r10, r11\n` = 4+3+2+3+1 = 13 字节。局部文本缓冲区取 256 字节，覆盖 C9 通式上界 16×13 = 208（实际最多 12×13 = 156）；拼接时仍逐行检查 `n ≤ 256 − at`，因此不会越界。

## 检查顺序与内存

1. `INVALID`（描述符）：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；moves 长度乘法溢出、区间回绕、非空却为 NULL 或未 8 字节对齐；out 区间回绕；written 与完整 out、moves 与完整 out、moves 与 written 任一重叠。
2. `INVALID`（数据）：moves.len > 8；C9 拒绝（槽号 ≥ 8、重复 dst）。
3. `CAPACITY`：总长大于 out.len。

C9 与 CR14 的调用以及总长检查都在局部完成后，才一次写入 out 和 `*written`；任何失败不改 out、written 和输入。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_pcopy_emit`（另导出 C9 schedule 供测试对照顺序）。
