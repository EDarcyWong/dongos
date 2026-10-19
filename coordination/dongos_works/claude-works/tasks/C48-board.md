# C48 — [L3] 受限u64直线IR到完整SysV函数接线

负责人：claude。状态：待领取。

所属阶段：L3：Dong自举后端 → 受限IR到完整函数接线。模块bootstrap.nasm_u64_function。本项把已集成发射组件接成真实可调用函数，不宣称完整AST降级、完整IR、自举或客体门禁完成。不重复已有C41~C47。

pub struct Instruction{pub operation:u64,pub destination:usize,pub left:usize,pub right:usize,pub immediate:u64}
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,parameter_count:usize,slot_count:usize,instructions:[]const Instruction,return_slot:usize,out:[]u8,written:*usize)u64
OK0/INVALID1/CAPACITY2。module/item各1..64字节，字节编码完全复用CR3；parameter_count0..6，slot_count1..32且>=parameter_count，instructions0..64，return_slot<slot_count。每槽为u64，[rbp-8*(slot+1)]；frame=align_up(8*slot_count,16)，saved_mask=0。入口捕获前parameter_count个u64参数到同编号槽，采用C37 kinds=0标量INTEGER、offset=8*(i+1)。

operation固定：0 CONST，destination合法、left=right=0、immediate任意u64；1 COPY，destination/left合法、right=immediate=0；2 ADD、3 SUB、4 AND、5 OR、6 XOR、7 IMUL，destination/left/right合法、immediate=0。所有算术显式u64模2^64，不声称debug溢出检查。执行前用局部32槽初始化标记完整预检整串：只有参数槽初始已初始化；COPY/二元在其指令之前读源必须已初始化，写后置位；允许覆盖/同槽和left=right，但不能靠本条写来伪造本条读取已初始化；返回槽最终必须初始化。未知operation、未用字段非零、任意越界及未初始化均INVALID，优先于用户容量；不读取非法数量描述符正文。

生成内容仅：CR3.encode符号 + ':\n'，CR11.prologue(frame,0)，C37.emit入口捕获，各instruction顺序，C42.emit返回与尾声。无bits/section/global/extern等全局指令。CONST仅手拼固定'mov rax, '前后缀，整数必须CR4.encode(raw,64,false)；COPY调用CR12.load rax从left，CR13.store rax到destination；二元调用CR12把left装rax、right装rcx，再C23.emit(operation-2,rax,rcx)，最后CR13存rax。CR12/13都rbp基址、负槽偏移、width64，load signed=false。C42用kind8(U64)、low=8*(return_slot+1)、high=0、frame与saved0。不得重写已集成组件、将Python代码当生产降级、注入任意汇编文本或读取未集成依赖。

先完整验证written、module/item/instructions/out描述符及元素乘法、端点、Instruction对齐/完整数组长度，完整输入与out/written别名，输入彼此可重叠且只读。完整验证所有IR与名长，局部最终scratch充分证明上界后实际调用依赖，最后一次性发布out/written。可用16384字节最终scratch，另有限临时依赖scratch；必须给出符号<=266、序言/捕获/每指令/尾声的逐项保守上界证明，不可用实际一次输出长度代替上界；任何合法IR不足容量不panic，任何INVALID/CAPACITY不留下函数头或序言。不得分配、全局可变缓存、OS调用。不要仅为定容量先调用out发射然后回滚。

永久定向测试：实际Dong debug/release编译、NASM ELF64/COFF组装，实际生成的整函数由独立手写SysV桥call/ret，单模式主要函数向量<=24（指令条数不算额外函数向量）。独立Python u64解释器按输入IR求值，不用生产组件输出当oracle；文本拼装亦独立核对。覆盖0/1/6参数、0/64指令、1/32槽、所有operation、u64边界、乘加环绕、参数/临时同槽覆盖、left=right、读取旧destination顺序、返回首末槽、空串返回已初始化参数。捕获真实RAX结果、callee-saved全保持与rbp/rsp恢复；安全恢复宿主ABI后再断言，不通过崩溃充当失败。完整容量exact/短1/0/富余尾部，INVALID先于CAPACITY，非法字段/未初始化/所有描述符完整尾部别名可达，真实只读输入保护并检查保护成功，guards及输入/依赖SHA前后稳定。

至少三类真实坏Dong：把非交换SUB左右装载互换（安全正常执行后返回数值拒绝）、提前标记destination导致读旧未初始化槽被错误接受（只调用发射器、不执行该不合法IR生成的机器码，以INVALID状态拒绝）、容量不足提前发布函数头/序言（完整原子性拒绝）。每类debug/release同输入先执行正式好侧；语义负控好侧必须实际Dong生成并实际执行整函数，不能用Python模板代替。可增加选择性尾部别名敏感性但保持有限规模。不运行OS/VM/全回归/AI CLI，不自行验收或集成。

现有提交后续若被退回，先修本人返修，再做本项。仅下方四文件，临时产物claude-works/build/C48/<唯一目录>；完成写真实命令、tests/skips、完整输入SHA、每种坏体拒绝依据及未跑限制，再worker MCP submit。

## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动客户端。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。




## 可修改文件

- `claude-works/src/bootstrap/nasm_u64_function.dg`
- `claude-works/src/bootstrap/nasm_u64_function.md`
- `claude-works/tests/test_nasm_u64_function.py`
- `claude-works/deliveries/C48.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_u64_function.py`

交付：`claude-works/deliveries/C48.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
