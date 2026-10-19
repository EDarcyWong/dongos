# CR34 — [L3] 固定有限次数u64循环与真实回边的完整SysV函数接线

负责人：cursor。状态：待领取。

所属阶段：L3：Dong自举后端 → 完整函数控制流接线。模块bootstrap.nasm_u64_loop_function。本项补常量range/计数循环的真实回边，独立于C48直线IR、C49双分支、C50跨函数调用；不是展开循环，不宣称完整AST/CFG降级、自举或客体门禁完成。

pub unsafe fn emit(module_name:[]const u8,item_name:[]const u8,iterations:usize,header_block:u64,body_block:u64,exit_block:u64,out:[]u8,written:*usize)u64
OK0/INVALID1/CAPACITY2。名字各1..64字节，经CR3符号编码。iterations=0..64是生成器参数；运行时不接收无限次数。三个block都不为u64::MAX、两两不同；调用方保证汇编单元内跨函数block唯一，本项不硬编码/分配全局标签。

生成真实可调用函数u64 f(u64 seed,u64 factor,u64 increment)。精确语义：acc=seed；执行iterations次 acc=(acc*factor+increment) mod 2^64；返回acc。乘加明确wrapping，不作为debug检查算术。每次都执行同一body和回边，哪怕iterations=0/1也不得按次数展开/常量替换成直接返回。只生成函数符号/标签/指令，无section/global/bits/extern。

固定frame32、saved_mask0；四槽[rbp-8/-16/-24/-32]分别acc/factor/increment/remaining。输出严格按下述复用步骤：
1.CR3.encode名字后加冒号LF；C44 nasm_sysv_function_entry.emit(kinds=[0,0,0],destination_offsets=[8,16,24],frame_bytes=32)，真实捕获三参数。
2.CR9 nasm_integer_load.emit(rax=0,iterations,64,false)后CR13 nasm_integer_memory_store.emit(source0,base5,displacement-32,width64)初始化remaining。
3.CR18.emit(kind0,header_block)；CR12 nasm_integer_memory_load.emit(destination0,base5,-32,64,false)；CR9.emit(rcx=1,0,64,false)；C22 nasm_compare_emit.emit(EQ=0,rax0,rcx1)；固定ASCII文本 test rax, rax 后接一个真实单LF；CR10 nasm_branch_emit.emit(NE=1,yes=exit_block,no=body_block,fallthrough=body_block)，真零值跳exit，非零实际落入body。
4.CR18定义body；CR12将acc(-8)装rax、factor(-16)装rcx；C23 nasm_integer_binary.emit(IMUL=5,0,1)；CR12将increment(-24)装rcx；C23.emit(ADD=0,0,1)；CR13把rax存acc(-8)；CR12把remaining(-32)装rax；CR9把1装rcx；C23.emit(SUB=1,0,1)；CR13写回remaining(-32)；CR18.emit(kind1,header_block)构成真实回边。
5.CR18定义exit；C42 nasm_sysv_function_exit.emit(kind8 U64,frame32,saved0,low8,high0)完成实际ret。
所有CR12 width64/signedfalse、base5；CR13 width64/base5。不得重写上述组件或依赖未integrated项。

在读取输入前完整验证written非NULL/8对齐/8字节端点、全部名字/out描述符和完整区间端点、完整输入与out/written别名；名字输入可互叠。验证名长、iterations、所有block，INVALID优先CAPACITY。所有依赖在有证明上界的局部scratch调用，最后一次性发布out和written。可用4096最终scratch；保守总上界可取1993=函数头268+C44入口916+3次CR9各40+8次CR12/13各32+3次C23各16+C22比较48+固定test14+CR10分支66+3个CR18标签各34+CR18回边33+C42出口122；固定槽位使每条内存文本<=32，分别核实并写明。可用依赖临时区1536（C44）及其它足够有限临时区；每次拼接仍检查。不得用实测单例长度代替上界，不得因合法容量不足panic，不先发布函数头或序言。

永久定向测试实际Dong debug/release编译、NASM ELF64/COFF组装，实际Dong生成整函数经独立SysV桥call/ret；每模式主要原生函数向量<=24。独立Python按三参数和iterations重复求值，不使用生产组件输出作oracle。有限覆盖iterations0/1/2/64、0/1/u64max/最高位seed/factor/increment、乘加wrapping、factor0/1、seed回传及两个不同全局block组同文件组装；最大20位block与名长1/64。精确文本另独立拼接核对；真实观察RAX、全部callee-saved(rbx/r12-r15)、rbp/rsp和guards，先安全恢复宿主ABI再断言。检查exact/短1/0/富余容量与未用尾部、非法65/max次数、非法/重复/NONE块、完整尾部别名及端点独立可达、只读页保护成功与完整输入/依赖SHA稳定。

至少三类真实坏Dong：把IMUL改ADD（正常终止后数值拒绝）；把回边目标header改exit（iterations>=2正常终止后数值拒绝，不依赖超时/死循环）；容量不足提前发布函数头/序言（完整失败原子性拒绝）。每类两模式同输入先实际执行好Dong产出的整函数；不能以Python模板、构建失败、崩溃或超时代替。坏体不破坏宿主栈/ret。

只修改下列四文件，依赖只读；不动主线、活动编译器、其它负责人或已集成实现，不运行AI CLI/OS/VM/全回归，不自行accept/integrate/提交/推送。本人已有领取/返修优先。临时产物cursor-works/build/CR34/<唯一目录>；交付写真实命令、tests/skips、两模式/双格式、源码及完整输入SHA、每类坏体实际观察和未跑限制，worker MCP submit等待独立复验。

## 共用固定契约与执行归属

本任务是L3 Dong自举后端的独立生产组件；仅四个声明文件，Dong实现，不导出C符号（临时测试wrapper可导出），无分配、全局可变状态、OS调用。不可改code/lang、活动编译器、内核、协调器、其它负责人、在途任务或已集成依赖；既有队列/返修优先。依赖只读，只用已integrated模块；不得以宿主Python/C算法替代Dong生产逻辑。

统一OK=0、INVALID=1、CAPACITY=2；接口另有Result时按任务正文完整尺寸。written非NULL、8对齐、完整8字节端点不回绕；out完整声明区间端点不回绕，非空非NULL，空可NULL。written与完整out不重叠（包括成功未使用尾部）。有输入切片/结构/嵌套名字时，必须在任何读写前验证完整描述符、元素乘法、端点、所需对齐、非空非NULL和完整对象别名；输入彼此如正文无禁止可互叠，只读输入与完整out/结果不得重叠。所有数据/枚举/标签/尺寸INVALID优先CAPACITY。失败out、计数或完整Result、输入全文不变；成功只写精确前缀/结果，尾部保持。先全预检及正确求长，在充分且有证明上界的局部区调用只读依赖，再最后发布用户out；不允许内部scratch越界或对合法容量不足输入panic。

文本严格ASCII，换行真实单LF，无NUL/注释/额外空行/隐式section/global/ret（任务另定声明除外）。涉及__dong_b<N>标签时N=0..MAX-1，MAX为NONE非法；数字复用已声明decimal_integer，不另写格式化。寄存器编号若有0..15参数，固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15；固定寄存器任务按正文集合测试，不强凑16矩阵。

测试只跑本任务checks：实际编译/链接/原生执行Dong debug与release，NASM ELF64/COFF都组装；原生C桥显式SysV，保护宿主栈/被调用者保存寄存器。COFF组装不冒充Win64调用ABI。只暂存本模块及已声明只读依赖的传递闭包，不引入整个lang根遮蔽坏源码。独立Python/C oracle，不用生产规划器输出当唯一期望。有限固定边界，每模式不超过24个主要原生向量（并发操作另按正文有限检查）；不做全笛卡尔积或性能基准。源码、说明、测试、只读依赖前后SHA256稳定，0skip才可验收。

每个描述符/端点/别名预检要独立可达，其它字段合法。written端点溢出用8对齐UINT64_MAX-7且合法空out，漏检坏体应安全返回CAPACITY而非非法解引用。初始化guard后再取快照，立刻观察失败全文/计数/guard、成功精确文本/长度/未用尾部；输入真实只读保护须检查系统调用成功，不能只声称只读。

至少保留两类真实坏Dong：一种完成构建、链接、正常原生执行后，由指定数值/内存/分支/链接后地址断言拒绝；一种容量不足提前写out或结果，由完整原子性断言拒绝。同夹具先跑好体。构建失败、崩溃、超时、文本不同、无关预检错误不能冒充指定语义负控；源码中缺锁/不同内存序等结构检查单列，不能假装单次正常运行证明并发语义。坏体所有内存访问在预留安全可访问区内，不破坏真实宿主栈/ret、不依靠越界或硬件异常拒绝。

本人客户端先worker MCP get_task/read_document读取最新rev和完整契约/归属，claim成功才执行；先完成已有领取/返修。产物在本人works/build/<编号>/<唯一目录>/，完成原编号交付写真实命令、tests/skips、模式/对象格式、全部输入SHA256、每种坏体实际观察/拒绝依据、未跑与剩余限制，再MCP submit。不得自行accept/integrate、提交/推送、运行OS/VM/全回归、启动模型CLI/定时器/关机，不用管理工具自动启动客户端。任务发布不代表实现或通过，最后由Codex独立复验再验收集成。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_u64_loop_function.dg`
- `cursor-works/src/bootstrap/nasm_u64_loop_function.md`
- `cursor-works/tests/test_nasm_u64_loop_function.py`
- `cursor-works/deliveries/CR34.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_u64_loop_function.py`

交付：`cursor-works/deliveries/CR34.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
