# bootstrap.constant_arithmetic：纯常量整数/布尔求值

对 `bootstrap.expression` 产生的表达式树，求值**无类型的纯整数/布尔表达式**。整数为任意精度，经 `bootstrap.bigint`、`bootstrap.bigint_div`（C1）、`bootstrap.bigint_bits`（C2）计算，不经 i64/u64 截断，也不套用任何目标位宽规则。这不是完整的常量语义：名称、类型转换、布局、调用等由 Codex 的语义层负责。

```text
module bootstrap.constant_arithmetic;
pub struct Value { pub kind:u64, pub negative:bool, pub used:usize }   // 24 字节，偏移 0/8/16
pub unsafe fn evaluate(source:[]const u8, tokens:[]const lexer.Token,
 nodes:[]const expression.Node, root:usize, out:[]u32, work:[]u32,
 max_depth:usize, result:*Value)u64
```

`kind=1` 整数，值为 `out` 前 `used` 个小端 u32 limb 加 `negative`；`kind=2` 布尔，false 为 `used=0`，true 为 `used=1, out[0]=1`，`negative` 恒为 false。

## 支持的形式

| 节点 | 形式 |
| --- | --- |
| `INTEGER` | 十进制、`0x`、`0b`，可含 `_`（文本取自 `source[token.start..token.end]`） |
| `BOOLEAN` | `true`、`false` |
| `UNARY` | `-x`、`~x`（整数），`!x`（布尔） |
| `BINARY` | `+ - * / %`、`& \| ^`、`<< >>`、`== != < <= > >=`、`&& \|\|` |

其余节点种类（名称、null、字符串、调用、字段、索引、切片、数组、`as`、`sizeof` 等布局、结构体字面量、`try`、`orelse`、`error.X`）以及一元 `&`、`*` 返回 `UNSUPPORTED`。

## 语义

- `/` 向零截断，`%` 与被除数同号（C1）。`~`、`& | ^`、`>>` 为无限补码语义，负数右移向负无穷取整（C2）。
- 算术与位运算只接受整数；`&& ||` 只接受布尔；比较两边种类必须相同，布尔只允许 `== !=`。违反为 `TYPE`。
- 移位数必须是可表示为 usize 的非负整数，否则 `SHIFT`。零左移任意量为 0；非零的巨大左移在预留工作区时返回 `WORKSPACE`，不构造巨大值，也不循环。
- `false && r`、`true || r` 不求值 `r`：`r` 中的 `DIVZERO`、`SHIFT`、`WORKSPACE` 不会泄漏。但 `r` 仍要通过结构检查（INVALID/DEPTH）和静态类型检查（UNSUPPORTED/TYPE）。这个子语言的种类不依赖值就能确定，所以 `false && (1 + true)` 与编译器一样报 `TYPE`。

## 状态与顺序

公开状态：`OK=0`、`INVALID=1`、`CAPACITY=2`、`WORKSPACE=3`、`DIVZERO=4`、`TYPE=5`、`SHIFT=6`、`UNSUPPORTED=7`、`DEPTH=8`。

1. 描述符：`max_depth` 必须在 1..256；`result` 非空且 8 字节对齐；tokens、nodes 8 字节对齐，`out`/`work` 4 字节对齐；长度乘法和端点不溢出；`root < nodes.len`。三个输出区间（out、work、result）彼此不重叠，也不与 source/tokens/nodes 重叠，输入之间可以重叠，空视图可为 NULL。违反为 `INVALID`。
2. 结构遍历（只读）：深度从根算 1，超过 `max_depth` 为 `DEPTH`。节点和 token 索引越界、token 种类与节点不符（INTEGER 要 INTEGER token 且区间在 source 内，BOOLEAN 要 true/false，UNARY/BINARY 的 op 必须等于其 token 的种类、BINARY 的 op 必须是上表运算符）为 `INVALID`。树的布局必须与自举解析器的输出一致：每个节点排在它所有操作数子树之后，左子树整体排在右子树之前。因此子树索引区间互不相交，共享节点和环一律 `INVALID`，遍历是线性的。不支持的节点种类在这一遍不展开。
3. 种类遍历（只读，从左到右深度优先）：报告遇到的第一个 `UNSUPPORTED` 或 `TYPE`。
4. 求值：按求值顺序报告遇到的第一个 `DIVZERO`、`SHIFT`、`WORKSPACE`。在同一节点内，零除数和非法移位数先于工作区检查。
5. 发布：结果 limb 数超过 `out.len` 为 `CAPACITY`。

存储：前三步失败（INVALID、DEPTH、UNSUPPORTED、TYPE）不改变任何存储，`work` 也不变。`DIVZERO`、`SHIFT`、`WORKSPACE`、`CAPACITY` 可能改变 `work`，但 `out` 和整个 Value 不变。成功只写 `out[0..used)` 和 Value，`out` 尾部不变。所有输入只读，可以放在只读页上。

## 工作区

求值把每个中间值放在 `work` 里，像栈一样向上增长：节点 `x` 在偏移 `base` 处求值，结果留在 `work[base..base+u(x))`，其中 `u(x)` 是该值的 limb 数（布尔 true 为 1，false/0 为 0）。每一步按下表检查“从某起点再预留 n 个 limb”，只要 `start+n <= work.len` 就继续，否则返回 `WORKSPACE`：

| 节点 | 预留（在求值子节点之后） |
| --- | --- |
| 整数字面量，文本长 L | `base + 2*(L/8+1)`（字面量 limb 数不超过 L/8+1，`big.parse` 的输出与暂存各一份） |
| `true`；结果为 true 的 `!`、比较 | `base + 1` |
| `-x`、`false`、结果为 false 的 `!`/比较 | 无 |
| `~x` | `base + u(x) + 2*(u(x)+1)` |
| `a && b`、`a \|\| b` | 左右都在 `base` 处求值，无额外预留 |
| 其它二元：左在 `base`，右在 `base+u(a)`，记 `at = base+u(a)+u(b)`，`m=max(u(a),u(b))` | |
| `+ - & \| ^` | `at + 2*(m+1)` |
| `*` | `at + 2*(u(a)+u(b))` |
| `/ %` | `at + u(a) + 2*u(a) + 2` |
| `<<`，移位数 k，`a≠0` | `at + 2*(u(a) + k/32 + 1)` |
| `<<`，`a=0` | `at` |
| `>>` | `at + 2*u(a) + 1` |

所需 `work.len` 就是整棵树求值过程中上述各项的最大值（只计实际求值的分支）。这是精确值：给这么多一定成功，少一个就在最高点返回 `WORKSPACE`，测试对 100 棵随机树逐一验证了这个边界。由于 `u(a·b) <= u(a)+u(b)` 等关系都可由子树逐级推出，调用方可以按同样的递推，用各字面量的长度给出静态上界；含 `<<` 时上界还取决于移位数。

所有加法都在预留检查前确认不会回绕：`work.len <= 2^62`，左移的 `k/32 < 2^59`。

输出所需容量就是结果的 limb 数。

## 复杂度与限制

- 递归深度不超过 `max_depth <= 256`；结构遍历 O(节点数)，求值的代价由 C1/C2 与 bigint 的各运算决定。
- 不分配、无全局可变状态、无宿主求值调用、无 OS 依赖，不依赖 DeepSeek 的 arena。
- 只读使用 `bootstrap.lexer`、`bootstrap.expression`（使用时 SHA256 见交付记录）的公开 Token/Node 编号与字段；公共 AST 若变动，以其公开定义为准。
- 模块本身不导出 C 符号；测试通过临时 wrapper 导出 `dong_const_eval`。
