# Dong 原生表达式解析器

`bootstrap.expression` 接收 `bootstrap.lexer` 生成的只读 source/token 流，在调用方提供的 Node 工作区建立表达式树。运行时没有 Python、分配器、全局可变状态或宿主调用；不依赖 Claude 的大整数扩展或 DeepSeek 的 arena/UTF-8 任务。

当前覆盖整数（保留拼写、不计算值）、布尔、null、字节字符串、名字、error 路径、一元 `! ~ - & *`、try、全部二元运算、右结合 orelse、受限控制退出、括号、调用、字段、索引、切片、数组/重复数组、`as` 类型转换、结构体字面量和 sizeof/alignof/offsetof。比较链拒绝规则、括号和 postfix/二元优先级遵循现有 Python 前端。类型语法包含限定名、指针/const、切片/const、数组维度表达式、可选值、错误结果和带 ABI/unsafe/可选参数名的函数类型。

声明与语句解析通过同一有界引擎的 [bootstrap.syntax](syntax.md) 入口提供，避免两个阶段复制 token 或共享未验证的游标。**尚未实现**名称/类型检查、常量计算、代码生成和 CLI；数组长度/重复计数只构建语法树，正数、范围、目标布局与常量计算留给后续语义阶段。语法组件不能单独标记 L3 自举完成。UNSUPPORTED 仍用于当前规格明确不支持的 ABI/语法（如未知 ABI），不再用于本次已实现的三类表达式。

## 接口与内存

```text
unsafe parse(source:[]const u8, tokens:[]const lexer.Token, start:usize,
 nodes:[]Node, max_depth:usize, allow_struct:bool, result:*Result)u64
```

所有切片指向调用者实际拥有、可访问的存储。函数检查非空指针、自然对齐、长度乘法/端点溢出和工作区重叠；无法探测宿主地址权限。source/tokens 可相互重叠但只读；nodes/result 彼此及与两个输入的整个声明区间均不得重叠。空视图允许 NULL，tokens 必须非空。

token 范围按 source 字节偏移单调不交叠，每个 start<=end<=source.len，最后且只有最后一个 token 为 EOF。调用者使用 lexer 的已成功 token 流及其对应的原始 source；这里不重新验证 token 拼写、关键字或 UTF-8。start 必须位于 token 流内；表达式解析在第一个不属于表达式的 token 之前结束。调用者检查 Result.next 处的语句/参数分隔符，成功不代表整个输入已经消费。

max_depth 为 1..256，控制递归表达式/类型层数；不耗递归层的 postfix/左结合循环由 token 与 Node 容量约束。allow_struct=false 用于 if/while 等允许后续 `{` 块的上下文；括号和实参内部与现有前端一样恢复普通表达式规则。结构体字面量只允许名字/限定名作为构造目标，保留字段的原始次序；类型和重复字段是否合法由后续语义检查决定。

## AST 布局

Node 是 8 个 u64/usize 字段，大小64、对齐8：`kind, token, op, a, b, c, next, flags`。Result 是5个 usize/u64，大小40、对齐8：`root, used, next, error_code, error_token`。`NONE=usize最大值`，表示无孩子/空列表。所有引用是 Node 索引，token 是原流索引，整数/标识符拼写由该 token 的 source 范围借用，字符串内容仍由词法阶段的字符串 arena 提供。

| kind | 内容 |
| --- | --- |
| INTEGER/BOOLEAN/NULL/STRING/NAME | token 指向原字面量或名字，a/b/c 无 |
| UNARY/TRY | op 为原 lexer kind，a 为操作数 |
| BINARY/ORELSE | op 为原 lexer kind，a/b 为左右孩子 |
| CALL | a 为 callee，b 为实参链首，链用每个实参根节点的 next 连接 |
| FIELD | token 指向字段名，a 为对象 |
| INDEX | a 为对象，b 为索引 |
| SLICE | a 为对象，b/c 为可省略的起止表达式 |
| ARRAY | a 为元素链首，元素根的 next 连接 |
| REPEAT | a 为元素，b 为原始计数表达式（不折叠） |
| EXIT | op 为 return/break/continue 的 lexer kind，a 为可选返回值 |
| ERROR | a 为 NAME/FIELD 组成的错误名字路径 |
| CAST=18 | token 指向 as，a 为原表达式，b 为类型树 |
| STRUCT=19 | a 为名字/限定名树，b 为 INITIALIZER 链首 |
| LAYOUT=20 | token 为 sizeof/alignof/offsetof 名字，a 为类型树，op 为 offsetof 字段 token 索引或 NONE |
| INITIALIZER=21 | token 为字段名，a 为初始化表达式，next 为下一字段 |
| TYPE_NAME=32 | a 为名字/限定名树；不在运行时将 usize 等转换成目标布局 |
| TYPE_POINTER/TYPE_SLICE=33/34 | a 为元素类型，flags 位0为 const |
| TYPE_ARRAY=35 | a 为元素类型，b 为未折叠维度表达式 |
| TYPE_OPTIONAL/TYPE_ERROR=36/37 | a 为 payload 类型 |
| TYPE_FUNCTION=38 | a 为 PARAMETER 链首，b 为返回类型；op=0/1 表示 sysv64/win64，flags 位0为 unsafe |
| PARAMETER=39 | a 为类型；flags 位0表示有参数名，此时 token 指向该名字，否则指向类型起点 |

表达式节点 flags 位0表示原式被括号包围；类型/参数节点按表解释该位，其余位保留为0。next 不代表表达式孩子，只用于父节点的参数/元素/字段链。树不共享节点；调用者只在成功后遍历，从 Result.root 开始，且索引必须小于 used。

## 状态与发布

- OK=0：root 有效，used 为已建立 Node 数，next 为未消费 token 索引。只改 nodes[0..used) 和 Result，工作区尾部不变。Result.error_token 成功时无诊断含义。
- INVALID=1：参数、区间、token 结构或深度参数非法；所有输入、工作区和整个 Result 保持不变。
- SYNTAX=2、CAPACITY=3、DEPTH=4、UNSUPPORTED=5：nodes 是可被改写的工作区，Result.root 必须为 NONE，不发布可用树。used/next 描述已尝试前缀，error_token 指向诊断 token，error_code 与返回状态一致。尾部 nodes[used..len) 不变；所有输入和声明区间外字节始终不变。

源位置通过 error_token 的 lexer line/column/start 获得；例如空数组定位到 `[`，比较链定位到第二个比较运算符。先完成参数校验，才开始改写工作区。nodes 是语法阶段工作区，不应当作失败保持不变的最终产物。

## 复验

`python -m unittest lang.tests.test_bootstrap_expression -v` 用实际 Dong lexer→parser、C/SysV 原生探针与 Python Parser 的独立 AST 比较；包含确定种子的生成树、真实模块表达式、语法错误位置、精确/不足工作区、深度、只读输入、元数据/缓冲区 guard、两个格式组装及实际坏 Dong 源码负控。每次原始输入、输出、组装/链接日志和源哈希保存到独立 `build/test/bootstrap-expression/run-*/`。测试不构建 OS 或启动虚拟机。
