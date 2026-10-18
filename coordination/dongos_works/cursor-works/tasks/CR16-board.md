# CR16 — 64位整数一元与零比较发射

负责人：cursor。状态：待领取。

module bootstrap.nasm_integer_unary。
pub unsafe fn emit(operation:u64,register:u64,out:[]u8,written:*usize)u64。
operation仅0=wrapping neg、1=bitwise not、2=零比较取反，register仅0..15。0严格输出一行"neg <reg64>\n"；1一行"not <reg64>\n"；2严格三行"test <reg64>, <reg64>\nsete <reg8>\nmovzx <reg64>, <reg8>\n"。operation2结果在同一register中严格0/1（输入0返回1，其它64位位模式返回0）；不是固定RAX。只改目标寄存器及允许的flags。neg是模2^64，i64最小值保持位模式，不负责debug溢出门禁；零比较是机器级原语，不放宽语言逻辑非要求bool的前端规则。
有限原生覆盖0/1/全1/最高位/i64两端及RAX/R8等低字节编码，Python整数独立期望；全部16目标文本/双格式组装，rsp/rbp写目标不原生执行。至少真实坏Dong把not改成neg或翻转sete的数值负控（指定输入产生不同值）及容量失败提前写原子性负控。

## 共用固定契约与归属

这是L3真实后端所需的独立Dong文本发射组件，不能代替完整代码生成/语言溢出检查/自举。源码必须Dong，不导出C符号，不用Python/C宿主实现代替生产逻辑；无分配、全局可变状态或OS调用。仅修改本人本任务4个授权文件，依赖只读，绝不改code/lang、活动编译器、内核、协调器、CR11或Codex语义主线。

寄存器编号0..15固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。32位名eax,ecx,edx,ebx,esp,ebp,esi,edi,r8d..r15d；16位ax,cx,dx,bx,sp,bp,si,di,r8w..r15w；低8位al,cl,dl,bl,spl,bpl,sil,dil,r8b..r15b，不支持ah等高8位。严格ASCII和单字节LF，除任务另定的块标签外，不含section/global/注释/额外空行/NUL；本任务规定几行就精确几行，成功尾部不变。

unsafe调用方保证对象真实可访问。仍必须在任何读写前检查written非空、8对齐、完整8字节端点不溢出；out完整描述符端点/非空非NULL；written完整8字节与完整声明out不重叠（包括输出未使用尾部）。空out可NULL。OK=0、INVALID=1、CAPACITY=2，所有参数/枚举/位移/描述符INVALID优先CAPACITY；失败out和written全文不变。先验证/计算，在局部暂存调用只读组件，最后一次写用户out；不得通过只看已用前缀逃过完整别名。长度加法不溢出。

测试要让每个目标预检独立可达：其它字段合法，真实guard/快照初始化后再取。written端点溢出使用8对齐UINT64_MAX-7和合法空out，正确INVALID，漏检坏实现返回CAPACITY，不能非法解引用；NULL/奇地址、out端点、对齐前缀/尾部别名、参数INVALID且out容量0亦独立覆盖。失败全文/双端guard、成功精确文本/计数/剩余尾部立即检查。C观察器对齐存储明确声明，不能用另一个非法字段掩盖目标。

测试实际编译、链接、原生执行Dong debug/release，NASM ELF64/COFF都组装。只暂存本组件和声明的已集成依赖，含坏源码时不引入整个lang根遮蔽临时模块。独立Python/C期望；有限固定边界优先、无需随机堆矩阵。文本/组装覆盖全部16个寄存器（可旋转配对，不要求全笛卡尔积）；受控原生仅用安全调用者保存寄存器的少量组合（每模式不超过24个主要向量），保留宿主ABI/栈，rsp/rbp写目标只组装。COFF组装不等于Win64 ABI可调用，原生C桥显式SysV。

至少两类真实坏Dong成功编译/链接/原生执行，再由指定数值/原子性断言拒绝；同一夹具先跑好实现。至少一类是原生实际结果错误，另一类容量失败提前写输出/计数，以全文/guard立即拒绝；若任务另定两类语义负控，则另保留一次原子性验证。构建失败、崩溃、超时、文本不同或无关预检错误不得冒充指定原生负控。坏源码执行的目标输入必须合法且不导致非法内存/栈访问。

先通过自己的worker MCP get_task/read_document读取最新rev、完整契约、依赖和归属，claim后执行。只运行本任务声明的定向测试，产物放本人works/build/编号/<唯一目录>/；无OS/VM/全回归/性能基准/定时器/关机/提交/推送，不启动模型CLI。客户端手动执行；完成后落盘原编号交付并通过MCP submit，不能自行accept/integrate。交付列真实命令、tests/skip、模式/对象格式、生产/测试SHA256、产物目录、每种负控实际观察/拒绝原因和未运行/剩余限制。依赖或归属问题先报告，不擅自扩大范围。

## 可修改文件

- `cursor-works/src/bootstrap/nasm_integer_unary.dg`
- `cursor-works/src/bootstrap/nasm_integer_unary.md`
- `cursor-works/tests/test_nasm_integer_unary.py`
- `cursor-works/deliveries/CR16.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_integer_unary.py`

交付：`cursor-works/deliveries/CR16.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## Codex R1（2026-10-18）：补齐原生R8路径

2026-10-18，正式 job 6110c53f6fec4c709df7c0456177b4c9：3项通过、0skip，来源稳定。生产源码当前未发现缺陷；原交付与正式回执保留，未验收/集成。

原任务明确要求原生覆盖RAX/R8等低字节编码。当前 test_dong_assemble_and_native_unary 按 reg=(0,1,8,9,10)，每寄存器3种op、每op8个values依次追加，然后 native=native[:24]。首个寄存器RAX正好产生24项，截断后原生集合仅{0}；其它寄存器只在文本/组装阶段出现。静态重建清单见本轮证据CR16-native-selection-audit.json。没有声称生产R8实现有错，也没有声称16寄存器文本测试漏检。

请仅修改原有有限向量选择：显式小表或轮转，仍至多24主要原生向量/模式，至少同时有RAX和R8，三操作均覆盖，保留0/非零、最高位/全1及op2完整64位0/1检查。不要先构造大候选池再前缀截断而漏掉目标寄存器。交付列实际已执行的寄存器集合、操作与关键值，保留13预检、成功尾部/失败全文guard、双模式/双格式、not-as-neg数值负控与提前written原子性负控。不要求增加另一种负控、重写生产算法或扩大矩阵。

通过自己的worker MCP claim后执行，仅原CR16四授权文件和本人build/CR16唯一产物；原编号追加交付再submit，不自行验收。先保存已有CR17在途工作，再依客户端工作量处理，不能抢占其它任务。
