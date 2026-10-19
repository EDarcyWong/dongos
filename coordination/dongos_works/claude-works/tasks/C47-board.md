# C47 — [L3] 接续CR31：组合除法异常门禁与商余数内核

负责人：claude。状态：待领取。

所属阶段：L3：Dong自举后端。

用户明确授权转交：cursor:CR31 → claude:C47。原任务创建时间2026-10-19T07:30:06+00:00，转交前状态in_progress rev2，原领取人cursor-mcp-05de65f92bc04a7c。原任务书cursor-works/tasks/CR31-board.md及原交付cursor-works/deliveries/CR31.md保持原样，完整历史及SHA快照见reviews/2026-10-19-Cursor-Claude-transfer-20261019T081242Z。本任务新发布时间与后续办理时间单独记录，不能抹掉原任务的进行中/返修历史。

已将原负责人现有源码/说明/永久测试复制到本任务声明的claude-works路径，测试只适配负责人和构建目录；这些是未验收交接基线，不是Claude新交付或通过证明。不要重写正确的生产组合。先用worker MCP读取最新任务和完整原审查，再领取后继续；只写本项四文件，依赖只读，不自动启动AI CLI。原Cursor任务暂停后归档，禁止继续并行处理。

原项尚在开发中，没有正式交付/独立验收结论；继续现有实现，按完整契约补齐自测和交付。

模块bootstrap.nasm_guarded_integer_divide。这是独立生产组合组件，补齐已集成底层组件的真实接线，不声称活动IR或完整L3完成。

pub unsafe fn 接口emit(signed:bool,remainder:bool,zero_target:u64,overflow_target:u64,success_block:u64,out:[]u8,written:*usize)u64。三个label均!=NONE且两两不同；success_block由本片段定义一次，两个异常目标由上游定义且不得指向片段内部。实际复用C31.emit(signed,zero,overflow,success)，CR18标签定义组件，再CR19.emit(signed,remainder)。严格guard→success标签→divide；不得重写门禁或除法，不额外jmp/ret/section。输入RDI/RSI；成功RAX商/余数，仅RAX/RCX/RDX/flags可变，异常路径遵从C31（不执行除法）。scratch按各组件上界证明，可512。每模式<=24主原生向量覆盖signed/unsigned商余数、正负/截零、MIN/1、unsigned最大、0除数、MIN/-1的异常路由及最大标签，比较完整保持寄存器。真实坏Dong把remainder布尔取反，正常运行后数值拒绝；异常路由负控仅可替换为另一个安全异常桩，禁止漏门禁触发真实#DE或崩溃。另容量提前发布负控。

## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动客户端。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


转交例外：正文“原编号交付”对本后继指C47；交付写claude-works/deliveries/C47.md。如已带入旧交付，仅为原交付基线，须补写实际返修/验证命令、SHA与限制后submit；不继承旧通过状态。

## 可修改文件

- `claude-works/src/bootstrap/nasm_guarded_integer_divide.dg`
- `claude-works/src/bootstrap/nasm_guarded_integer_divide.md`
- `claude-works/tests/test_nasm_guarded_integer_divide.py`
- `claude-works/deliveries/C47.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_guarded_integer_divide.py`

交付：`claude-works/deliveries/C47.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
