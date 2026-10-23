# P2FLUSH11 — P2逐CPU实际CR4失效选择与共享屏障三态原生门禁

负责人：codex。状态：待领取。

用户最新要求先完成P2、再P5；不重做已integrated11个P2组件。当前user/shared_barrier.asm的纯selector声称原生测试但tests没有调用，调度后per-CPU PCIDE已由sched/user_arch启用，不能靠旧BSP软件flag选MOV CR3。补对真实生产ASM selector和共享屏障三态orchestration的native正反例，RUNTIME4/6/7分支、inactive才legacy、active成功不fallback、active失败永久拒绝、local或AP广播失败拒绝、PCIDE开关/PGE拒绝及旧BSP flag不具权威均覆盖；特权读CR/INVPCID仅在明确硬件边界替身，不能在宿主执行或声称硬件效果。只对私有copy替换local_flush硬件body（保持被测orchestration和selector逐字）；唯一漏broadcast/active错误回退/PGE接受真实坏ASM须正常构建运行并被独立C状态/顺序断言拒绝。保存命令/对象/日志/receipt/SHA及source stability；不skip，不启动OS/VM/CLI，不commit/push。更新地址空间契约，说明其余真实AP PCIDE和调度后owner范围，独立审查+协调器定向复验后本地集成。

## 可修改文件

- `tests/test_user_shared_flush.py`
- `tests/user_shared_flush_probe.c`
- `docs/user-address-spaces.md`
- `codex-works/deliveries/P2FLUSH11.md`

## 定向验收

- `module:tests.test_user_shared_flush`
- `module:tests.test_user_domain`
- `module:tests.test_user_smp_barrier`

交付：`codex-works/deliveries/P2FLUSH11.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
