# Dong 原生模块图

`bootstrap.modules` 从调用方提供的显式源码目录建立模块图，直接调用 Dong 词法器与语法器；不调用 Python Resolver。源码目录由 I/O provider 预先读取为 `Source {root,path,bytes}`。当前未提供 DongOS 文件系统读取适配器，provider 必须先规范化真实根目录、检查符号链接/实际路径不会越出根目录，并提供完整、稳定的目录。不能把此组件视为完整编译器 CLI 或自举。

```text
unsafe load(entry:usize, roots:usize, sources:[]const Source,
 units:[]Unit, tokens:[]lexer.Token, strings:[]u8, nodes:[]expression.Node,
 edges:[]Edge, states:[]u8, max_depth:usize, result:*Result)u64
```

`root` 为 `[0,roots)` 的逻辑根编号；path 是 UTF-8 相对路径，使用 `/`、以 `.dg` 结尾，不允许绝对路径、反斜杠、NUL、冒号、空段及 `.`/`..` 段。provider 保证路径和根编号对应实际文件。模块声明/导入的每个标识符对应一个目录段。跨根同名文件拒绝，不隐式优先选第一个根。roots=0 只允许无导入单文件，所有 Source.root 必须为 NONE，声明名不要求匹配文件路径。

输入为只读借用，可共享字节；输出池、states 和 result 必须自然对齐且彼此及与所有输入区间不重叠，字节池不要求额外对齐。调用者保证描述符指向实际可访问内存。所有区间/乘法溢出、空指针、对齐、别名在写入前检查。max_depth 为1..256，同时约束导入递归与单文件语法深度。所有池均由调用方拥有，无隐式分配和扩容。

成功时 Unit 按首次深度优先到达顺序分配，重复依赖只解析一次。每个 Unit 的 token/node 索引均是**本模块局部索引**，使用 token_start/node_start 定位到池；它们不是全池节点编号。UTF-8 BOM 仅在文件开头跳过3字节，skip记录该值，token偏移针对跳过后的字节视图。Edge 保存导入方/目标 Unit 编号、IMPORT 节点和别名 token。返回的边顺序保留遍历中的导入顺序。不可达源码仅检查描述符和路径，不解析内容。

| 结构 | 字段顺序 | x86-64大小/对齐 |
| --- | --- | --- |
| Source | root, path切片, bytes切片 | 40/8 |
| Unit | source_index, skip, token_start, token_count, string_start, string_count, node_start, node_count, root | 72/8 |
| Edge | from, to, import_node, alias_token | 32/8 |
| Result | count, token_used, string_used, node_used, edge_used, code, error_source, error_start, detail | 72/8 |

状态：OK=0、INVALID=1、MISSING=2、AMBIGUOUS=3、PATH=4、CYCLE=5、CAPACITY=6、LEX=7、SYNTAX=8、ROOT_REQUIRED=9、DUP_ALIAS=10、DEPTH=11。INVALID 不改任何输出；其它失败允许池和 states 部分写入，但 Result.count=0，不发布可用模块图。成功只发布已用前缀，所有池尾保持原字节。error_source 指向目录项；error_start 为相应跳过 BOM 后的字节偏移，循环/容量诊断可能为0，detail保留底层词法/语法状态或容量类别。

`unit_source`、`unit_tokens`、`unit_nodes` 是成功图的 unsafe 借用辅助函数，不验证伪造 Unit。C/raw 入口 `dong_bootstrap_modules` 按 load 的逻辑顺序将全部切片拆成指针/容量；具体签名见源文件 `load_raw`。未实现类型兼容、局部作用域、流程分析、代码生成或产物发布；名称语义见 [names](names.md)。

验证：`python -m unittest lang.tests.test_bootstrap_modules -v`。两模式实际执行、ELF64/COFF 组装；真实临时文件的既有 Python 文件系统 Resolver 独立对照29个图（含随机 DAG、菱形共享、Unicode/BOM、多根），覆盖循环、重名、路径、别名、容量/深度及12类无写入参数拒绝。私有董源码删除重名/循环检查的4次原生负控均因状态断言拒绝。证据保存于 `build/test/bootstrap-modules/run-*/summary.json`。
