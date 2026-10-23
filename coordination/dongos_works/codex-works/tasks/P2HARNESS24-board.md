# P2HARNESS24 — P2真实UART GUI收尾采集器命令契约修复

负责人：codex。状态：待领取。

实际P2LARGE16 normal-r1在close_gui发送stop terminal后收到unknown command，fresh_response准确拒绝，未取得B before/after；旧失败回执保持failed。修复共享close_gui，读取真实暂停一致Catalog的14..17配置/current token+generation/slot/incarnation身份、必要时真实ps回执，使用现有shell kill <token>，核精确新鲜KILL OK和后续Catalog KILLED=5/旧token释放；已不运行配置只据真实state安全跳过，不凭任意异常/旧输出当成功，防token代际竞争、错误配置/essential被kill/自动restart。不要新增shell stop别名、放松fresh_response或写guest内存寄存器。现有三调用方negative/PCID/B保持同helper，允许函数新增结构化执行证据不破坏调用；失败和QEMU清理保持。新增有效host控制覆盖坏PS/KILL回执、stale token/changedgeneration/alias、已停止/部分运行、正确配置与essential保留，默认/host不启动VM。写明只是采集器修复，B实际交易/AP PCID仍待root隔离VM，不能改历史回执。实现者只声明路径、不编译测试VM/提交推送/状态；root独立0skip复验后再实际使用。

## 可修改文件

- `tests/run_current_user_smp_qemu.py`
- `tests/test_user_smp_gui_control.py`
- `docs/p2-smp-gui-control.md`
- `codex-works/deliveries/P2HARNESS24.md`

## 定向验收

- `module:tests.test_user_smp_gui_control`
- `module:tests.test_user_smp_oracle`

交付：`codex-works/deliveries/P2HARNESS24.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
