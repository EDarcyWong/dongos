# P2SYNC40 — P2 历史采集、44项复验与真实屏障观察失败进度同步

负责人：codex。状态：待领取。

用户固定顺序：P2全部软件/本机门→P5全部软件/本机门→真机待验留档→完整代码GitHub推送并验证→关机，执行不询问，未完成前不提前上传/关机。同步当前09:40+08左右真实检查点并保留六主文档原有全部body历史；每篇只在顶部追加明确带时间/边界的新checkpoint，旧07:50 SYNC35 integrated6记录保留。MCP优先实际核任务最新rev；source/contract/raw evidence各自区分。OBS36 R3 submitted12正式0e6d7f219f48448eab82270188736f59独立71/0skip/stable/stopped/exited，主预检99/0skip；R4历史image诊断failed ps timeout，首pause1281ms(922stopconfirm+343bulk+16tail)，E1Domain/Bridgehealthy E2Timeout/Held，444raw独核；R5同冻结observer+明确795历史R6image诊断observationscompletedtrue但diagnosticonly/acceptancefalse/passedfalse，13epochs78bulks690slices52HMP/742files26batches/strictGUIps4kill，末Domain/Bridgefailed0、四CPUACK8388，Battempted0/requestedfalse，独核359leafwalk+36parts，最大pause859ms但配置10s非1s保证。B R8正式c33a7c763bd94b86925883bd6e76b217完整44零skip/stable/exited，两fresh run-892cf48fd37a build各1109source/1109stage/286artifacts、kernel1966480 margin130672，root重新identity及18主线指纹匹配。真实normal-r8仍passedfalse：32epochs末B.complete1 poison0 steps127/barriers16/2retiredreclaimed，APtimer真增长，但当前Domaincompleted84550/later barrier84551/owner0锁1，B.post22280；原idle gate90s未采到idle，不把B组件完成当actual gatepass。R8omit真实首ps超时/首pause1781ms/无B触发，不算精确负控，两个actual都inputstable/ownedexit/finaldisktrue，原件保留。B R9 claim36只4路径normalprofile返修：legacy默认原样，新current-kernel-v2显式同epoch全4CS8/GSHeader/kernelCR3/ACK下界区分laterpending，negativeexact保持。此检查点R9未测试/未通过，验收/集成仍待后续全套。新的C/D三书与P5恢复/依赖计划仅只读build产物，非已发布实现/测试；C/D GOPledger/Rawtrace/7森林、PCID cold-warm-retire-reuse+wrongtag、真正WC性能仍未关；P2partial，P5本轮实施未开始。CTX1 integrated7 CTX2 integrated6原历史组件保留不可重做。G5和既有集成不重复。Git main db4ea7c9a74839d95a5e80a0bbf8468a4bfa0d73/origin已核，当前未commit/push/shutdown。只改九声明路径，不碰B/OBS正文doc/delivery及code/tests/coordination状态库index；状态由MCP统一。JSON列明确绝对evidence路径/实际SHA、scope、schema、tests/skips/source-stable/cleanup、actualfailed与diagnostictrue区分，machine flags不得布尔拼成总pass；root独立hash/artifact/source状态审查后正式barrier1复验再分accept/integrate。作者只编辑不测试编译VM/自行状态写。

## 可修改文件

- `PLAN.md`
- `docs/p2-acceptance.md`
- `docs/p2-extensions.md`
- `docs/p2-alias-consumers.md`
- `docs/remaining-plan.md`
- `docs/progress-map.md`
- `codex-works/reviews/2026-10-23-P2-historical-progress.md`
- `codex-works/reviews/2026-10-23-P2-historical-progress.json`
- `codex-works/deliveries/P2SYNC40.md`

## 定向验收

- `module:tests.test_user_smp_barrier`

交付：`codex-works/deliveries/P2SYNC40.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
