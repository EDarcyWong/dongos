# bootstrap.u64_expression_ir：原生表达式 AST 降为 C48 的受限 u64 直线 IR（C51）

把真正的 Dong lexer + `bootstrap.expression` 解析出的树，转换成已集成的 `bootstrap.nasm_u64_function.Instruction`。只覆盖显式模 2^64 的 u64 测试后端子集，不冒充一般 Dong 源码的默认受检算术或完整类型检查，也不是完整 IR、自举或 L3 完成。它不重写词法/语法/大整数/整函数发射，只做校验和转换。

```text
module bootstrap.u64_expression_ir;
import bootstrap.lexer as lex;                 // 现有原生前端（只读基线）
import bootstrap.expression as ast;            // 同上
import bootstrap.bigint as bi;                 // 同上，字面量解析
import bootstrap.nasm_u64_function as f;       // 已集成 C48
pub const OK:u64=0; INVALID=1; CAPACITY=2; UNSUPPORTED=3;
pub struct Result{pub instruction_count:usize,pub slot_count:usize,pub return_slot:usize}   // 24 字节，8 对齐
pub unsafe fn lower(source:[]const u8, tokens:[]const lex.Token, nodes:[]const ast.Node, root:usize,
                    parameter_tokens:[]const usize, out:[]f.Instruction, result:*Result)u64
```

`nodes` 只是该表达式的已用树，所有索引相对这个切片；`tokens`/`source` 是完整只读 token 流。`parameter_tokens` 的顺序定义参数槽 0..p-1，每项指向一个 IDENTIFIER token（可在完整函数签名里，表达式从 `return` 之后解析，所以不需要伪造 AST）。

## 校验顺序（任何一步失败都不写 out 和 Result）

1. **描述符**（INVALID）：`result` 非 NULL、8 对齐、端点不回绕；`source ≤ 4096`、`tokens 1..256`、`nodes 1..24`、参数 `0..6`、`out.len*40` 不溢出（数量先于乘法，非法数量不读正文）；每个切片非空时非 NULL、端点不回绕，tokens/nodes/参数/out 自然 8 对齐；输入之间可任意重叠，`out` 与 `result` 同每个完整输入（含未消费的尾部）及彼此都不得重叠；`root < nodes.len`。
2. **token 流**（INVALID）：`start ≤ end ≤ source.len`、单调不交叠，EOF 只出现在最后一个 token。
3. **索引**（INVALID）：每个 `node.token < tokens.len`；每个参数 token 在范围内、种类为 IDENTIFIER、拼写非空，且各参数字节名两两不同。
4. **UNSUPPORTED**：任何节点的 kind 不是 INTEGER/NAME/BINARY，或 BINARY 的 operator 不在 `+ - * & | ^`。这一步发生在安全的描述符/索引检查之后、形状检查之前，只看 kind 和 operator，不声称验证复杂子树。unary、call、cast、bool、比较、除法、移位、`orelse`、字段、索引、字符串、数组等一律 UNSUPPORTED，不折叠成受支持树。
5. **形状**（INVALID）：所有 `next = NONE`、`flags ∈ {0,1}`（只允许括号位）。INTEGER：`op=0`、`a=b=c=NONE`、token 为 INTEGER 且拼写 1..256 字节，**必须**经 `bi.parse` 解析（复用十进制/`0x`/`0b`/下划线规则；2 个输出 limb、32 个工作 limb），非法、超出 u64 一律 INVALID，不截断。NAME：`op=0`、`a=b=c=NONE`、token 为 IDENTIFIER，且拼写等于某个参数（槽号即参数序号），否则 INVALID。BINARY：`a`、`b` 是节点范围内的孩子，`c=NONE`，`node.op` 等于其 token 的 kind，且 token 拼写恰是该单字符（`+`=1067、`-`=1069、`*`=1066、`&`=1062、`|`=1148、`^`=1118）。
6. **树**（INVALID）：从 root 做带显式栈（最多 24 项）的遍历，每个节点恰被访问一次，因此环、共享孩子、多父、不可达节点都被拒绝，不会无限递归。
7. **容量**：`out.len < 非 NAME 节点数` 返回 CAPACITY。INVALID/UNSUPPORTED 总是先于它。

## 降级

后序：左子树 → 右子树 → 父。NAME 直接引用其参数槽，不发指令；每个 INTEGER 分配一个新槽并发 `CONST`（left=right=0）；每个 BINARY 在两个源都已生成后分配新槽，并通过显式映射（不是按字符值推算）发 `ADD/SUB/IMUL/AND/OR/XOR`（immediate=0）。新槽从 p 开始，不重用、不折叠。`instruction_count` 是非 NAME 节点数（≤ 24，实际受 23 个节点的奇数树限制），`slot_count = max(1, p + instruction_count)`（≤ 30），`return_slot` 是 root 对应的槽。

## 内存与发布

不分配、无全局状态、无 OS 调用，不导出 C 符号（测试 wrapper 导出）。局部数组只有：`values[24]`（192 字节）、`slot_of[24]`（192）、2 个 u32 limb、32 个 u32 工作 limb（128）、一个 bigint `Result`、遍历用的 `stack[24]`（192）和 `state[24]`；`tree_ok` 里再有 `visited/stack/state`（约 240）。合计远小于 dongc 的 4096 字节最坏栈帧限制，debug/release 都能编译。没有 24 条 Instruction 的局部副本：所有检查（包括字面量解析）全部完成并确认容量足够后，才第一次写 `out`，然后写 `*result`；所以任何失败都不改变 `out`、`*result` 和输入。

## 测试（`claude-works/tests/test_u64_expression_ir.py`）

- 只暂存：生产模块、现有基线（lexer/unicode/expression/bigint）和已集成 C48 的完整只读闭包，共 18 个文件；debug/release 都实际编译、链接、原生执行，生产汇编与桩组装成 ELF64 与 COFF(win64)。
- 全程走真实管线：真实 lexer → 真实 `expression.parse`（从 `return` 后第一个 token 起）→ 本 `lower` → 已集成 C48 `emit` → 汇编 → 手写 SysV 桥真实 `call/ret`。签名参数 token 和表达式起点由 Python 从真实 lexer 的 token 流里定位；期望值由独立的 Python 表达式分词/解析（优先级 `|`<`^`<`&`<`+ -`<`*`、均左结合）、IR 展开和 u64 求值给出，文本由独立 C48 文本模型核对，不拿生产输出当唯一 oracle，也不在 Python 里构造 IR 代替 lower。
- 20 个夹具（≤ 24）：0/1/6 参数、单 NAME、单常量、左右不交换的 SUB（两个方向）、嵌套优先级与括号、重复参数读取、六种运算、0/UINT64_MAX/高位、乘加环绕、十进制/十六进制/二进制及下划线、1 字节和 64 字节名字，以及 23 个节点的最大树（17 条指令、23 槽）。
- 精确容量/短 1/0/富余尾部，out 与 Result 带 guard；失败时整个 out 和整个 Result 保持不变。语法错误只在 parser 阶段失败（单独观察，lower 不运行）。
- 23 个 UNSUPPORTED 表达式、8 个 INVALID 表达式（未知名字、重复参数、超大/超范围字面量、257 位字面量、节点过多）、参数 token 为非标识符/越界/EOF，全部经真实 parser。
- 31 条手工破坏 INVALID（节点/参数 token 越界、孩子越界、自环、共享孩子、不可达节点、`next`/`flags`/`op`/`a`/`b`/`c` 非法、token 种类/运算符/拼写不匹配、字面量拼写损坏、token 流缺 EOF/EOF 居中/start>end/end 越界/重叠、root 越界、参数重复/越界/过多、节点>24、token>256、source>4097）与 4 条 UNSUPPORTED（含"UNSUPPORTED 先于后续形状错误"），不执行它们产生的任何机器码。
- 34 个描述符/端点/尾部别名预检（用真实 lexer/parser 产生的基线）各自独立可达，Result 端点溢出用 8 对齐的 `UINT64_MAX-23`；真实只读页输入（检查保护调用成功）。
- 真实坏 Dong：SUB 两个源交换（同输入先跑好侧并原生执行，坏侧正常返回后按 RAX 拒绝）；未知 NAME 被映射到合法参数槽（只用有安全参数槽的夹具，按 INVALID 状态拒绝）；容量不足时先写一条 IR / 先写 Result（按 lower 的原子性 guard 拒绝）；已集成 C48 的坏副本在 `ret` 前插入 `add rbx, 8`（观察桥用独立静态观察地址与宿主栈锚，RBX 预设已知值，正常返回后只按 RBX 数值拒绝）；去掉别名检查（只让预检 24..33 失败）。
