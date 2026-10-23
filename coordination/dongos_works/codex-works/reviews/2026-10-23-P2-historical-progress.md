# P2 历史采集、真实运行与后续屏障观察检查点

检查点：**2026-10-23 09:40 +08:00**。P2SYNC40仅同步这一有界事实；六份主文档原07:50及更早正文完整保留。P2软件/本机门仍 **partial**，P5本轮未实施，物理WC仍待真机。用户顺序为完成P2软件及本机门后进入P5，再将真机待验留档、完整代码上传GitHub并验证、最后关机。暂无真机不阻断该软件顺序；当前commit/push/shutdown均未执行。

[机器可读证据及SHA](2026-10-23-P2-historical-progress.json)按formal、historical diagnostic、actual failure、未测返修分别记录，没有总体pass布尔。旧[07:50 SYNC35检查点](2026-10-23-P2-deferred-capture-progress.md)及其JSON不改写。

## 正式结果与当前状态

| 项目 | 09:40边界状态 | 已实际执行的范围 |
| --- | --- | --- |
| OBS36 R3 | submitted rev12 | [0e6正式回执](../../.local/runs/0e6d7f219f48448eab82270188736f59/result.json)：bulk17+pcid22+GUI15+history17，共71项、0skip，source_stable/stopped/exited=true；尚未验收或集成 |
| B R8 | 历史submitted rev34的formal保留 | [c33正式回执](../../.local/runs/c33a7c763bd94b86925883bd6e76b217/result.json)：native1+harness37+Domain2+barrier1+buddy1+paging2，共44项、0skip，source_stable/stopped/exited=true；不是actual门通过 |
| B R9 | **in_progress rev36，未测试/未通过** | 原四个runner/test/doc/delivery路径做normal observation profile返修；负控exact-post/held/全ACK保持，验收和集成待后续整套 |
| SYNC35 | integrated rev6 | 旧07:50文档门及全部历史保留 |
| P5CTX1 / CTX2 | integrated rev7 / rev6 | 旧上下文记录和故障保持组件有效，不重复开发；未提供新恢复/复用通过 |
| P2SYNC40 | in_progress rev2 | 本文档交付尚待root审查、独立barrier1和分开的accept/integrate |

主目录另有[99项零skip预检日志](../../../../code/build/test/p2-historical36-review/host-precheck-r4.log)：19.321秒，OBS71+BHost28，仅协调者预检，不能与正式71相加成新的验收总数。其[源/契约复核](../../../../code/build/test/p2-historical36-review/obs36-root-review-r3.json)同样没有授予P2通过。

## R4/R5：明确历史镜像与诊断边界

两次均为冻结0e6观察器配显式795历史R6 normal image，不是c33新源B实跑。原始result始终diagnostic_only=true、acceptance=false、passed=false。

- R4 [原始result](../../../../code/build/test/p2-historical36-review/observer36-historical-image-diagnostic-r4/diagnostic-result.json)首个ps超时；首stop请求到cont1281ms=922ms确认+343ms bulk+16ms尾段。[独立raw审查](../../../../code/build/test/p2-historical36-review/r4-independent-review.md)核444份唯一raw：E1 Domain/Bridge.failed0，E2 AP Timeout/BSP Held并全核HLT。原1s绝对期限可能被观察消耗；未取得stop瞬间RDTSC，不能把全部时长归给bulk或认定WHPX内部首因。
- R5 [原始result](../../../../code/build/test/p2-historical36-review/observer36-historical-image-diagnostic-r5/diagnostic-result.json)仅observations_completed=true：13epochs、78bulks、690slices、52HMP；742物化文件、26批次，严格ps和四个GUI kill完成。[独立审查](../../../../code/build/test/p2-historical36-review/observer36-r5-independent-review.md)核359次leaf walk、末36parts及父子hash/真实UART；末Domain/Bridge.failed0、四CPU ACK8388，B attempted0/requested=false。最大pause859ms，但配置budget10s，不能称严格1s安全保证，也不是B/PCID/P2验收。

## B R8：新完整构建和两次actual失败均保留

c33不可变workspace的 `build/test/p2-runtime-large-build/run-892cf48fd37a/{normal,omit-ap-flush}` 均真实fresh构建，各 **1109 source / 1109 staged / 286 artifacts**，kernel.bin1966480B，距2MiB上限余130672B。两组大小相同但source/overlay/产物分别绑定，不能把历史1108或误写1119代入本轮。[真实build.identity重核](../../../../code/build/test/p2-historical36-review/b-r8-fresh-build-recheck.json)及[R8当时18项主线指纹](../../../../code/build/test/p2-historical36-review/b-r8-main-source-check.json)均保留；后者不表示正在返修的R9四文件仍与R8相同。

normal kernel SHA：`78fdf1e1dad488c754f57e20f26069946ef21299a1a8bafc7cf9171aaf716817`；omit kernel SHA：`7b05ca34ed325413ffb3fdda67198521e91b210df47c7cb165219882979a13e1`。具体receipt/command/log/kernel绝对路径和现读SHA见JSON。

[normal-r8原始result](../../.local/runs/c33a7c763bd94b86925883bd6e76b217/workspace/build/test/p2-runtime-large/qemu/normal-r8/result.json)仍passed=false，仅一次boot，未完成所需两个boot及later PCID/replay整链。32次epoch末E32已记录B complete1/poison0/steps127/barriers16/retired=reclaimed2，四CPU A→B→A→A真实读者记录完整，AP user_timers分别3852/3817/3742。B.post=22280，当前Domain.completed84550、后续sequence=barrier84551、expected15、CPU0持锁，Domain/Bridge健康。原legacy idle门反复未采到lock0/ownerNONE/barrier0，不能把继后屏障pending误写成B自身未完成，也不能据report.complete1宣布actual通过。[独立契约审查](../../../../code/build/test/p2-historical36-review/b-r9-normal-observation-review.md)已按原始内存/HMP核实该差别。

[omit-ap-flush-r8原始result](../../.local/runs/c33a7c763bd94b86925883bd6e76b217/workspace/build/test/p2-runtime-large/qemu/omit-ap-flush-r8/result.json)仍passed=false：首pause1781ms、首个严格ps超时，尚未触发B，无A/PTE-B负控窗口。因此这是观察失败，**不算指定漏AP flush负控成功**。两次actual均inputs_unchanged=true、owned exit rc0、cleanup完成；bulk_capture.final_disk_verified=true仅表示原始采集文件在退出后按磁盘现字节完整复核，两个failed result均未形成data.img的final_disk_sha256整链，不能据此宣称数据盘跨boot稳定或没有写入，更不能拼成验收通过。

时限按c33不可变源码 `tests/run_p2_runtime_large_qemu.py:686` 的 `until=time.monotonic()+120` 记录为120秒重试窗；早期口头90秒不精确，原任务书不改写。这个重试窗不是放宽guest原1s绝对期限。

## R9与剩余执行顺序

R9只在原四路径实施显式normal profile：默认legacy-idle-v1维持原样；current-kernel-v2仅允许同epoch全四CS8、GS对应实际Header、kernel CR3/tag0、BSP IF0/LOCKED、AP IDLE/KERNEL，completed>=B.post、各ACK>=completed，后续seq=completed+1的pending状态单独标注，绝不宣称当前barrier完成。negative exact-post/held/全ACK门不变；negative选择v2在启动前拒绝。这只是已审返修方向，此09:40边界未测、未通过、未验收集成，不把静态审查或旧R8回放重标为新actual通过。

P2仍待B修复后的完整正式与真实normal/精准negative双boot、最终raw replay；PCID cold→warm→retire→reuse及wrong-tag实际门；C/D正常服务接线、GOP授权ledger闭包、真实PF RawTrace和CACHE七森林；真正WC性能仍未验证。[C/D三项草稿](../../../../code/build/test/p2-historical36-review/cd-task-book-draft.md)及其[独审](../../../../code/build/test/p2-historical36-review/cd-plan-independent-review.md)仅是build目录只读计划，建议编号不是已发布任务或实现。

[P5恢复计划](../../../../code/build/test/p2-historical36-review/p5-recovery-implementation-plan.md)与[依赖独审](../../../../code/build/test/p2-historical36-review/p5-plan-independent-review.md)也仅只读：可信whole-device reset、post-unmap全核退休、整块隔离零化及最终identity后发布仍待实现；devmgr外部新block代际还需init有界接纳，不能声称现依赖链会自动恢复。P5本轮实施未开始，CTX1/CTX2历史不覆盖该差集。

Git当前main及本地origin/main均为`db4ea7c9a74839d95a5e80a0bbf8468a4bfa0d73`；工作区有未提交改动。此处仅记录已核本地ref，没有执行新上传。既有G5与已集成组件不重复；完成P2/P5软件和本机门前，不提前commit/push/shutdown。
