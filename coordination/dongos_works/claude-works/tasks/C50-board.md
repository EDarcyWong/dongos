# C50 — [L3] 实参重排与真实跨函数调用的完整SysV函数接线

负责人：claude。状态：待领取。

所属阶段：L3：Dong自举后端 → 整函数调用链接线。模块bootstrap.nasm_u64_forward_function。与C48直线运算、C49条件分支独立，不依赖未验收组件，不宣称完整IR/链接器或自举完成。

pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,callee_module:[]const u8,callee_item:[]const u8,incoming_count:usize,argument_map:[]const usize,out:[]u8,written:*usize)u64
名字各1..64字节，incoming_count0..6，argument_map.len0..6，每项<incoming_count。允许重排/重复/丢弃实参，零incoming只允许空map。函数自身module/item与callee两名字同时逐字节相同则INVALID（本受限包装器不允许直接自递归）；输入名字/参数映射可彼此重叠，但整体只读并与out/written完整互斥。完整验证map乘法/usize对齐/端点/数量后才读取；所有INVALID优先CAPACITY。

生成函数u64 f(u64 a0,... incoming_count个u64) { return callee(a[map[0]],...); }。每incoming槽offset=8*(i+1)，结果专用槽offset=8*(incoming_count+1)，frame=align_up(8*(incoming_count+1),16)，saved_mask0。CR3自身符号加冒号LF，CR11.prologue(frame,0)，C37(kind0 scalar INTEGER)捕获incoming到对应槽；C41.emit实际复用direct-invoke：参数kinds全部0（这里0是单字INTEGER，不是返回kind8），source_offsets[j]=8*(map[j]+1)，return_kind8 U64、frame、low=结果槽、high0；然后C42.emit(kind8,frame,mask0,low结果槽,high0)读取该结果并真实尾声ret。严格capture→真实setup/call/cleanup/capture-return→load-return/epilogue；不得用尾跳绕过本契约，不重写ABI规划。callee由上游解析并提供实际符号；不生成callee函数体或extern/global/section/bits，测试包装负责。

完整written/4名字/map/out描述符与尾部别名先检查，名字逐字节相同检查在合法长度后。全部组件局部scratch，逐段证明上界，可4096最终scratch但必须留足C41段1536、C37段1024、符号/序言/尾声等并给出实上界；最后一次发布out/written，不允许容量不足已写函数头。无分配、全局可变状态、OS调用。

永久测试：实际Dong debug/release生成整包装函数，NASM ELF64/COFF组装；独立手写SysV调用桥实际调用包装器→另一个真实链接目标→返回。callee为独立C/汇编SysV函数，不使用生产ABI规划作为oracle；通过汇编alias或测试global把CR3符号绑定到实际目标，目标按参数位置带权求hash，记录真实收到的实参、callee入口rsp%16=8、调用次数并返回不同高位u64。测试观察最终RAX、完整callee-saved/rbp/rsp恢复与guard。每模式主要向量<=24，覆盖0/1/6incoming，空/1/6map、逆序、重复、丢弃、6对1/1对6、非交换位置权重、64位边界、结果槽与全部实参槽隔离；最大名长1/64、输入名相互重叠和空map NULL；invalid自调用/任意map越界/数量/对齐/所有名字及map完整尾部别名独立可达，容量exact/短1/0/富余、真实只读输入并检查保护成功、输入/依赖SHA稳定。

真实坏Dong：安全改变合法重排map（例如两个不同索引交换），正常执行后callee实参及返回数值拒绝；返回时读取另一已初始化实参槽而非结果槽，正常执行后数值拒绝（只在incoming>=1向量注入）；容量不足提前写函数头由完整原子性拒绝。同输入正式好侧必须实际Dong生成完整函数并执行真实调用，debug/release都跑。不用缺call的文本差异、未定义符号/构建失败或栈崩溃当负控。本人已有领取及返修优先，四文件不修改C48/C49，临时产物claude-works/build/C50/<唯一目录>。完成如实交付，等待独立验收与实际集成。

## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动客户端。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。




## 可修改文件

- `claude-works/src/bootstrap/nasm_u64_forward_function.dg`
- `claude-works/src/bootstrap/nasm_u64_forward_function.md`
- `claude-works/tests/test_nasm_u64_forward_function.py`
- `claude-works/deliveries/C50.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_u64_forward_function.py`

交付：`claude-works/deliveries/C50.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
