# C51 — [L3] 原生表达式AST降为C48的受限u64直线IR

负责人：claude。状态：待领取。

所属阶段：L3：Dong自举后端 → AST到已集成整函数IR的首次受限接线。不是再造词法/语法器或C48发射器；新增bootstrap.u64_expression_ir，把真正Dong lexer/expression输出的树转换成C48.Instruction。仅u64显式模2^64的测试后端子集，不冒充一般Dong源码的默认受检算术或完整类型检查。

import bootstrap.lexer as lex; import bootstrap.expression as ast; import bootstrap.bigint as bi; import bootstrap.nasm_u64_function as f;
pub struct Result{pub instruction_count:usize,pub slot_count:usize,pub return_slot:usize} // 24字节，8对齐
pub unsafe fn lower(source:[]const u8,tokens:[]const lex.Token,nodes:[]const ast.Node,root:usize,parameter_tokens:[]const usize,out:[]f.Instruction,result:*Result)u64
OK=0 INVALID=1 CAPACITY=2 UNSUPPORTED=3。source<=4096字节，tokens1..256，nodes1..24，参数token索引0..6个，root<nodes.len。传入nodes仅是该表达式的已用树，所有索引均相对该切片；token指向原完整只读source/token流。parameter_tokens顺序定义参数槽0..p-1，每项指向IDENTIFIER token，拼写非空且各项字节名不同；它们可位于完整函数签名中，表达式parse可从return后的token开始，因此无需伪造AST或把参数表拼进表达式。

核心只读基线：code/lang/bootstrap/{lexer,unicode,expression,bigint}.dg及实际存在的说明文档，它们是已存在的原生前端/整数核心，不是本次新任务；C48及其只读发射闭包来自integrated主线。不能修改这些基线或为它们虚构新协调任务。本项依赖C48 integrated后方可领取。

先校验所有source/token/node/parameter_tokens/out/Result描述符、完整输出及输入别名和数量。tokens整流start<=end<=source.len、单调不交叠，最后且仅最后EOF；root、参数token索引及各node.token均在范围。调用者保证source/token对应成功lexer输出，本模块不重写lexer；节点与对应token种类/操作符仍须核对。参数表重复、无此参数的NAME、非法引用、环、共享孩子、多父或不可达垃圾节点均INVALID，不能无限递归或静默忽略。只对支持的三种node做完整形状预检：INTEGER/NAME的op=0且a/b/c=NONE；BINARY的a/b为孩子、c=NONE；所有next=NONE，flags仅允许括号位0。三类之外的kind或BINARY不支持的operator返回UNSUPPORTED，不声称验证其完整复杂子树；此判定在安全描述符/索引预检后且不写输出。对支持树要求全部nodes恰被root树访问一次。

仅支持INTEGER、NAME、BINARY的+、-、*、&、|、^。BINARY.op须对应其token.kind且拼写是该单字符，不用Python解释器执行生产转换。无unary、call、cast、bool、比较、除法、移位、控制流或局部绑定；这些明确UNSUPPORTED，不常量折叠成受支持树。INTEGER拼写<=256字节，必须实际调用bi.parse，复用十进制/0x/0b及合法下划线规则，非负且最终<=UINT64_MAX；超范围/非法字面量INVALID，不截断。可用局部2个u32输出limb、32个u32解析work（最多256字节字面量够用）；零used=0解释为0，禁止自写第二套整数解析。

确定性lowering：左子树后序→右子树后序→父，NAME直接引用其参数槽不发指令；每个INTEGER依次分配一个新槽并发CONST；每个BINARY在两个源已生成后分配新槽，映射C48.ADD/SUB/IMUL/AND/OR/XOR（不是按字符值推算opcode）。新槽从p开始，不重用、不折叠；每个CONST unused left/right=0，每个二元immediate=0。instruction_count为非NAME节点数<=24，slot_count=max(1,p+instruction_count)<=30，return_slot为root对应槽；可用本地24条Instruction先完成全部检查和lower，最后一次发布out精确前缀及整个Result。用户out不足才CAPACITY；INVALID/UNSUPPORTED优先；out和Result失败全文不变。

永久测试必须真实Dong lexer→expression.parse→本lower→已集成C48.emit→汇编/真实call/ret，并用独立Python表达式求值/输入AST期望核对IR次序/槽/结果。禁止在Python直接构造生产IR代替lower，也不能仅检查生成文本。用完整函数源码夹具，真实lexer定位签名参数token与return表达式起点，真实parser生成nodes，再lower。覆盖0/1/6参数、单NAME/单常量、左右不交换的SUB、嵌套优先级/括号、重复参数读取、六运算、0/max/高位、乘加环绕、十/十六/二进制及下划线、最大合法树规模（支持的叶/二叉树节点数必为奇数，24上限内最大23）、精确IR容量/短1/0/富余尾部。全部正常向量<=24。负面包括未知/重复参数、超大字面量、节点/参数token越界、token/Node字段不匹配、未支持构造、环/共享/多父/不可达节点、完整尾部别名与只读保护；不得执行非法lower生成的机器码。

至少：真实坏Dong交换SUB两个IR源→同输入正式好侧先lower并执行，坏侧正常函数返回后按RAX拒绝；删除未知NAME拒绝并错误映射到合法参数槽→只用有安全参数槽的夹具，按INVALID状态拒绝；输出容量不足提前写一条IR或Result→完整原子性拒绝。另保留共用要求的安全RBX数值保持敏感性。测试需对parser的工作区失败契约与本lower最终产物原子性分开观察，不能拿parser允许写scratch为理由放宽lower输出。临时产物claude-works/build/C51/<唯一目录>。

## 执行、内存和复验共同要求
只改声明的四文件，生产为Dong；不修改code/lang、编译器、既有组件、其它负责人或本批另一任务。本人领取/返修优先。没有隐式分配、全局可变生产状态或OS/I/O调用，新模块不导出C符号（临时wrapper可导出）。依赖仅从已integrated主线及明确列出的既有核心只读基线暂存完整传递闭包，不能复制整个lang掩盖坏源码。不得改旧任务/恢复归档项或用Python/C代替生产lowering。
所有切片/结构/结果先检查完整声明区间：非空非NULL、元素乘法、自然对齐、端点不回绕；空切片可NULL。结果非NULL、自然8对齐、完整对象端点有效。输入彼此可重叠且只读；所有输出/Result及显式work按正文要求彼此并与全部完整输入（含嵌套名字/数组、未消费尾部）不重叠。在任何输入正文读取或输出写入前先完成可安全做的描述符检查，非法数量不读正文。正文限定的INVALID/UNSUPPORTED先于用户输出容量。除C52显式work外，失败所有输出、整个Result/计数、输入全文和guards不变；成功只写精确前缀及结果，未用尾部不变。
局部栈以当前dongc的4096 worst-case frame限制设计；给出结构尺寸、临时片段、每段及总上界证明，实际debug/release均可编译。不要照搬无法编译的大局部最终数组，不改编译器来逃避限制。若正文给显式work，只能修改该调用方工作区，不影响最终产物失败原子性。
只跑本任务checks，实际Dong debug/release编译、NASM ELF64/COFF组装及显式SysV桥链接/原生执行；COFF组装不冒充Win64调用ABI。单模式不同主要原生函数向量总量<=24，复用相同输入的好/坏重放不另算。独立Python/C oracle，不能用生产输出作为唯一oracle。观察真实RAX、所有callee-saved和RSP：独立保存观察区地址和宿主栈锚，返回后先从独立地址捕获现场，再恢复宿主栈及ABI，最后断言；不能用返回RBX作观察指针或信任返回RSP。永久保留安全真实坏Dong的RBX数值保持负控（同输入好侧先实际生成调用，坏侧正常返回后按指定数值拒绝）；不要重现C48~C50首交的桥缺口。
覆盖完整描述符/端点/尾部别名的独立可达用例，written/Result端点溢出用8对齐UINT64_MAX-7或与Result尺寸匹配的安全参数，不能通过非法解引用拒绝；输入真实只读保护并断言保护调用成功，输入/依赖/生产/说明/测试SHA256前后稳定。有限边界，不跑笛卡尔积、全回归、OS/VM或性能基准。真实坏体必须正常构建/链接/执行后由指定语义/状态/原子性断言拒绝；构建失败、缺符号、崩溃、超时、仅文本不同不算指定语义负控，所有坏体访问和返回路径在预留安全范围内。
本人客户端先worker MCP get_task/read_document读最新rev、完整契约、review_note、write_paths和依赖，claim成功后执行；不由协调器启动AI CLI。临时产物仅本人works/build/<编号>/<唯一目录>/。交付记录实际命令、tests/skips、模式/格式、全部输入SHA、各坏体实际拒绝依据及未执行限制，再原编号submit。不得自行accept/integrate、提交/推送或启动定时器。交付仍须Codex独立复验、验收和真实集成；本组件不代表完整IR/语义/CLI、stage1/stage2或整个L3完成。

## 可修改文件

- `claude-works/src/bootstrap/u64_expression_ir.dg`
- `claude-works/src/bootstrap/u64_expression_ir.md`
- `claude-works/tests/test_u64_expression_ir.py`
- `claude-works/deliveries/C51.md`

## 定向验收

- `discover:claude-works/tests:test_u64_expression_ir.py`

交付：`claude-works/deliveries/C51.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
