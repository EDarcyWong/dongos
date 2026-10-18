# CR10 — 由分支规划生成可执行NASM条件跳转

负责人：cursor。状态：待领取。

module bootstrap.nasm_branch_emit。
pub unsafe fn emit(condition:u64, yes:u64, no:u64, fallthrough:u64, out:[]u8, written:*usize)u64。
输入规则完全沿用已集成bootstrap.branch_plan（CR6），必须调用该组件而非重写逆谓词和落空规划。块号标签严格b"__dong_b"+无符号十进制块号，数字复用CR4。先在局部获得Plan及所需所有数字，验证输出描述符、长度/容量后一次写。
Plan.has_cond=1时输出<mnemonic> SPACE <cond_target标签> LF；has_jump=1时随后输出b"jmp "+<jump_target标签>+LF。mnemonic按Plan.condition=0..9固定je,jne,jb,jbe,ja,jae,jl,jle,jg,jge。未启用的行完全省略，不含section/global/冒号/ret/NUL。零行时成功written=0且out全文不变（空NULL out可用，但written仍需合法）。真实LF单字节0A。
独立Python真值和精确文本验证所有10谓词、目标相同、yes/no各自落空、无落空u64最大哨兵、其它落空、非法枚举/目标/指针及容量。实际Dong输出接在临时NASM cmp rdi,rsi后，定义所需标签并按真实fallthrough布局，块返回不同标记；原生执行真假路径检查有符号/无符号高位，不能只检查Python模拟或字段。组装ELF64/COFF。不把比较或源副作用优化掉。坏Dong至少覆盖有符号助记符映射错误，以及无落空漏jmp；两者必须被原生分支结果断言拒绝，不能只依赖文本不同。容量/别名原子性亦覆盖。

## 实现、测试与交付

这是L3生产后端的有界独立组件，完整代码生成器/自举尚未完成。实现必须是Dong，模块不导出C符号；C/Python/NASM仅作独立测试观察器，不用宿主实现替代Dong生产逻辑。无分配、全局可变状态或OS调用。仅修改声明的本人works文件，不改code/lang、活动编译器/内核、协调器或他人文件。Codex负责独立复验后集成。

unsafe调用方保证实际可访问的对象；实现仍须在读写前验证完整描述符、地址端点无溢出、长度乘法、自然对齐和所有别名规则。除任务另定外，OK=0、INVALID=1、CAPACITY=2；written非空8对齐，完整8字节与完整out分离；空out可NULL，非空out不可NULL。INVALID优先CAPACITY，失败out与written全文不变；成功只写精确前缀/计数，尾部不变。不以未使用前缀代替完整声明区间检查。先预检再写，子组件在局部暂存中调用以保证原子性。

只读依赖须已accepted/integrated且不修改。所有任务声明的依赖已集成；测试只暂存本组件和声明的只读依赖，避免当前主线同名模块遮蔽临时坏源码。测试实际编译并原生执行Dong debug/release，至少组装ELF64/COFF；有限固定边界与小规模确定性随机，Python/C独立期望，不堆大矩阵。双端guard、只读输入（如有）、输出尾部及失败全文立即核对。指针负例只触发预检，不非法解引用；其它前置条件必须合法，不能用另一非法字段遮蔽目标缺陷。

至少两种真实错误Dong副本成功编译、链接、原生执行，再被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置断言不算负控成功。只运行本任务声明的定向测试，产物在cursor-works/build/CR10/<唯一目录>，不运行OS/VM、全回归、性能基准、定时器、关机、提交或推送。不启动任何模型CLI，Cursor保持客户端手动执行。

先通过本人的worker MCP get_task/read_document查看最新rev、完整契约、归属与依赖，claim成功后才修改。完成后写cursor-works/deliveries/CR10.md，列出真实命令、tests/skip、模式/格式、源码测试SHA256、证据目录、负控拒绝原因和限制，未运行明确未运行；落盘后submit_task，不能自行accept/integrate。需要扩大归属时说明，不擅自扩范围。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_branch_emit.dg`
- `cursor-works/src/bootstrap/nasm_branch_emit.md`
- `cursor-works/tests/test_nasm_branch_emit.py`
- `cursor-works/deliveries/CR10.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_branch_emit.py`

交付：`cursor-works/deliveries/CR10.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
