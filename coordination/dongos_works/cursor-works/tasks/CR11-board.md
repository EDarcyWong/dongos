# CR11 — 受限SysV函数栈帧序言与尾声发射

负责人：cursor。状态：待领取。

module bootstrap.nasm_function_frame。
两个接口 pub unsafe fn prologue(frame_bytes:usize,saved_mask:u64,out:[]u8,written:*usize)u64 与同签名epilogue。输出纯文本，不接入当前活动编译器。frame_bytes是局部区字节数，须0..4096且16的倍数；mask仅低5位允许，依次rbx,r12,r13,r14,r15。n=置位数，padding=n为奇数时8否则0，adjust=frame_bytes+padding；函数入口额外栈消耗total=8+8*n+adjust，total>4096 INVALID。这里是独立有界预算，不更换当前编译器栈布局/ABI约定。
严格prologue为b"push rbp\nmov rbp, rsp\n"，随后按上述顺序逐个b"push <reg>\n"，adjust>0时最后b"sub rsp, <adjust十进制>\n"；epilogue先在adjust>0时b"add rsp, <adjust>\n"，随后按逆序b"pop <reg>\n"，最后b"pop rbp\nret\n"。所有\n为真实单字节LF，没有section/global/标签/NUL；adjust=0不生成sub/add。复用CR4生成数字，两接口各自预检原子写。
约定SysV入口rsp%16=8，上述序言后调用点rsp%16=0，rbp保留入口栈基准。只支持上述5个callee-saved整数寄存器，无Win64 shadow space/SEH、浮点、动态对齐、红区、栈参数搬运、unwind或大对象，不声称完整函数生成。独立Python逐行期望与算术预算验证全部32mask、有限frame0/16/64/4080/4096、非法mask/对齐/超预算和容量边界；实际Dong序言+受控函数体+尾声NASM双格式组装。原生探针由独立汇编调用者用互异哨兵检查rbp及所保存寄存器、栈平衡与嵌套调用的栈对齐；函数体确实改写所选寄存器，再验证恢复。不声明COFF意味着Windows ABI可调用。两种坏Dong分别破坏奇数mask的padding及恢复顺序，必须被实际原生栈对齐/哨兵断言拒绝，不以崩溃当负控通过。

## 实现、测试与交付

这是L3生产后端的有界独立组件，完整代码生成器/自举尚未完成。实现必须是Dong，模块不导出C符号；C/Python/NASM仅作独立测试观察器，不用宿主实现替代Dong生产逻辑。无分配、全局可变状态或OS调用。仅修改声明的本人works文件，不改code/lang、活动编译器/内核、协调器或他人文件。Codex负责独立复验后集成。

unsafe调用方保证实际可访问的对象；实现仍须在读写前验证完整描述符、地址端点无溢出、长度乘法、自然对齐和所有别名规则。除任务另定外，OK=0、INVALID=1、CAPACITY=2；written非空8对齐，完整8字节与完整out分离；空out可NULL，非空out不可NULL。INVALID优先CAPACITY，失败out与written全文不变；成功只写精确前缀/计数，尾部不变。不以未使用前缀代替完整声明区间检查。先预检再写，子组件在局部暂存中调用以保证原子性。

只读依赖须已accepted/integrated且不修改。所有任务声明的依赖已集成；测试只暂存本组件和声明的只读依赖，避免当前主线同名模块遮蔽临时坏源码。测试实际编译并原生执行Dong debug/release，至少组装ELF64/COFF；有限固定边界与小规模确定性随机，Python/C独立期望，不堆大矩阵。双端guard、只读输入（如有）、输出尾部及失败全文立即核对。指针负例只触发预检，不非法解引用；其它前置条件必须合法，不能用另一非法字段遮蔽目标缺陷。

至少两种真实错误Dong副本成功编译、链接、原生执行，再被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置断言不算负控成功。只运行本任务声明的定向测试，产物在cursor-works/build/CR11/<唯一目录>，不运行OS/VM、全回归、性能基准、定时器、关机、提交或推送。不启动任何模型CLI，Cursor保持客户端手动执行。

先通过本人的worker MCP get_task/read_document查看最新rev、完整契约、归属与依赖，claim成功后才修改。完成后写cursor-works/deliveries/CR11.md，列出真实命令、tests/skip、模式/格式、源码测试SHA256、证据目录、负控拒绝原因和限制，未运行明确未运行；落盘后submit_task，不能自行accept/integrate。需要扩大归属时说明，不擅自扩范围。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_function_frame.dg`
- `cursor-works/src/bootstrap/nasm_function_frame.md`
- `cursor-works/tests/test_nasm_function_frame.py`
- `cursor-works/deliveries/CR11.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_function_frame.py`

交付：`cursor-works/deliveries/CR11.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## 2026-10-18 R1：补齐两接口预检与RBP原生观察

Codex正式定向3项通过、0skip、来源稳定，但未验收，MCP已登记rework。生产算法目前未发现缺陷，不要求重写生产实现。

1. 独立坏Dong只删除epilogue内的`if overlap(wp,8,op,out.len){return INVALID;}`，原全部3项仍通过（debug/release及原负控均运行）。现有14种invalid预检绝大多数只调用prologue，不能证明epilogue自己的完整描述符/原子性。请对两个接口分别覆盖written NULL、8对齐/端点、out端点、完整out前缀/尾部别名和INVALID优先CAPACITY；夹具其它条件合法，失败立即检查整块不变。对仅漏epilogue别名检查的真实坏源码，必须指定status/原子性断言拒绝，不扩大为大矩阵。
2. 原生调用者只检查rbx、r12～r15，没有给rbp设置/检查哨兵。Codex真实坏Dong把尾声`pop rbp`改为`pop rsi`，两模式成功编译、链接、执行，原`_probe_frame`仍返回(0,0)。请补独立调用者的RBP哨兵和显式调用前后栈基准观察，正确保存/恢复宿主RBP；重新计算调用点对齐。用这类保持栈平衡、只损坏RBP恢复的坏Dong，确认原生哨兵能拒绝，不能以文本不同、崩溃或宿主偶然使用RBP作为拒绝依据。

测试暂存本组件与只读CR4依赖，不引入整个lang源码根遮蔽坏模块。保留奇数padding、恢复顺序的既有有效负控。仅修原4个授权文件及本人build/CR11唯一产物，不占用Codex主线、CR8～CR10或其它任务。保留首交历史，补交写R1证据/tests/skip/hash/观察点，通过worker MCP重新提交；Cursor继续客户端手动执行。

独立证据：`D:\projects\2026\dongos\coordination\dongos_works\.local\reviews\cursor-deepseek-f8c79e198215`。`CR11-extra-audit.json`及同名log记录3项漏检；`CR11-rbp-audit.json`记录两模式真实RBP漏检，原坏源码/汇编/可执行文件在记录的native_dir。参见[本轮审查](../../reviews/2026-10-18-Cursor-DeepSeek-review.md)。


## 2026-10-18 原R1复验：仅剩written端点溢出

正式3项通过0skip、来源稳定；原R1的两接口别名预检、RBP哨兵/栈平衡及相应两类新增负控已关闭，保留原有效实现，不再重做。当前唯一未补齐的是原R1已要求的written端点溢出。独立坏Dong仅删除epilogue中`||!span(wp,8)`，原全部3项（含debug/release/全部原负控）仍通过，证据`D:\projects\2026\dongos\coordination\dongos_works\.local\reviews\D20-Codex-R1-a3d770c4afd0`中的CR11-written-endpoint-audit.json/log，原生产代码未改。

请仅对prologue/epilogue各补1个夹具：written指向`UINT64_MAX-7`（8对齐且完整8字节端点溢出），out为合法空描述符（可NULL、cap0），frame0/mask0，其它条件合法；正确结果必须INVALID且真实可访问out/计数guard保持不变。这样漏检坏实现只返回CAPACITY，不会非法解引用。新增仅漏epilogue written端点验证的实际坏Dong，成功编译/链接/执行后由该接口该路径的status断言拒绝；不能由奇地址、NULL、其它错误或崩溃遮蔽。保留原4种有效负控和已闭项，不扩矩阵、不改生产算法、不新增编号，只写原授权文件，补交通过MCP提交。


## 2026-10-18 复验快照中止：保留R2，重新提交即可

本次coordination验证job 6f6b7fc1ccb744a9b6a03942118c0c41在创建隔离副本时报告“复制期间源文件发生变化，本次未执行CLI；请重试”。没有执行定向测试，不是新的功能失败结论；runner同时检查整个项目挂载源码，不能据此认定是CR11自身文件在变。当前源码审查确认两接口26个预检包含written端点/空out以及对应坏Dong，既有RBP/别名等修复保留。

协调器已将状态恢复rework；请通过原worker MCP重新claim并submit现有R2交付（可先确认本人4文件已保存且不再编辑）。无需新增修订编号/数值矩阵，不要因这次快照失败重写生产算法。Codex将按新submitted状态再排定向复验，只有真实通过才验收。本次未给CR11登记验收/集成。证据：`D:\projects\2026\dongos\coordination\dongos_works\.local\reviews\L3-client-batch-ed559455-ea6`内CR11-snapshot-failure.json。
