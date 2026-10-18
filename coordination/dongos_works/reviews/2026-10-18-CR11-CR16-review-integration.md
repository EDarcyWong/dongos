# Cursor CR11～CR16 复验与主线集成

2026-10-18，通过coordination MCP检查Cursor全部队列，读取最新任务/交付，实际审查源码、契约和完整定向测试并排队独立复验。先处理CR11～CR15，期间新到CR16亦纳入本轮。没有启动模型CLI。

| 任务 | 正式复验 | 结论 |
| --- | --- | --- |
| CR11 函数栈帧 R2 重提 | 3通过、0skip、来源稳定 | 已验收并集成；历史返修闭合 |
| CR12 内存装入 R1 | 3通过、0skip、来源稳定 | 已验收并集成；只读夹具闭合 |
| CR13 内存存储 R1 | 3通过、0skip、来源稳定 | 已验收并集成；寄存器观察闭合 |
| CR14 整数截断/规范化 | 3通过、0skip、来源稳定 | 已验收并集成 |
| CR15 基址位移LEA | 3通过、0skip、来源稳定 | 已验收并集成 |
| CR16 一元/零比较 | 3通过、0skip、来源稳定 | R1有限补测；未验收/集成 |

## 返修项核实

CR11本次真正完成正式测试，不再以此前快照中止推测结果。prologue/epilogue各13预检共26项，包含written=UINT64_MAX-7配合法空out、两接口完整别名；RBP独立哨兵、调用前后RSP基准、保存寄存器及嵌套调用对齐均有效。5种真实坏Dong涵盖奇数padding、pop顺序、epilogue别名/端点与错恢复RBP；均正常编译链接后由指定原生状态/哨兵拒绝。

CR12用VirtualAlloc/VirtualProtect(PAGE_READONLY)，检查成功才执行发射指令，返回后比较完整40字节输入和两端guard。原signed-as-zx仍在同一只读夹具由数值拒绝，提前written原子性保留。CR13在片段前后用直接内存存储捕获source/base，不用scratch覆盖未观察值；两寄存器完整64位比较、src==base真实地址以及目标低位/完整非目标字节guard均有效。

CR14的8/16符号或零扩展、unsigned32清高位、64位复制、dest==source及两种原生错误值负控有效。CR15复用CR8，原生观察i32位移两端/零/负值及dest==base，错误目的保留原哨兵而被准确拒绝，未解引用测试地址。各模块源码预检、INVALID优先CAPACITY、完整out/written端点/别名、失败不写和成功尾部不变正确；依赖只读、私有源码根没有引入整个lang遮蔽坏实现。

CR16的候选循环按寄存器→三操作→八values生成，native[:24]实际上只保留RAX，漏掉原任务明确要求的R8原生路径。16寄存器文本/组装不是该原生要求。仅要求重新选择至多24向量，保留已有预检/负控，不重写Dong算法，见[CR16 R1](../cursor-works/reviews/2026-10-18-CR16-R1.md)。没有把3项通过当成验收。

## 真实集成与主线复验

五模块nasm_function_frame、nasm_integer_memory_load、nasm_integer_memory_store、nasm_integer_cast、nasm_address_emit的.dg/.md按验收指纹复制到code/lang/bootstrap。五份永久test_bootstrap_nasm_*.py仅适配主线路径和唯一产物目录，保留原测试断言及私有依赖根。客户端生产源码/测试未由Codex改写。

主线同15项全部通过、0skip，124.500秒，源码/永久测试/相关编译器输入指纹稳定。首次主线连接中断没有完整回执，未计通过；已另取完整重跑日志/result。正式与主线重复运行不合计成30项不同测试。

新增永久test_bootstrap_frame_memory_integration.py另1项通过、0skip，12.612秒，debug/release各8向量。真实运行Dong发射器后，将栈帧→LEA取址→cast→store→load→反向LEA→嵌套调用→epilogue拼接组装为原生程序。独立Python/C观察规范值、逐字节非目标区guard、实际回算地址、输入寄存器、六种算术flags位、RBP/所保存寄存器、显式RSP平衡和callee入口对齐。ELF64/COFF均组装，SysV桥在本机执行。主线共16项不同测试通过（15组件+1组合），不是把重复验证算成新测试。

证据：D:/projects/2026/dongos/coordination/dongos_works/.local/reviews/Cursor-review-c57fc924，含各原任务/交付快照、正式日志和指纹、验收/集成回执、主线映射/重跑结果、组合摘要、CR16选取清单。组合产物code/build/test/bootstrap-frame-memory-integration/run-a4b15ea6d5e6，摘要引用五发射器实际产物目录。状态以MCP为准；CR17在途、CR18/CR19待领取，本轮不新增派单。

这是独立后端模块与真实组合的主线集成，活动Python编译器后端未切换；完整Dong后端/CLI、defer lowering及stage1/stage2/DongOS自举仍未完成。没有运行全语言回归、OS/VM、提交/推送或关机。
