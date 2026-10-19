# CR41 — [L3] 8/16/32位窄算术的checked与wrapping完整函数

负责人：cursor。状态：待领取。

所属阶段：L3：Dong自举后端 → 窄整数运行时语义到完整函数接线。新增bootstrap.nasm_narrow_arithmetic_function。仅8/16/32位ADD/SUB，与CR38接续D26的64位ADD/SUB/MUL/NEG独立，不替代/复制CR38，不抢DeepSeek其它任务；不是完整AST或类型检查。
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,operation:u64,width:u64,signed:bool,checked:bool,error_block:u64,out:[]u8,written:*usize)u64
operation=0 ADD、1 SUB，其它INVALID；width仅8/16/32；error_block!=NONE，无论checked是否开启均验证。signed/checked是语言bool。runtime为真正SysV Pair f(u64 lhs,u64 rhs)，RAX=value、RDX=status。两输入先按各自低width位用CR14规范到u64零扩展或i64符号扩展，高位垃圾不影响操作数。checked=true：数学和/差在相应width有/无符号范围内返回{规范结果,0}，否则{0,1}。checked=false：按低width模2^width求和/差，再按signed规范成64位，status=0。不是把signed i8结果当未扩展u8返回。
固定frame32、mask0，输入槽8/16，结果value/status槽24/32。严格CR3标签→C44([0,0],[8,16],32)入口→CR12以64位读取lhs/RAX、rhs/RCX→分别CR14.emit(RAX,RAX,width,signed)与CR14.emit(RCX,RCX,width,signed)规范输入→C23.emit(ADD或SUB,RAX,RCX)算术→checked时实际调用D21 bootstrap.nasm_checked_narrow_result.emit(width,signed,error_block)，unchecked时实际CR14规范结果。检查必须在结果截窄之前，不能先cast再guard。8/16/32位两数规范后ADD/SUB的数学结果可用64位承载（unsigned SUB借位所得u64大值应被unsigned范围guard拒绝），不得误用64位溢出标志代替窄范围判断。
成功路径CR13写结果槽24，CR9装0并CR13写status32，C42(kind11,frame32,mask0,low24,high32)真实ret；随后CR18错误标签，CR9/CR13写value0/status1，同规格C42真实ret。unchecked仍输出合法但不可达的错误块，不根据测试输入在宿主端预选路径。使用D21现有guard→cast次序，不重写范围或cast组件。先全部预检/充分局部生成，再最后发布；按受限frame/宽度证明每段上界。
永久测试<=24主要向量，不强求width×signed×op×checked的全笛卡尔积。有限选择覆盖三个宽度、两signed、两op、两checked，正/负边界、0/最大值、上/下越界、unsigned借位、lhs/rhs高位垃圾、checked与unchecked对同输入的不同结果；同文件至少两函数含20位error ID无冲突。真实Dong生成整函数、真实call/ret捕获RAX/RDX；独立Python无限精度先按输入width解释，算数学结果再判范围或模运算，最后正确扩展，不能用生产guard判定当oracle。断言错误路径RAX严格0且RDX1，所有正常路径RDX0，两个出口安全保持/栈恢复。发射层覆盖bad width/op/NONE、名字与完整别名/只读输入/精确容量等。
真实坏Dong：在checked路径把CR14结果cast提前并删除D21对原值的检查（u8 200+100、i8 127+1等安全夹具）→正常返回后按Pair数值/状态拒绝；安全交换SUB源（选unchecked不同操作数）→正常返回后按RAX拒绝；CAPACITY提前发布头部→完整原子性拒绝。另保留两个出口的RBX数值保持敏感性。

## 共用执行与复验要求
本项仅四个声明文件，生产为Dong，无隐式分配/全局可变生产缓存/OS调用，新模块不导出C符号（临时wrapper可导出）。不得修改code/lang、编译器、已集成依赖、协调器、其它负责人或本批其它任务。CR38继续原队列，本人已领取/返修优先；不恢复已转交归档任务。
统一发射状态OK0/INVALID1/CAPACITY2。先完整检查written非NULL、8对齐、8字节端点；所有输入/嵌套数组和out完整区间非空非NULL、自然对齐、元素乘法、端点不回绕；空可NULL。written与整个out（包括未用尾部）及全部完整输入互斥；out亦与全部输入互斥，输入之间可重叠且只读。所有非法枚举/名称长度/块ID/结构内容先于容量拒绝，非法数量不读取正文。任何INVALID/CAPACITY均保持输入、out、written全文不变；成功只写精确前缀和written，尾部不变。
module/item及被调用者名字均为1..64原始字节，CR3编码，不能裸拼标签。块ID不得NONE，多个块必须不同，上游保证全文件唯一。本模块不分配全局编号。文本严格ASCII/单LF，仅函数标签、必要块标签和指令，无bits/section/global/extern/注释/额外空行；测试包装可补节/global和独立桥。
真实复用正文指定已集成组件及只读完整传递闭包，不复制既有规划/发射算法，不以Python/C模拟生产。每段给保守长度证明和完整缓冲/栈证明，不能拿一次输出实长代替上界；遵守dongc每函数4096 worst-case frame限制，不能直接堆无法编译的大局部数组。可在证明外部失败原子性、输入不变与依赖确定性的前提下使用有界片段完整预演后重放，必须说明第二遍失败为何不可达；或用充分且可编译的最终局部缓冲。不要改编译器/依赖逃避限制，不能先写用户out再回滚。
只跑本项checks：真实Dong debug/release编译、ELF64/COFF组装、显式SysV桥链接并原生执行。单模式不同主要原生输入向量总数<=24，复用同输入的好/坏重放不新增向量；不做全笛卡尔积/全回归/性能基准。独立Python/C oracle，不用生产输出作为唯一oracle。全部返回路径捕获真实RAX（PAIR还RDX）、所有callee-saved及RSP，独立保存观察区/宿主栈锚，先独立捕获现场，再恢复宿主ABI后断言；不能让返回RBX承担观察指针或依赖返回RSP恢复宿主。
除正文语义/原子性负控外，永久保留安全实际坏Dong的RBX保持数值负控（正文有两个出口则覆盖两个出口）：同输入正式好侧先实际生成并执行，坏侧正常编译/链接/原生返回后按指定RBX数值拒绝，不用错位/guard/对齐/崩溃代替。其它坏体也必须正常构建执行后按指定数值/状态/顺序/原子性拒绝，缺符号、组装失败、崩溃、超时、仅文本不同不算指定语义负控；所有访问和ret都在预留安全范围。
有限覆盖exact/短1/0/富余容量、成功未用尾部、INVALID优先、完整描述符和尾部别名独立可达；written端点溢出使用8对齐UINT64_MAX-7+合法空out，避免漏检后非法解引用。输入真实只读保护须断言保护调用成功；源码、说明、测试、全部只读依赖/输入SHA前后稳定，0skip才可验收。
仅用户在Cursor客户端手动通过worker MCP读最新rev/完整任务书/review_note/write_paths/依赖，claim成功后实现，交付真实命令、tests/skips、双模式/双格式、全部SHA、坏体实际观察和未执行限制，再原编号submit。临时产物cursor-works/build/<编号>/<唯一目录>。不启动Cursor CLI或任何AI CLI/自动化，不自行accept/integrate、提交/推送、运行OS/VM。最后由Codex独立复验、验收和真实集成；组件通过不等于完整语义/IR、stage1/stage2、客体自举或L3完成。

## 可修改文件

- `cursor-works/src/bootstrap/nasm_narrow_arithmetic_function.dg`
- `cursor-works/src/bootstrap/nasm_narrow_arithmetic_function.md`
- `cursor-works/tests/test_nasm_narrow_arithmetic_function.py`
- `cursor-works/deliveries/CR41.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_narrow_arithmetic_function.py`

交付：`cursor-works/deliveries/CR41.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
