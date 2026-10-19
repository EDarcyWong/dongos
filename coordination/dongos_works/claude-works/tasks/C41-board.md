# C41 — 组合SysV直接调用及结果接收

负责人：claude。状态：待领取。


模块bootstrap.nasm_sysv_direct_invoke。把已集成C34实参setup、C25符号direct call、C34 cleanup、C40返回值capture真正组合为一次调用片段；必须实际调用各组件，不重写它们算法。只读依赖的传递闭包也须暂存，不引入全lang根。

pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,kinds:[]const u8,source_offsets:[]const usize,return_kind:u64,frame_bytes:usize,low_offset:usize,high_offset:usize,out:[]u8,written:*usize)u64

严格拼接顺序setup -> call -> cleanup(同一setup.Result.stack_bytes) -> capture_return。capture在cleanup之后；add rsp会改flags，上游不得认为调用跨界flags保持。调用点在setup前rsp16对齐，rbp帧有效。只支持既有INTEGER ABI，不改IR/寄存器分配/Win64桥。运行时callee正常返回且遵守SysV。名称采用C25完整原始字节命名限制。输入种类及word上限完全继承C34；额外frame为0..4080且16倍数，每个source_offsets使用槽8对齐且8<=offset<=frame_bytes，source数量仍遵从C34 word计数规则；返回槽和return_kind完全继承C40。源与返回槽可相同（实参先装载，call后才保存结果）。输入只读区之间可重叠；out/written与每个完整输入区不得重叠，out与written互不重叠。任一描述符乘法/端点/对齐、名字/参数/返回布局非法须先于容量判断，任何失败完整out/written/所有输入不变。不能把依赖在局部暂存中成功当作可提前发布用户out。C34局部1024、C25局部272、cleanup32、C40局部64合计上界1392，最终scratch可1536；证明各段够大，绝不让合法输入因内部scratch不足panic/截断。成功只发布精确前缀及written。

验收主要原生向量每模式合计<=24、永久断言；debug/release实际Dong组合产出，ELF64/COFF组装并本机显式SysV真实call链接执行。callee独立手写NASM或C显式SysV，捕获实际寄存器/栈参数及入口对齐、返回单字/PAIR/VOID/窄类型高位垃圾；调用者完整frame/目标槽/guard及rsp、callee-saved保持按独立模型比较。覆盖0/6/7/最大16word、PAIR跨寄存器预算边界按C8既定规则、栈参数、返回槽与实参槽相同、名字1/64及原始非ASCII。所有执行体必须实际Dong输出，不能用Python模板替代；完整最大名字/参数/返回文本长度与exact/少1/0容量必须覆盖。每个输入描述符/尾部别名有效可达，不用非法返回布局遮蔽实参/名字检查。

至少两个真实坏Dong组合负控：将真实call目标换为另一个合法符号，正常链接运行后按返回槽数值拒绝；错误跳过有栈实参时的setup栈分配不能破坏宿主栈，故不要用该方式，改把capture返回高槽错误指向低槽或将cleanup放capture之前/之后不作为必错语义。优先使用PAIR capture低高槽互换（委托调用参数互换），以返回槽值准确拒绝。另用户容量不足提前写written按完整原子性拒绝。每个好侧正式Dong实际文本且同输入先通过，坏侧必须正常执行后命中指定数值断言。保留真实SHA/命令/模式/计数/限制，不宣称完整L3已完成。


## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动Cursor。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `claude-works/src/bootstrap/nasm_sysv_direct_invoke.dg`
- `claude-works/src/bootstrap/nasm_sysv_direct_invoke.md`
- `claude-works/tests/test_nasm_sysv_direct_invoke.py`
- `claude-works/deliveries/C41.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_sysv_direct_invoke.py`

交付：`claude-works/deliveries/C41.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
