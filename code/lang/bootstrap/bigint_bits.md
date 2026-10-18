# bootstrap.bigint_bits：任意精度位运算与移位

编译器内部使用的任意精度位运算组件，建立在 `bootstrap.bigint` 的表示与存储契约上。接口值始终是规范符号/幅值；运算结果与 Python 无限符号扩展的补码整数 `& | ^ ~ << >>` 一致。

```text
module bootstrap.bigint_bits;
import bootstrap.bigint as big;
pub const AND:u64=1;
pub const OR:u64=2;
pub const XOR:u64=3;
pub unsafe fn bitwise(operation:u64, negative_a:bool, a:[]const u32,
 negative_b:bool, b:[]const u32, out:[]u32, work:[]u32, result:*big.Result)u64
pub unsafe fn invert(negative:bool, a:[]const u32,
 out:[]u32, work:[]u32, result:*big.Result)u64
pub unsafe fn shift(left:bool, negative:bool, a:[]const u32, amount:usize,
 out:[]u32, work:[]u32, result:*big.Result)u64
```

## 语义

- `bitwise`：在宽度 `W=max(a.len,b.len)+1` limb 上逐 limb 求两个操作数的补码（负数为 `~|x|+1`，进位逐 limb 传递），按位运算后若结果为负再取补得到幅值。多出的一个 limb 保证符号扩展足够：两输入都在 `[-2^(32L), 2^(32L))` 内，结果也在该范围内，幅值至多 `2^(32L)`，正好放进 W 个 limb。结果符号由输入符号直接得出：AND 为两者皆负，OR 为任一为负，XOR 为两者不同。
- `invert`：`~x=-x-1`。非负数得 `-(x+1)`，负数得 `|x|-1`。例如 `~0=-1`、`~-1=0`。不是对幅值逐 limb 取反。
- `shift(left=true)`：精确数学左移 `x*2^amount`，符号不变；零左移任意量仍为零。
- `shift(left=false)`：算术右移，向负无穷取整。负数在被丢弃位非零时幅值加一，例如 `-4>>1=-2`、`-3>>1=-2`；移位量超过有效位数时非负数得 0、负数得 -1。
- `amount` 是任意 `usize`，包括 `usize` 最大值。组件不施加目标位宽或移位次数规则，这由语义层负责。

## 状态与优先顺序

使用 `big.OK=0`、`big.INVALID=1`、`big.CAPACITY=2`、`big.WORKSPACE=3`，无模块局部状态。

检查顺序：opcode（仅 bitwise）与描述符 → 规范表示 → 工作区 → 输出容量。`invert` 和 `shift` 只有一个输入，描述符检查按单输入进行。因此非规范输入配合巨大左移量报 `INVALID`，不报 `WORKSPACE`。

## 存储契约

与 `bootstrap.bigint` 相同：非空指针（空切片可为 NULL）、自然对齐、`len*4` 与端点不溢出；输入可相互重叠，`out`、`work`、`result` 与彼此及任一输入的整个声明区间不得重叠。`INVALID` 不改变任何存储；`WORKSPACE`、`CAPACITY` 不改变 `out` 和整个 Result；成功只写 `out[0..used)` 和 Result。

## 工作区（精确所需 limb 数）

实现检查的就是下表，达到即可，少一个即返回 `WORKSPACE`。记 `n=a.len`，`q=amount/32`。

| 操作 | 所需 `work.len` |
| --- | --- |
| `bitwise` | `max(a.len,b.len)+1`（零结果同样要求） |
| `invert` | `n+1` |
| `shift`，`a=0` | 0 |
| 左移 | `n+q+1` |
| 右移，非负，`q<n` | `n-q` |
| 右移，非负，`q>=n` | 0 |
| 右移，负，`q<n` | `n-q+1` |
| 右移，负，`q>=n` | 1 |

可计算的统一充分上界：位运算与取反为 `max(a.len,b.len)+1`；右移为 `a.len+1`；左移为 `a.len+amount/32+1`。

### 极大移位

`a.len<=2^62`，`q<=(2^64-1)/32<2^59`，所以 `n+q+1` 在 u64 内不会回绕，可以直接与 `work.len` 比较。`work.len` 本身受 `MAX/4` 限制，超大左移在比较处即返回 `WORKSPACE`，不会进入循环。右移的 `q>=n` 分支不循环。所有循环只按 limb 数（`n`、或已通过工作区检查的 `n+q+1`）进行，不按移位量逐位循环，也不先计算 `amount+bits`。

输出所需容量就是结果 limb 数；对 `bitwise`/`invert`/右移，`work` 的上表需求同时也是充分的输出容量。

## 限制

- 只处理规范符号/幅值表示；不探测宿主页权限。
- 不分配、无全局可变状态、无宿主算术调用、无 OS 依赖。
- 模块本身不导出 C 符号；测试通过临时 wrapper 导出 `dong_big_bitwise`、`dong_big_invert`、`dong_big_shift`。
