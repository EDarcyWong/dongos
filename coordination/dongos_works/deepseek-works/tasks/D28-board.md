# D28 — [L3] 模块AST中的函数声明清单与重名检查

负责人：deepseek。状态：待领取。

所属阶段：L3：Dong自举后端 → 多函数模块驱动的前置分析。新增bootstrap.module_function_index：读取真实syntax mode 2产生的完整模块树，按源码次序列出全部函数声明，供后续“逐函数降级→多函数模块”驱动使用。只做分析，不降级、不发射、不做类型检查。不依赖C52或本批Cursor任务。

```text
module bootstrap.module_function_index;
import bootstrap.lexer as lex; import bootstrap.expression as ast;
pub const OK:u64=0; INVALID=1; CAPACITY=2; DUPLICATE=3;
pub const PUB:u64=1; EXTERN:u64=2; EXPORT:u64=4; RECEIVER:u64=8;
pub struct Entry{pub declaration:usize,pub function:usize,pub name_token:usize,pub parameter_count:usize,pub body:usize,pub flags:u64}  // 48字节，8对齐
pub struct Result{pub count:usize,pub first_duplicate:usize,pub second_duplicate:usize}  // 24字节
pub unsafe fn index(source:[]const u8, tokens:[]const lex.Token, nodes:[]const ast.Node, root:usize,
                    out:[]Entry, result:*Result)u64
```

输入：source<=65536、tokens 1..16384、nodes 1..16384，root为MODULE节点；全部只读。
校验（INVALID）：描述符/对齐/别名；token流单调且EOF仅在末尾；root及沿b链（IMPORT/DECLARATION混合链）访问到的每个节点索引在范围内、kind合法；用有界迭代遍历链（最多nodes.len步，检测环→INVALID，不递归）。DECLARATION的a为FUNCTION时，FUNCTION.token必须是IDENTIFIER，参数链（FUNCTION_PARAMETER）同样有界遍历、检测环；body为c（extern为NONE）。非函数声明（struct/enum/error/alias/global）跳过但仍需DECLARATION本身的a在范围内。
flags：DECLARATION的ATTRIBUTE链中出现pub→PUB、extern→EXTERN、export→EXPORT（按lexer关键字kind显式映射，未知修饰保持不设位）；参数链首flags位0→RECEIVER。parameter_count包括receiver。
重名：函数名按原始字节比较；任一对重复→DUPLICATE，result写first_duplicate/second_duplicate为两个Entry序号（最先出现的一对，按第二个出现位置最小、再第一个最小），count写0，out不变。receiver函数（方法）不参与顶层重名检查。
容量：函数个数>out.len→CAPACITY，out不变，result.count写所需个数（这是唯一允许在失败时写result的情形，须在说明中写清）；INVALID时out与result全不变。成功写out[0..count]与result（duplicate字段为NONE）。

测试：真实lexer+syntax(mode 2)解析源码，<=16个模块夹具：空模块、仅import、混合struct/const/fn、pub/export/extern组合、receiver方法、0..6参数、1字节与64字节名字、64个函数、重名（相邻/相隔/与方法同名不算）。独立Python oracle按源码文本解析函数声明并比较全部Entry字段（节点索引用独立遍历核对）。手工破坏：链成环、越界索引、错误kind、FUNCTION.token非IDENTIFIER、token流缺EOF→INVALID；out刚好/短1/0。真实坏Dong：忽略ATTRIBUTE链（flags错误，按字段拒绝）；重名检查只比较前8字节（用前缀相同的两个名字，按状态拒绝）；容量不足时先写一项（原子性guard拒绝）。本项无机器码生成，不需要SysV桥，但仍需debug/release编译与原生执行生产代码。

## 共用执行与复验要求
本项仅声明文件；生产为Dong，无隐式分配/全局可变状态/OS调用，新模块不导出C符号（测试wrapper可导出）。不得修改code/lang、编译器、已集成依赖、协调器、其它负责人或本批其它任务的文件；需要的依赖只读暂存其完整传递闭包。不依赖未集成的C49/C50/C52或本批其它任务。
先完整检查结果指针非NULL、8对齐、端点不回绕；所有输入切片非空时非NULL、自然对齐、元素乘法与端点不回绕，空可NULL；数量先于乘法、非法数量不读正文。out/结果指针/调用方工作区彼此及与全部完整输入（含未消费尾部）互斥；输入之间可重叠且只读。INVALID/UNSUPPORTED/SYNTAX一律先于CAPACITY。任何失败都保持out与结果指针全文不变（调用方工作区按正文说明可被改写）；成功只写精确前缀和结果，out未用尾部不变。不能先写out再回滚。
真实复用正文指定组件，不复制既有lexer/parser/C51/C48算法，不以Python/C模拟生产。每个局部数组给出栈上界并遵守dongc每函数4096字节worst-case frame限制；大缓冲一律由调用方工作区提供。
只跑本项checks：真实Dong debug/release编译、ELF64/COFF组装、显式SysV桥链接并原生执行生成的函数。单模式不同主要原生输入向量<=24，好/坏重放复用同输入不新增向量；不做全回归/性能基准。期望值由独立Python分词/解析/求值oracle给出，不用生产输出作为唯一oracle。执行生成函数时捕获真实RAX、全部callee-saved及RSP，观察地址/宿主栈锚放在桥自己的静态内存，先独立捕获现场再恢复宿主ABI后断言。
真实坏Dong须正常构建、执行后按指定数值/状态/原子性拒绝；缺符号、组装失败、崩溃、超时或仅文本不同不算负控。描述符/尾部别名预检各自独立可达；结果端点溢出用8对齐的UINT64_MAX-(sizeof-1)夹具。输入真实只读保护须断言保护调用成功；源码、说明、测试、全部只读依赖/输入SHA前后稳定，0skip才可验收。
由负责人在本人客户端通过worker MCP读取最新rev/完整任务书/review_note/write_paths/依赖，claim成功后实现；交付真实命令、tests/skips、双模式/双格式、SHA、坏体实际观察和未执行限制，再原编号submit。临时产物放在本人works的build/<编号>/<唯一目录>。不启动任何AI CLI或自动化，不自行accept/integrate、提交/推送、运行OS/VM。由协调者独立复验、验收和真实集成；组件通过不等于通用AST→IR、stage1/stage2、客体自举或L3完成。

## 可修改文件

- `deepseek-works/src/bootstrap/module_function_index.dg`
- `deepseek-works/src/bootstrap/module_function_index.md`
- `deepseek-works/tests/test_module_function_index.py`
- `deepseek-works/deliveries/D28.md`

## 定向验收

- `discover:deepseek-works/tests:test_module_function_index.py`

交付：`deepseek-works/deliveries/D28.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
