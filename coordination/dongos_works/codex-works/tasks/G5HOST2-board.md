# G5HOST2 — 固定ELF窗口在宿主预分配与两次装载间的真实持有

负责人：codex。状态：待领取。

继续用户授权的G5闭包必要宿主适配。G5HOST1小门禁证明原线程退出后2MiB固定窗口可用，但完整闭包c464866d6f9b4fb2beeac4c23d9974fc仍真实FAIL ELF map：宿主guarded小块/CRT分配在首次load前可重用释放的低地址。Windows worker在进入原harness前暂时reserve 400000–600000，真实load前释放并按ELF原始段映射，small ELF卸载后立即重新reserve，保护随后malloc保存完整ELF到实际load之间的窗口。不能移动/修改ELF，不解除无关分配，arena/64KiB compiler栈/2MiB ELF不变。扩展真实宿主门禁在映射前执行guarded/堆分配并验证窗口的持有、释放、重持有及重复装载；固定坏PE必须实际失败，零skip独立复验及源码审查，之后完整闭包另行冷构建。

## 可修改文件

- `tools/compiler_job.py`
- `codex-works/tests/test_g5_host_mapping.py`
- `codex-works/deliveries/G5HOST2.md`

## 定向验收

- `discover:codex-works/tests:test_g5_host_mapping.py`

交付：`codex-works/deliveries/G5HOST2.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
