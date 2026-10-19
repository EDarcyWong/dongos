# bootstrap.nasm_checked_narrow_result — 8/16/32 位 debug 窄算术结果的组合门禁与规范化

```text
module bootstrap.nasm_checked_narrow_result;
import bootstrap.nasm_narrow_range_guard as guardm;   // 已集成 CR28
import bootstrap.nasm_integer_cast as castm;          // 已集成 CR14
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(width:u64, signed:bool, trap_block:u64, out:[]u8, written:*usize)u64
```

固定以 RAX 为尚未截窄、规范化的完整 64 位算术结果（signed 按 i64、unsigned 按 u64）。
成功时 out 前缀为严格 ASCII 的两段拼接：先 CR28 的范围门禁全部文本，再
CR14 的 `emit(destination=0, source=0, width, signed)` 规范化文本。检查作用于
完整 64 位结果，先于截窄；越界转上游安全 trap 块 `__dong_b<trap>`，未越界
落空且 RAX 变为目标统一 64 位表示。除 RAX、R11 与 flags 外其它 GPR 保持。

## 输出文本

`signed=true`（先 CR28 后 CR14）：

```text
mov r11, <min>
cmp rax, r11
jl __dong_b<N>
mov r11, <max>
cmp rax, r11
jg __dong_b<N>
<cast-line>
```

`signed=false`：

```text
mov r11, <max>
cmp rax, r11
ja __dong_b<N>
<cast-line>
```

`<cast-line>`（destination=0, source=0，经 CR14）：

| width | signed | 行 |
| --- | --- | --- |
| 8 | true | `movsx rax, al` |
| 8 | false | `movzx rax, al` |
| 16 | true | `movsx rax, ax` |
| 16 | false | `movzx rax, ax` |
| 32 | true | `movsxd rax, eax` |
| 32 | false | `mov eax, eax`（CR14 kind 5 为 dest32/src32，隐式零扩展到 RAX） |

## 顺序与边界证明

- guard 段最大 131 字节：signed i32、20 位十进制 trap 块（`mov r11, ` 10 +
  20 位 min + LF + `cmp rax, r11` 12 + LF + `jl __dong_b` 10 + 20 + LF +
  `mov r11, ` 10 + 10 位 max + LF + cmp 13 + `jg __dong_b` 10 + 20 + LF）。
  局部 guard 缓冲 256 字节覆盖之。
- cast 段最大 16 字节：`movsxd rax, eax`（7+3+2+3）+ LF。局部 cast 缓冲
  32 字节覆盖之。
- 组合文本上界 131+16 = 147 字节；两段各自在局部组装完成、容量判定
  `total>out.len → CAPACITY` 通过后才一次性拷入用户 out 并写 written。
  任何 INVALID/CAPACITY 下完整 out 与 written 不变；不存在先发布 guard
  再发现 cast 放不下的中间态。

## 预检顺序（INVALID 优先 CAPACITY）

1. written 非 NULL、8 对齐、完整 8 字节端点不回绕；
2. out 完整声明区间端点不回绕（空可 NULL）；
3. written 与完整 out（含成功未用尾部）不重叠；
4. width 只允许 8/16/32 且 trap_block 非 NONE；
5. 依赖调用返回非 OK、或子段长度超出缓冲证明上界 → INVALID；
6. `glen+clen` 回绕 → INVALID；`total>out.len` → CAPACITY。

## 范围与限制

- 只支持 debug 语义检查；不支持 release/wrapping/cast/shift 组合，
  不能补正先前已发生的 64 位机器溢出，不声称已接活动 IR 或完整 L3。
- 数字全部复用 CR4 十进制（经 CR28），本文本不新增格式化。
- 无分配、无全局可变状态、无 OS 调用、不导出 C 符号（临时测试 wrapper
  可导出）。
- 依赖闭包只读：CR28、CR14 及 CR28 的 CR4 传递依赖。
