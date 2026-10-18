# CR12 — 有界NASM整数内存装入

负责人：cursor。状态：待领取。

module bootstrap.nasm_integer_memory_load。
pub unsafe fn emit(destination:u64,base:u64,displacement:i64,width:u64,signed:bool,out:[]u8,written:*usize)u64。
width仅8/16/32/64，位移仅i32范围，base与destination均上述0..15。必须复用已集成CR8 nasm_memory_operand.encode生成完整地址操作数（只读CR4是其传递依赖），不重写位移/寄存器地址格式。输出固定单行：8/16位分别为`movsx <dest64>, byte/word <operand>\n`（signed）或`movzx <dest64>, byte/word <operand>\n`；32位signed为`movsxd <dest64>, dword <operand>\n`，unsigned为`mov <dest32>, dword <operand>\n`；64位两种signed都为`mov <dest64>, qword <operand>\n`。这里只含普通整数load，无原子/volatile额外语义，无界限检查；上游负责地址范围、对象生命周期和语言对齐。
有限原生探针用真实只读内存和可访问完整宽度，观察装入值的准确64位位模式、符号扩展/零扩展，含8/16/32高位、u64两端、负位移和dest==base（地址先读再写）。Python按little-endian有符号整数独立期望，读内存不得改变。坏Dong至少错误符号扩展并由实际装入结果拒绝；另一类CAPACITY时提前写以原子性拒绝。不要以加载RSP/RBP破坏宿主栈充当负控。

## 共用固定契约与归属

这是L3真实后端所需的独立Dong文本发射组件，不能代替完整代码生成/语言溢出检查/自举。源码必须Dong，不导出C符号，不用Python/C宿主实现代替生产逻辑；无分配、全局可变状态或OS调用。仅修改本人本任务4个授权文件，依赖只读，绝不改code/lang、活动编译器、内核、协调器、CR11或Codex语义主线。

寄存器编号0..15固定rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。32位名eax,ecx,edx,ebx,esp,ebp,esi,edi,r8d..r15d；16位ax,cx,dx,bx,sp,bp,si,di,r8w..r15w；低8位al,cl,dl,bl,spl,bpl,sil,dil,r8b..r15b，不支持ah等高8位。严格ASCII和单字节LF，不含section/global/标签/注释/空白多行/NUL；本任务规定几行就精确几行，成功尾部不变。

unsafe调用方保证对象真实可访问。仍必须在任何读写前检查written非空、8对齐、完整8字节端点不溢出；out完整描述符端点/非空非NULL；written完整8字节与完整声明out不重叠（包括输出未使用尾部）。空out可NULL。OK=0、INVALID=1、CAPACITY=2，所有参数/枚举/位移/描述符INVALID优先CAPACITY；失败out和written全文不变。先验证/计算，在局部暂存调用只读组件，最后一次写用户out；不得通过只看已用前缀逃过完整别名。长度加法不溢出。

测试要让每个目标预检独立可达：其它字段合法，真实guard/快照初始化后再取。written端点溢出使用8对齐UINT64_MAX-7和合法空out，正确INVALID，漏检坏实现返回CAPACITY，不能非法解引用；NULL/奇地址、out端点、对齐前缀/尾部别名、参数INVALID且out容量0亦独立覆盖。失败全文/双端guard、成功精确文本/计数/剩余尾部立即检查。C观察器对齐存储明确声明，不能用另一个非法字段掩盖目标。

测试实际编译、链接、原生执行Dong debug/release，NASM ELF64/COFF都组装。只暂存本组件和声明的已集成依赖，含坏源码时不引入整个lang根遮蔽临时模块。独立Python/C期望；有限固定边界优先、无需随机堆矩阵。文本/组装覆盖全部16个寄存器（可旋转配对，不要求全笛卡尔积）；受控原生仅用安全调用者保存寄存器的少量组合（每模式不超过24个主要向量），保留宿主ABI/栈，rsp/rbp写目标只组装。COFF组装不等于Win64 ABI可调用，原生C桥显式SysV。

至少两类真实坏Dong成功编译/链接/原生执行，再由指定数值/原子性断言拒绝；同一夹具先跑好实现。至少一类是原生实际结果错误，另一类容量失败提前写输出/计数，以全文/guard立即拒绝；若任务另定两类语义负控，则另保留一次原子性验证。构建失败、崩溃、超时、文本不同或无关预检错误不得冒充指定原生负控。坏源码执行的目标输入必须合法且不导致非法内存/栈访问。

先通过自己的worker MCP get_task/read_document读取最新rev、完整契约、依赖和归属，claim后执行。只运行本任务声明的定向测试，产物放本人works/build/编号/<唯一目录>/；无OS/VM/全回归/性能基准/定时器/关机/提交/推送，不启动模型CLI。客户端手动执行；完成后落盘原编号交付并通过MCP submit，不能自行accept/integrate。交付列真实命令、tests/skip、模式/对象格式、生产/测试SHA256、产物目录、每种负控实际观察/拒绝原因和未运行/剩余限制。依赖或归属问题先报告，不擅自扩大范围。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_integer_memory_load.dg`
- `cursor-works/src/bootstrap/nasm_integer_memory_load.md`
- `cursor-works/tests/test_nasm_integer_memory_load.py`
- `cursor-works/deliveries/CR12.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_integer_memory_load.py`

交付：`cursor-works/deliveries/CR12.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## 2026-10-18 R1：仅补原生输入只读与不变性观察

正式定向3项通过0skip、受测来源稳定，生产Dong算法目前未发现错误。已有符号/零扩展、负位移、dest==base、15种预检和两类真实坏Dong负控保留，不要求重写实现或扩大数值矩阵。

原任务明确要求真实只读输入；当前_probe_load用NASM `.data` 定义可写mem，C调用者只观察返回数值，没有保护或逐次比较输入、前后guard。Codex独立真实坏Dong把64位load发射成`xchg rax, qword [rcx]`，两模式成功编译/链接/原生执行，原_probe_load仍返回准确原内存值，说明该原生观察不拒绝写输入。精确文本测试会拒绝这个坏体，本轮没有声称整套3项漏检。

请仅修原native夹具：使用实际只读映射（Windows VirtualAlloc/VirtualProtect PAGE_READONLY、其它平台等效接口，检查保护成功），正确Dong文本在只读输入执行成功；调用前初始化真实存储/guard并快照，调用后立即比较完整输入与前后guard，不能只比较装入值。保证负位移调整后有效读取窗口和完整声明区间可访问；测试C/汇编桥仍遵守宿主SysV，不用RSP/RBP写目标执行。保留原signed-as-zx数值负控和提前写written原子性负控，在相同只读夹具上确认前者仍由真实数值断言拒绝。可记录权限控制作为额外证据，但不要把写只读页造成的崩溃当作原有语义负控通过。

只修改本任务4个授权文件和本人build/CR12唯一产物，生产算法若不需要修改则保持原字节。保留首交历史，补交通过自己的worker MCP claim/submit；不改变协调器/主线或其它任务。证据：`D:\projects\2026\dongos\coordination\dongos_works\.local\reviews\L3-client-batch-ed559455-ea6`内CR12-readonly-audit.json；actual_bad_Dong_text、原native_dir及两模式观察均保留。
