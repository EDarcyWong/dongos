# D27 — [L3] 接续CR37：有界索引装入与存储的完整SysV函数接线

负责人：deepseek。状态：待领取。

所属阶段：L3：Dong自举后端。用户明确要求转派Cursor未完成任务，本项接续cursor:CR37。原任务已暂停归档，Cursor停止原编号写入和提交；原书、领取、审查和事件全部保留。
来源任务书：cursor-works/tasks/CR37-board.md；SHA256=d087a90d101500fe46d1d9597582e900269464ba7ead35307f9caae55ba0d33b。原发布时间=2026-10-19T12:00:17+00:00；转交前状态=todo rev1；原领取时间=未领取。
迁移范围：完整保留原接口、依赖、失败原子性、定向测试和真实坏体验证要求，仅将本项可写文件与临时构建路径改为deepseek-works、本交付编号改为D27。转交检查时原四个实现/说明/测试/交付文件尚未落盘，无实现需要复制。若随后发现原稿，先核对转交证据再接续，不重复实现或恢复Cursor原任务。
本项从待领取开始，不继承原领取、提交、测试通过、验收或集成；DeepSeek在本人客户端通过worker MCP读取最新rev及完整任务书，先处理本人已有领取/返修，再逐项claim与submit，不自动启动AI CLI。原文中的既有组件编号仍为只读依赖，不随归属改变。

## 原任务契约（本人路径已映射）

所属阶段：L3：Dong自举后端 → 有界索引内存整函数接线。模块bootstrap.nasm_indexed_memory_function。补齐现有CR20边界门禁、C30缩放地址和CR12/13实际访问的真实函数组合，与C48~C50和本批其它整函数任务无文件/语义重复；不宣称完整数组/切片IR降级或L3完成。

pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const LOAD:u64=0; pub const STORE:u64=1;
pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,operation:u64,width:u64,signed:bool,error_block:u64,out:[]u8,written:*usize)u64

module/item各1..64原始字节，CR3编码。operation仅0/1，width仅8/16/32/64，scale=width/8。LOAD的8/16/32允许signed决定符号或零扩展；LOAD64只允许signed=false（返回原64位模式）。STORE所有宽度只允许signed=false。其它枚举组合均INVALID，先于容量；error_block为0..MAX-1且由上游保证全单元唯一，MAX=NONE非法。

生成真正SysV函数Pair f(u64 base,u64 len,u64 index,u64 value)，四参依次RDI/RSI/RDX/RCX。Pair按INTEGER_PAIR返回RAX=result、RDX=status。len是元素数；只有unsigned index<len时访问。LOAD返回元素经指定宽度/符号扩展后的64位模式，忽略value；STORE把value低width位写入目标，返回零扩展后的所写低width位；两者成功status0。index>=len（含len=0、高位index/u64MAX）返回{0,1}，该路径必须在读取目标base/算元素地址前分支，更不能先读或写目标。发射状态OK/INVALID/CAPACITY与函数运行时status分开。

unsafe运行前提：对于index<len的输入，调用者保证base描述真实可访问、相应LOAD可读/STORE可写且至少len个width/8字节元素的区域，整个声明区域/目标地址无整数回绕，且与生成函数代码、当前栈帧、ret及桥的元数据分离。本项不新增地址映射/权限/长度溢出校验、不验证非法unsafe指针。对于OOB路径允许base=NULL或任意不解引用的位模式，len=0无需有效存储。这是约定边界，不借删掉检查接受不支持的内存语义。

固定frame48、saved_mask0；四个输入捕获槽8/16/24/32，结果value/status槽40/48。严格生成顺序：
1. CR3.encode函数符号加冒号LF；C44.emit(kinds=[0,0,0,0],offsets=[8,16,24,32],frame48)，真实序言与捕获。
2. CR12.load(index槽24→RAX)和CR12.load(len槽16→RCX)，width64、signed=false。立刻CR20.emit(index=RAX,length=RCX,error_block)。在此门禁之前不读取base槽、不生成LEA、不读写目标内存。允许捕获base的原始实参到帧槽，因为它不解引用base。
3. 门禁落空后CR12.load(base槽8→RDI,64,false)；实际C30.encode(base=RDI,index=RAX,scale=width/8,displacement0)在局部缓冲得到完整操作数；只拼固定'lea r10, '+该操作数+LF。禁止自写缩放索引编码，不提前覆盖RAX里的index。
4. LOAD：CR12.emit(destination=RAX,base=R10,displacement0,width,signed)实际读目标。STORE：先CR12.load(value槽32→RAX,64,false)，再CR13.emit(source=RAX,base=R10,displacement0,width)实际写目标，最后CR14.emit(RAX,RAX,width,false)规范化返回所写低位，不额外重新读取目标。依赖生成的内存指令原样复用，不另写mov/movsx/movzx。
5. CR13.store(RAX,rbp,-40,64)，CR9.emit(RAX,0,64,false)+CR13.store到-48，C42.emit(kind11,frame48,mask0,low40,high48)返回成功。
6. CR18.emit(kind0,error_block)定义错误块；CR9/CR13分别写结果0/status1到40/48，再同规格C42返回。成功ret后的错误标签不需要额外done块。

无bits/section/global/extern；不在生产接口接受任意汇编文本。先完整written、两个名字、out描述符/端点、完整输入输出别名、名长/枚举组合/块号预检，名字可互叠，其它完整别名受共用契约约束。先在足够局部scratch实际调用全部依赖，再容量判断、最终一次发布；INVALID/CAPACITY完整out、written、输入不变。可用4096最终scratch：符号加冒号LF268；入口1536；所有读取帧参数最多4×128；bounds段64；C30操作数64+LEA前后缀10共74；实际访问/规范化最多STORE128+cast64=192（LOAD<=128）；成功结果/状态写出128+64+128=320；成功出口192；错误标签64；错误常量/写槽2×(64+128)=384；错误出口192。合计3798<=4096。必须逐段证明该保守界和子调用预留，不能以一次运行长度代替上界，不对合法输入在内部slice/panic。

每模式<=24主要原生函数向量（两种operation合计）。用有限代表覆盖LOAD七种合法宽度/符号形式（8/16/32×两符号加64）、STORE四宽度、index0/len-1、OOB index==len和>len、len0、index高位/MAX、相邻元素不同且含符号高位、value高位垃圾以及STORE只改精确低width字节、LOAD整个输入不变。LOAD value忽略也要证实。可在<=24内复用同一向量多个断言。独立Python字节序/符号扩展/地址偏移oracle；捕获Pair两个寄存器并比较完整安全目标区域与两端guard。实际目标源只读保护仅用于LOAD，STORE使用独立可写区。正常区域目标与观察器元数据分离。

安全证明OOB不访问：至少一项LOAD len0/baseNULL正常返回{0,1}，同时另用真实可读写预留区建立逻辑len小于物理容量的OOB向量（目标以外全是canary），预期所有物理字节不变；不以保护页fault充当主要负控。至少三类真实坏Dong：其一改变C30传入scale为另一个合法1/2/4/8，选择index非0且安全物理缓冲足够覆盖两地址，正常运行后以LOAD数值或STORE精确内存拒绝；其二在坏体中先用CR9令R11=0，再把CR20调用的index寄存器从RAX改为R11（仅给逻辑len>0、index==len的安全缓冲向量注入，RAX真实index仍用于后续LEA），坏体正常访问预留隐藏元素并返回错误status或改变canary，不能崩溃/越界；其三容量不足提前写函数头/计数，以完整原子性拒绝。还须确保好侧所有OOB指向错误返回而不访问，LOAD/STORE返回值与status角色不能互换。坏体注入不得作用于baseNULL的OOB向量，全部物理内存访问均在预留安全区域。

仅运行本任务定向检查。实际Dong debug/release生成完整函数；NASM ELF64/COFF均组装，COFF组装不冒充Win64调用ABI。手写SysV桥真正call/ret，捕获RAX/RDX，检查RBX、RBP、R12~R15和调用前后RSP；先安全恢复宿主ABI再断言。输入与输出guard、成功精确文本/计数/完整未用尾部、INVALID优先CAPACITY、容量exact/短1/0/富余均覆盖。所有written/名字/out端点、对齐、NULL、完整尾部别名预检独立可达；真实只读输入页保护并检查保护成功。每模式主要原生函数向量合计<=24，不作全笛卡尔积；边界/容量/预检可采用独立有限发射器调用。记录全部源码、说明、测试及只读依赖前后SHA256，0skip才可验收。
坏体必须成功构建、链接并正常返回，由指定返回值/状态/内存或完整原子性断言拒绝；同输入每个模式先用正式Dong实际生成并执行好侧。文本差异、构建失败、崩溃或无关预检不得冒充负控，不用Python汇编模板代替好侧。坏体全部访问在预留的真实安全内存内，不破坏宿主栈/ret。
本人已有领取/返修优先。仅声明的四文件，已integrated依赖只读；不改主线、活动编译器、其它任务或协调器，不自行验收/集成、提交/推送、运行OS/VM/全回归/AI CLI。临时产物在deepseek-works/build/本编号/<唯一目录>。完成后交付列真实命令、tests/skips、模式/对象格式、全部输入SHA、每类坏体观察与拒绝依据、未运行限制，再worker MCP按最新rev submit。

## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动客户端。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `deepseek-works/src/bootstrap/nasm_indexed_memory_function.dg`
- `deepseek-works/src/bootstrap/nasm_indexed_memory_function.md`
- `deepseek-works/tests/test_nasm_indexed_memory_function.py`
- `deepseek-works/deliveries/D27.md`

## 定向验收

- `discover:deepseek-works/tests:test_nasm_indexed_memory_function.py`

交付：`deepseek-works/deliveries/D27.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
