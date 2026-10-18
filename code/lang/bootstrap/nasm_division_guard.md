# bootstrap.nasm_division_guard：固定寄存器除法异常门禁分支

```text
module bootstrap.nasm_division_guard;
import bootstrap.decimal_integer as dec;   // 已集成 CR4
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(signed:bool, zero_target:u64, overflow_target:u64, success_target:u64,
 out:[]u8, written:*usize)u64
```

运行时输入与 CR19 一致：RDI 为被除数，RSI 为除数。只把 RAX 和 flags 当作暂存，RDI/RSI 及其它寄存器保持不变。只发射除法之前的控制流门禁，不执行除法，不 panic，不实现错误码策略，不修改 CR19，也不 import CR19。

unsigned（3 行）：

```text
test rsi, rsi
jz __dong_b<zero>
jmp __dong_b<success>
```

signed（8 行）：

```text
test rsi, rsi
jz __dong_b<zero>
cmp rsi, -1
jne __dong_b<success>
mov rax, 0x8000000000000000
cmp rdi, rax
je __dong_b<overflow>
jmp __dong_b<success>
```

除数为 0 进入除零块，signed 的 MIN/-1 进入溢出块，其它进入成功块。MIN 用完整 64 位常量装入 RAX 后比较（x86 没有 `cmp r64, imm64`）。标签为 `__dong_b` + CR4 无符号十进制（无前导零）；不输出标签定义/section/global。三个目标可以相同，各块由上游定义；余数特殊规则和完整语言 lowering 不在此处。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：三个目标任一为 NONE（u64 最大值）——unsigned 时 overflow_target 虽不使用也要检查；容量为 0 时也先报 INVALID。
3. `CAPACITY`：文本长度大于 out.len。

三个十进制标签先写入局部暂存区，整段在 224 字节局部缓冲区组装。signed 长度为 `117 + digits(zero) + digits(overflow) + 2*digits(success)`（success 标签出现两次），四个 20 位标签时最长 197 字节；unsigned 最长 79 字节。224 是对所有合法输入都充分的固定界限，全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_guard_emit`。
