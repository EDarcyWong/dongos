# L3：CR30 / D21 首交独立审查

两项生产组合均已实际阅读：CR30在局部调用CR21完整RCX范围门禁后C26移位；D21在局部调用CR28范围门禁后CR14规范化，预检后最后发布。尚未发现需要重写这些生产算法的证据。

本次审查不把交付者自测或排队状态当作正式复验通过。两项当时仍排在CX2之后；发现以下明确永久测试契约缺口后，通过控制台HTTP取消仅对应queued复验，随后原任务退回，不中断运行中作业。未改负责人源码/测试，未运行OS/VM或全项目回归。

## cursor:CR30

- `test_actual_compiled_wrong_sources_are_rejected`两个语义负控的好侧原生执行取`good=expected(...)`，即Python拼接汇编，未把正式Dong产出传入同输入好侧原生路径。前面的`run_both`仅检查发射器文本，不补足该契约。须从正式debug/release可执行体获取实际text，再分别以count63和count64同输入跑好体后跑坏体，按明确路由/数值拒绝；保留真实生成来源。
- `_probe`只观测SAFE={rax,rcx,rdx,rsi,r8,r9,r10,r11}加目标且扣除spill，未观测rbx、r12..r15、rbp/rsp，spill也未验证。任务要求成功时除目标/flags外全部GPR保持、trap全部GPR保持。须补安全桥：保存宿主callee-saved，在真实片段执行前设置值，执行后先捕获再恢复；用安全可访问状态区/栈槽保存地址，不以破坏宿主ret的变体做负控。至少以实际坏Dong修改一个本应保持的寄存器，并由捕获值拒绝，不能依靠崩溃。

## deepseek:D21

- 主向量及倒序负控均确实使用实际Dong产出；24向量、两种顺序边界、容量落在guard/cast之间的原子性检查已存在，予以保留。
- `_probe`的SAFE={rax,rcx,rdx,rsi,rdi,r8,r9,r10}遗漏rbx、rbp/rsp、r12..r15；rbx仅push/pop用作状态指针，没有对执行片段后的值进行独立捕获与比较。任务明确只允许RAX/R11/flags改变，必须覆盖全部其它GPR。修订应采用安全桥，捕获完整保持集后恢复宿主ABI，并保留正常返回的实际坏Dong保持寄存器数值负控；不得靠崩溃/构建失败代替拒绝。

两项均需原编号返修、写真实测试时间/命令/模式/计数/输入SHA、提交后重新排正式定向复验。尚未验收或集成。

## D21 R1新提交审查（16:11北京时间）

原负责人已在原编号完成R1并提交rev6。已阅读返修交付和新版_probe：状态指针落栈；片段前设置独立魔数，片段后捕获RAX及13个非R11其它GPR（含RBX/RBP/R12..R15）、RSP前后观察和路由标记，再恢复宿主callee-saved后正常ret，RBX不再作为未观测spill。栈偏移核对：15个捕获push共120字节，状态指针位于当前rsp+128，观察结束add120+16后反向pop六个callee-saved，保持宿主ABI。RSP基线与片段后值须精确相差原基线push的8字节。

新增实际坏Dong追加`mov rbx, 61453`，正常落空/返回后由捕获RBX数值拒绝，同一原生输入正式好侧先通过，debug/release都有；原24向量、范围边界倒序及guard/cast容量原子性保留。生产.dg/.md未变。已排新正式复验39046cc968224146804cad44d9ad5f9f；源码审查闭合上述R1缺口，仍须新正式结果/指纹通过才可验收，不能继承首轮排队状态。

审查者独立重新运行D21 R1完整定向测试：5项全部通过、0skip、65.636秒，包括新增正常返回的保持寄存器坏Dong数值负控。正式复验仍以新作业结果为准。

新正式作业39046cc968224146804cad44d9ad5f9f在复制隔离副本时发现源变化，未执行CLI/测试，不能计为测试失败或通过。审查者核对独立R1产物run-0d37b29b56a4/summary.json列出的6项生产/说明/永久测试/依赖输入，当前SHA全部相同。通过控制台显式project=dongos、最新rev7的manual submit重新发布同一真实交付（未编辑实现/交付内容，也未伪造worker领取），保留旧事件和作业；再以MCP最新rev8排正式复验de0ef4232c8c49fd8895092ef08fe05b。此重试仅为基础设施复制失败，不是新一轮代码修改；原领取/提交和R1工时保持原事件，不新增虚假办理时长。

### D21 R1最终验收与集成

正式新作业de0ef4232c8c49fd8895092ef08fe05b于2026-10-19 16:31:20北京时间通过：5项0skip、67.678秒、source_stable=true。源码/契约/有效测试审查和独立复验完成后，按最新rev登记accepted。

实际复制nasm_checked_narrow_result.dg/.md到code/lang/bootstrap，永久测试只适配ROOT/SOURCE/DOC、三项只读依赖定位和构建输出路径，保存为lang/tests/test_bootstrap_nasm_checked_narrow_result.py；CR28/CR14主线与原works依赖原始SHA相同。主线完整5项0skip、66.719秒，三个新文件前后SHA稳定，生产/说明与正式验收原字节一致。证据`.local/reviews/D21-R1-independent-20261019/integration-files.json`。集成状态另由协调器最新CAS登记；不宣称已接活动IR或完整L3。

### CR30后续归属

后续查询显示原cursor:CR30已由另客户端按用户转交要求暂停归档（rev6），后继为claude:C46；原R1审查意见和历史保留，不能将其计作已验收。C46是后续新提交，本记录不继承或假定其复验结果。
