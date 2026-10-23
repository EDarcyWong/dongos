# P2DISCOVERY22 — P2设备发现提前至AP用户域交接前避免长BKL扫描

负责人：codex。状态：待领取。

用户先P2后P5。Root实际WHPX固定pre-B source current-r3，cpu host,-vmx,-mpx,-sgx,-sgxlc，q35 kernel-irqchip=off，真实已启动4CPU/PCIDE1但desktop前失败。R6/R7只读RAM/regs显示：oldTLB ECAM VA0xffffc00000080000单AP落后，全部AP在user_smp_fail halt，newDomain.failed=Bridge.failed=1，BSP BKL owner0 LOCKED CURRENT6设备管理器，AP IDLE/无用户入口、Header ready2/PCID1/Metrics.failed1，新域seq51全部ACK已完。源码discover在首次dev.ENUMERATE一次BKL syscall中全扫bus*32+multifn，AP acquire固定1秒；即使数万次legacy ACK进展，仍会超过现有绝对界。禁止扩大/不断刷新锁等待期限、跳ACK、禁用PCID/改timer或修改Domain/legacy/旧owner政策。本最小修复将一次完整可信硬件inventory发现在已初始化device_host.TABLE、旧parallel读者已真实drained、但新user Domain/Bridge/Header尚未创建或publish/AP用户交接之前完成。device_host新增明确unsafe内核preflight入口（调用实际discover，真实失败传播，不使用fixture伪造identity，不分配DMA、不提前授user设备权限）；user_boot.prepare在全部旧live/拓扑/drained条件后、新INFO/Domain构建前显式调用。后续enumerate仍使用现有完整ledger，PCI逐条真实hardware identity revalidation/bind/revoke不削弱；不把部分扫描标完成，不在hot path再全扫描，不放宽发现总线/多功能覆盖，原非SMP fallback语义保留。检查services.prepare已先initialize及真实entry调用顺序，避免别profile或无TABLE失败，拒默默fallback。仅3源码文档路径，不改B的services/memory/domain/build，不增加不必要模仿实现的tests；既有normal activation完整DG图/多级ASM policy和device_manager真实native正负回归保留。Root做实际fresh源构建和四核WHPX重跑，再判断是否消除该失败及PCID门禁，不凭host宣布修复完成。文档保留R6/R7 214原始物理读取与输入稳定/owned QEMU退出事实，区分已观测状态和首因推断；此为P2硬件验收前置修复，P5不启动。执行者仅读/写3声明路径，不编译/测试/VM/提交推送/改状态；最终冻结给root独立复验/真实集成。

## 可修改文件

- `kernel/user/device_host.dg`
- `kernel/sched/user_boot.dg`
- `docs/p2-device-preflight.md`
- `codex-works/deliveries/P2DISCOVERY22.md`

## 定向验收

- `module:tests.test_user_smp_normal_activation`
- `module:tests.test_device_manager`

交付：`codex-works/deliveries/P2DISCOVERY22.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
