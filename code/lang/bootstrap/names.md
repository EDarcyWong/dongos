# Dong 原生模块名称语义

`bootstrap.names` 接在成功的 [modules](modules.md) 图之后，收集模块级符号并检查名称冲突、成员重名和导入可见性。输入是董 AST 和 token，不使用宿主语义器。此层仍不是完整语义检查：局部作用域、方法 receiver 合法性/方法冲突、类型依赖与兼容、常量/布局、初始化和控制流等后续阶段尚未完成。

```text
unsafe collect(sources:[]const modules.Source, units:[]const modules.Unit,
 tokens:[]const lexer.Token, nodes:[]const expression.Node, edges:[]const modules.Edge,
 out:[]Symbol, work:[]Symbol, result:*Result)u64
unsafe resolve(sources:[]const modules.Source, units:[]const modules.Unit,
 tokens:[]const lexer.Token, symbols:[]const Symbol, owner:usize,
 name:[]const u8, out:*usize)u64
```

`collect` 按 Unit 及源码声明顺序收集导入、函数、结构体、枚举、error、别名、常量和全局变量；receiver 方法保留为 METHOD，暂不进入普通名称查找/冲突域。收集检查普通顶层名称与导入别名冲突、结构体字段/枚举 variant/函数参数重名，以及类型声明对内建类型名的重定义。前向名称无需按声明顺序解析。

Symbol 为48字节、8字节对齐：`unit,name_token,declaration,kind,flags,target`。unit/name_token/declaration 分别是 Unit编号、该模块局部token/节点索引；target 为导入目标Unit，普通声明为自身Unit。flags位0为pub。kind为 IMPORT1、FUNCTION2、STRUCT3、ENUM4、ERROR5、ALIAS6、CONST7、GLOBAL8、METHOD9。Result 为40字节、对齐8：`code,count,unit,token,detail`，重名诊断detail为原名字token。

输入可共享且借用只读；输出、工作表、结果必须自然对齐且与全部输入/源字节互不重叠。collect先在work建表，仅成功后复制到out；失败时out全部保持不变，Result.count=0，工作表可部分写入。INVALID保持所有输出/工作表/结果不变。成功仅改out使用前缀，尾部保留。无隐藏分配；工作表和输出容量均需容纳全部符号。所有描述符须由调用者提供实际可访问存储，参数检查不探测任意宿主地址。

resolve接受本模块名字或单层 `import_alias.member`，返回Symbol索引。跨模块member必须pub，导入别名不作为再导出；METHOD不参与。它不解析内建类型、本地变量、结构体字段或枚举后缀。不做透明别名展开。所有失败保持 `*out` 原值，成功只写该索引。

状态：OK0、INVALID1、DUPLICATE2、BAD_GRAPH3、CAPACITY4、UNKNOWN5、PRIVATE6。collect额外检查Unit/token/node/edge索引边界以及遍历链终止性；这些防御检查不替代成功模块图的结构契约。`text`是成功图的unsafe token字节借用辅助函数。

验证：`python -m unittest lang.tests.test_bootstrap_names -v`。经真实董词法器→语法器→模块加载→名称表，debug/release原生执行、双格式组装，对照确定及固定种子随机名称表、pub/private、导入别名、Unicode、重复成员、容量/失败发布、非法参数和损坏图。实际删除private检查的私有董变体必须编译、链接、运行，并由lookup断言拒绝。证据位于 `build/test/bootstrap-names/run-*/summary.json`，明确记录完整语义和自举均未完成。
