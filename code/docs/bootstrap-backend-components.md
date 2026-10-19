# L3 后端规划组件集成

2026-10-19最新推进：CR28窄算术范围门禁、CR29切片lo/hi/len门禁均已独立验收并真实集成；正式各3项零skip，主线各3项零skip（57.381秒/41.553秒），输入指纹稳定。审查者补跑正式实际Dong与坏体相同输入的精确路由对照，共8次正确拒绝。完整L3/IR接线仍未完成。Claude C41在途、C42待领取，以协调器实时状态为准。详见[CR28](../../coordination/dongos_works/reviews/2026-10-19-CR28-integration.md)、[CR29](../../coordination/dongos_works/reviews/2026-10-19-CR29-integration.md)。

2026-10-19最新集成：C39/C40与CR24～CR27返修已完成独立验收、真实文件集成；正式独立与主线相同20项分别零skip通过，主线191.761秒且源码/永久测试/只读依赖/编译器前后指纹稳定。返回值装载/保存、原子store/CAS/fetch-add和重叠memmove均为独立组件，完整L3仍未完成。详见[本批集成证据](../../coordination/dongos_works/reviews/2026-10-19-L3-returns-atomics-integration.md)。历史返修/待领取文字为当时快照，以协调器最新状态为准。

2026-10-19补充：CR22 R2已独立验收并真实集成，正式/主线各3项零skip且来源稳定；与本批C35/C36/C37/C38/CR23合计6组件、26项主线定向测试通过。CR24/CR25审查发现原生观察及实际产出并发验证缺口，已原任务退回Cursor返修。完整L3仍未完成，最新状态以MCP为准。见[CR22 R2记录](../../coordination/dongos_works/reviews/2026-10-19-CR22-R2-integration.md)。

## 2026-10-19 C35～C38 / CR23最新返修集成

新增nasm_switch_dispatch、nasm_scope_cleanup、nasm_sysv_incoming_args、nasm_symbol_pointer_data与nasm_checked_negate五个Dong模块、说明和永久主线测试，均按验收字节真实复制。各输入尾部别名、返回值/栈/路由/64位重定位和原子性测试契约已逐项复查；正式共23项零skip，主线同23项零skip、165.804秒，生产/测试/依赖及宿主编译器指纹稳定后登记integrated。CR22虽人工独立3项通过，但48个主要原生向量违反每模式合计24上限，原任务有限R2、未集成。见[逐项证据](../../coordination/dongos_works/reviews/2026-10-19-L3-latest-review-integration.md)。完整后端/CLI、自举与客体内执行仍未完成。

## 2026-10-19 C34 / CR21 R1集成

新增nasm_sysv_call_args与nasm_shift_guard及永久测试，生产/说明按验收字节复制。C34完整合法输入的三处别名预检和选择性坏Dong敏感性、CR21完整64位计数/原生输入保持/显式对齐/45字节上界均关闭R1。正式5+3项零skip通过，主线同8项零skip、110.209秒，全部受测文件和只读依赖指纹稳定后登记integrated。见[本轮证据](../../coordination/dongos_works/reviews/2026-10-19-C34-CR21-R1-integration.md)。与下批C33/CR20合计新增4个Dong模块，主线16个不同测试全部通过；完整L3仍未完成。

## 2026-10-19 C33 / CR20 R1集成

新增nasm_parallel_copy与nasm_bounds_guard及永久主线测试，生产/说明按验收字节复制。C33完整合法Move尾部别名与重复dst/cap0补测、CR20原生寄存器保持/对齐/46字节上界均关闭R1。正式共8项0skip通过，另6次独立选择性坏Dong原生观察准确拒绝；主线同8项通过0skip、83.438秒，生产/测试/依赖指纹稳定后分别登记integrated。见[本轮完整证据](../../coordination/dongos_works/reviews/2026-10-19-C33-CR20-R1-integration.md)。C37/C38正式各4项通过但完整输入尾部别名夹具不足，已返修、未验收集成；完整L3自举仍未完成。

## 2026-10-18 C30～C32集成

新增nasm_indexed_operand、nasm_memory_intrinsic、nasm_division_guard及永久测试，生产/说明按验收hash复制。C30/C32正式同8项及主线8项分别0skip通过，主线13.907秒；包括真实LEA数值、COPY/ZERO字节/只读源/0计数NULL/寄存器与guard及两类坏Dong负控。C31首交197>192长标签缺陷先退回，由原负责人R1修复为224局部区并补197/79正确上界、同/异20位目标容量与双格式组装；重提正式5项及主线5项各0skip通过，主线7.140秒，另16次独立边界重放正确。三项最终全部真实集成，主线13个不同组件测试通过、生产/测试/关联编译器指纹稳定。另经MCP新增Cursor CR20～CR23、Claude C33/C34，见[完整记录](../../coordination/dongos_works/reviews/2026-10-18-C30-C32-and-new-allocation.md)。完整Dong后端/CLI与自举未完成。

## 2026-10-18 C29与CR16～CR19集成

五模块已按验收hash集成，主线16组件+2实际组合共18项0skip通过，两个完整结果分别11项/72.813秒与7项/26.843秒，来源稳定。C29本次完整正式复验，快照历史问题闭合；CR16显式RAX/R8原生向量关闭R1。扩展shift_select_call加入真实Dong RIP符号取址；新block_divide组合连接块跳转/除余，补signed MIN/MAX和unsigned边界及输入寄存器保持。C31已派给Claude补CR19上游异常门禁，内核本身不替代完整除法语义。见[本轮记录](../../coordination/dongos_works/reviews/2026-10-18-C29-CR16-CR19-integration.md)。下方C29/CR16待修为历史，完整L3仍未完成。

## 2026-10-18 C26～C28可变移位/选择/调用集成

新增nasm_variable_shift、nasm_indirect_call、nasm_conditional_move，生产/说明按验收字节复制；正式12项及主线12组件+1真实组合共13项各0skip通过，主线21.454秒、来源稳定。新增shift_select_call_integration两模式各12向量实际执行CL移位→cmp→cmov选择有效callee→寄存器间接call，独立核对结果/目标返回及入口栈对齐。C26真实坏Dong产物另重放确认正常exit0后数值拒绝；C29快照中止未跑测试，待原交付重提，未集成。见[本轮记录](../../coordination/dongos_works/reviews/2026-10-18-C26-C29-review-integration.md)。完整L3未完成。

## 2026-10-18 CR11～CR15栈帧与内存组件集成

新增nasm_function_frame、nasm_integer_memory_load/store、nasm_integer_cast、nasm_address_emit，生产/说明按验收hash复制；正式同15项及主线15项分别0skip通过，主线124.500秒、来源稳定。新增test_bootstrap_frame_memory_integration另1项通过：真实Dong发射片段组合栈帧、取址、cast、store/load和嵌套调用，双模式各8向量，验证内存guard、寄存器/flags、栈平衡/调用对齐，主线共16项不同测试。CR11～CR13历史返修已闭；CR16仅补原生R8覆盖，未集成。见[本轮记录](../../coordination/dongos_works/reviews/2026-10-18-CR11-CR16-review-integration.md)。完整L3未完成。

## 2026-10-18 C25 直接调用集成

新增nasm_direct_call及永久测试，生产字节按验收hash复制；正式与主线同3项分别0skip通过、来源稳定。真实SysV探针检查参数、编码目标返回值与栈对齐，含只读名字/别名及两种坏Dong负控。CR13须补原生输入寄存器保留观察，未集成；见[后续记录](../../coordination/dongos_works/reviews/2026-10-18-C25-CR13-followup.md)。完整后端与自举仍未完成。

## 2026-10-18 C22～C24 发射与组合集成

新增nasm_compare_emit、nasm_integer_binary、nasm_checked_add_sub，生产/说明按验收hash复制，永久测试仅适配路径；正式12项、主线同12项加真实组合1项各0skip通过。新增arithmetic_emit_integration真实执行Dong产出的wrapping add→bool及signed/unsigned checked sub，每模式12向量，双格式组装。CR12夹具有限返修，CR11快照冲突未运行，均未集成；见[本轮集成](../../coordination/dongos_works/reviews/2026-10-18-C22-C24-mainline-integration.md)。完整L3继续未完成。
## 2026-10-18 D20 SLEB128解码集成

用户授权Codex完成D20 R1，保留已有未提交的有效改动并补独立任意精度/重编码oracle、4路径分别精确负控及证据；按验收字节新增sleb128_decode.dg/.md和永久test_bootstrap_sleb128_decode.py。正式4项与主线同4项各0skip通过，四路径两模式8次漏检坏Dong准确拒绝。生产算法未改，见[接手验收](../../coordination/dongos_works/reviews/2026-10-18-D20-Codex-CR11-R1.md)。CR11未集成，完整L3仍未完成。
## 2026-10-18 CR8～CR10 集成

新增nasm_memory_operand、nasm_integer_load、nasm_branch_emit及说明，生产字节保持验收hash；永久测试为相应test_bootstrap_nasm_*.py，私有源码根只暂存本模块与声明的decimal_integer/branch_plan依赖。正式同9项与主线9项分别通过0skip、受测来源稳定，真实Dong文本经ELF64/COFF组装并在受控SysV探针执行LEA算术、整数装入及分支；CR10另12次落空反转/MAX无落空/同目标原生观察通过。CR11、D20仅测试通过，因实证漏检退回R1，未集成。见[本轮审查](../../coordination/dongos_works/reviews/2026-10-18-Cursor-DeepSeek-review.md)。这是独立库集成，完整董后端/CLI及自举仍未完成。
## 2026-10-18 D19 R1与LM8集成

新增bootstrap.uleb128_decode（生产/说明按验收hash），永久测试test_bootstrap_uleb128_decode.py；LM8固定基址位移数据在lang/tests/fixtures/memory-operand-known-vectors.json，永久检查test_bootstrap_memory_operand_vectors.py。正式5项和主线同5项各通过0skip、来源稳定。D19先前别名夹具漏检已由负责人R1修复，Codex另以4种选择性坏Dong共8次实际两模式原生执行确认每种前缀/尾部、value/consumed角色准确拒绝。见[本轮集成](../../coordination/dongos_works/reviews/2026-10-18-D19-R1-LM8-integration.md)。这些是独立模块/数据集成，不是完整L3自举。

## 2026-10-18 CR5 BSS声明集成

新增bootstrap.nasm_bss模块与说明，生产文件与验收hash完全一致；永久测试为lang/tests/test_bootstrap_nasm_bss.py。正式3项和主线同3项均通过、0skip、指纹稳定，含debug/release原生格式/原子性、两种坏Dong控制与实际NASM ELF64/COFF符号/BSS大小验证。依赖decimal_integer、语义核心及nasm_bytes保持不变。两次路径复跑不冒充6个不同测试。见[CR5集成](../../coordination/dongos_works/reviews/2026-10-18-CR5-integration.md)。完整代码生成器与自举仍未完成。

## 2026-10-18 当前集成增量

CR2/CR7、D14～D18及LM7完成第一批集成，随后新交付CR3/CR4/CR6也独立验收并集成。新增主线模块为 `nasm_rodata`、`sysv_return_plan`、`rel32_patch`、`string_table`、`data_pool_layout`、`cfg_postorder`、`phi_copy_plan`、`nasm_symbol`、`decimal_integer`、`branch_plan`；模块和说明与验收hash一致，各有 `lang/tests/test_bootstrap_<模块>.py` 永久测试。LM7固定数据位于 `lang/tests/fixtures/decimal-known-vectors.json`，独立检查为 `test_bootstrap_decimal_vectors.py`。

主线第一批24项、后续10项通过，均0skip、来源指纹稳定。第一批含新组合 `test_bootstrap_data_backend_integration.py`：真实DFS/phi及C9消环→SysV规划→字符串表/rel32→对齐常量池→CR2/CR1文本输出，两模式实际NASM恢复11字节并检查失败原子性。永久测试的私有源码根仅引入声明的只读依赖，首轮同名模块冲突与修正记录保留。语义核心和既有字节编码器未改。

见[第一批8项集成](../../coordination/dongos_works/reviews/2026-10-18-CR2-CR7-D14-D18-LM7-integration.md)及[Cursor后续3项](../../coordination/dongos_works/reviews/2026-10-18-Cursor-followup-integration.md)。这是库模块、数据、永久测试和实际组合调用的集成，完整Dong代码生成器/CLI/stage1/stage2及客体自编译继续未完成。CR5随后已独立验收并集成，详见下节。以下是此前批次历史。

七个已验收的纯Dong组件位于lang/bootstrap：cfg_reachability、sysv_integer_args、parallel_moves、stack_slots、switch_cases、cleanup_plan、nasm_bytes。公开接口和明确子集见各同名.md；原协作交付保存在coordination/dongos_works。

主线测试：`python -m unittest lang.tests.test_bootstrap_cfg_reachability lang.tests.test_bootstrap_sysv_integer_args lang.tests.test_bootstrap_parallel_moves lang.tests.test_bootstrap_stack_slots lang.tests.test_bootstrap_switch_cases lang.tests.test_bootstrap_cleanup_plan lang.tests.test_bootstrap_nasm_bytes lang.tests.test_bootstrap_backend_components -v`，从code目录运行。产物分别位于build/test/bootstrap-components/<编号或integration>/<唯一目录>/。

2026-10-18，模块本体与验收hash一致；七项永久测试和模块图/语法/语义相关回归共38项通过、0skip、源码稳定，组合原生测试另1项通过。组合测试观察了七个组件之间的数据交接及NASM实际二进制恢复。回执 `build/test/bootstrap-components/mainline-1d495b26962d/result.json`；逐文件映射见[集成记录](../../coordination/dongos_works/reviews/2026-10-18-batch3-integration.md)。

这是主线可导入模块、永久测试和组合执行的集成。生产编译器仍使用现有Python后端；完整Dong语义/代码生成、CLI、目标I/O、stage1/stage2及DongOS内自举仍待完成，不据此关闭L3。未运行OS/VM。


## C13–C15 后续集成

2026-10-18，新增bootstrap.leb128、bootstrap.linear_intervals、bootstrap.register_slots主线模块与永久测试。前者编码最短ULEB/SLEB，后两者仅为线性编号包络及不驱逐/不复用spill的保守寄存器策略。

三个定向模块9项及新组合test_bootstrap_interval_encoding的1项全部通过、0skip；组合实际从事件包络经寄存器分配、LEB编码至CR1 NASM恢复字节，debug/release与两种对象格式均覆盖。证据及scope见[本轮集成](../../coordination/dongos_works/reviews/2026-10-18-C13-C15-LM5-integration.md)。未声称完整后端或L3自举完成。


## C17 行索引集成

2026-10-18，bootstrap.line_index及路径适配的永久测试已集成。正式3项和主线同3项均通过零skip，另有3868次穷举小输入原生调用；两次路径复跑不算6个不同测试。C16/C18待原负责人R1，L3自举仍未完成。见[复验记录](../../coordination/dongos_works/reviews/2026-10-18-C16-C18-review.md)。
