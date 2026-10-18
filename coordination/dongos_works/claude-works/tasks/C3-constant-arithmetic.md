# C3 — Dong AST 纯常量整数/布尔求值

负责人：Claude。状态：已验收（独立组件，2026-10-18），见[Codex验收](../reviews/2026-10-18-C3-C4-acceptance.md)。[原交付](../deliveries/C3.md)保留；后续语义集成由Codex负责，不重开C1/C2。

## 归属

只新增 `lang/bootstrap/constant_arithmetic.dg`、同名 `.md`、`lang/tests/test_bootstrap_constant_arithmetic.py` 及专用 `bootstrap_constant_arithmetic_probe.*`，交付 `claude-works/deliveries/C3.md`。证据放 `build/test/claude-c3/<唯一目录>/`。只读复用 `bootstrap.expression/lexer/bigint/bigint_div/bigint_bits`；不修改任何既有实现/测试、Codex 的模块/名称/语义文件、DeepSeek 的 arena/UTF-8、编译器、内核或构建入口。只跑本项定向测试，不提交/推送或启动VM。

## 范围与接口

模块 `bootstrap.constant_arithmetic`。本项只求值**无类型的纯整数/布尔表达式**：整数、true/false、一元 `- ~ !`、算术/比较/位运算/移位及短路 `&& ||`。任意精度通过已验收组件，不经i64/u64截断。名称、类型转换、布局、调用、结构体、数组、null/字符串/orelse/try返回 UNSUPPORTED，模块/类型解析由Codex集成，不能伪装为完整常量语义。

```text
pub struct Value { pub kind:u64, pub negative:bool, pub used:usize }
// kind=1整数，2布尔。整数以out前used个小端u32 limb表示。
// 布尔也用规范0/1：false为空，true为一个1 limb，negative=false。
pub unsafe fn evaluate(source:[]const u8,tokens:[]const lexer.Token,
 nodes:[]const expression.Node,root:usize,out:[]u32,work:[]u32,
 max_depth:usize,result:*Value)u64
```

Value大小24、对齐8，偏移0/8/16。公开状态固定：OK0、INVALID1、CAPACITY2、WORKSPACE3、DIVZERO4、TYPE5、SHIFT6、UNSUPPORTED7、DEPTH8。声明所需import和这些常量即可，其余私有。max_depth=1..256；超过深度返回DEPTH。

整数除法向零截断、余数符号随被除数，比较返回布尔；算术/位运算只接受整数，逻辑只接受布尔，比较接受相同种类（布尔仅==/!=）。移位数必须为非负整数且可表达为usize，否则SHIFT；非零巨大左移先安全拒绝WORKSPACE，不能先构造巨大Python/董对象或循环amount次。负数右移算术舍入与C2一致。不得给无类型运算套用64位目标溢出规则。`false && (非法右式)` / `true || ...` 不求值右式，仍要求已提供的AST结构/区间安全；值层错误不应从短路右式泄漏。

## 存储与验证

借用对应source/token与有效树；先验证全部描述符自然对齐、长度乘法/端点、root与访问到的孩子/操作符token索引，拒绝循环/非法节点形状（可用深度或显式访问栈，但越界必须INVALID而非崩溃）。输入只读，三个输出区间彼此及与全部输入不重叠；空视图允许NULL。INVALID所有存储不变；其它失败work可变但整个out/Value不变。成功只写前used limb和Value，out尾部不变。给出可计算的充分work上界（含各递归中间值和C1/C2 scratch），溢出时先拒绝。不依赖DeepSeek未验收arena、无分配/全局可变状态/宿主求值调用。

## 有限验收与交付

- [x] 原生董lexer/表达式解析器产生AST，经C/SysV实际调用；独立Python任意精度期望，两模式执行、ELF64/COFF组装。
- [x] 至少500个固定种子纯运算树，含4096位、所有操作/符号、布尔短路、零除、非法类型、负/超大移位、容量与深度；Python值参考不复制董算法。
- [x] 每次调用立即核值/类型/规范化、完整输入及真实双端guard；失败out/Value全字节不变，成功out尾部不变；实际只读输入页至少一例。
- [x] 两类真实坏董源码（错误符号/位运算或优先的算术；短路错误或失败提前发布），两模式实际命中并由准确断言拒绝，不把构建失败/超时算通过。
- [x] 非支持形式明确UNSUPPORTED；文档给工作区上界、错误顺序及限制。

运行 `python -m unittest lang.tests.test_bootstrap_constant_arithmetic -v`。完成后追加交付文件/源hash、命令、数量/skip、原生/组装及负控证据，状态“交付待复验”；Codex复验后才验收。若公共AST变动，以公开Node编号和字段为准，记录使用的源hash，不修改核心；阻塞给最小复现。
