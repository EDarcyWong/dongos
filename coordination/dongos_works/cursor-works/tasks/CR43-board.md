# CR43 — [L3] 源码u64函数声明→C51→C48完整SysV函数

负责人：cursor。状态：待领取。

所属阶段：L3：Dong自举后端 → 通用AST→IR降级的第一段“声明级”接线。新增bootstrap.u64_source_function：把真实lexer token流中的一个完整函数声明 `fn NAME(p0:u64,...)u64 { return EXPR; }` 经真实syntax解析、C51降级、C48发射成完整NASM函数文本。首次让函数名、参数表和函数体来自源码本身，而不是由测试从token流里手工定位。只覆盖单return体，局部绑定/赋值由CR44另做，不在本项实现。

```text
module bootstrap.u64_source_function;
import bootstrap.lexer as lex; import bootstrap.expression as ast; import bootstrap.syntax as syn;
import bootstrap.u64_expression_ir as lower;   // C51 integrated rev6
import bootstrap.nasm_u64_function as f;      // C48 integrated rev13
pub const OK:u64=0; INVALID=1; CAPACITY=2; UNSUPPORTED=3; SYNTAX=4;
pub unsafe fn emit(module_name:[]const u8, source:[]const u8, tokens:[]const lex.Token,
                   declaration_nodes:[]ast.Node, expression_nodes:[]ast.Node, ir:[]f.Instruction,
                   out:[]u8, written:*usize)u64
```

输入与工作区：tokens是真实lexer对整个source的完整输出（末项EOF），source<=4096、tokens 1..256。声明从token 0开始。declaration_nodes（1..256项）、expression_nodes（1..24项）、ir（1..24项）是调用方工作区，本函数可在任何返回路径改写它们，但不得越界；它们与source/tokens/module_name/out/written两两互斥。module_name 1..64字节，按C48/CR3规则交给C48编码。

流程（必须按此顺序真实调用组件）：
1. 描述符/别名/数量预检（INVALID）。
2. syn.parse(mode=4, source, tokens, 0, declaration_nodes, max_depth=32, &r)。parser返回SYNTAX→SYNTAX；CAPACITY→CAPACITY（工作区不足，仍先于out容量）；DEPTH或UNSUPPORTED→UNSUPPORTED；INVALID→INVALID。成功后r.next必须是EOF token（只允许一个声明），否则SYNTAX。
3. 形状（不满足一律UNSUPPORTED，不尝试折叠）：根为DECLARATION且ATTRIBUTE链为空（不支持pub/export/extern等修饰）；a为FUNCTION，c为非NONE的BLOCK；参数链0..6项，无receiver位，每个参数类型是TYPE_NAME且名字拼写恰为`u64`（限定名、指针、切片、可选等均UNSUPPORTED）；返回类型同样为`u64`；BLOCK恰有一个语句，为RETURN且a非NONE。参数名两两不同的检查交给C51（重复→INVALID）。
4. 表达式重解析：RETURN节点token是`return`关键字，表达式起点为其下一个token；ast.parse(source,tokens,起点,expression_nodes,max_depth=32,allow_struct=false,&e)。e.next必须是紧跟的`;`，且`;`之后恰是`}`，与声明树一致，否则INVALID（说明为何不可能在合法parse后出现时也要保留该检查）。expression_nodes不足→CAPACITY，SYNTAX/DEPTH按第2步映射。
5. 参数token数组：按声明顺序收集每个FUNCTION_PARAMETER的名字token索引，放在不超过6项的局部数组。
6. lower.lower(source,tokens,expression_nodes[0..e.count],e.root,params,ir,&lr)：C51的INVALID/UNSUPPORTED/CAPACITY原样映射。
7. f.emit(module_name, 函数名token拼写, 参数个数, lr.slot_count, ir[0..lr.instruction_count], lr.return_slot, out, written)：C48的INVALID→INVALID（应不可达，须说明）、CAPACITY→CAPACITY。C48自身保证失败时out/written不变；本模块在调用C48前不写out/written。
函数名拼写为1..64字节（超出→UNSUPPORTED）。不得在本模块内重新实现参数捕获、表达式降级或文本拼接；生成文本应与“同一参数token直接调用C51再C48”的结果逐字节一致。

永久测试（cursor-works/tests/test_u64_source_function.py）：暂存本模块、C51/C48及前端完整只读闭包；实际lexer产生token。<=20个原生向量：0/1/6参数、单NAME、单常量、全部六种运算、优先级与括号、0/MAX/高位环绕、十六进制/二进制/下划线字面量、1字节与64字节函数名、23节点最大表达式。每个向量：独立Python oracle求值；把同一函数源码的文本与“测试中定位token直接调用C51+C48”的参考输出逐字节比较；全部生成函数放进一个汇编文件并真实call/ret核对RAX与callee-saved。拒绝类（只观察状态与原子性，不执行机器码）：语法错误→SYNTAX；两个声明/尾部多余token→SYNTAX；pub fn、extern fn、receiver、参数或返回类型为u32/*u64/[]u8/?u64、多语句体、无返回值return、if/let体→UNSUPPORTED；C51不支持的运算（/、<<、比较、调用）→UNSUPPORTED；未知名字、重复参数→INVALID；declaration_nodes、expression_nodes、ir工作区刚好/短1→CAPACITY；out exact/短1/0/富余。真实坏Dong：把参数token顺序反转（2参数SUB夹具，正常返回后按RAX拒绝）；忽略r.next检查（两声明源码，按状态拒绝）；在C48 CAPACITY前先写written（按原子性guard拒绝）；另加生成函数的RBX保持数值负控（C48坏副本ret前add rbx,8，按RBX数值拒绝）。

## 共用执行与复验要求
本项仅声明文件；生产为Dong，无隐式分配/全局可变状态/OS调用，新模块不导出C符号（测试wrapper可导出）。不得修改code/lang、编译器、已集成依赖、协调器、其它负责人或本批其它任务的文件；需要的依赖只读暂存其完整传递闭包。不依赖未集成的C49/C50/C52或本批其它任务。
先完整检查结果指针非NULL、8对齐、端点不回绕；所有输入切片非空时非NULL、自然对齐、元素乘法与端点不回绕，空可NULL；数量先于乘法、非法数量不读正文。out/结果指针/调用方工作区彼此及与全部完整输入（含未消费尾部）互斥；输入之间可重叠且只读。INVALID/UNSUPPORTED/SYNTAX一律先于CAPACITY。任何失败都保持out与结果指针全文不变（调用方工作区按正文说明可被改写）；成功只写精确前缀和结果，out未用尾部不变。不能先写out再回滚。
真实复用正文指定组件，不复制既有lexer/parser/C51/C48算法，不以Python/C模拟生产。每个局部数组给出栈上界并遵守dongc每函数4096字节worst-case frame限制；大缓冲一律由调用方工作区提供。
只跑本项checks：真实Dong debug/release编译、ELF64/COFF组装、显式SysV桥链接并原生执行生成的函数。单模式不同主要原生输入向量<=24，好/坏重放复用同输入不新增向量；不做全回归/性能基准。期望值由独立Python分词/解析/求值oracle给出，不用生产输出作为唯一oracle。执行生成函数时捕获真实RAX、全部callee-saved及RSP，观察地址/宿主栈锚放在桥自己的静态内存，先独立捕获现场再恢复宿主ABI后断言。
真实坏Dong须正常构建、执行后按指定数值/状态/原子性拒绝；缺符号、组装失败、崩溃、超时或仅文本不同不算负控。描述符/尾部别名预检各自独立可达；结果端点溢出用8对齐的UINT64_MAX-(sizeof-1)夹具。输入真实只读保护须断言保护调用成功；源码、说明、测试、全部只读依赖/输入SHA前后稳定，0skip才可验收。
由负责人在本人客户端通过worker MCP读取最新rev/完整任务书/review_note/write_paths/依赖，claim成功后实现；交付真实命令、tests/skips、双模式/双格式、SHA、坏体实际观察和未执行限制，再原编号submit。临时产物放在本人works的build/<编号>/<唯一目录>。不启动任何AI CLI或自动化，不自行accept/integrate、提交/推送、运行OS/VM。由协调者独立复验、验收和真实集成；组件通过不等于通用AST→IR、stage1/stage2、客体自举或L3完成。

## 可修改文件

- `cursor-works/src/bootstrap/u64_source_function.dg`
- `cursor-works/src/bootstrap/u64_source_function.md`
- `cursor-works/tests/test_u64_source_function.py`
- `cursor-works/deliveries/CR43.md`

## 定向验收

- `discover:cursor-works/tests:test_u64_source_function.py`

交付：`cursor-works/deliveries/CR43.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
