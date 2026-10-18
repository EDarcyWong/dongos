# C29 — RIP相对内部符号地址发射

负责人：claude。状态：待领取。

module bootstrap.nasm_symbol_address。
pub unsafe fn emit(destination:u64,module_name:[]const u8,item_name:[]const u8,out:[]u8,written:*usize)u64。
destination仅0..15；两个名字各1..64原始字节，允许NUL/非ASCII/标点，0或>64 INVALID。复用已集成CR3 nasm_symbol.encode，用至多266字节局部scratch，严格单行"lea <dest64>, [rel <encoded-symbol>]\n"。不散列、不截断、不读符号内容、不用绝对地址常数。这与CR15基址+位移LEA（不支持RIP/符号）不同，也与C25直接调用不同。
完整written/out和两输入描述符端点预检；written的8字节及完整out各自与两完整输入分离，两个输入允许重叠；全部INVALID（含destination）优先CAPACITY，失败输入/out/written全文不变。名字放真实只读页，检查保护设置成功并核对原始内容；written对输入的对齐前缀/未使用尾部别名必须独立到达，不能被未对齐或非法名字掩盖。
独立Python bytes.hex算期望；有限短/64字节/NUL/非ASCII/歧义拼接对和容量边界；16目的名旋转文本/双格式组装。实际原生把编码符号独立定义为至少8字节可读的只读数据及guard，安全目的寄存器实际LEA的返回地址须等于独立C/汇编取得的同符号地址，而不是只比较解引用内容；数据/guard、其它受控输入寄存器保持，flags不变。测试只暂存本模块与CR3；原生每模式至多24主向量。
真实坏Dong将LEA改为MOV但保留合法[rel symbol]，由返回的实际地址数值不等于独立符号地址拒绝；坏体可以读取这至少8字节数据，观察器不可再解引用错误返回地址以崩溃冒充失败。另容量提前写原子性负控。

## 共用固定契约与归属

这是L3真实后端所需的独立Dong文本发射组件，不能代替完整代码生成/语言溢出检查/自举。源码必须Dong，不导出C符号，不用Python/C宿主实现代替生产逻辑；无分配、全局可变状态或OS调用。仅修改本人本任务4个授权文件，依赖只读，绝不改code/lang、活动编译器、内核、协调器、CR11或Codex语义主线。

寄存器编号0..15固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。32位名eax,ecx,edx,ebx,esp,ebp,esi,edi,r8d..r15d；16位ax,cx,dx,bx,sp,bp,si,di,r8w..r15w；低8位al,cl,dl,bl,spl,bpl,sil,dil,r8b..r15b，不支持ah等高8位。严格ASCII和单字节LF，除任务另定的块标签外，不含section/global/注释/额外空行/NUL；本任务规定几行就精确几行，成功尾部不变。

unsafe调用方保证对象真实可访问。仍必须在任何读写前检查written非空、8对齐、完整8字节端点不溢出；out完整描述符端点/非空非NULL；written完整8字节与完整声明out不重叠（包括输出未使用尾部）。空out可NULL。OK=0、INVALID=1、CAPACITY=2，所有参数/枚举/位移/描述符INVALID优先CAPACITY；失败out和written全文不变。先验证/计算，在局部暂存调用只读组件，最后一次写用户out；不得通过只看已用前缀逃过完整别名。长度加法不溢出。

测试要让每个目标预检独立可达：其它字段合法，真实guard/快照初始化后再取。written端点溢出使用8对齐UINT64_MAX-7和合法空out，正确INVALID，漏检坏实现返回CAPACITY，不能非法解引用；NULL/奇地址、out端点、对齐前缀/尾部别名、参数INVALID且out容量0亦独立覆盖。失败全文/双端guard、成功精确文本/计数/剩余尾部立即检查。C观察器对齐存储明确声明，不能用另一个非法字段掩盖目标。

测试实际编译、链接、原生执行Dong debug/release，NASM ELF64/COFF都组装。只暂存本组件和声明的已集成依赖，含坏源码时不引入整个lang根遮蔽临时模块。独立Python/C期望；有限固定边界优先、无需随机堆矩阵。文本/组装覆盖全部16个寄存器（可旋转配对，不要求全笛卡尔积）；受控原生仅用安全调用者保存寄存器的少量组合（每模式不超过24个主要向量），保留宿主ABI/栈，rsp/rbp写目标只组装。COFF组装不等于Win64 ABI可调用，原生C桥显式SysV。

至少两类真实坏Dong成功编译/链接/原生执行，再由指定数值/原子性断言拒绝；同一夹具先跑好实现。至少一类是原生实际结果错误，另一类容量失败提前写输出/计数，以全文/guard立即拒绝；若任务另定两类语义负控，则另保留一次原子性验证。构建失败、崩溃、超时、文本不同或无关预检错误不得冒充指定原生负控。坏源码执行的目标输入必须合法且不导致非法内存/栈访问。

先通过自己的worker MCP get_task/read_document读取最新rev、完整契约、依赖和归属，claim后执行。只运行本任务声明的定向测试，产物放本人works/build/编号/<唯一目录>/；无OS/VM/全回归/性能基准/定时器/关机/提交/推送，不启动模型CLI。客户端手动执行；完成后落盘原编号交付并通过MCP submit，不能自行accept/integrate。交付列真实命令、tests/skip、模式/对象格式、生产/测试SHA256、产物目录、每种负控实际观察/拒绝原因和未运行/剩余限制。依赖或归属问题先报告，不擅自扩大范围。

## 可修改文件

- `claude-works/src/bootstrap/nasm_symbol_address.dg`
- `claude-works/src/bootstrap/nasm_symbol_address.md`
- `claude-works/tests/test_nasm_symbol_address.py`
- `claude-works/deliveries/C29.md`

## 定向验收

- `discover:claude-works/tests:test_nasm_symbol_address.py`

交付：`claude-works/deliveries/C29.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## Codex 复验：快照中止，原交付重提（2026-10-18）

2026-10-18，正式job cf5b3a5b9e564e968012b390de507930 在创建隔离源码副本时报告“复制期间源文件发生变化，本次未执行CLI；请重试”。定向测试未运行，不是C29功能失败；快照包含整个项目及挂载works，不能据此认定C29自己的文件正在改动。

源码/契约与完整测试已审查，暂未发现生产逻辑缺陷，但本次没有正式通过回执，未登记验收/集成。原四授权文件、首交与历史证据保留。

请通过本人worker MCP重新claim当前rework任务，确认四文件已保存且不再改动后重新submit现有交付，以重新排队正式定向复验。无需新修订编号、重写算法或增加矩阵；仅说明快照重提并保留原交付。Codex待实际正式测试通过后验收/集成，不绕过MCP状态或指纹门禁。

本轮证据：D:/projects/2026/dongos/coordination/dongos_works/.local/reviews/Claude-C26-C29-0ef5b39b，含before和失败回执。
