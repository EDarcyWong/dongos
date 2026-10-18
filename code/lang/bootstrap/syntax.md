# Dong 原生声明与语句 AST

`bootstrap.syntax` 复用 `bootstrap.expression` 的 Node/Result、类型/表达式解析及参数验证，接收真正 Dong lexer 的 token 流，在调用方工作区建立声明/语句树。没有 Python 运行时、隐式分配或宿主语法器调用；也不依赖协作中 arena、UTF-8 或大整数扩展。

```text
unsafe parse(mode:u64, source:[]const u8, tokens:[]const lexer.Token,
 start:usize, nodes:[]expression.Node, max_depth:usize, result:*expression.Result)u64
```

mode=1 解析一个 `{...}` 块，2 解析完整 module 到 EOF，3 解析一个语句，4 解析一个声明。模式不在1..4内返回 INVALID，全部输出不变。前缀入口1/3/4由调用方检查 Result.next 处的剩余 token；不能把前缀成功当作完整文件成功。完整 token 流、源字节、别名/对齐/区间及发布契约沿用 [expression](expression.md)。同一深度限额覆盖类型、表达式、语句和块递归；连续兄弟/左结合表达式使用有界循环。

当前语法包括：

- module/import/别名，pub、packed、align、export、extern ABI/链接名和 unsafe 修饰；检查重复修饰与适用位置，链接名按解码后的 ASCII 标识符检查。
- 结构体及字段 pub、枚举及单 payload、error 编号、type 别名、显式类型/初始化的顶层 const/var；函数、receiver、具名参数、返回类型、函数体和 extern 声明。
- let/var/const 绑定、return、if/else/else-if、while/loop、两类 for、defer call/block、match/模式/绑定、unsafe、白名单单指令 asm、嵌套块、break/continue、全部赋值及调用语句。
- 复用完整表达式与类型语法；函数类型可有参数名，保留 const/unsafe/ABI 等语法信息。

这仍是**语法阶段**：保留未折叠长度/align/error 编号，尚不执行常量计算、正数/范围/布局验证、名字查找/重复声明检查、类型兼容、流分析、defer lowering、模块加载、后端、CLI 或产物发布。函数的合法 receiver 类型、调用权限和流程返回等留给后续语义。没有宣称通过 stage1/stage2 或 DongOS 自举。当前规格不支持的 match guard、显式枚举 tag、非白名单 asm 和未知 ABI 均拒绝。

## Node 形状

Node 仍为64字节（8字节对齐），Result 仍为40字节。下表的 a/b/c 是孩子索引或链首；链使用 next，NONE 表示缺失。token 指向相应关键字或名字，op 按表解释。未列出的字段为0或NONE，flags 未使用位为0。

| kind | a / b / c 与额外信息 |
| --- | --- |
| BLOCK=64 | a=语句链首 |
| BINDING=65 | token=变量名，op=let/var/const lexer kind；a=可选类型，b=可选初值 |
| RETURN=66 | a=可选返回值 |
| IF/WHILE=67/68 | a=条件，b=BLOCK，c=可选 IF/BLOCK 的 else（while 无 else） |
| LOOP=69 | a=BLOCK |
| FOR=70 | a=绑定 NAME，b=迭代表达式或 RANGE，c=BLOCK |
| RANGE=71 | a/b=上下界 |
| DEFER=72 | a=BLOCK；单调用规范成包含一个调用语句的 BLOCK |
| MATCH=73 | a=被匹配表达式，b=ARM 链 |
| ARM=74 | a=PATTERN，b=BLOCK |
| PATTERN=75 | op=0 时 a=NAME/FIELD路径、b=可选绑定 NAME；op=true/false/null lexer kind 时 a/b 无 |
| UNSAFE_BLOCK=76 | a=BLOCK |
| ASM=77 | token=指令名字 |
| BREAK/CONTINUE=78/79 | 无孩子 |
| ASSIGN=80 | token/op=赋值运算符，a/b=目标/右值 |
| EXPRESSION_STATEMENT=81 | a=CALL 或 TRY(CALL) |
| MODULE=96 | a=模块 NAME/FIELD路径，b=IMPORT/DECLARATION 混合链，保留源码次序 |
| IMPORT=97 | a=模块路径，b=可选显式别名 NAME |
| ATTRIBUTE=98 | token/op=修饰符；a=可选 align 表达式/字符串，b=extern 的可选链接名字字符串 |
| DECLARATION=99 | a=具体声明，b=ATTRIBUTE 链 |
| FUNCTION=100 | token=名字，a=FUNCTION_PARAMETER 链，b=返回类型，c=BLOCK（extern声明为NONE） |
| STRUCT_DECL=101 | token=名字，a=FIELD_DECL 链 |
| FIELD_DECL=102 | token=字段名，a=类型，flags 位0=pub |
| ENUM_DECL/VARIANT=103/104 | ENUM a=VARIANT链；VARIANT token=名字，a=可选payload类型 |
| ERROR_DECL=105 | token=名字，b=未折叠编号表达式 |
| ALIAS_DECL=106 | token=名字，a=类型 |
| GLOBAL=107 | token=名字，op=const/var lexer kind，a=类型，b=初值 |
| FUNCTION_PARAMETER=108 | token=名字，a=类型，flags 位0=receiver；receiver位于参数链首 |

## 验证

`python -m unittest lang.tests.test_bootstrap_expression lang.tests.test_bootstrap_syntax -v` 编译并原生执行 lexer→parser，再对照 Python 前端的独立 AST。覆盖实际语言/内核/服务模块、两种模式、双格式组装、只读页 source/token、参数与区间拒绝、失败不发布、容量/深度/诊断、修饰符和删除标点产生的坏模块；实际坏董源码负控必须完成编译/链接/执行并因准确断言拒绝。

证据分别保存于 `build/test/bootstrap-expression/run-*/` 和 `build/test/bootstrap-syntax/run-*/`。语料明确排除 Claude C1/C2/C3/C4 和 DeepSeek D12/D13 的协作实现文件；这些文件不由本轮修改或验收。没有 OS 构建或虚拟机启动。模块图与名称检查由后续独立的 [modules](modules.md) / [names](names.md) 组件负责，本语法入口不代替它们。
