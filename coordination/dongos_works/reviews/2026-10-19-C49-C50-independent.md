# C49 / C50 独立复验与 R1 审查

项目 dongos。实际阅读两项最新完整任务契约、交付、生产源码、说明、永久测试，以及 C22 compare、CR10 branch、C41 direct invoke/C34 setup 等相关已集成实现。独立定向复验与源码/测试有效性审查分开记录；定向测试通过不直接授予验收。本轮不改两项四文件、主线、依赖或编译器，不启动 AI CLI，不运行 OS/VM 或全回归。

## 正式定向复验

两项均从 submitted rev4 排队，只执行各自预先声明的 checks。完整结果与输入指纹见同目录 `2026-10-19-C49-C50-evidence.json`。

| 任务 | 作业 | 检查 |
| --- | --- | --- |
| C49 | `922a95d14f8247fd8616080fb93ff321` | `discover:claude-works/tests:test_nasm_u64_select_function.py` |
| C50 | `5f149631ee114d7ba816b16610f4d902` | `discover:claude-works/tests:test_nasm_u64_forward_function.py` |

正式回执及输出位于 `.local/runs/<job>/result.json` 与 `output.log`。各任务正式计数、耗时、源码稳定性和最终状态在文末追加，不把排队当作通过。

## 生产与容量方案审查

C49：写入之前完整检查 written/名字/out 区间、别名、名长、枚举与块编号；CR3→CR11→C37→CR12→C22→test→CR10→两组 CR18/C42 接线符合契约。yes 真落入、false 跳 no，两出口各有真实 ret。局部 1024 字节，段分配总界 1018，最大实际文本界 698；用户容量失败不会发布头部。文本/独立比较模型、20 个有限原生向量和原有槽互换/路由/容量负控均已审查。

C50：读取 map 之前完成乘法、对齐、端点、完整别名、数量与名字长度检查，自调用按两名字字节比较；frame 与专用结果槽隔离。C37 捕获之后，由 C41 真正 setup/call/cleanup/capture，再经 C42 返回，无尾跳绕过。对于最多 6 个 kind0 字，全部寄存器传参，C37 文本 ≤156，C41 setup ≤156 + call ≤272 + capture ≤26，总 ≤454；256/640 的接收段足够，各组件仍用自己的完整内部 scratch。各段累计 1356 ≤1536，最后复制发布。已确认当前编译器 4096 worst-case frame 限制，本轮不要求仅为达到任务书较大的接收段数字而重写正确生产算法或改编译器。原有 16 向量实参/调用次数/入口对齐/hash 与 map/返回槽/容量负控已审查。

本轮未发现需返修上述生产接线的证据；两项 R1 均限于下述原生测试桥观察与宿主恢复。

## 两项各自独立实证的阻塞问题

C49 的 `test_nasm_u64_select_function.py:325-333`、C50 的 `test_nasm_u64_forward_function.py:371-379` 都在调用前以 RBX 保存 io 指针，返回后仍直接用 `[rbx+...]` 写观察值，最后直接对返回的 RSP 执行 `add rsp,8; pop...; ret`。观察路径信任了正在受测的寄存器，且没有独立的宿主栈恢复锚。这与各任务要求的完整 callee-saved/RSP 观察和安全恢复后断言不符。RSP 恢复问题来自静态路径审查，本轮未执行坏返回栈或非法地址坏体。

独立脚本：`reviews/2026-10-19-C49-C50-probe.py`，分别运行：

```text
python coordination/dongos_works/reviews/2026-10-19-C49-C50-probe.py C49
python coordination/dongos_works/reviews/2026-10-19-C49-C50-probe.py C50
```

所有修改仅在独立临时构建副本：真实 Dong 在正常 ret 前生成 `add rbx,8`，保持 RAX、RSP、返回地址不变。原桥的错位写仍在其 14-qword io 分配范围内，不引入越界或依赖异常。每模式先运行正式隔离副本实际 Dong 生成的同输入好侧，再运行真实编译的坏体；全部实际组装 ELF64/COFF、链接与原生执行。

| 任务 | 输入与路径 | 独立 RIP 快照结果（debug/release） | 原桥结果 |
| --- | --- | --- | --- |
| C49 | 原向量 0 / 1，分别走 yes / no | 正常退出0，两个 RAX 分别为 6477583639042326529 / 13897545500111929602；RBX 4223048→4223056，RSP平衡、其他callee-saved和canary正确 | 两路径都将 canary 数值 6674804268309651740 错读为 ALIGN，报 `caller rsp aligned before call` |
| C50 | 原向量5，6入参/6项map，真实包装器→独立 C callee | 正常退出0，RAX=15723061614180230438，RBX 4227240→4227248；callee调用1次、入口rsp%16=8、arity和收到实参正确，RSP平衡、其余保持正确 | 同样因错位观察把 canary 读成 ALIGN，报调用前对齐错误 |

好体均先通过原桥与独立桥，RBX 差值0；坏体由独立地址先捕获现场、再从独立锚恢复宿主 ABI，最后正常返回，得到 RBX 差值8。此证据不是“原测试漏拒绝”的实证；它证明原桥写坏自己的观察结果，并把被调用者寄存器破坏误报为调用前状态错误。更任意的返回 RBX 会使观察写入指向不可访问区域；该后果仅由静态寻址推导，本轮没有执行。现有错误分类不能充当契约要求的可靠数值保持检查。

证据目录：

- C49：`claude-works/build/C49/independent-a9f6af944d35/review.json`；同输入正式好侧来自作业 workspace 的 `run-63524ed67d4b/`。
- C50：`claude-works/build/C50/independent-ea64fc80ceed/review.json`；同输入正式好侧来自作业 workspace 的 `run-6c1cd3779693/`。

独立探针前后 C49 生产/说明/永久测试与14个只读依赖、C50对应文件与13个只读依赖 SHA 均相同。完整原值与探针结果写入 evidence JSON，保留临时坏源码、汇编、对象、原生 stdout 和日志。没有把崩溃、构建失败或超时当作负控。

## 分别退回原负责人 R1 的要求

1. 各自只修改本任务四个授权文件。保留现有正确生产接线和全部已有负控，不借机重写组件、不改依赖、不让一个任务替另一个任务交付。
2. 在调用前独立保存宿主栈锚和观察区地址；返回后用独立地址捕获真实 RAX、RBX/RBP/R12..R15、RSP，然后恢复宿主栈及 ABI。不能用返回的 RBX 定位观察区或用返回的 RSP 恢复宿主。
3. 各自加入安全的真实坏 Dong RBX 保持负控；同输入正式好侧先真实生成与执行，坏侧正常原生返回后由指定 RBX 数值断言拒绝，不允许以错位/对齐/guard、构建失败、崩溃、超时或文本差异代替。C49 覆盖两出口；C50 保留真实跨函数调用链与 callee 记录。可复用本轮有界+8向量，不增加超出上限的主要向量。
4. 保持全部语义、路由、map、初始化、容量原子性、别名、只读保护、debug/release、ELF64/COFF 和 SHA 稳定要求。更新说明/交付，重跑本任务 checks 后原编号重新提交，再独立复验。

本轮不验收、不集成，不宣称完整 L3/自举完成。

## 正式结果与处置

- C49：4 项通过、0 skip，测试进程耗时 87.547 秒，source_stable=true，未取消、未超时，完成后 submitted rev5。
- C50：4 项通过、0 skip，unittest 91.116 秒、测试进程耗时 91.375 秒，source_stable=true，未取消、未超时，完成后 submitted rev5。
- 两项各自独立补查通过好侧并复现观察缺口，输入与依赖 SHA 稳定；分别从最新 rev5 登记原编号 R1（rework rev6），不授予验收或集成。退回说明完整记录于协调器任务 review_note，正式作业历史保留。
