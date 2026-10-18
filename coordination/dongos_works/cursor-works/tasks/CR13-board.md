# CR13 — 有界NASM整数内存存储

负责人：cursor。状态：待领取。

module bootstrap.nasm_integer_memory_store。
pub unsafe fn emit(source:u64,base:u64,displacement:i64,width:u64,out:[]u8,written:*usize)u64。
width仅8/16/32/64，位移仅i32范围。必须复用CR8 nasm_memory_operand（及传递CR4只读依赖）。严格单行`mov <size> <operand>, <source-width-register>\n`，size依次byte/word/dword/qword，源分别low8/16/32/64名称。准确写源的低width位，不改变任何寄存器。无原子/volatile、对象界限/生命周期或语言对齐处理。
有限真实原生探针向有前后guard的可写窗口写入，独立观察目标width字节little-endian低位和所有非目标字节/输入寄存器保留，含宽度边界、负位移、截断高位与base==source（此时被写数值是受控地址位模式，独立记录真实地址期望）。不得写真实宿主栈或只读页。全部寄存器名称组装；原生用少量安全组合。坏Dong错误宽度/源低位寄存器必须成功原生执行并由内容/目标边界断言拒绝（受控内存预留足够空间，不能靠越界崩溃）；另CAPACITY提前写负控。

## 共用固定契约与归属

这是L3真实后端所需的独立Dong文本发射组件，不能代替完整代码生成/语言溢出检查/自举。源码必须Dong，不导出C符号，不用Python/C宿主实现代替生产逻辑；无分配、全局可变状态或OS调用。仅修改本人本任务4个授权文件，依赖只读，绝不改code/lang、活动编译器、内核、协调器、CR11或Codex语义主线。

寄存器编号0..15固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。32位名eax,ecx,edx,ebx,esp,ebp,esi,edi,r8d..r15d；16位ax,cx,dx,bx,sp,bp,si,di,r8w..r15w；低8位al,cl,dl,bl,spl,bpl,sil,dil,r8b..r15b，不支持ah等高8位。严格ASCII和单字节LF，不含section/global/标签/注释/空白多行/NUL；本任务规定几行就精确几行，成功尾部不变。

unsafe调用方保证对象真实可访问。仍必须在任何读写前检查written非空、8对齐、完整8字节端点不溢出；out完整描述符端点/非空非NULL；written完整8字节与完整声明out不重叠（包括输出未使用尾部）。空out可NULL。OK=0、INVALID=1、CAPACITY=2，所有参数/枚举/位移/描述符INVALID优先CAPACITY；失败out和written全文不变。先验证/计算，在局部暂存调用只读组件，最后一次写用户out；不得通过只看已用前缀逃过完整别名。长度加法不溢出。

测试要让每个目标预检独立可达：其它字段合法，真实guard/快照初始化后再取。written端点溢出使用8对齐UINT64_MAX-7和合法空out，正确INVALID，漏检坏实现返回CAPACITY，不能非法解引用；NULL/奇地址、out端点、对齐前缀/尾部别名、参数INVALID且out容量0亦独立覆盖。失败全文/双端guard、成功精确文本/计数/剩余尾部立即检查。C观察器对齐存储明确声明，不能用另一个非法字段掩盖目标。

测试实际编译、链接、原生执行Dong debug/release，NASM ELF64/COFF都组装。只暂存本组件和声明的已集成依赖，含坏源码时不引入整个lang根遮蔽临时模块。独立Python/C期望；有限固定边界优先、无需随机堆矩阵。文本/组装覆盖全部16个寄存器（可旋转配对，不要求全笛卡尔积）；受控原生仅用安全调用者保存寄存器的少量组合（每模式不超过24个主要向量），保留宿主ABI/栈，rsp/rbp写目标只组装。COFF组装不等于Win64 ABI可调用，原生C桥显式SysV。

至少两类真实坏Dong成功编译/链接/原生执行，再由指定数值/原子性断言拒绝；同一夹具先跑好实现。至少一类是原生实际结果错误，另一类容量失败提前写输出/计数，以全文/guard立即拒绝；若任务另定两类语义负控，则另保留一次原子性验证。构建失败、崩溃、超时、文本不同或无关预检错误不得冒充指定原生负控。坏源码执行的目标输入必须合法且不导致非法内存/栈访问。

先通过自己的worker MCP get_task/read_document读取最新rev、完整契约、依赖和归属，claim后执行。只运行本任务声明的定向测试，产物放本人works/build/编号/<唯一目录>/；无OS/VM/全回归/性能基准/定时器/关机/提交/推送，不启动模型CLI。客户端手动执行；完成后落盘原编号交付并通过MCP submit，不能自行accept/integrate。交付列真实命令、tests/skip、模式/对象格式、生产/测试SHA256、产物目录、每种负控实际观察/拒绝原因和未运行/剩余限制。依赖或归属问题先报告，不擅自扩大范围。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_integer_memory_store.dg`
- `cursor-works/src/bootstrap/nasm_integer_memory_store.md`
- `cursor-works/tests/test_nasm_integer_memory_store.py`
- `cursor-works/deliveries/CR13.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_integer_memory_store.py`

交付：`cursor-works/deliveries/CR13.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## Codex 复验 R1（2026-10-18）

正式 job 9ec3c63188d14abaaa85f05f5eeaced2：3 项通过、0 skip、来源稳定，原交付及回执保留。生产源码未发现缺陷，尚未验收。

原任务要求原生检查输入寄存器保留。当前 _probe_store 在发射片段前保存 base 地址，片段后直接 ret；返回值仅为地址与 48 字节内存，因此没有检查片段后寄存器值。

在现有少量安全 SysV 向量中，于实际片段前后捕获受控输入寄存器并比较完整 64 位值；base==source 使用已经记录的真实地址期望。捕获桩保持宿主 ABI/栈正确，不能用捕获本身覆盖尚未记录的寄存器。保留已有内存目标/双端 guard、负位移/截断/base==source、双模式/双格式、坏宽度及提前写负控，不扩大矩阵，不重写 Dong 算法。补交原 CR13，通过 worker MCP claim/submit，不自行验收。

这是独立原生观察的缺项，不声称现有精确文本断言会接受多余指令，也不声称生产实现已破坏寄存器。
