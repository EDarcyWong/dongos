# bootstrap.nasm_narrow_range_guard：8/16/32 位 debug 算术结果范围门禁

```text
module bootstrap.nasm_narrow_range_guard;
import bootstrap.decimal_integer as dec;   // 已集成 CR4
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(width:u64, signed:bool, trap_block:u64, out:[]u8, written:*usize)u64
```

固定以 RAX 为尚未截断/规范化的完整 64 位算术结果。成功时 out 前缀为严格 ASCII：

`signed=true`：

```text
mov r11, <min>
cmp rax, r11
jl __dong_b<N>
mov r11, <max>
cmp rax, r11
jg __dong_b<N>
```

`signed=false`：

```text
mov r11, <max>
cmp rax, r11
ja __dong_b<N>
```

## 范围与数字

| width | signed min..max | unsigned 上界 |
| --- | --- | --- |
| 8 | −128..127 | 255 |
| 16 | −32768..32767 | 65535 |
| 32 | −2147483648..2147483647 | 4294967295 |

- 全部十进制经 CR4：`min` 以 64 位二补码 bits + `signed=true` 编码（ASCII `-`）；上界与块号用 `signed=false`。
- 上界一律先 `mov r11, …` 再 `cmp`，不用 sign-extended imm32 直接 CMP。
- `width` 仅 8/16/32；64/0/其它 → `INVALID`（优先于 `CAPACITY`）。
- `trap_block` 允许 `0..usize最大−1`，`NONE` 非法。trap 由上游定义（debug 溢出 kind2）；本组件不输出 trap 体。
- 保持 RAX 及其它 GPR；仅 R11 与 flags 可变。必须在 CR14 规范化之前接入；不补先前 64 位机器溢出；不用于 shift/cast/显式 wrapping；不改变 release 模运算契约。

## 求长与上界

局部 **256** 字节缓冲区。最长文本（signed i32、20 位块号）：

- `mov r11, -2147483648\n` = 21
- `cmp rax, r11\n` = 13
- `jl __dong_b` + 20 + `\n` = 32
- `mov r11, 2147483647\n` = 20
- `cmp rax, r11\n` = 13
- `jg __dong_b` + 20 + `\n` = 32

合计 **131** 字节。unsigned 上界模板（u32 / 20 位块号）最长 65 字节。实际长度 = 固定模板 + CR4 数字位数，先在局部求长，容量不足才 `CAPACITY`。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与完整声明 out 重叠（含未使用尾部）。
2. `INVALID`：非法 width、`trap_block == NONE`（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_narrow_range_guard_emit`。
