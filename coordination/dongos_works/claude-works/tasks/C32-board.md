# C32 — 固定寄存器字节复制与清零发射

负责人：claude。状态：待领取。

module bootstrap.nasm_memory_intrinsic。
pub const COPY:u64=0;pub const ZERO:u64=1;
pub unsafe fn emit(operation:u64,out:[]u8,written:*usize)u64。
operation仅0/1，其它INVALID且优先CAPACITY。COPY严格一行"rep movsb\n"；ZERO严格两行"xor eax, eax\nrep stosb\n"。固定运行时输入RDI=目的指针、RCX=字节数，COPY另RSI=源指针；调用方保证DF=0、真实区间可访问，COPY源目的不重叠（不是memmove），对象边界/生命周期及语言检查由上游负责。
执行后COPY将RCX归0、RDI/RSI各前移原count，RAX与其余寄存器和flags保持；ZERO将RCX归0、RDI前移count，RAX=0，RSI与其余寄存器保持，算术flags按xor允许改变，DF仍须0。count=0不访问源目的内存，COPY时指针保持、ZERO仍先清RAX。此为内存内建后端发射，不重写已验收D1标准库，也不修改当前活动编译器内建lowering。
本项固定寄存器，无16寄存器矩阵。有限实际原生向量含count0/1/7/8/15/16/31/64/65的选定组合，≤24/模式；输入/输出前后guard及完整非目标字节核对，COPY源完整快照且实际只读保护成功，ZERO目的预填非零；捕获RCX/RSI/RDI/RAX及其它受控寄存器，对count0以NULL源/目的执行（不额外解引用）并检查无访问。独立字节数组期望。SysV桩建立DF=0并保留宿主callee-saved，返回时满足宿主ABI；ELF64/COFF均组装。
真实坏Dong将COPY发成rep stosb，先给AL独立非匹配哨兵，目标区大小充足，必须正常执行后由复制字节不符拒绝；保留真实好体先在同一夹具通过。另文本out容量不足提前写的原子性负控；错误实现不能访问真实宿主栈、制造越界/只读写崩溃或用无关预检失败代替语义拒绝。

## 共用固定契约与归属

这是L3真实后端所需的独立Dong文本发射组件，不能代替完整代码生成/语言溢出检查/自举。源码必须Dong，不导出C符号，不用Python/C宿主实现代替生产逻辑；无分配、全局可变状态或OS调用。仅修改本人本任务4个授权文件，依赖只读，绝不改code/lang、活动编译器、内核、协调器、CR11或Codex语义主线。

寄存器编号0..15固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。32位名eax,ecx,edx,ebx,esp,ebp,esi,edi,r8d..r15d；16位ax,cx,dx,bx,sp,bp,si,di,r8w..r15w；低8位al,cl,dl,bl,spl,bpl,sil,dil,r8b..r15b，不支持ah等高8位。严格ASCII和单字节LF，除任务另定的块标签外，不含section/global/注释/额外空行/NUL；本任务规定几行就精确几行，成功尾部不变。

unsafe调用方保证对象真实可访问。仍必须在任何读写前检查written非空、8对齐、完整8字节端点不溢出；out完整描述符端点/非空非NULL；written完整8字节与完整声明out不重叠（包括输出未使用尾部）。空out可NULL。OK=0、INVALID=1、CAPACITY=2，所有参数/枚举/位移/描述符INVALID优先CAPACITY；失败out和written全文不变。先验证/计算，在局部暂存调用只读组件，最后一次写用户out；不得通过只看已用前缀逃过完整别名。长度加法不溢出。

测试要让每个目标预检独立可达：其它字段合法，真实guard/快照初始化后再取。written端点溢出使用8对齐UINT64_MAX-7和合法空out，正确INVALID，漏检坏实现返回CAPACITY，不能非法解引用；NULL/奇地址、out端点、对齐前缀/尾部别名、参数INVALID且out容量0亦独立覆盖。失败全文/双端guard、成功精确文本/计数/剩余尾部立即检查。C观察器对齐存储明确声明，不能用另一个非法字段掩盖目标。

测试实际编译、链接、原生执行Dong debug/release，NASM ELF64/COFF都组装。只暂存本组件和声明的已集成依赖，含坏源码时不引入整个lang根遮蔽临时模块。独立Python/C期望；有限固定边界优先、无需随机堆矩阵。文本/组装覆盖全部16个寄存器（可旋转配对，不要求全笛卡尔积）；受控原生仅用安全调用者保存寄存器的少量组合（每模式不超过24个主要向量），保留宿主ABI/栈，rsp/rbp写目标只组装。COFF组装不等于Win64 ABI可调用，原生C桥显式SysV。

至少两类真实坏Dong成功编译/链接/原生执行，再由指定数值/原子性断言拒绝；同一夹具先跑好实现。至少一类是原生实际结果错误，另一类容量失败提前写输出/计数，以全文/guard立即拒绝；若任务另定两类语义负控，则另保留一次原子性验证。构建失败、崩溃、超时、文本不同或无关预检错误不得冒充指定原生负控。坏源码执行的目标输入必须合法且不导致非法内存/栈访问。

先通过自己的worker MCP get_task/read_document读取最新rev、完整契约、依赖和归属，claim后执行。只运行本任务声明的定向测试，产物放本人works/build/编号/<唯一目录>/；无OS/VM/全回归/性能基准/定时器/关机/提交/推送，不启动模型CLI。客户端手动执行；完成后落盘原编号交付并通过MCP submit，不能自行accept/integrate。交付列真实命令、tests/skip、模式/对象格式、生产/测试SHA256、产物目录、每种负控实际观察/拒绝原因和未运行/剩余限制。依赖或归属问题先报告，不擅自扩大范围。

## 可修改文件

- `claude-works/src/bootstrap/nasm_memory_intrinsic.dg`
- `claude-works/src/bootstrap/nasm_memory_intrinsic.md`
- `claude-works/tests/test_nasm_memory_intrinsic.py`
- `claude-works/deliveries/C32.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_memory_intrinsic.py`

交付：`claude-works/deliveries/C32.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
