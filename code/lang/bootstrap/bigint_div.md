# bootstrap.bigint_div：任意精度有符号除法与余数

编译器内部使用的任意精度整数除法组件，建立在 `bootstrap.bigint` 的表示与存储契约上。只有一个公开函数，其余均为私有。

```text
module bootstrap.bigint_div;
import bootstrap.bigint as big;
pub const DIV:u64=1;
pub const REM:u64=2;
pub const DIVZERO:u64=5;
pub unsafe fn calculate(operation:u64, negative_a:bool, a:[]const u32,
 negative_b:bool, b:[]const u32, out:[]u32, work:[]u32, result:*big.Result)u64
```

## 语义

- `DIV`：商向零截断，例如 `-7/2=-3`、`7/-2=-3`。
- `REM`：满足 `a=q*b+r`、`|r|<|b|`，非零余数与被除数同号，例如 `-7%2=-1`、`7%-2=1`。
- 与 `lang/dongc/model.py` 的 `integer_div` 一致；Python 的 `//`、`%` 向负无穷取整，不能直接作为参考。
- 零结果总是 `negative=false, used=0`。
- 零除数返回 `DIVZERO`，此时尚未执行任何除法指令，不会触发 CPU #DE 或 panic。
- 不施加目标位宽规则（例如 i64 的 `MIN/-1`），该检查由语义层负责。

## 状态与优先顺序

| 状态 | 值 | 含义 |
| --- | --- | --- |
| `big.OK` | 0 | 成功 |
| `big.INVALID` | 1 | 非法 opcode、描述符违规或非规范输入（负零、冗余高零） |
| `big.CAPACITY` | 2 | `out` 容量不足 |
| `big.WORKSPACE` | 3 | `work` 容量不足 |
| `DIVZERO` | 5 | 除数为零（模块局部） |

检查顺序固定为：opcode 与描述符 → 规范表示 → 零除数 → 工作区 → 输出容量。因此非规范的负零除数报 `INVALID` 而非 `DIVZERO`；工作区和输出同时不足时报 `WORKSPACE`。

## 存储契约

与 `bootstrap.bigint` 相同：

- 指针非空（空切片可为 NULL）、自然对齐（limb 4 字节、Result 8 字节），`len*4` 和区间端点不溢出。
- 两个输入可以相互重叠；`out`、`work`、`result` 与彼此及任一输入的整个声明区间都不得重叠。
- `INVALID` 不改变任何存储。`DIVZERO`、`WORKSPACE`、`CAPACITY` 不改变 `out` 和整个 Result（当前实现在 `DIVZERO` 与 `WORKSPACE` 时也不写 `work`，但调用方不应依赖）。
- 成功只写 `out[0..used)` 和 Result，`out` 尾部不变；输入及各区间以外字节不变。

## 工作区（精确所需 limb 数）

记 `m=a.len`、`n=b.len`（规范输入，`n>=1`）。实现检查的就是下表，`work.len` 达到即可，少一个即返回 `WORKSPACE`：

| 情形 | DIV | REM |
| --- | --- | --- |
| `a=0` | 0 | 0 |
| `\|a\|<\|b\|` | 0 | m |
| `\|a\|=\|b\|` | 1 | 0 |
| `\|a\|>\|b\|`，`n=1` | m | m |
| `\|a\|>\|b\|`，`n>=2` | 2m+2 | 2m+2 |

可计算的统一充分上界：`work.len >= 2*a.len + 2`。因 `a.len <= 2^62`，该式不会溢出。

输出所需容量：DIV 至多 `m-n+1` limb，REM 至多 `n` limb；`out.len >= a.len` 对两种操作总是充分。

## 算法

- 单 limb 除数：从高到低逐 limb 做 64/32 位除法，余数始终小于除数，商 limb 不溢出。
- 多 limb 除数：Knuth TAOCP 4.3.1 Algorithm D。先左移使除数最高 limb 最高位为 1，按 limb 估商、用次高 limb 修正、乘减，借位时回加一次，最后右移还原余数。
- `work` 布局（`n>=2`）：`[0,m+1)` 规范化被除数/余数，`[m+1,m+1+n)` 规范化除数，`[m+1+n,2m+2)` 商。
- 循环次数只取决于 limb 数（O(m·n)），不按商值重复相减。所有中间乘积都在 u64 范围内，debug 模式不会溢出 panic。

## 限制

- 只处理规范符号/幅值表示；不探测宿主页权限，调用方须保证描述的内存可访问。
- 不分配、无全局可变状态、无宿主算术调用、无 OS 依赖。
- 模块本身不导出 C 符号；测试通过临时 wrapper 导出 `dong_big_div`。
