# P2 延后落盘、实际诊断与验证环境进度

检查点：2026-10-23 07:50 +08:00。本文完成 P2SYNC35 的有界状态同步；
OBS36 与 LARGE16 R7 的后继实现不在本次通过范围内。
P2 软件仍 **partial**，P5 本轮仅只读准备，尚未开始实现。

用户已明确最终范围：完成 **P2、P5 全部软件工作及本机复验**，真机待验项留档，
之后将完整代码 commit/push 到 GitHub 并关机。当前暂无真机，物理 WC 性能仍为
**待外部环境验证**；P2 软件及本机门完成后可以进入 P5，物理待验不阻断该顺序，
也不能把 QEMU/WHPX 结果写成真机通过。上传与关机已授权，末端操作尚未执行。
这项直接澄清覆盖初始任务书及历史记录中“真机缺失阻断进入 P5”的旧措辞。

[机器可读来源](2026-10-23-P2-deferred-capture-progress.json) 保存回执和文件 SHA；
[06:32 历史记录](2026-10-23-P2-observer-progress.md)及
[05:42/05:55 历史记录](2026-10-23-P2-lock-diagnostics.md)保留原文。
各历史结果仍只适用于当时源码、授权范围和已执行的验证。

## 正式结果与当前任务

| 任务 | 最新 MCP 状态 | 正式独立回执及范围 |
| --- | --- | --- |
| OBS32 | integrated rev6 | [c44b321d8dd0470b8989a23fbd24804f](../../.local/runs/c44b321d8dd0470b8989a23fbd24804f/result.json)，bulk10+pcid19，共29项、0skip |
| SYNC33 | integrated rev6 | [0c2eb82c5c8a41c8bf1ad6819318acd7](../../.local/runs/0c2eb82c5c8a41c8bf1ad6819318acd7/result.json)，barrier1项、0skip，文档语义另经实际审查 |
| OBS34 | integrated rev6 | [afc75c10c58e4ca7aca83b82ce71b217](../../.local/runs/afc75c10c58e4ca7aca83b82ce71b217/result.json)，bulk17+pcid19，共36项、0skip；仅 IO 证据组件 |
| LARGE16 | in_progress rev26 | R6 [7951803b495e40bcbd2ff85940ea7063](../../.local/runs/7951803b495e40bcbd2ff85940ea7063/result.json)正式37项、0skip保留，实际 R4 失败后原任务返修 R7 |
| OBS36 | in_progress rev2 | [任务书](../tasks/P2OBS36-board.md)所述历史镜像/离线审计改造，尚未测试或取得实际新结果 |

上述完成的正式回执均为 source_stable、process_stopped、execution_exited=true。
R6 的37项为 runtime_large1、harness30、Domain2、barrier1、buddy1、paging2，
不是实际正常或精确漏 AP 失效门通过。
旧 [bc1cdec40017404eabc6103c7abe44ec](../../.local/runs/bc1cdec40017404eabc6103c7abe44ec/result.json)
35项、旧 R3 31项与历次失败均继续保留，不被新结果覆盖。

root 还实际执行 bulk17+pcid19+B Host21 共57项、0skip、6.199秒本机预检，
[原始日志](../../../../code/build/test/p2-deferred34-review/host-precheck.log)
SHA256 为 `0d5b5ee46bd15ca5ed7d380fbdefa4df099f42cd30153dc9b2b93ea7f17c15b3`。
这与36/37项正式副本复验分开，不将重复运行相加为新增功能覆盖。

## 服务中断与真实新源构建

R6 首作业 [630b7740b10041239acbf372630b50fa](../../.local/runs/630b7740b10041239acbf372630b50fa/output.log)
因协调服务07:20:45重启而 interrupted，没有 result.json，不计通过。
root 实际 Win32_Process 清点确认无原 job/unittest/build/NASM/GCC/LLD/QEMU 存活，
[停止确认记录](../../../../code/build/test/p2-deferred34-review/service-interruption-stop-check.json)
SHA256 为 `915b193d73fb219ed8034e67b0f0114bae01c87ae072ebc0fd1626b738672dd4`。
经文档 HTTP client.manage_task confirm_pause 为 rev22 paused，再正常 resume 为
submitted rev23 后重排795；没有手改 DB/index 或用中断回执冒充通过。

795的 ActualBuildTests 在其真实 immutable B workspace 重新构建 normal/omit。
root 在复核时检查 build.identity 两份完整来源及当时主目录23份指纹一致，
[构建复核回执](../../../../code/build/test/p2-deferred34-review/build-recheck.json)
SHA256 为 `5ebfcb6312919808eb9f33f07453b6e96c5e3f9ff77e867c29bbccd84f0588ed`。
每份均1108 source、1108 staged、286 artifacts、1,966,480B，
loader余量130,672B；真实链接、源码与工具/产物链通过，测试篡改后恢复。
后继 R7 正在修改 main，这份比对只证明复核时指纹，不将其扩展到未冻结新源码。

| 795新构建 | 实际来源回执 | kernel.bin SHA256 |
| --- | --- | --- |
| normal | [run-4287abada43e/normal](../../.local/runs/7951803b495e40bcbd2ff85940ea7063/workspace/build/test/p2-runtime-large-build/run-4287abada43e/normal/runtime-large-source.json) | `78fdf1e1dad488c754f57e20f26069946ef21299a1a8bafc7cf9171aaf716817` |
| omit-ap-flush | [run-4287abada43e/omit-ap-flush](../../.local/runs/7951803b495e40bcbd2ff85940ea7063/workspace/build/test/p2-runtime-large-build/run-4287abada43e/omit-ap-flush/runtime-large-source.json) | `7b05ca34ed325413ffb3fdda67198521e91b210df47c7cb165219882979a13e1` |

两来源回执 SHA 分别为 `8bee4e5a208d5cb4935b0fce72fad9e77a0ebbc17f3a49cd28eeef787b76a4af`、
`d0ec4f48adc71477ffa28bdf9752bcf5869b536e01d32ee36884f981ba3c01cd`。
旧c44的 [normal](../../../../code/build/test/p2-observer32-review/runtime-r5-normal/runtime-large-source.json)、
[omit](../../../../code/build/test/p2-observer32-review/runtime-r5-bad/runtime-large-source.json)
也各为1,966,480B/286产物、kernel字节相同，但来源仍是c44，不能重标为795或OBS34构建。

## 旧 R1–R3 诊断完整保留

[actual-normal-r1](../../../../code/build/test/p2-observer32-review/actual-normal-r1/result.json)
首次 ps 出现 `ValueError: UTF-8 UART response timeout`，passed=false、输入不变。
首停原字节独立解码时16个Failure槽全零，Report/Domain/Bridge.failed均0，
四CPU requested=acknowledged=4752；BSP PROJECT持锁、AP ACQUIRE等待。
stop→cont为5266ms：确认1094ms、六dump156ms、sealed后host工作约4016ms。
只有首epoch，不能拿首缓存当作cont后内存，也不能据failed=0证明期限尚有余量。

[R2诊断](../../../../code/build/test/p2-observer32-review/resume-diagnostic-r2/diagnostic-result.json)
被 `ValueError: only read-only register HMP is captured` 拒绝，属于诊断API使用失败，
不是新生产超时或正常门结果。diagnostic_only=true、acceptance=false、passed=false，
输入稳定与QEMU rc0清理原样保留。

[R3实际脚本](../../../../code/build/test/p2-observer32-review/diagnose_resume_r3.py)与
[归档脚本](../../../../code/build/test/p2-observer32-review/resume-diagnostic-r3/diagnostic-script.py)
逐字相同，SHA256 为
`6dcd9d958290a33c07b84d869cd8996b7c35a2b1b1419ff6a2f367111e80b8ee`。
[结果](../../../../code/build/test/p2-observer32-review/resume-diagnostic-r3/diagnostic-result.json)
及[两epoch manifest](../../../../code/build/test/p2-observer32-review/resume-diagnostic-r3/boot-1/physical-bulk-manifest.json)
记录 before→显式cont→约203ms连续运行→terminal after，最后不再恢复。

[独立审查](../../../../code/build/test/p2-observer32-review/r3-independent-review.json)
SHA256 为 `dae2012717c3d9d9ec49ccd7f5aab02426a1db53d248fddb90bc6d536ed7614b`。
12 bulk+506 slice+8 register source+8 alias共534文件，最终磁盘长度/SHA、
父bulk逐字切片、epoch/CPU/HMP原文、serial prefix与时间线全部一致。
另核1108源、1108 staged、286产物、4构建工具、284运行工具及真实ELF/layout；
独立页表解码与结果内Report/Domain/Bridge/16 Failure/16 Progress/16 Cpu逐项一致。
审查通过只指证据一致性，R3仍diagnostic_only=true、acceptance=false、passed=false。

| R3观察 | Domain / Bridge | 锁、ACK与首错 |
| --- | --- | --- |
| epoch1 before | failed均0 | owner2/lock1，sequence=completed=4216、barrier0，16个Failure全零 |
| epoch2 terminal | failed均1 | 原Progress不变；AP1/AP3原Timeout `0x06090005`，BSP/AP2传播Held `0x06090004` |

R3 stop→cont **3921ms**，dump→sealed140ms；终末dump219ms后不再cont。
按真实tsc_hz=3417784570，原deadline−wait约1秒，Failure.clock−wait约3.933秒，
超过旧deadline约2.933秒。强烈支持本轮暂停自然老化原期限，不能据此放宽deadline、
更改guest TSC或认定FIFO已经修复生产首因，也不证明全部旧故障同源。
首stop没有精准guest RDTSC，主机monotonic与guest TSC起点不同，无法确定越界瞬间。
disk_unchanged缺持久化pre-boot SHA，只能保留协调器报告和独立最终disk SHA；
无完整QMP总录，未写guest的依据是实际脚本及来源绑定，不冒充hypervisor写陷阱证明。

## 新 R4：IO 优化成立，实际正常门仍失败

root 从795新normal ESP实际执行四CPU WHPX，CPU参数为
`host,-vmx,-mpx,-sgx,-sgxlc`，`kernel-irqchip=off`、require_pcid=true。
[actual-normal-r4/result.json](../../../../code/build/test/p2-deferred34-review/actual-normal-r4/result.json)
SHA256 为 `a034554b0f18da17970df8a2cdde65ad28a0540d58d68955ccf77035a84f72e2`：
首个 ps 仍为 `ValueError: UTF-8 UART response timeout`，passed=false、
inputs_unchanged=true。仅启动一次normal boot，QEMU rc0、进程停止、cleanup完成、
final_disk_verified=true；没有正常完成或精确omit-AP-flush实际通过证据。

[原始v2 manifest](../../../../code/build/test/p2-deferred34-review/actual-normal-r4/boot-1/physical-bulk-manifest.json)
SHA256 为 `4a62b300db0067d8ab585e06e93d1998253aef1bf08e2d100152256f82b12ab3`。
首stop确认0ms、六bulk235ms；之后host暂停内审计4453ms，
总stop→cont **4688ms**。424个派生slice在真实cont/query确认后的resume批次中
用250ms物化，6bulk+424slice共430raw的长度/SHA/父切片由root独立核对。
延后IO的时序成立，仍未消除暂停内Python/ELF/池审计；固定10秒预算不保护原1秒期限。
这里只有一个epoch，不能把它解作恢复后的Failure，也不把通用UART超时当精确坏体命中。

OBS34因此以**IO证据组件**验收并 integrated6，不声称实际性能问题全部解决、AP/PCID/P2通过。
LARGE16在实际失败后由submitted24返修25再claim26，R6正式37项及新构建继续作为历史证据，
不能代表正在修改的R7源码已经通过。

## 接续工作与软件完成边界

[OBS36](../tasks/P2OBS36-board.md) in_progress2 将引入独立历史镜像 profile：
真正paused阶段只做stop/query、六bulk、四CPU只读HMP及固定serial边界封存，
runner显式cont/query后才以CapturedImage(epoch)进行重型constructor/ELF/私有池、
PCID/B组装和解码。live Guest读数继续要求真实paused，不伪造stopped，不把历史PA
数据冒充当前读取；新profile记录真实派生/物化时间，旧v1/v2仍绑定旧immutable runner。
失败/terminal镜像在owned退出后解码，不为节约时间恢复已知失败。
这仍是未测试接续实现，不是本次已完成的修复。

LARGE16 R7按原四路径接此API，保留before→五个真实ordinary UART launch→after→later PCID，
完整身份/ACK/原期限/精确负控不弱化，首failed after不得覆盖。
[备选设计](../../../../code/build/test/p2-deferred34-review/offline-audit-design.md)
SHA256 为 `728226556ec1b870d1dc9590f147a4afd3c29851cba082de6b0deecf0de5dbaa`，
只是只读设计，不是实现或实际运行证明。最小暂停窗口若仍扰动原期限，需另做连续UART
加guest内部不可变phase/raw trace，不能直接放宽门槛。

P2软件还包括实际大页正常/精确负控、生产EXEC/受控PF/CACHE接线、暖PCID等；
组件验收不替代正常runtime7服务及每CPU真实操作、ACK、根身份和字节证据。
P5的 [cursor:P5CTX1](../../cursor-works/tasks/P5CTX1-board.md) 已 integrated7，
[codex:P5CTX2](../tasks/P5CTX2-board.md) 已 integrated6，旧交接todo不是当前状态。
本轮P5只读准备，后继软件差集包括真实drain/unmap后全核TLB退休、精确回收与新token重启等，
不重复已集成上下文组件。P2软件及本机门闭合后进入P5，真机待验留档不阻断该顺序。

## 本次文档检查范围

六入口新增本checkpoint，移除新增前缀后与SYNC33 immutable正文逐字一致，
所有06:32/05:55/05:42历史保持原样。JSON绑定六入口、本文、正式回执和原始artifact，
交付单再绑定JSON，避免自引用哈希。
本次实施者只做静态JSON、本地链接、SHA与历史字节检查，未编译、运行unittest、
OS/VM或修改MCP状态、DB/index、共享派生进度；未commit/push/shutdown。
本次文档的barrier独立检查与语义验收由root后续实际执行，不预写新通过回执。
