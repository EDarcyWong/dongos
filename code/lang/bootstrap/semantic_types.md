# 原生声明类型、常量布局与运行时语义子集

`bootstrap.semantic_types` 位于已成功加载、名称收集和 `bootstrap.binding.check` 之后。它直接消费这些 Dong 组件产生的 AST、符号和绑定引用，不调用宿主 Python 检查器。数字解析、整数/布尔算术交给已验收 C3 `constant_arithmetic.evaluate`，尺寸、对齐、字段偏移和按值递归交给已验收 C4 `type_layout.calculate`。

```text
unsafe analyze(sources:[]const modules.Source, units:[]const modules.Unit,
 tokens:[]const lex.Token, nodes:[]const ast.Node, edges:[]const modules.Edge,
 symbols:[]const names.Symbol, refs:[]const binding.Ref,
 w:*const Workspace, max_depth:usize, result:*Result)u64
```

输入必须是成功模块/名称/绑定阶段的同一张不可变图，且在调用期间有效。每个 Unit 的 AST/token ID 仍是单元局部索引；`node_types`、`values` 和两组声明状态使用全局节点池索引。`max_depth` 为1～256。裸接口依旧要求 unsafe 调用者保证声明区间真实可访问；描述符检查不能证明任意伪造地址是宿主有效内存。

`Workspace` 的24个切片描述符共384字节、对齐8，全由调用者提供；包括规范类型/字段池、节点缓存、永久值 limb 池、C3小型合成树和算术工作区、C4紧凑依赖图及布局缓存。不隐式分配、不引入全局状态或 OS 调用。整数使用符号和小端 u32 limb，不把整个常量截为64位。依赖常量的数组长度/对齐要求最终可表示为正 usize；实际对象尺寸上限由 C4 检查。

所有24个可写池及 Result 必须彼此不重叠，并与输入、源码/路径字节、Workspace 描述符不重叠。先检查乘法、端点溢出、对齐和别名，再读图或写 scratch。`INVALID=1` 时包括 Result 在内全部保持不变。其它失败允许 scratch 部分改变，但 Result 的 types/fields/limbs/unchecked_initializers 均为0，禁止使用部分图。成功时仅相应有效计数范围发布；`value_states==2` 的声明值可读。Workspace 描述符本身永远只读。

基础容量：types≥9，node_types/values/value_states/type_states≥全局节点数；layout_ids/map/types/out/work/states、layouts、layout_ready≥types容量；layout_fields/offsets/work_offsets、field_offsets≥fields容量。其它字节/整数/AST工作区按实际算术规模提供，不足返回 CAPACITY，不隐式扩容。永久 limb 采用有界 bump 分配，包括中间值，调用后由调用者整体回收；尚未用 D12 arena 代替此生命周期。

`Type` 为72字节，`Field`24，`Value`40，`Result`64，均对齐8。Type.kind 1～8为u8/u16/u32/u64/i8/i16/i32/i64，9为bool；12 pointer、13 slice、14 optional、15 result、16 array、17 struct、18 enum、19 function。前9个类型索引固定，usize/isize规范为u64/i64。VOID=usize最大值-1、NORETURN=最大值-2是特殊ID，无对象布局；NONE为最大值。结构体/枚举保留定义单元和节点的名义身份；其它复合存储类型按元素/限定/计数合并。函数保留参数字段范围、返回类型及ABI/unsafe标记。

常量 Value.typ 为类型索引，NONE 表示尚未物化的整数；first/used 引用永久 limb 池。布局表达式类型为 usize。数组与结构体字段偏移由 C4提供；枚举 variant 的 Field 元数据用于 payload 类型，field_offsets 为0，不把它当作枚举运行时 tag/payload 两槽的偏移。

当前检查范围：

- 基础类型、跨模块名义类型及别名依赖；拒绝别名环、无效存储类型、按值布局环；允许指针自引用。
- 正数组长度、结构体 packed/显式对齐、字段布局、枚举 scalar payload、optional/result payload及 `!void`。
- 全局/局部标量 const 的名称依赖、整数/布尔运算与整数 cast，以及 sizeof/alignof/offsetof；跨模块 offsetof 保留私有字段限制。
- 显式整数类型的范围、typed算术溢出、移位宽度与左移截断、整数 cast 截断、带符号除余边界。标量常量检查两侧逻辑表达式，与宿主完整语义阶段的错误拒绝行为一致；C3独立组件的短路契约没有改变。
- 函数及函数指针的声明签名、返回特殊类型；SysV允许规定的双字值，Win64/外部入口限制为scalar（含无payload枚举），不允许结构体/数组按值传参或返回。

状态：OK0、INVALID1、CAPACITY2、TYPE3、CYCLE4、CONSTANT5、LAYOUT6、DEPTH7、UNSUPPORTED8、BAD_GRAPH9、PRIVATE10。Result 给出首个错误 unit/token/detail；这不是最终面向用户的稳定错误编号。Claude C5诊断格式化已独立验收，尚未接入原生CLI。

**声明入口的边界：** `analyze` 不检查函数体或所有初始化。非标量或运行时初始化只计入 `unchecked_initializers`，不能把此入口的 OK 解释为整程序可编译。下面新增的入口在声明检查后执行运行时子集检查；两者保留不同的发布契约。

定向验证入口：`python -m unittest lang.tests.test_bootstrap_semantic_types -v`。实际模块图经原生模块加载、名称收集和绑定后进入本模块；独立 Python 整数期望、宿主 TypeSystem 布局、只读页、完整池 guard、INVALID不变性及两种实际坏董实现检查集成结果。最终执行记录见 `docs/language-l2-l3.md`，历史失败保留，不把构建失败计为有效坏实现拒绝。

## 运行时类型与流程入口

```text
unsafe analyze_program(sources, units, tokens, nodes, edges, symbols, refs,
 w:*const Workspace, rw:*const RuntimeWorkspace,
 max_depth:usize, result:*Result)u64

Info { typ:usize, flags:u64, length:usize } // 24字节、对齐8
RuntimeWorkspace { info:[]Info, initialized:[]u8, snapshots:[]u8,
 breaks:[]u8, loop_seen:[]u8 } // 80字节、对齐8
```

前七项与声明入口同型，同样要求成功绑定的同一张图。原24池ABI和Result不变，新增5池全部由调用者拥有；`info`/`initialized`长度至少为全局节点池长度N，`snapshots`至少2×N×max_depth字节、`breaks`至少N×max_depth字节、`loop_seen`至少max_depth字节。尺寸乘法溢出为INVALID；合法但不足为CAPACITY。池与输入、源码/路径、两个工作区描述符、Result及其它可写池必须不重叠。先完成描述符与别名预检，INVALID不改任何scratch或Result；容量及其它失败不发布部分计数，允许已声明的scratch部分改变。两个工作区描述符均只读，不分配、不读写文件、不调用宿主语义器。

成功发布类型/字段/limb计数，`unchecked_initializers==0`；不支持的构造返回UNSUPPORTED，不能忽略后继续发布成功。新增状态：UNINITIALIZED11、IMMUTABLE12、UNSAFE13、RETURN_PATH14、FLOW15。Info以全局节点索引访问；flags位1=place、2=可写、4=已知标量值、8=表达式不正常返回、16=已知长度、32=已知标签；length在位16时为长度，在位32时为标签（optional 0/1、当前成功result为0），两位互斥。初始化位图为分析scratch，最终内容属于最后分析的函数，不是所有函数的持久流程图。入口尚未生成可供后端使用的lowered IR。

已实现的范围：

- 局部推导、整数/布尔运算及cast、显式整数范围、wrapping物化、静态除零/移位/有符号最小值除负一拒绝；底类型传播及逻辑短路的可达性，死代码仍检查类型。
- 普通调用和结构化函数指针签名、参数/返回兼容、unsafe函数/间接调用；指针读写、索引/算术和重新解释cast需要unsafe，参数/let/const及只读指针/切片不可写。
- volatile_load/store、read/write_unaligned、atomic_load/store/compare_exchange/fetch_add及compiler_fence：按各自0/1/2/3个参数检查，所有操作（包括屏障）要求unsafe。volatile/非对齐只允许八种整数元素指针，原子只允许u32/u64；写操作拒绝只读指针，值参数按精确元素类型检查。store/屏障返回void，load/CAS/fetch_add返回元素类型（CAS不是bool）。参数按顺序分析并传播不返回状态；局部/全局同名函数继续按普通调用处理。这些是语义约束，不在分析阶段执行或重排访存，也不代替目标后端代码生成。
- 结构体字面量完整性与私有字段、固定数组/重复数组、字段/索引/长度及切片指针；已知常量索引检查固定数组和直接字符串的UTF-8字节长度。
- 切片表达式 `base[lo..hi]`（上下界均可省略）：支持已有切片和可寻址数组，保留元素类型/只读限定；界限按usize检查，已知长度时拒绝越界，已知上下界时拒绝倒序并传播结果长度供后续索引检查。字符串长度使用UTF-8字节数，允许末端空视图；不把运行时界限当常量折叠。数组临时值拒绝，数组place按真实字段偏移和嵌套索引递归计算对齐保证，packed字段不足元素自然对齐时拒绝。原工作区ABI不变；这只是语义检查，运行时边界检查与视图代码生成仍待后端接线。
- 全局初始化必须静态可表示；局部变量按整体初始化，不以写单个结构体字段代替整体初始化。if分支和循环break出口按可达路径取初始化交集，while/for保留零次执行路径；检查返回路径、noreturn、嵌套循环及bool match穷尽性。
- `try`检查所在函数为result返回类型、操作数为result，提取准确payload类型（含!void），禁止defer内传播；错误返回值不能作为普通调用语句丢弃。`orelse`要求optional，回退值按payload检查；支持return/break/continue回退及既有循环出口初始化交集。已知不可变全局/局部const的空/有值标签用于短路可达性，未知optional保留两条路径；不正常返回标志只在必经路径传播，死回退仍检查类型。现有隐式payload包装和null包装清除旧scalar/place事实并记录标签，Info及工作区尺寸/ABI不变。这里只检查类型与流程，不生成错误传播或defer清理指令。
- 普通defer检查捕获变量在声明处已经初始化，不能把defer中的赋值计入外层确定初始化；defer局部声明独立检查。终止型defer明确拒绝，避免把尚未实现的清理出口语义当作完整支持。

`match`支持bool、optional的null/some及result的ok/err，检查正确payload类型、是否需要绑定、重复/不可达模式与穷尽性。err绑定为u64，!void的ok无payload。各可达分支的确定初始化取交集，已知不可变const标签过滤不可能出口；payload绑定只进入所在分支。复用现有Info/TAG与快照工作区，ABI不变。此处仅类型和流程检查，不生成match代码。

仍未完成：方法接收者与错误码专项、枚举构造/成员及枚举match、some/ok/err等尚未落实语言契约的带标签构造调用、完整聚合常量求值与所有常量长度传播（含全局静态切片物化）、defer清理lowering。方法/error声明即使未被使用也明确UNSUPPORTED；带载荷枚举禁止直接相等比较。**这仍是受限语义子集，不是完整编译器或L3验收。** 目标I/O、后端/CLI、stage1/stage2及真正DongOS自编译仍待完成。

运行时定向测试：`python -m unittest lang.tests.test_bootstrap_semantic_runtime -v`。实际模块加载/名称/绑定后由Dong原生检查，宿主编译器独立核对可接受性；两模式、双格式组装，输入及描述符真实只读页，29池双端guard与20类INVALID预检。删除真实类型拒绝及把分支交集改为并集的董副本必须完成编译、链接、执行，再被状态断言拒绝。
