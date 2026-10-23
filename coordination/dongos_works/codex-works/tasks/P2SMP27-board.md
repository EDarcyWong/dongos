# P2SMP27 — P2真实AP首次进入失败的精确只读诊断回执

负责人：codex。状态：待领取。

实际WHPX R8使用已验收Discovery22新完整构建到达DESKTOP_READY，但所有AP user_entries/timers/switches仍0、Domain/Bridge failed，只有通用Header USER_ENTRY_ERR，不能确认具体失败原因。保留此真实失败；实现严格有限的生产诊断字段来定位真实Bridge错误及阶段，不放宽任何成功条件/timeout/PCID/ACK/BKL/fail-held、不改Domain/Cpu/Bridge/Header既有ABI或原异常恢复。建议每真实cpu一固定Failure槽，仅自身当前CPU写且只首次错误发布，记录实际stage,error_code,clock,raw_root,Domain sequence/owner/lock/mode/requested/ack；读者须published=1。首次出错前明确阶段标记checked/poll/acquire/drain/choose/commit，不能在每个轮询中无限日志、不得字符串/串口热点，保持失败返回MAX和held逻辑完全相同。原本err(e)被held丢失应记录真实e再调用原held；诊断自身不调用Domain acquire/poll/flush/alloc，不改变requested/ACK/队列/Frame/注册。仅附加独立BSS小字段，禁止巨型局部或扩大budget；无ACTIVE/invalidCPU时必须安全最小记录或拒，不能解引用坏指针。补有效host真实DG/native控制核超时/硬件错误/checked失败的实际code与stage、首错不覆盖、CPU归属/guard、失败返回不变，保留既有entry/services/barrier检查。新实际guest由root后续freshbuild读原始字段才判原因，host不宣称AP成功。实现者只声明路径，不编译测试VM/提交推送/状态/验收集成。

## 可修改文件

- `kernel/sched/user_bridge.dg`
- `tests/user_smp_failure_probe.dg`
- `tests/user_smp_failure_probe.c`
- `tests/test_user_smp_failure.py`
- `docs/p2-smp-failure-diagnostics.md`
- `codex-works/deliveries/P2SMP27.md`

## 定向验收

- `module:tests.test_user_smp_failure`
- `module:tests.test_user_smp_entry`
- `module:tests.test_user_smp_services`
- `module:tests.test_user_smp_barrier`

交付：`codex-works/deliveries/P2SMP27.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
