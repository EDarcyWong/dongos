# P2 锁诊断与当前状态：05:42检查点及05:55追加

## 2026-10-23 05:55 +08:00 追加

SIZE23 已验收并 integrated rev6，SMP27 v2 已验收并 integrated rev9；LARGE16 仍 submitted rev13，完整实际门禁未关闭。SMP27 作业 `326a3816570445f08a69f2c87658e27a` 四模块全部通过、零skip、source_stable/process_stopped/execution_exited=true；root又核134条命令、46条原生执行、420产物SHA均一致。HARNESS28待其本项复验；GOP29已submitted rev3，FIFO BKL30仍组件开发/审查，不因此接入生产。

新同源完整构建含诊断v2及永久Gate，raw **1,966,480B**、余 **130,672B**；285产物经严格identity绑定，Gate entry SHA与交付完全一致。R12读到AP实际旧deadline约38.675e9 tick，failure约51.671e9 tick，而BSP原获锁时刻约35.258e9。源码审查发现继承采集器在首stop后做数百QMP读，再由`ProcessGuest.settle`执行cont；不能把这段长暂停引入的绝对时间间隔当作生产锁首因。

R13对照保持相同guest代码、寄存器、TSC和期限，首次stop前让guest连续运行2秒，并禁止任何后续resume、抑制原settle的cont。**Domain.failed=0、全部Failure槽未发布，AP user_entries/switches分别161/168/213，user_timers仍全0**。这验证了AP能实际运行，也说明此前观察流程确有干扰风险；完整PCID/计时/事务门禁仍待后续采集，不能将本诊断的passed=false升级为阶段通过。

R13完整根池审计成功：检查全部16槽，其中11个live根，slot0静态、其余真实arena32页（compositor128页），PA/VA/Space/Frame/generation/metadata/511共享槽与全部池别名均通过。内核used_total=74/128，NEXT_PAGE=10423/32768（42,692,608B）。548份原始读取长度/SHA逐一核对；inputs_unchanged=true；owned QEMU rc0/stopped=true/alive=false/cleanup=true；本轮诊断脚本在启动前另存副本且SHA吻合。证据：[R12](../../../../code/build/test/p2-smp27-review/actual-timing-whpx-r12/boot-1/smp-diagnostics.json)、[R13](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/boot-1/smp-diagnostics.json)，更多字段及SHA见机器检查点的追加记录。

下一步先将多次慢QMP读取改为同一次短暂停内批量封存，再离线读取同epoch原始字节；保留真实停机/恢复时间线与严格来源校验，禁止改TSC/期限或以FIFO代替观察方法修复。P2仍partial，P5本轮余项仍未开始。下方05:42检查点完整保留，按当时状态阅读。

## 05:42历史检查点

执行顺序为 **先完成 P2，再完成 P5**。P2 保持 partial；本轮尚未开始 P5 余项开发或验收，既有存储等已验子集保留。G6DOC1 仍 paused rev2。此检查点记录实际状态，不关闭阶段复选框。源码 HEAD 为 `db4ea7c9a74839d95a5e80a0bbf8468a4bfa0d73`，本地工作树有已授权未提交变更；未提交或推送。

| 任务 | 此检查点状态 | 实际证据与边界 |
| --- | --- | --- |
| P2SIZE23 | submitted rev4，正式复验通过，未验收/集成 | 作业 `17210f23966143d098950d2a4a119714`，十模块共99项、零skip、source_stable/process_stopped/execution_exited均true |
| P2LARGE16 R3 | submitted rev13，正式复验通过，未验收/集成 | 作业 `1edb5da569a54e5a8ff2a067e2ac1ee9`，六模块共31项、零skip、三稳定/退出标志均true；实际多核事务正负控仍未通过 |
| P2SMP27 v2 | submitted rev6，复验运行中 | 作业 `326a3816570445f08a69f2c87658e27a`；新增等待起点/原deadline/实际获锁时刻，不改锁、ACK、期限或held。完整四模块结果尚未产生 |
| P2HARNESS24 | integrated rev6 | 作业 `1e1aca5ebfee495f83d984acb615f038`，18项零skip；真实shell GUI收尾采集组件，不是guest通过 |
| P2HARNESS28 | submitted rev3，未复验/验收 | 修复旧服务测试缺少 LARGE 接线依赖；真实类型和poll注册、受限RAM边界，LARGE事务明确未启用 |
| P2GOP29 | in_progress rev2，待提交复验 | 永久静态GOP writer Gate与真实渲染器原生探针；未编译/测试/VM，不证明CPL3 compositor已排空 |
| P2BKL30 | in_progress rev2 | FIFO sidecar组件开发中；不改Domain ABI、不续绝对期限，仍须真实轮询/ACK及失败持有；尚未接Bridge或测试 |

ENTRY21、DISCOVERY22 已各自 integrated rev6；ROOT13/MASK18、FLUSH11、PCID12/WC14准备、EXEC19/CACHE20组件既有结论保持原范围。组件集成不证明实际 AP 用户执行、受控 PF 或调度后缓存迁移。

## 本轮实际构建与资源

LARGE16 R3 的正常版和仅漏AP失效调用的负控版均真实构建成功。root 在测试恢复所有篡改后，分别重新调用严格 `identity`，重建验证完整命令、工具、源图、profile、ELF/raw/IMG/bundle和每份285项产物。

| 构建 | raw字节 | 2MiB余量 | kernel.bin SHA256 |
| --- | ---: | ---: | --- |
| normal | 1,962,384 | 134,768 | `2906f46ff0f7fcd67fa6e07e5314093b2a057bc23ba3a695d714240d874f5d33` |
| omit-ap-flush | 1,962,384 | 134,768 | `fc4fc7b1ef484f9ce5d0afa578ebd0bb783694292a706cdc4b0420f1c6d74484` |

构建位置：`coordination/dongos_works/.local/runs/1edb5da569a54e5a8ff2a067e2ac1ee9/workspace/build/test/p2-runtime-large-build/run-f030f60846df/`。当前runtime7绑定精确单静态池；正常/负控不能沿用旧两池回执。

SIZE23 正式作业还产生真实WC私有overlay构建，raw **1,974,672B**、余 **122,480B**。它保留两文件overlay和test=True，不是物理WC性能结果。R11实际暂停读到 canonical kernel Space：pool_count=128、used_total=68；service PLAN arena=128MiB、NEXT_PAGE=8175/32768（33,484,800B，剩24593页）。这些是失败暂停状态的实际资源观察，不证明完整健康运行。R10离线树重走的67个可达表不等同分配元数据中的free数；R11 used_total才是该暂停点的实际计数。

通用完整池审计在R10/R11均明确拒绝 `empty process retained Space/root identity`。当时存在root=0且Space非空的记录，不能把此前部分已审根或最终预算数写成整次审计通过；需要健康运行后重做完整16槽/Frame/generation/Space/metadata/alias审计。loader仍持有2MiB物理窗，静态减少不表示归还物理RAM。

## WHPX R9、R10、R11 的实际失败

三轮均由root启动独占QEMU，实际配置为Q35、4 CPU、2GiB、WHPX、`host,-vmx,-mpx,-sgx,-sgxlc`、`kernel-irqchip=off`。构建/工具输入前后相同；诊断从未返回阶段通过，始终 `diagnostic_only=true, acceptance=false, passed=false`。

| 运行 | 首错和暂停观察 | 原始物理读取 |
| --- | --- | ---: |
| R9 | CPU2/1先报Domain.Timeout `0x06090005` @ACQUIRE，owner=3；CPU3随后Held `0x06090004` @UNLOCK；CPU0也Timeout。sequence/completed=1922、barrier=0，实际ACK完整 | 519 |
| R10 | 三个AP均Timeout @ACQUIRE，owner=0，sequence/completed=1931、barrier=0 | 538 |
| R11 | AP1/3 Timeout、AP2 Held @ACQUIRE，owner=0，sequence/completed=1933、barrier=0 | 543 |

所有AP的 user_entries/user_timers/switches **仍为0**。BSP分别有3671/3670/3645次用户进入；桌面就绪或BSP进展不替代AP门禁。所有原始文件的长度及SHA256由root逐一核对，无缺项；独立审查还把R9 Failure/Progress原始数组逐字段复算为JSON。只把published=1且版本/CPU槽匹配的记录作为完整首错。

三轮所有owned QEMU均真实停止，returncode=0、process_alive=false、cleanup_completed=true。该退出码只证明清理成功，不能把客体超时变为通过。原始位置及JSON/manifest SHA见[机器检查点](2026-10-23-P2-lock-diagnostics.json)：
[R9诊断](../../../../code/build/test/p2-smp27-review/actual-whpx-r9/boot-1/smp-diagnostics.json)、
[R10诊断](../../../../code/build/test/p2-smp27-review/actual-whpx-r10/boot-1/smp-diagnostics.json)、
[R11诊断](../../../../code/build/test/p2-smp27-review/actual-large-whpx-r11/boot-1/smp-diagnostics.json)。

这三轮使用诊断v1，缺少等待起点和持锁持续时间，**不能认定最后owner就是首因**，也不能排除长服务、锁竞争或WHPX调度停顿。当前TAS没有公平保证是代码事实；FIFO只修复插队风险，不能先宣称已消除超时。SMP27 v2新增三项真实时间字段，正在生成新完整构建供下一轮采集。旧失败回执不重写或升级。

## 仍需完成

1. SMP27/HARNESS28/GOP29/BKL30的完整独立复验和源码审查；公平锁通过后实际接Bridge并重新构建。
2. 健康四核下的AP用户进入、真实timer/switch、PCIDE=1、暖tag/跨代复用；大页正常事务与精确漏AP失效负控。
3. C/D正常服务接线：完整独立GOP alias ledger/epoch、统一poll、EXEC真实42/43与受控写保护PF、全部GOP alias WC→UC→WC及每CPU维护/退休回收原始证据；Gate不能替代compositor capture。
4. 相关桌面/USB/进程生命周期回归、最终尺寸与完整根池/arena审计。
5. 物理显示WC吞吐。先前机器可用性问题尚未收到答复；本轮不假定已有机器，不操作物理USB、重启或以虚拟计时替代物理门槛。

全部P2必需门禁通过后再进入P5余项：可信DMA排空、全别名退休/回收复用及设备恢复等。当前阶段状态不由宿主测试数量关闭。

此前[05:02运行检查点](2026-10-23-P2-runtime-progress.md)及R1/R2、R8、509f首轮services夹具失败历史保留。此次文档只更新声明的六份代码进度文档和本检查点；协调器仍统一管理任务状态，没有手改数据库、index、协作总图或roadmap。

