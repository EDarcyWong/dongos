# CR9 — NASM定宽整数常量装入64位寄存器

负责人：cursor。状态：待领取。

module bootstrap.nasm_integer_load。
pub unsafe fn emit(register:u64, raw:u64, width:usize, signed:bool, out:[]u8, written:*usize)u64。
寄存器编号固定0..15依次为rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9,r10,r11,r12,r13,r14,r15；其它编号INVALID。
width仅8/16/32/64，窄raw必须小于2^width，不截断。signed解释补码并符号扩展到64位，unsigned零扩展；严格输出b"mov "+64位寄存器名+b", "+bootstrap.decimal_integer.encode(raw,width,signed)的规范结果+b"\n"，其中换行是真实0A，不是反斜杠n。i64最小值和u64最大值均必须可编码，不能先在i64中求负。只生成立即数mov，不生成内存/符号/浮点，不插入section/global/ret；必须调用CR4而不复制十进制算法。
Python任意精度补码独立期望覆盖位宽/符号/边界、非法raw/register、容量和失败原子性；Dong实际文本NASM双格式组装。原生返回探针实际执行mov并将目标值搬入rax观察结果；只执行安全的caller-saved目标（例如rax/rcx/rdx/r8..r11），rsp/rbp及callee-saved的全部文本仍须真实组装，不破坏宿主栈/ABI。两种实际坏Dong控制至少覆盖有符号窄值当无符号，以及失败提前改written或out。

## 实现、测试与交付

这是L3生产后端的有界独立组件，完整代码生成器/自举尚未完成。实现必须是Dong，模块不导出C符号；C/Python/NASM仅作独立测试观察器，不用宿主实现替代Dong生产逻辑。无分配、全局可变状态或OS调用。仅修改声明的本人works文件，不改code/lang、活动编译器/内核、协调器或他人文件。Codex负责独立复验后集成。

unsafe调用方保证实际可访问的对象；实现仍须在读写前验证完整描述符、地址端点无溢出、长度乘法、自然对齐和所有别名规则。除任务另定外，OK=0、INVALID=1、CAPACITY=2；written非空8对齐，完整8字节与完整out分离；空out可NULL，非空out不可NULL。INVALID优先CAPACITY，失败out与written全文不变；成功只写精确前缀/计数，尾部不变。不以未使用前缀代替完整声明区间检查。先预检再写，子组件在局部暂存中调用以保证原子性。

只读依赖须已accepted/integrated且不修改。所有任务声明的依赖已集成；测试只暂存本组件和声明的只读依赖，避免当前主线同名模块遮蔽临时坏源码。测试实际编译并原生执行Dong debug/release，至少组装ELF64/COFF；有限固定边界与小规模确定性随机，Python/C独立期望，不堆大矩阵。双端guard、只读输入（如有）、输出尾部及失败全文立即核对。指针负例只触发预检，不非法解引用；其它前置条件必须合法，不能用另一非法字段遮蔽目标缺陷。

至少两种真实错误Dong副本成功编译、链接、原生执行，再被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置断言不算负控成功。只运行本任务声明的定向测试，产物在cursor-works/build/CR9/<唯一目录>，不运行OS/VM、全回归、性能基准、定时器、关机、提交或推送。不启动任何模型CLI，Cursor保持客户端手动执行。

先通过本人的worker MCP get_task/read_document查看最新rev、完整契约、归属与依赖，claim成功后才修改。完成后写cursor-works/deliveries/CR9.md，列出真实命令、tests/skip、模式/格式、源码测试SHA256、证据目录、负控拒绝原因和限制，未运行明确未运行；落盘后submit_task，不能自行accept/integrate。需要扩大归属时说明，不擅自扩范围。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_integer_load.dg`
- `cursor-works/src/bootstrap/nasm_integer_load.md`
- `cursor-works/tests/test_nasm_integer_load.py`
- `cursor-works/deliveries/CR9.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_integer_load.py`

交付：`cursor-works/deliveries/CR9.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
