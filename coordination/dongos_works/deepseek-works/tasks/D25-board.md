# D25 — [L3] 接续CR35：有界i64 switch及case返回关联的完整SysV函数接线

负责人：deepseek。状态：待领取。

所属阶段：L3：Dong自举后端。用户明确要求转派Cursor未完成任务，本项接续cursor:CR35。原任务已暂停归档，Cursor停止原编号写入和提交；原书、领取、审查和事件全部保留。
来源任务书：cursor-works/tasks/CR35-board.md；SHA256=ef7dd8439858fe9dbea8c223fab5d0e4f485b4279ac2a8c6cba4674b4ed35a60。原发布时间=2026-10-19T12:00:17+00:00；转交前状态=todo rev1；原领取时间=未领取。
迁移范围：完整保留原接口、依赖、失败原子性、定向测试和真实坏体验证要求，仅将本项可写文件与临时构建路径改为deepseek-works、本交付编号改为D25。转交检查时原四个实现/说明/测试/交付文件尚未落盘，无实现需要复制。若随后发现原稿，先核对转交证据再接续，不重复实现或恢复Cursor原任务。
本项从待领取开始，不继承原领取、提交、测试通过、验收或集成；DeepSeek在本人客户端通过worker MCP读取最新rev及完整任务书，先处理本人已有领取/返修，再逐项claim与submit，不自动启动AI CLI。原文中的既有组件编号仍为只读依赖，不随归属改变。

## 原任务契约（本人路径已映射）

所属阶段：L3：Dong自举后端 → 多分支完整函数接线。模块bootstrap.nasm_i64_switch_function。C35已有selector分发片段但没有入口/各case结果绑定/全部ret，本项实际组合它生成可调用完整函数；与C49两值比较函数不同，不重写case排序或生成第二套分发器，不宣称完整match/AST/CFG、自举或客体门禁完成。

pub struct Arm { pub value:i64, pub block:u64, pub result:u64 } // 24字节、8对齐
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,arms:[]const Arm,default_block:u64,default_result:u64,out:[]u8,written:*usize)u64
统一OK0/INVALID1/CAPACITY2。名字各1..64字节、经CR3.encode；arms.len<=16。每个value唯一（重复值即使结果相同也INVALID），每个block!=u64::MAX且两两不同，default_block同样非NONE且与全部arm block不同。调用方保证整个汇编单元block唯一，本项不硬编码/自行分配全局标签。result/default_result允许任意u64，无符号结果原样返回。空arms合法，只走default。

生成函数u64 f(i64 selector)：对selector与每个完整i64 value作相等匹配，匹配返回该Arm.result，否则default_result。禁止排序后丢失value/block/result关联；dispatch按C35有符号排序确定，返回块按arms原始顺序确定，不按result排序。

固定frame16、saved0，slot8捕获selector、slot16放最终结果。输出：
1.CR3.encode函数符号加冒号LF；C44 nasm_sysv_function_entry.emit(kinds=[0],destination_offsets=[8],frame16)。CR12 nasm_integer_memory_load.emit(destination=rdi7,base=rbp5,displacement=-8,width64,signed=false)从真实捕获槽恢复selector。
2.局部bootstrap.switch_cases.Case[16]（C11定义{value:i64,label:usize}，16字节8对齐）逐项填{Arm.value,Arm.block}，保留原对；实际调用C35 nasm_switch_dispatch.emit(local_cases,default_block,local_out,&n)。C35内部真实调用C11.order拒绝重复value，不重写其排序/查重；本项可在调用前校验block唯一，所有字段必须在用户CAPACITY前检查。
3.对每个原始Arm，CR18 nasm_block_emit.emit(kind0,Arm.block)定义块；CR9 nasm_integer_load.emit(register0,raw=Arm.result,width64,signedfalse)；CR13 nasm_integer_memory_store.emit(source0,base5,displacement=-16,width64)；C42 nasm_sysv_function_exit.emit(kind8 U64,frame16,saved0,low16,high0)返回。每块自己的真实ret阻止落入下一case。
4.同规格生成default_block和default_result块。无bits/section/global/extern、跳表、隐式fallthrough或额外ret；所有ret来自C42。不得注入任意汇编文本或依赖未integrated项。

完整预检written非NULL/8对齐/完整8字节端点、名字/arms/out描述符；arms.len*24乘法溢出/完整端点/非空非NULL/8对齐，完整输入与out/written别名，输入彼此可互叠。arms.len>16在读正文前拒绝；所有枚举/尺寸/标签/重复value的INVALID优先CAPACITY（C35局部容量总足够）。失败out/written/输入全文不变；成功只发布精确前缀/长度，尾部不变。全部依赖局部调用后最后发布，不能先写头再回滚。可用8192最终scratch，局部Case[16]和有限依赖临时区。保守上界：函数头268+C44入口916+CR12恢复32+C35分发1233+最多17块*(CR18标签34+CR9立即数40+CR13存储32+C42尾声122)=6325<8192。写明每段上界，C35最多1233/临时1280、C44最多916/临时1536，逐次追加仍检查；不得以一次测量代替证明，合法长数字和容量不足不panic。

永久测试实际Dong debug/release编译、NASM ELF64/COFF组装，实际生成整函数经独立手写SysV桥call/ret。每模式主要原生selector向量<=24，统筹覆盖16个无序case各一次命中（含i64min/max、-1/0/1、非邻近完整高位值）、不匹配default、0/1/16 case；结果与selector不同且互异，包含u64max/最高位。独立Python字典匹配计算返回值，文本独立按signed sorted核对dispatch、按输入序核对块与结果关联，不能用C35/C11生产输出当唯一oracle。观察真正RAX、全部callee-saved(rbx/r12-r15)、rbp/rsp和guards，先安全恢复宿主ABI再断言。至少两个函数同文件不同block组组装；名长1/64、最大20位block/result；INVALID覆盖17case/非邻近重复value/重复块/default冲突/NONE和完整字段数组尾部描述符别名，保持其它字段合法可达。exact/短1/0/富余容量、完整失败原子性/未用尾部、只读保护成功、输入/依赖SHA前后稳定。

至少三类真实坏Dong：建立Case时把label错配到下一Arm（合法唯一块、构建链接正常call/ret后按数值拒绝）；给Arm块装入下一Arm.result（正常返回按数值拒绝；选无序且结果互异向量确保敏感）；容量不足提前写函数头（完整原子性拒绝）。两模式同输入先用真实好Dong生成并执行整函数；不以Python模板、文本差异、构建失败、崩溃或超时代替指定语义负控。所有坏体访问/栈/ret保持安全。

仅下列四文件，依赖只读；不动主线、活动编译器、其它负责人或已集成实现，不运行AI CLI/OS/VM/全回归，不自行accept/integrate/提交/推送。本人已有领取/返修优先。临时产物deepseek-works/build/D25/<唯一目录>；交付写真实命令、tests/skips、两模式/双格式、源码及完整输入SHA、每类坏体实际观察和未跑限制，worker MCP submit等Codex独立复验。

## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动客户端。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `deepseek-works/src/bootstrap/nasm_i64_switch_function.dg`
- `deepseek-works/src/bootstrap/nasm_i64_switch_function.md`
- `deepseek-works/tests/test_nasm_i64_switch_function.py`
- `deepseek-works/deliveries/D25.md`

## 定向验收

- `discover:deepseek-works/tests:test_nasm_i64_switch_function.py`

交付：`deepseek-works/deliveries/D25.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
