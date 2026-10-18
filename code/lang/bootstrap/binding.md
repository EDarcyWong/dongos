# Dong 原生语义绑定层

`bootstrap.binding` 接在成功的 [模块图](modules.md) 和 [模块符号表](names.md) 之后，直接遍历董 AST，把名字连接到具体声明。它检查类型名称类别、局部作用域、导入可见性以及控制转移上下文；不执行完整类型兼容、常量/布局、确定初始化或路径可达性分析，不能据此标记 L3 自举完成。

```text
unsafe check(sources:[]const modules.Source, units:[]const modules.Unit,
 tokens:[]const lexer.Token, nodes:[]const expression.Node, edges:[]const modules.Edge,
 symbols:[]const names.Symbol, out:[]Ref, work:[]Ref, locals:[]Local,
 max_depth:usize, result:*Result)u64
```

输入必须是成功模块加载/名称收集所发布的只读前缀，且原始源码稳定。输入可以共享；输出/工作区/result自然对齐、彼此及与所有输入描述符/源码字节互不重叠。预检检查区间、乘法/端点溢出、对齐、别名及深度1..256；unsafe调用方仍保证存储实际可访问。没有隐式分配、全局状态、宿主运行时或修改AST。

out/work均至少容纳整个nodes视图，每个全池节点索引对应一个Ref；未绑定节点的kind为0、target=NONE。locals为当前活跃局部声明栈，函数/块退出后回收其前缀，容量取决于最大同时可见绑定数。所有诊断保留unit编号和该模块局部token编号。Result为40字节、8字节对齐，字段`code,count,unit,token,detail`。

Ref大小32/对齐8，字段`kind,unit,target,detail`：

| kind | target含义 | detail |
| --- | --- | --- |
| LOCAL=1 | unit内声明节点；参数、绑定、for或pattern名字节点 | let261/var262/const260等原绑定形式 |
| GLOBAL=2 | symbols索引 | names.Symbol.kind |
| BUILTIN_TYPE=3 | u8/u16/u32/u64=1..4、i8/i16/i32/i64=5..8、bool9、void10、noreturn11 | 0，usize/isize分别归一到4/8 |
| INTRINSIC=4 | 既有wrapping/内存/原子/切片及some/ok/err内建编号，见源码 | 0 |
| DEFERRED_MEMBER=5 | 接收者节点 | 0，字段/方法/别名枚举后缀留给类型阶段 |
| ENUM_MEMBER=6 | unit内VARIANT节点 | 所属enum的symbols索引 |
| METHOD_CANDIDATE=7 | 第一个同名method的symbols索引，表示候选组 | METHOD；不是已选定的方法 |

Local大小40/对齐8，字段`unit,token,declaration,scope,form`，仅为scratch，不作为返回句柄。LOCAL直接引用持久AST节点，退出作用域不会使Ref变成失效scratch索引。

当前规则：

- 参数与函数最外层块共享作用域，同层重复绑定拒绝；嵌套块允许遮蔽，查找最近绑定。初始化式在新绑定进入作用域前解析，因此能引用外层同名绑定，不能错误地引用尚未声明的自己。声明后的未初始化读取由后续流分析检查。
- 顶层名称、命名类型、error、结构体初始化目标、字段/数组长度表达式、函数签名和布局内建都被访问。类型位置只允许内建、struct/enum/alias。支持带空白的import限定路径，不通过拼接文本调用宿主解析器。
- 运行时局部名字能遮蔽导入别名；普通导入成员必须pub，不允许再导出导入别名。枚举直接variant连接到其声明；对象字段及透明别名后缀保留为待类型分析。直接或导入的方法重载保留候选组，选型/receiver合法性/该方法的可见性由后续类型阶段决定，不能把候选首项当作实际选中的函数。
- for绑定只在其循环体内可见，match payload绑定只在相应arm内可见；defer引用其声明处可见的名字。检查未声明名字、重复结构体初始化字段、循环外break/continue、defer内控制转移及嵌套defer。unsafe权限、返回类型/完整返回路径、match覆盖、赋值可变性等尚未检查。
- 前向类型/函数/常量引用可绑定；透明别名环、常量依赖环、数值范围、布局及按值类型环尚未求解，不能把名字已绑定当作声明最终合法。

状态：OK0、INVALID1、CAPACITY2、UNKNOWN3、PRIVATE4、KIND5、DUPLICATE6、CONTROL7、DEPTH8、BAD_TREE9。INVALID全部输出/scratch/result保持不变。其它失败允许scratch部分改变，out全部不变，Result.count=0。成功在所有模块都完成后一次复制work前nodes.len项到out，out/work尾部保持原字节；不发布半张绑定表。max_depth按语义遍历的递归调用深度约束，链表另按该模块节点数限制。

`names.valid_graph`为可复用的只读索引/链前置检查辅助函数；调用前必须先完成描述符span/对齐预检，不能将它当作探测任意宿主地址的接口。输入图应来自成功模块加载，完整类型和表达式形状仍由各阶段检查。

验证命令：`python -m unittest lang.tests.test_bootstrap_binding -v`。真正董lexer→syntax→modules→names→binding，两模式原生执行、双格式组装；生成时独立记录的局部声明边用于核对遮蔽目标，覆盖类型/导入/枚举/方法候选、参数/for/match/defer、错误/容量/深度及10类无写入参数拒绝。实际bootstrap模块图端到端绑定；私有董源码错误最近作用域/省略循环检查必须完成构建和原生执行后，被对应绑定/状态断言拒绝。逐次检查全部输入、输出/scratch/result真实guard、失败发布和成功尾部。证据保存在 `build/test/bootstrap-binding/run-*/`；没有OS/VM构建或启动。
