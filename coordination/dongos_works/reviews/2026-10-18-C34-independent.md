# C34独立审查

2026-10-18，读取submitted/rev3完整任务、交付、生产Dong及全部Python/C/NASM测试。结论：生产实现未发现功能缺陷，**测试夹具需原任务有限返修，当前不可验收集成**。

## R1：别名预检被其它非法数据掩盖

HARNESS.invalid的case11、13、15声称分别检查Result与kinds、完整offsets尾部与Result、完整offsets尾部与out的别名，但输入并未同时合法：

- case11声明kinds.len=16而offsets.len=2，只初始化前两个kinds为0，其余是0xA5；既有非法kind，也有展开字数与offset数不匹配。
- case13/15声明kinds.len=2、offsets.len=16，展开字数2与offset数16不匹配，其余offset未初始化成合法值。

因此本应由别名检查独立拒绝的用例，在缺少目标检查时仍被数据INVALID挡住。原实现的完整区间检查本身正确，不能用当前正向通过证明夹具有效。

独立在原临时源码根实际编译/链接并原生执行三类选择性坏Dong：仅删除kinds与Result别名检查；仅把offsets与Result别名长度截为前16字节；仅把offsets与out别名长度截为前16字节。debug/release共6次，原28预检全部正常通过。此处仅证明原预检组漏检，没有声称完整四项坏版本套件均通过。

另在review副本中将三个目标用例全部设为16个合法scalar kind及16个8..128合法offset，初始化后再取快照；正式源码在两模式通过全部28预检。三个相同坏体被各自case11/13/15准确拒绝，均正常原生exit93、错误状态CAPACITY(2)而非应有INVALID(1)，无崩溃、panic或非法解引用。容量512不足以容纳该16字文本仍属于合法容量请求，恰好证明INVALID必须优先CAPACITY。

复现脚本：`coordination/dongos_works/.local/reviews/C33-C34-CR20-CR23-review/check_c34.py`；结构结果同目录`C34-alias-mutants.json`。全部源码、原/修正观察器、输入输出在`claude-works/build/C34/run-96c523642393/`，未改原生产/测试文件。

## 已确认的有效部分

生产实际复用C8 plan、CR8操作数与CR4数字；最长理论893字节小于局部1024，所有用户输出在预检/局部生成/容量通过后发布，Result完整16字节检查正确。独立Python ABI oracle实现双字整体落栈而不占剩余单寄存器；12个实际原生向量捕获6实参、栈字/padding、入口对齐、cleanup后栈恢复、完整源帧/guard、callee-saved及R10/R11，无栈时RAX保持。第一栈槽0改8的坏Dong正常执行后按栈实参拒绝，setup/cleanup提前写负控有效。全范围offset、重复offset、精确/少1/0容量、只读输入保护、16字与空输入已覆盖。正式定向4项通过0skip、来源稳定仍不足以关闭上述独立夹具缺口。

## 原负责人有限返修要求

仅原四文件内调整case11/13/15：其它参数/所有输入元素合法，展开字数恰等offset数，明确_Alignas保持，初始化后取完整快照，目标别名独立触发INVALID；保留Result第二字别名、所有其它原预检、ABI向量、原正常语义/原子性坏Dong。增加上述三种选择性坏Dong在原生预检中被准确拒绝的证据（可用单组有限临时坏体，两模式）；不修改生产接口/允许范围，不扩大矩阵或重写算法。修正说明/交付后MCP重提，待独立复验。
