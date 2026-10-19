# bootstrap.nasm_guarded_integer_divide — 除法异常门禁与商余数内核组合

```text
module bootstrap.nasm_guarded_integer_divide;
import bootstrap.nasm_division_guard as guardm;   // 已集成 C31
import bootstrap.nasm_block_emit as blockm;       // 已集成 CR18
import bootstrap.nasm_integer_divide as divm;     // 已集成 CR19
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(signed:bool, remainder:bool, zero_target:u64,
                   overflow_target:u64, success_block:u64,
                   out:[]u8, written:*usize)u64
```

严格复用 `guardm.emit(signed, zero, overflow, success)` →
`blockm.emit(kind=0, success_block)` → `divm.emit(signed, remainder)`。
顺序固定为 guard → success 标签 → divide；不重写门禁或除法，不额外
jmp/ret/section。`zero_target` / `overflow_target` 由上游定义且不得指向本
片段内部；`success_block` 由本片段定义一次。三个标签均 `!= NONE` 且两两不同。

运行时输入 RDI=被除数、RSI=除数。成功时 RAX 为商或余数；仅 RAX/RCX/RDX/flags
可变。异常路径遵从 C31（不执行除法）。

## 输出文本形状

```text
<C31 guard … ending with jmp __dong_bS>
__dong_bS:
<CR19 divide/remainder>
```

## 顺序与边界证明

- guard 段最大 197 字节（signed、四个 20 位标签）；局部 224。
- label 段最大 30 字节（`__dong_b` + 20 位 + `:\n`）；局部 32。
- divide 段最大 60 字节（unsigned remainder）；局部 64。
- 组合上界 197+30+60 = 287；最终发布证明上界 512。三段各自在局部组装完成、
  `total>out.len → CAPACITY` 通过后才一次性拷入用户 out。

## 预检顺序（INVALID 优先 CAPACITY）

1. written 非 NULL、8 对齐、完整 8 字节端点不回绕；
2. out 完整声明区间端点不回绕（空可 NULL）；
3. written 与完整 out 不重叠；
4. 三个标签均 `!= NONE` 且两两不同；
5. 依赖非 OK、或子段超出证明上界、或长度回绕 → INVALID；
6. `total>out.len` → CAPACITY。

## 范围与限制

- 只做门禁 + 标签 + 内核接线；不声称活动 IR 或完整 L3。
- 依赖闭包只读：C31、CR18、CR19 及 CR4 传递依赖。
- 无分配、无全局可变状态、无 OS 调用、不导出 C 符号。
