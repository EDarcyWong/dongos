# C30 — NASM缩放索引地址操作数

负责人：claude。状态：待领取。

module bootstrap.nasm_indexed_operand。
pub unsafe fn encode(base:u64,index:u64,scale:u64,displacement:i64,out:[]u8,written:*usize)u64。
base为0..15；index为0..15但禁止4/RSP（12/R12合法）；scale仅1/2/4/8；位移仅i32范围；其它INVALID且优先CAPACITY。严格输出ASCII操作数，无LF/NUL："[<base64> + <index64>*<scale十进制>]"，disp正则在右括号前加" + <正数>"，负则加" - <绝对值>"，disp0省略位移项。scale=1也保留*1；base==index合法；无无基址、RIP、符号、segment或addr32形式。不修改CR8现有base+disp操作数或CR15 LEA接口，这是新增的数组索引寻址原语。
scale与位移数字复用已集成CR4 decimal_integer到局部scratch；全部预检/总长和容量通过后才写用户out。MAX_LINE采用明确足够的固定局部界限或checked求长，不依赖宿主格式化。
有限旋转文本/ELF64+COFF组装覆盖16个base、每个合法index（必须有R12且RSP作index独立INVALID）、4种scale及位移0/正负/i32两端，不做全笛卡尔积。原生只用安全寄存器，在真实Dong输出操作数前加独立LEA执行（不解引用结果），每模式至多24个向量；独立任意精度期望(base+index*scale+disp)模2^64，含base==index及溢出环绕，捕获非目的输入寄存器和flags保持。RSP/RBP参与的地址只组装。
真实坏Dong把scale4错误写成2等，使用scale4且index非0输入，必须正常原生执行后由LEA结果拒绝；不能停在文本差异。另容量失败提前写负控。

## 共用固定契约与归属

这是L3真实后端所需的独立Dong文本发射组件，不能代替完整代码生成/语言溢出检查/自举。源码必须Dong，不导出C符号，不用Python/C宿主实现代替生产逻辑；无分配、全局可变状态或OS调用。仅修改本人本任务4个授权文件，依赖只读，绝不改code/lang、活动编译器、内核、协调器、CR11或Codex语义主线。

寄存器编号0..15固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。32位名eax,ecx,edx,ebx,esp,ebp,esi,edi,r8d..r15d；16位ax,cx,dx,bx,sp,bp,si,di,r8w..r15w；低8位al,cl,dl,bl,spl,bpl,sil,dil,r8b..r15b，不支持ah等高8位。严格ASCII和单字节LF，除任务另定的块标签外，不含section/global/注释/额外空行/NUL；本任务规定几行就精确几行，成功尾部不变。

unsafe调用方保证对象真实可访问。仍必须在任何读写前检查written非空、8对齐、完整8字节端点不溢出；out完整描述符端点/非空非NULL；written完整8字节与完整声明out不重叠（包括输出未使用尾部）。空out可NULL。OK=0、INVALID=1、CAPACITY=2，所有参数/枚举/位移/描述符INVALID优先CAPACITY；失败out和written全文不变。先验证/计算，在局部暂存调用只读组件，最后一次写用户out；不得通过只看已用前缀逃过完整别名。长度加法不溢出。

测试要让每个目标预检独立可达：其它字段合法，真实guard/快照初始化后再取。written端点溢出使用8对齐UINT64_MAX-7和合法空out，正确INVALID，漏检坏实现返回CAPACITY，不能非法解引用；NULL/奇地址、out端点、对齐前缀/尾部别名、参数INVALID且out容量0亦独立覆盖。失败全文/双端guard、成功精确文本/计数/剩余尾部立即检查。C观察器对齐存储明确声明，不能用另一个非法字段掩盖目标。

测试实际编译、链接、原生执行Dong debug/release，NASM ELF64/COFF都组装。只暂存本组件和声明的已集成依赖，含坏源码时不引入整个lang根遮蔽临时模块。独立Python/C期望；有限固定边界优先、无需随机堆矩阵。文本/组装覆盖全部16个寄存器（可旋转配对，不要求全笛卡尔积）；受控原生仅用安全调用者保存寄存器的少量组合（每模式不超过24个主要向量），保留宿主ABI/栈，rsp/rbp写目标只组装。COFF组装不等于Win64 ABI可调用，原生C桥显式SysV。

至少两类真实坏Dong成功编译/链接/原生执行，再由指定数值/原子性断言拒绝；同一夹具先跑好实现。至少一类是原生实际结果错误，另一类容量失败提前写输出/计数，以全文/guard立即拒绝；若任务另定两类语义负控，则另保留一次原子性验证。构建失败、崩溃、超时、文本不同或无关预检错误不得冒充指定原生负控。坏源码执行的目标输入必须合法且不导致非法内存/栈访问。

先通过自己的worker MCP get_task/read_document读取最新rev、完整契约、依赖和归属，claim后执行。只运行本任务声明的定向测试，产物放本人works/build/编号/<唯一目录>/；无OS/VM/全回归/性能基准/定时器/关机/提交/推送，不启动模型CLI。客户端手动执行；完成后落盘原编号交付并通过MCP submit，不能自行accept/integrate。交付列真实命令、tests/skip、模式/对象格式、生产/测试SHA256、产物目录、每种负控实际观察/拒绝原因和未运行/剩余限制。依赖或归属问题先报告，不擅自扩大范围。

## 可修改文件

- `claude-works/src/bootstrap/nasm_indexed_operand.dg`
- `claude-works/src/bootstrap/nasm_indexed_operand.md`
- `claude-works/tests/test_nasm_indexed_operand.py`
- `claude-works/deliveries/C30.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_indexed_operand.py`

交付：`claude-works/deliveries/C30.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
