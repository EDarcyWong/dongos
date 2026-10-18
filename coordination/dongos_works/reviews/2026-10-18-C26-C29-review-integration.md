# Claude C26～C29 交付复验与集成

2026-10-18，通过coordination MCP查询四项最新任务、原任务书与交付，排队正式独立复验，实际审查全部Dong生产源码、说明和测试，没有启动模型CLI。

| 任务 | 正式复验 | 本轮结果 |
| --- | --- | --- |
| C26 CL可变移位 | 4通过、0skip、来源稳定 | 已验收并真实集成 |
| C27 寄存器间接调用 | 4通过、0skip、来源稳定 | 已验收并真实集成 |
| C28 条件移动 | 4通过、0skip、来源稳定 | 已验收并真实集成 |
| C29 RIP符号取址 | 复制源码快照时变化，中止，未执行测试 | 保留原交付，需worker重提；未验收/集成 |

## 审查依据

C26先检查written/out完整端点、对齐、别名与枚举，在局部缓冲组装后写出；24个有限向量/模式覆盖SHL/SHR/SAR、有效计数低6位、64/65/MAX、RCX兼任目的的同初始位模式，并比较8个受控寄存器完整64位。全16名文本与双格式组装通过。另对正式副本中的真实好/坏Dong原生产物独立重放：各模式7个负SAR向量，正常exit0、完整448字节；坏SAR→SHR中6项数值不符（计数64的有效0位移保持相同），其余寄存器符合期望。该补验排除了用链接失败、崩溃或截断输出冒充native拒绝；见C26-negative-replay.json。

C27原生选择rax/r10/r11，各装入同文件已定义的不同callee地址，检查目标专属返回值、参数、入口RSP&15==8以及返回后栈差0，正确保留宿主callee-saved。错误r10→r11有两个均有效的目标，由真实返回标记拒绝，未依赖未知符号或非法地址。

C28复用已集成CR6谓词常量，10谓词每项都有真/假，包含dest==source及有/无符号分歧。cmp建立flags后用mov载入受控寄存器、pushfq/pop内存记录，不破坏待观察flags；比较全部受控寄存器与CF/PF/AF/ZF/SF/OF位。错误SLT→ULT由真实目的值拒绝。三项的完整输出/计数失败不写、成功尾部、真实guard及提前写负控均有效，私有源码根只暂存本组件和已声明依赖。

C29生产与完整测试审查暂未发现逻辑缺陷，但正式job cf5b3a5b9e564e968012b390de507930在复制整个项目和挂载works期间发现变化，未启动定向测试；不能推断是C29自身在改或功能失败。协调器已置rework；[重提说明](../claude-works/reviews/2026-10-18-C29-snapshot-retry.md)已追加到原任务书，要求通过本人worker MCP claim/submit现有交付，无需重写算法或增加矩阵。本轮未绕过状态/指纹门禁，也未因源码审查就登记验收。未执行的测试不计入通过数。

## 主线集成与实际组合

nasm_variable_shift、nasm_indirect_call、nasm_conditional_move的.dg/.md按验收hash复制到code/lang/bootstrap。三份永久test_bootstrap_nasm_*.py只适配主线路径/产物目录，保留全部断言和私有根；客户端实现/测试未改写。主线同12项组件测试加新增组合1项共13项通过、0skip，21.454秒，生产、测试及相关编译器输入指纹稳定。正式与主线重复12项不合计为24项不同测试。

新增test_bootstrap_shift_select_call_integration.py运行真实Dong发射器，取得CL移位、cmov和call寄存器文本；将它们组合为可执行程序，按移位结果的signed/unsigned比较选择两个真实callee之一，再间接调用。debug/release各12向量覆盖三移位、计数0/1/63/64/65/MAX、真/假及有无符号分歧；独立Python按低64位/有符号规则计算期望，核对实际callee参数衍生返回值、目标标记、调用入口对齐8和输出guard，ELF64/COFF均组装。没有把生产运算改成宿主常量或声称完成完整函数指针lowering。

证据：D:/projects/2026/dongos/coordination/dongos_works/.local/reviews/Claude-C26-C29-0ef5b39b，包含任务/交付快照、4份正式回执、C26真实负控重放、验收/集成回执、主线文件映射/hash与完整log/result。新组合产物在code/build/test/bootstrap-shift-select-call-integration唯一目录，summary.json引用三个发射器实际构建目录。

C29仍未集成，完整Dong后端/CLI、defer lowering、stage1/stage2及DongOS自举继续未完成。没有新增派单、运行全语言回归/OS/VM、提交推送或关机。
