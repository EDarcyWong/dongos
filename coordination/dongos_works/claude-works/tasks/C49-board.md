# C49 — [L3] 条件比较与双分支返回的完整SysV函数接线

负责人：claude。状态：待领取。

所属阶段：L3：Dong自举后端 → 整函数控制流接线。模块bootstrap.nasm_u64_select_function。不是C48直线IR重复，独立新增真实双分支函数；不宣称完整CFG/AST降级、自举或客体门禁完成。

pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,condition:u64,yes_block:u64,no_block:u64,out:[]u8,written:*usize)u64
统一OK0/INVALID1/CAPACITY2。名字各1..64字节，CR3符号编码；condition=branch_plan的0..9 EQ/NE/ULT/ULE/UGT/UGE/SLT/SLE/SGT/SGE，两个block!=NONE且不同，上游负责跨函数/全文件block ID唯一，不自造局部标签编号/改动全局符号规则。

实际生成可调用函数u64 f(u64 lhs,u64 rhs,u64 yes_value,u64 no_value)：函数CR3符号加冒号LF，CR11.prologue(32,0)，C37把4个kind0单字参数捕获到[rbp-8/-16/-24/-32]；CR12以width64,signed=false把lhs装rax、rhs装rcx；C22.emit(condition,rax,rcx)实际得到规范bool RAX；固定'test rax, rax\n'后调用CR10.emit(NE,yes_block,no_block,yes_block)，因此yes为真实fallthrough，false跳no；CR18.emit(kind0,yes_block)，C42.emit(kind8 U64,frame32,mask0,low24,high0)返回yes；CR18.emit(kind0,no_block)，C42同规格low32返回no。两个块各自真实ret，无共享漏恢复路径；禁止重写现有compare/branch/布局或用宿主替代。Signed条件只把原始64位模式作i64比较，结果仍原样u64，不缩窄。

先完整written/名字/out描述符、端点、完整别名、名长、condition、block预检，INVALID优先容量。输入名字可互叠，只读且与完整out/written互斥。所有依赖在足够且有界的局部scratch里实际调用，证明每段和总上界，可用4096最终scratch但须给出逐段证明；最后一次发布out/written，不能先发布函数头。文本只有函数/块标签与指令，不含section/global/bits。临时构建可添加节/global和独立桥。

测试debug/release实际Dong产生完整函数、ELF64/COFF组装、独立手写SysV桥真正call/ret。每模式主要原生函数向量<=24，以有限向量覆盖全部10条件的真/假、相等、0/u64max/符号边界及有符号无符号相反结果；yes/no返回值不同且含高位。独立Python比较模型，不使用生产规划器作为唯一期望。观察实际RAX、全部callee-saved/rbp/rsp及guard，安全恢复宿主ABI后断言；组装同文件至少两函数、不同合法block IDs，验证无标签冲突。覆盖最大20位block、名长1/64、非法枚举/相同或NONE块、exact/短1/0/富余及未用尾部、独立可达完整尾部别名/端点、只读保护返回成功、输入及依赖SHA稳定。

真实坏Dong：一类把两返回槽24/32互换，正常call/ret后按返回数值拒绝；另一类把NE跳转判定改EQ，正常执行后路由数值拒绝；容量不足提前发布函数头以完整原子性拒绝。各debug/release同输入先用正式Dong生成并实际执行好侧，不用Python模板充当好侧，不破坏宿主栈或依靠崩溃。完整源码/契约/永久测试和交付只四文件。本人已有领取/返修优先，不抢C48；本项提交等待Codex独立复验后再验收集成。临时产物claude-works/build/C49/<唯一目录>。

## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动客户端。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。




## 可修改文件

- `claude-works/src/bootstrap/nasm_u64_select_function.dg`
- `claude-works/src/bootstrap/nasm_u64_select_function.md`
- `claude-works/tests/test_nasm_u64_select_function.py`
- `claude-works/deliveries/C49.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_u64_select_function.py`

交付：`claude-works/deliveries/C49.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
