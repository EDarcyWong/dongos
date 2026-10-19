# L3 最新交付复验与集成（2026-10-19，本轮）

通过协调器HTTP/MCP适配读取dongos项目最新任务/rev、完整原任务书、交付和历史返修说明。初始6项：Claude C35/C36/C37/C38、Cursor CR22/CR23；CR24/CR25仍在本人执行中，不抢占。原始快照与全文保存在 `.local/reviews/L3-latest-20261019/initial-tasks.json` 和逐项task/delivery文档。

## 源码、契约与测试审查

- **C35 switch分发：** 原生产/说明未改，实际复用C11排序查重、CR9完整i64装入、CR4标签十进制；局部1280覆盖1233上界，selector在RDI且scratch仅RAX/flags。R1在快照前初始化全16个合法不同值Case，关闭10/11尾部别名遮蔽；永久prefix32坏Dong仅命中目标10/11，正常执行后按错误OK/容量及全文断言拒绝。原24个selector、MIN/MAX、重复值、1233精确/不足、路由jne与容量提前写负控保留。
- **C36 scope清理：** 实际复用C12计划，验证全scope计数和<=16、未使用ID亦不得MAX，按顺序调用并保存/恢复RAX/RDX和RSP。R1在快照前将sc2..7初始化为合法根的空子作用域，case14不再被非法count遮蔽；永久仅截断scopes-written为48字节的坏Dong正常执行且只报14。原21预检、10主要向量、日志/调用对齐/返回双字/栈和callee-saved、逆序/不恢复/提前写负控保留。756上界与1024局部区正确。
- **C37 incoming捕获：** 生产/说明未改，C8规划、CR8位移及CR4闭包符合frame<=4080、saved_mask=0契约；先寄存器字后RAX中转栈字。R1在快照前初始化16合法kinds/16不同8..128槽并将case12/14/16参数统一为16/16/frame128，补非法kind且容量0（含只读输入），三个永久选择性坏Dong分别只命中12/14/16。原原生帧/寄存器/flags/guard、incoming+24数值与提前写负控保留。
- **C38 静态指针：** 生产/说明未改，CR3编码和CR4幅度复用、MIN的u64 wrapping_sub、dq完整64位重定位及560/576上界正确。R1追加四名字64字节时分别与written/out在+8重叠的8例，31预检其它字段合法；组合prefix1坏Dong只命中23..30，两个独立target_item坏体只命中26或30。原ELF64 RELA/COFF ADDR64对象解析、实际链接后地址+addend数值、±8安全解引用及归零/反号/提前写负控保留。
- **CR23 checked negate：** 生产逻辑未改，仅说明40字节上界；显式arena/saved16对齐和meta8对齐，容量/INVALID优先、RAX/R8的MIN等边界及其它受控寄存器观察有效。jo→jno真实坏Dong必须正常编译/链接/执行后命中route断言，永久测试已由宽AssertionError改为精确route正则；提前写原子性负控保留。
- **CR22 checked multiply：** 生产逻辑、低积/高积/输入保持及signed RDX/unsigned RDX契约暂无新缺陷；显式对齐、59字节说明与精确route负控已修。但原任务明确每个debug/release模式合计最多24个主要原生向量；当前SIGNED_VECTORS=24、UNSIGNED_VECTORS=24，test_dong_assemble_and_native_multiply拼接两表后在每个mode执行48个，错误断言只分别限制每张表。因此R1仍未完全满足，需原任务有限R2：总和<=24（保留两类必要边界），直接断言组合长度、更新计数/交付，不改正确算法或扩大矩阵。正式通过不能消除此契约缺口。

## 正式复验与集成规则

六项按最新rev排队独立定向复验，保留原失败/重试记录。实际每项tests>0、0skip、source_stable且当前4文件指纹与verification一致后，才对审查合格项accept。CR22在正式作业结束后按最新rev退回原负责人有限返修，不验收/集成。

合格项生产/说明按验收字节真实复制至 `code/lang/bootstrap/<module>.dg/.md`，永久 `code/lang/tests/test_bootstrap_<module>.py` 仅适配ROOT/SOURCE/DOC/独立build路径，保留全部断言、语料、负控。主线真实定向测试零skip、生产/测试/依赖/编译器指纹稳定后才integrate。最终正式回执、实物映射、主线结果和任务状态见同名JSON。

不将组件完成冒充完整L3：完整代码生成/目标I/O/诊断CLI、stage1/stage2和DongOS内自举仍未完成。本轮不启动AI CLI、OS/VM，不跑全语言回归，不提交/推送。

## 本批最终结果

| 任务 | 独立正式复验 | 最终处理 |
| --- | --- | --- |
| C35 | 5通过/0skip，27.778秒 | 真实集成完成 |
| C36 | 5通过/0skip，27.877秒 | 真实集成完成 |
| C37 | 5通过/0skip，35.068秒 | 真实集成完成 |
| C38 | 5通过/0skip，39.900秒 | 真实集成完成 |
| CR23 | 3通过/0skip，36.620秒 | 真实集成完成 |
| CR22 | 3次正式快照中止，0测试；人工私有复跑3通过/0skip | 因48>24的原契约缺口退回R2，原负责人已领取 |

合格五项正式共23项通过零skip。五模块源码/说明共10文件逐字节复制，五份永久主线测试的全部非路径内容保持；主线共23项通过零skip、165.804秒，生产/永久测试/只读依赖及宿主编译器前后SHA256一致，随后逐项通过协调器登记integrated。完整结果在同名JSON及 `.local/reviews/L3-latest-20261019/`。

CR22第三次快照仍受其它任务并发修改影响；审查者另核对其私有副本中原四文件、CR4、全部宿主编译器源码和公共测试工具与当前文件逐字节一致，再直接运行定向测试：3项通过、0skip、22.111秒，前后指纹稳定。此结果单列为人工独立复跑，没有填充为正式job通过；同一副本的实际主向量数为24+24=48，故仍未验收或集成。R2仅要求合计收敛至24以内并直接断言总数，保持必要边界和有效负控，不改生产算法。
