# 任务图“尚待完成”实质核实

2026-10-21。结论：原先6处已验收节点中的“尚待完成”并非全部已经完成。既有任务/代码合并的限定交付已完成，DMA完整恢复、P2后续消费者、G5完整语言覆盖确实仍未闭环；这些真实待办继续保留在所属阶段。不能依据节点绿色删除待办，也不能用代码合并代替阶段验收。

本次检查覆盖任务图28个节点，重点逐项核对存在“complete + remaining”矛盾的P5CTX1、P5CTX2、P2LIVE1、L3B、M7、M10。原任务书明确范围、当前源码、正式验收指纹与原始回执分别核对，未修改协调器任务状态。

| 原内容 | 核实结论 | 实质证据 |
| --- | --- | --- |
| P5CTX1精确持有上下文、P5CTX2真实客体上下文核验 | 已完成原任务范围；不是DMA回收完成 | MCP当前integrated rev7/rev6；原任务书从发布时就明确不实现drain/unpin/free/reuse/新token/驱动重启。正式指纹与主目录一致，P5正常和故障两份实际客体归档本轮重新完整离线解码均通过 |
| DMA可信排空、撤映射后全核退休、unpin/free/reuse、新token与驱动重启 | **未完成，保留P5待办** | 正常与故障各两次实际观察全为held=1/drain=0(UNKNOWN)。`device_host.dg:31`明确drain未知；`services.dg:391`对PINNED租约隔离后返回而不destroy；`:403`的ACK发生在后续撤映射之前，不证明post-unmap TLB退休。reset结果不等于drain证明 |
| P2LIVE1正常私有根AP启动前BSP大页生命周期 | 已完成原任务范围 | P2单核/四核归档本轮重新完整离线复算：complete1、phase10、steps1023、held0、full_flush516、retired4。14个正式文件指纹匹配；实际分配块归还与最终表树审计由同一raw replay复算 |
| 持久大页、多核在线大页转换/回收、通用动态EXEC/WC消费者 | **当前活动路径未接入，保留P2待办** | `active_paging.dg:1`要求BSP单写、IF0；`:126`仅接受0/WRITE，拒绝EXEC/WC；`memory_mutation.asm:437`在AP启动前调用大页hook，`large_memory.dg:147`归还租约并恢复普通树。既有paging/planner/UEFI探针只能证明底层机制 |
| L3B宿主有界固定点及L3C现有runtime5/49模块profile的客体固定点 | 已有限定范围验收通过 | 本轮重新核对G6原归档ZIP及两份独立审查报告SHA，全部匹配原验收记录。历史实际两启/同盘ELF/FLUSH/隔离/退休证据范围保持；本轮没有重新启动G6虚拟机 |
| G5完整语言、ABI与诊断差分覆盖 | **未完成，保留L3/G5待办** | 当前`lang/bootstrap/lower_program.dg:258`对GLOBAL/METHOD/ERROR/ENUM明确返回UNSUPPORTED；`docs/language-l2-l3.md`G5门槛仍未通过。49模块固定点不能代替完整语言覆盖 |
| M7、M10的代码合并与本地包含 | 合并项已完成；P5恢复仍未完成 | 本轮实际执行`git merge-base --is-ancestor 1dfebe1 HEAD`与`... d7468a1 HEAD`均exit0，证明两次实际merge已在当前HEAD祖先中；未用旧CI绿色宣称DMA恢复完成 |
| 未提交/推送、异机任务档案保留 | 约束与历史边界，不是开发待办 | 用户明确要求不建PR、不提交/推送；异机任务身份保持档案，不导入或制造新待办 |

## 本轮实际复验

对保留的实际客体原始归档执行现有完整runner的`--replay`，不启动VM、不写guest内存或寄存器、不模拟解码器：

| 归档 | 本轮结果 | 关键原始读回 |
| --- | --- | --- |
| P5正常control | exit0，6.219秒 | 两次held1/drain0 |
| P5故障fault | exit0，5.531秒 | 两次held1/drain0 |
| P2四核 | exit0，0.203秒 | phase10/steps1023/held0/516完整失效 |
| P2单核 | exit0，0.188秒 | phase10/steps1023/held0/516完整失效 |

完整命令、输入归档SHA、stdout SHA、当前源码SHA、合并祖先验证以及逐项结论保存在[机器可核对记录](2026-10-21-roadmap-completion-check.json)。原始输出在`code/build/roadmap-evidence-recheck/`；正式P5CTX2七文件和P2LIVE1十四文件当前字节仍匹配各自验收指纹。

## 展示修正

- `remaining`只列本节点原定范围内的真实未完成项；原定范围尚有缺口时不能标complete。
- 已完成节点的限定范围与其它阶段仍未完成的工作单列`scope_notes`，明确写“未完成”及所属P2/P5/L3阶段；不把它们当作已实现。
- P2/P5/L3/L3A继续partial，真实待办保留。没有通过本次文字调整关闭这些阶段或新增任何验收证明。
- 前端对已验收且无本项待办的节点显示“验收结论”；范围与后续归属另列。校验拒绝complete节点携带本项remaining，避免再次出现同一节点既通过又欠验收的矛盾。

相关任务图数据校验与界面回归共19项通过；首次新DOM断言暴露测试夹具不支持h4标签选择器，修正夹具为合法含数字HTML标签后复跑通过。无内核源码修改、任务状态修改、PR、commit或push。
