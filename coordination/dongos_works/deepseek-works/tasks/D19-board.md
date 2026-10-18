# D19 — 有界最短ULEB128 u64解码

负责人：deepseek。状态：待领取。

module bootstrap.uleb128_decode。
pub unsafe fn decode(input:[]const u8,value:*u64,consumed:*usize)u64；OK=0、INVALID=1、TRUNCATED=2、OVERFLOW=3、NONCANONICAL=4。只解码最短ULEB128 u64，不负责SLEB/文件/调试节。独立于已有编码模块，不重复编码任务。
先验证input完整描述符/端点（空可NULL）、两个输出均非空8对齐/各8字节有效，完整input与输出两两分离；input不能因只读取前缀而允许尾部别名。描述符不合法一律INVALID且不读取输入。扫描最多10字节，低7位为载荷、bit7为继续。前9字节任意；若到第10字节，该字节payload>1或继续位=1返回OVERFLOW（优先该字节的终止/规范检查）。遇终止字节时，若不是第一字节且其payload=0返回NONCANONICAL，否则成功；成功value为无符号组合，consumed为1..10，忽略剩余输入。未遇终止且输入耗尽（不足10字节）返回TRUNCATED；空input亦TRUNCATED。例如00→0/1；80 01→128/2；80 00→NONCANONICAL；FF×9 01→u64最大/10；80×9 02、80×10均OVERFLOW；80×9为TRUNCATED。禁止移位>=64或溢出移位后才检查。
任意非OK两个输出全文不变，input只读；成功只改两个输出字段，无CAPACITY码。循环最多10次，无分配/OS。上述定义覆盖状态优先级，不能把第10字节继续错误当缺输入，也不能解码后才检查输出别名。
独立Python任意精度解码/最短再编码期望，固定各7位边界、最大、尾随字节、非最短、截断、溢出与少量固定随机。真实Dong debug/release原生执行，ELF64/COFF组装；只读input、完整input尾别名、坏指针预检、双端guard及失败字段全文不变。坏Dong至少覆盖第10字节溢出被接受，及截断前提前写value；两者实际编译运行并被对应状态/原子性断言拒绝。

## 实现、测试与交付

这是L3生产后端的有界独立组件，完整代码生成器/自举尚未完成。实现必须是Dong，模块不导出C符号；C/Python/NASM仅作独立测试观察器，不用宿主实现替代Dong生产逻辑。无分配、全局可变状态或OS调用。仅修改声明的本人works文件，不改code/lang、活动编译器/内核、协调器或他人文件。Codex负责独立复验后集成。

unsafe调用方保证实际可访问的对象；实现仍须在读写前验证完整描述符、地址端点无溢出、长度乘法、自然对齐和所有别名规则。除任务另定外，OK=0、INVALID=1、CAPACITY=2；written非空8对齐，完整8字节与完整out分离；空out可NULL，非空out不可NULL。INVALID优先CAPACITY，失败out与written全文不变；成功只写精确前缀/计数，尾部不变。不以未使用前缀代替完整声明区间检查。先预检再写，子组件在局部暂存中调用以保证原子性。

只读依赖须已accepted/integrated且不修改。所有任务声明的依赖已集成；测试只暂存本组件和声明的只读依赖，避免当前主线同名模块遮蔽临时坏源码。测试实际编译并原生执行Dong debug/release，至少组装ELF64/COFF；有限固定边界与小规模确定性随机，Python/C独立期望，不堆大矩阵。双端guard、只读输入（如有）、输出尾部及失败全文立即核对。指针负例只触发预检，不非法解引用；其它前置条件必须合法，不能用另一非法字段遮蔽目标缺陷。

至少两种真实错误Dong副本成功编译、链接、原生执行，再被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置断言不算负控成功。只运行本任务声明的定向测试，产物在deepseek-works/build/D19/<唯一目录>，不运行OS/VM、全回归、性能基准、定时器、关机、提交或推送。不启动任何模型CLI，Cursor保持客户端手动执行。

先通过本人的worker MCP get_task/read_document查看最新rev、完整契约、归属与依赖，claim成功后才修改。完成后写deepseek-works/deliveries/D19.md，列出真实命令、tests/skip、模式/格式、源码测试SHA256、证据目录、负控拒绝原因和限制，未运行明确未运行；落盘后submit_task，不能自行accept/integrate。需要扩大归属时说明，不擅自扩范围。


## 可修改文件

- `deepseek-works/src/bootstrap/uleb128_decode.dg`
- `deepseek-works/src/bootstrap/uleb128_decode.md`
- `deepseek-works/tests/test_uleb128_decode.py`
- `deepseek-works/deliveries/D19.md`

## 定向验收

- `discover:deepseek-works/tests:test_uleb128_decode.py`

交付：`deepseek-works/deliveries/D19.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## R1 有限返修要求（Codex，2026-10-18）

本轮暂不验收：正式4项虽通过0skip且生产解码实现未发现错误，但输入/输出别名测试没有真正覆盖契约。test_uleb128_decode.py的invalid()中case4/5使用arena+1作为u64输出，先被8对齐检查拒绝；没有只在完整input尾部与value/consumed重叠的合法对齐夹具。Codex已真实编译删除两处input-output overlap检查的坏Dong，原全部4项仍通过；独立前缀/尾部四种对齐别名探针在debug/release明确区分好坏实现。

只修原D19测试并追加交付，不新建重复任务，不改生产算法以迁就测试。保留当前生产源码hash af79d3adfabe377f496220802a85ceff69380aa449450e596c2bae769b6f4821，除非补测确实发现实现错误并在交付说明原因。

1. 将case4/5修为8字节对齐、输出相互分离、端点合法，仅因输入与其中一个输出重叠而INVALID；给出本来可成功解码的合法输入，不能依靠未对齐/空指针/错误编码拒绝。使用明确8对齐C存储（例如u64数组）避免隐含对齐假设，快照在合法输入全部初始化之后。
2. 另补两种有限尾部别名：input从arena+64开始、len=96、首字节00；value=arena+128而consumed=arena+240，及consumed=arena+128而value=arena+224。arena至少320字节且8对齐，两个输出与输入的地址端点有效。解码前缀只有1字节，仍因声明的完整输入尾部重叠而INVALID，整个arena与两个输出均不变。可用等价布局，不依赖刚好这些地址。同步真实PREFLIGHTS数量，不放宽现有断言。
3. 新增真实别名漏检坏Dong控制：只删除input与两输出的重叠检查，保留描述符/对齐/输出相互分离检查；在上述其它条件合法夹具上，必须成功编译/链接/原生执行，再被指定status/atomicity断言拒绝。至少前缀与尾部、value与consumed两种角色均真实观察，debug/release覆盖。保留既有第10字节溢出及提前写入负控；崩溃/构建失败/无关前置断言不算成功。
4. 只运行本任务原定向测试；不扩大随机矩阵、不运行全回归/OS/VM，不改他人或主线。原D19.md保留历史、追加R1真实命令/tests/skip/hash、夹具触发规则和负控原因，落盘后由worker MCP重新领取/提交，等待Codex复验。

详见deepseek-works/reviews/2026-10-18-D19-R1.md，原交付和正式复验历史保留。
