# P2SYNC35 — P2 观察器实际诊断、延后落盘复验与真机不可用状态同步

负责人：codex。状态：待领取。

按用户顺序先 P2 后 P5。更新六个现有主线计划/进度入口的顶部检查点并新增可追溯 MD/JSON，不覆盖历史。同步 OBS32 integrated6/正式29、SYNC33 integrated6、LARGE16 submitted17/正式35零skip但 actual 正常尚未通过，记录 actual-normal-r1、R2 API诊断失败、R3 before→explicit cont→terminal after 的真实来源/磁盘hash/stop-cont 3921ms/原1s期限自然老化及局限；OBS34 实现、独立复验、实际重建/启动最终结果以完成时真实回执为准，不预写 passed。用户于当前会话明确暂无真机环境，physical WC性能门标记待外部环境验证，不能关闭P2或以QEMU代替。P2仍partial直到所有原门实际通过；P5本轮尚未开始，不能因硬件不可用自行提前开始P5。绑定实际源码HEAD、任务最新rev、正式receipt和原artifact SHA，分清组件与运行接线/实际正常与精确负控/warmPCID/物理WC余项。原失败完整保留，无提交推送物理设备。可修改路径仅以下9项，禁止改DB/index/协调器状态文件。文档实施者不运行编译测试VM或自行验收；root冻结所有源/works再定向复验及实际审查链接/hash。

## 可修改文件

- `PLAN.md`
- `docs/p2-acceptance.md`
- `docs/p2-extensions.md`
- `docs/p2-alias-consumers.md`
- `docs/remaining-plan.md`
- `docs/progress-map.md`
- `codex-works/reviews/2026-10-23-P2-deferred-capture-progress.md`
- `codex-works/reviews/2026-10-23-P2-deferred-capture-progress.json`
- `codex-works/deliveries/P2SYNC35.md`

## 定向验收

- `module:tests.test_user_smp_barrier`

交付：`codex-works/deliveries/P2SYNC35.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
