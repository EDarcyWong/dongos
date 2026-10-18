# CR8 — NASM基址加有符号位移操作数

负责人：cursor。状态：待领取。

module bootstrap.nasm_memory_operand。
pub unsafe fn encode(base:u64, displacement:i64, out:[]u8, written:*usize)u64。
寄存器编号固定0..15依次为rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。
displacement只允许[-2147483648,2147483647]，越界INVALID不截断。严格文本：[<reg>]（零）；[<reg> + <正位移十进制>]；[<reg> - <负位移绝对值十进制>]。例如base=5,disp=-8输出b"[rbp - 8]"。没有大小前缀、LF或NUL；括号内部空格严格如此。只支持一个64位基址，不支持索引/比例/RIP/符号。必须复用已集成bootstrap.decimal_integer编码绝对值，先检查有界位移再安全求绝对值。
用独立Python格式期望检查16个寄存器、0/±1/±8、两端点和越界、容量恰好/少一/多余、完整输出别名及计数对齐。实际Dong文本放入NASM lea目的寄存器,<文本>，两种对象格式组装；原生探针用有限输入基址及安全寄存器，观察lea计算结果等于64位模加法而不解引用。rsp/rbp等影响栈的基址仅作组装验证；临时执行探针必须保持宿主栈和ABI。两种坏源码至少覆盖漏负号/位移，以及容量不足先写输出。LM8只作可选给定数据补充，不能依赖它完成。

## 实现、测试与交付

这是L3生产后端的有界独立组件，完整代码生成器/自举尚未完成。实现必须是Dong，模块不导出C符号；C/Python/NASM仅作独立测试观察器，不用宿主实现替代Dong生产逻辑。无分配、全局可变状态或OS调用。仅修改声明的本人works文件，不改code/lang、活动编译器/内核、协调器或他人文件。Codex负责独立复验后集成。

unsafe调用方保证实际可访问的对象；实现仍须在读写前验证完整描述符、地址端点无溢出、长度乘法、自然对齐和所有别名规则。除任务另定外，OK=0、INVALID=1、CAPACITY=2；written非空8对齐，完整8字节与完整out分离；空out可NULL，非空out不可NULL。INVALID优先CAPACITY，失败out与written全文不变；成功只写精确前缀/计数，尾部不变。不以未使用前缀代替完整声明区间检查。先预检再写，子组件在局部暂存中调用以保证原子性。

只读依赖须已accepted/integrated且不修改。所有任务声明的依赖已集成；测试只暂存本组件和声明的只读依赖，避免当前主线同名模块遮蔽临时坏源码。测试实际编译并原生执行Dong debug/release，至少组装ELF64/COFF；有限固定边界与小规模确定性随机，Python/C独立期望，不堆大矩阵。双端guard、只读输入（如有）、输出尾部及失败全文立即核对。指针负例只触发预检，不非法解引用；其它前置条件必须合法，不能用另一非法字段遮蔽目标缺陷。

至少两种真实错误Dong副本成功编译、链接、原生执行，再被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置断言不算负控成功。只运行本任务声明的定向测试，产物在cursor-works/build/CR8/<唯一目录>，不运行OS/VM、全回归、性能基准、定时器、关机、提交或推送。不启动任何模型CLI，Cursor保持客户端手动执行。

先通过本人的worker MCP get_task/read_document查看最新rev、完整契约、归属与依赖，claim成功后才修改。完成后写cursor-works/deliveries/CR8.md，列出真实命令、tests/skip、模式/格式、源码测试SHA256、证据目录、负控拒绝原因和限制，未运行明确未运行；落盘后submit_task，不能自行accept/integrate。需要扩大归属时说明，不擅自扩范围。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_memory_operand.dg`
- `cursor-works/src/bootstrap/nasm_memory_operand.md`
- `cursor-works/tests/test_nasm_memory_operand.py`
- `cursor-works/deliveries/CR8.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_memory_operand.py`

交付：`cursor-works/deliveries/CR8.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
