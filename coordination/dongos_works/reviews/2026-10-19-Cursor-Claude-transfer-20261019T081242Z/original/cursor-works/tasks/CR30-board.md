# CR30 — 先检查完整RCX计数再执行64位可变移位

负责人：cursor。状态：待领取。

模块bootstrap.nasm_checked_variable_shift。这是独立生产组合组件，补齐已集成底层组件的真实接线，不声称活动IR或完整L3完成。

pub unsafe fn 接口emit(operation:u64,destination:u64,trap_block:u64,out:[]u8,written:*usize)u64。operation0/1/2继承C26 SHL/SHR/SAR；destination0..15但禁止rsp(4)/rbp(5)，trap!=NONE。严格复用CR21.emit(count=1,width=64,trap)后C26.emit(operation,destination)，固定64位wrapping移位，只检查计数<64，不宣称检查左移算术溢出或窄整数。完整RCX先比较，不得只看CL；destination=RCX也合法，比较和移位使用原始计数。只目标及flags改变，trap保持全部GPR；不改RCX除非其为目标。局部guard64/shift16/final80可用但须证明。每模式<=24主原生向量覆盖3operation、0/1/63/64/256/2^32计数、负数SAR、RCX作为目标、扩展寄存器及trap大标签，有限组合而非笛卡尔积。完整容量和别名原子性。真实坏Dong把guard width从64改为32，用count63正常执行错误trap由路由拒绝（无硬件异常）；或移除guard后count64错误落空，数值/路由拒绝。另提前发布容量负控。

## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动Cursor。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_checked_variable_shift.dg`
- `cursor-works/src/bootstrap/nasm_checked_variable_shift.md`
- `cursor-works/tests/test_nasm_checked_variable_shift.py`
- `cursor-works/deliveries/CR30.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_checked_variable_shift.py`

交付：`cursor-works/deliveries/CR30.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
