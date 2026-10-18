# C34 — 从固定帧槽建立SysV整数调用实参

负责人：claude。状态：待领取。


module bootstrap.nasm_sysv_call_args。
pub struct Result{pub written:usize,pub stack_bytes:usize} //16字节8对齐
pub unsafe fn setup(kinds:[]const u8,source_offsets:[]const usize,out:[]u8,result:*Result)u64。
pub unsafe fn cleanup(stack_bytes:usize,out:[]u8,written:*usize)u64。
kinds同C8：0单字标量、1两个INTEGER字聚合，其它INVALID；最多16参数且展开总字数<=16。source_offsets.len必须等于展开字数，每项8..4096且8倍数，可重复，指已规范化64位值在[rbp-offset]。不支持寄存器源/立即数/窄扩展/sret/SSE/varargs/Win64。不发射call或callee符号、不依赖C33。运行时上游保证rbp稳定且全部源8字节槽含于[rsp_before,rbp)已分配帧（允许槽首地址等于rsp_before），建立前rsp%16=0；新出栈参数区在rsp_before以下，与源槽分离。文本生成期间不访问这些运行时地址。
setup在局部Location[16]和Result实际调用已集成C8 plan，不重写ABI规划；out顺序严格：stack_bytes>0先"sub rsp, <bytes>\n"；按展开字原顺序输出所有STACK项，每项"mov rax, qword <source>\nmov qword <dest>, rax\n"；再按展开字原顺序输出REGISTER项，每项"mov <argreg>, qword <source>\n"。source必须复用CR8.encode(5,-offset)，dest复用CR8.encode(4,location.index)，argreg按C8 index0..5映射rdi,rsi,rdx,rcx,r8,r9。两个数字/sub字节复用CR4。先所有栈后寄存器避免scratch覆盖已装实参；只尾部padding，不输出padding写入。若无STACK项RAX保持；有STACK项允许RAX变；仅实参目的寄存器、RSP/flags按指令改变，其它GPR保持。空输入OK result两字段0，不写out。本项固定集合替代共用16寄存器矩阵。
cleanup仅接受0..128且16倍数，其它INVALID先于容量；0时OK written0无文本；正值精确"add rsp, <bytes>\n"（CR4十进制），仅RSP/flags改变。上游只传同次setup返回stack_bytes，不恢复实参/RAX或擦除栈数据。
setup使用完整16字节result（此点覆盖共约written8，仅cleanup用written8）：非NULL/8对齐/完整端点；kinds字节描述符、offsets usize数组8对齐及乘法/端点、完整out全部有效；输入彼此可重叠（均只读），但任何完整输入区间与out/result不重叠，out/result互不重叠。INVALID数据全部先于CAPACITY，失败out和完整result不变且输入不变。成功尾部不变。最多16字，每字两行保守55字节、sub至多13字节总<=893，2048局部充分；必须准确论证边界，不允许局部越界后panic。局部依赖/完整算长通过再发布。
原生<=12主要向量/模式：空/1/6/7/8/16标量，5标量+1双字+1标量（聚合整体落栈且末标量R9），6标量+双字，重复offset；含offset8/4096与16words最大文本。安全SysV NASM callee入口捕获6参数GPR、实际栈参数和rsp%16，cleanup后核对精确rsp恢复、源槽/周边guard/padding/callee-saved保持；不要用C自行重排调用参数。独立Python ABI oracle核对每字/rounded stack_bytes，不以C8输出当唯一期望。marker或观察器不能覆盖尚未捕获参数。
真实坏Dong将第一个栈槽0改8，用7标量（已分配16字节出栈区含padding）或更大安全区域确保正常原生执行，由callee入口第一栈参数错误拒绝，不能破坏ret/宿主帧或将崩溃当成功；另setup与cleanup容量提前写原子性负控。声明kinds与offsets输入实际只读保护成功；完整Result尾部别名/端点、offset描述符/非法值、words越界、容量精确/少1/0/成功尾部、空输入均独立覆盖，debug/release与ELF64/COFF。先完成已领取/返修C31 R1，再领取新项。

## 共用固定契约与归属

这是L3真实后端所需的独立Dong文本发射组件，不能代替完整代码生成/语言溢出检查/自举。源码必须Dong，不导出C符号，不用Python/C宿主实现代替生产逻辑；无分配、全局可变状态或OS调用。仅修改本人本任务4个授权文件，依赖只读，绝不改code/lang、活动编译器、内核、协调器、CR11或Codex语义主线。

寄存器编号0..15固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。32位名eax,ecx,edx,ebx,esp,ebp,esi,edi,r8d..r15d；16位ax,cx,dx,bx,sp,bp,si,di,r8w..r15w；低8位al,cl,dl,bl,spl,bpl,sil,dil,r8b..r15b，不支持ah等高8位。严格ASCII和单字节LF，除任务另定的块标签外，不含section/global/注释/额外空行/NUL；本任务规定几行就精确几行，成功尾部不变。

unsafe调用方保证对象真实可访问。仍必须在任何读写前检查written非空、8对齐、完整8字节端点不溢出；out完整描述符端点/非空非NULL；written完整8字节与完整声明out不重叠（包括输出未使用尾部）。空out可NULL。OK=0、INVALID=1、CAPACITY=2，所有参数/枚举/位移/描述符INVALID优先CAPACITY；失败out和written全文不变。先验证/计算，在局部暂存调用只读组件，最后一次写用户out；不得通过只看已用前缀逃过完整别名。长度加法不溢出。

测试要让每个目标预检独立可达：其它字段合法，真实guard/快照初始化后再取。written端点溢出使用8对齐UINT64_MAX-7和合法空out，正确INVALID，漏检坏实现返回CAPACITY，不能非法解引用；NULL/奇地址、out端点、对齐前缀/尾部别名、参数INVALID且out容量0亦独立覆盖。失败全文/双端guard、成功精确文本/计数/剩余尾部立即检查。C观察器对齐存储明确声明，不能用另一个非法字段掩盖目标。

测试实际编译、链接、原生执行Dong debug/release，NASM ELF64/COFF都组装。只暂存本组件和声明的已集成依赖，含坏源码时不引入整个lang根遮蔽临时模块。独立Python/C期望；有限固定边界优先、无需随机堆矩阵。文本/组装覆盖全部16个寄存器（可旋转配对，不要求全笛卡尔积）；受控原生仅用安全调用者保存寄存器的少量组合（每模式不超过24个主要向量），保留宿主ABI/栈，rsp/rbp写目标只组装。COFF组装不等于Win64 ABI可调用，原生C桥显式SysV。

至少两类真实坏Dong成功编译/链接/原生执行，再由指定数值/原子性断言拒绝；同一夹具先跑好实现。至少一类是原生实际结果错误，另一类容量失败提前写输出/计数，以全文/guard立即拒绝；若任务另定两类语义负控，则另保留一次原子性验证。构建失败、崩溃、超时、文本不同或无关预检错误不得冒充指定原生负控。坏源码执行的目标输入必须合法且不导致非法内存/栈访问。

先通过自己的worker MCP get_task/read_document读取最新rev、完整契约、依赖和归属，claim后执行。只运行本任务声明的定向测试，产物放本人works/build/编号/<唯一目录>/；无OS/VM/全回归/性能基准/定时器/关机/提交/推送，不启动模型CLI。客户端手动执行；完成后落盘原编号交付并通过MCP submit，不能自行accept/integrate。交付列真实命令、tests/skip、模式/对象格式、生产/测试SHA256、产物目录、每种负控实际观察/拒绝原因和未运行/剩余限制。依赖或归属问题先报告，不擅自扩大范围。

## 可修改文件

- `claude-works/src/bootstrap/nasm_sysv_call_args.dg`
- `claude-works/src/bootstrap/nasm_sysv_call_args.md`
- `claude-works/tests/test_nasm_sysv_call_args.py`
- `claude-works/deliveries/C34.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_sysv_call_args.py`

交付：`claude-works/deliveries/C34.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
