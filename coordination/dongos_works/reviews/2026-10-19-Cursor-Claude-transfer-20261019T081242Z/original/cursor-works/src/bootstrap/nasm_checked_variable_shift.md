# bootstrap.nasm_checked_variable_shift — 完整 RCX 计数门禁后的 64 位可变移位

```text
module bootstrap.nasm_checked_variable_shift;
import bootstrap.nasm_shift_guard as guardm;       // 已集成 CR21
import bootstrap.nasm_variable_shift as shiftm;    // 已集成 C26
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub const SHL:u64=0; pub const SHR:u64=1; pub const SAR:u64=2;
pub unsafe fn emit(operation:u64, destination:u64, trap_block:u64, out:[]u8, written:*usize)u64
```

严格复用 `guardm.emit(count=1, width=64, trap_block)`（完整比较 RCX）再
`shiftm.emit(operation, destination)`（`shl|shr|sar <dest>, cl`）。固定 64 位
wrapping 移位：只检查计数 `< 64`，不宣称检查左移算术溢出或窄整数。比较使用
完整 64 位 RCX，不得只看 CL；`destination == RCX` 合法，比较与移位均使用原始
计数。成功落空时只改目标寄存器与 flags；trap 路径保持全部 GPR；除非目标是
RCX，否则不改 RCX。

## 输出文本

```text
cmp rcx, 64
jae __dong_b<trap_block>
shl|shr|sar <dest64>, cl
```

## 顺序与边界证明

- guard 段最大 45 字节（`cmp rcx, 64\n` + `jae __dong_b` + 20 位十进制 + LF）；
  局部 64 字节缓冲覆盖之。
- shift 段最大 12 字节（`shl r15, cl\n`）；局部 16 字节缓冲覆盖之。
- 组合上界 45+12 = 57 字节；最终发布缓冲证明上界 80。两段各自在局部组装完成、
  `total>out.len → CAPACITY` 判定通过后才一次性拷入用户 out 并写 written。
  任何 INVALID/CAPACITY 下完整 out 与 written 不变。

## 预检顺序（INVALID 优先 CAPACITY）

1. written 非 NULL、8 对齐、完整 8 字节端点不回绕；
2. out 完整声明区间端点不回绕（空可 NULL）；
3. written 与完整 out（含成功未用尾部）不重叠；
4. `operation` 仅 0/1/2；`destination` 为 0..15 且禁止 rsp(4)/rbp(5)；
   `trap_block != NONE`（容量为 0 时也先 INVALID）；
5. 依赖非 OK、或子段超出证明上界、或 `glen+slen` 回绕 → INVALID；
6. `total>out.len` → CAPACITY。

## 范围与限制

- 只做完整计数门禁 + 64 位 CL 可变移位接线；不声称活动 IR 或完整 L3。
- 依赖闭包只读：CR21、C26 及 CR21 的 CR4 传递依赖。
- 无分配、无全局可变状态、无 OS 调用、不导出 C 符号（临时测试 wrapper 可导出）。
