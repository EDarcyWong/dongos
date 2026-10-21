# P5CTX1 — [P5] 接入真实DMA申请与退休路径的精确持有上下文

负责人：cursor。状态：待领取。

所属阶段：P5设备故障恢复。接续main 244b18c的reset-hold、整块DMA租约和别名拒绝；只完成真实运行时的精确持有上下文，不实现回收或声称P5完成。旧cursor:CR43/codex:CX6存在异机同号异义且已归档，不恢复，不作为依赖。本任务按最新版分工给Cursor，在本人客户端手动worker MCP读取、领取和执行，不启动AI CLI。

真实缺口：services.dg的syscall 0x63当前try devices.dma_acquire失败后直接返回；memory.DmaLease已经保留分配前HELD、完整舍入块和partial attempted/mapped，但与Catalog owner/incarnation、设备token/generation尚未绑定。device_host真实revoke_owner有可信隔离/reset-hold，services.retire_one已有smp_bridge.retire，不重写已有账本、停止、分配或复位算法。

实施范围：
1. 在真实0x63调用devices.dma_acquire之前，从可信内核Catalog owner、当前slot、device_host原角色绑定及memory.process/root/generation建立有界内核私有上下文，用户不传物理地址、token或所谓“已排空”布尔证明。至少固定slot/configuration、owner与incarnation、旧device token和设备generation、可信ECAM/硬件identity、memory root及独立memory generation。三种generation不能互相替代，blk.Lease的常量token=1不能作为恢复唯一身份。
2. 在真实申请成功和err两分支均保存实际memory.dma_snapshot，不因try提前返回而丢失失败回执。覆盖COMPLETE、部分own/map的HELD、HELD且physical=0；无快照/尚未进入申请单独表示，不能用全零捏造租约。保存完整pages（含未映射舍入尾部）、physical/virtual/root/generation/attempted/mapped/state。
3. 首次记录身份与原租约不可被重复请求、错误请求、新incarnation、不同root或slot重用覆盖。可单调追加同一笔申请/退休的状态，但不得把后次申请/新根接管为旧记录。无有效上下文的新控制器/未申请路径保持原行为；上下文错误不得短路现有隔离或使错误路径跳过quarantine。
4. 接入真实services retire/revoke与device_host路径，将已有永久停止、撤权前后设备generation、隔离和reset结果附到同一上下文。已有SMP退休ACK的范围和时序必须如实说明，不将其冒充撤映射后的全核TLB退休。现代VirtIO reset成功仅记RESET_CONFIRMED，DMA drain始终UNKNOWN；其他控制器不借用VirtIO结论。失败sticky held，不自动重试或重新发布。
5. 不修改memory.dg/devices.dg/device_manager.dg/Process/Frame布局，不增加公共syscall，不调用ledger.recover/reclaim、不清PINNED、不释放或零化DMA、不撤销/重发新token、不重启驱动。新上下文是后续可信回收的前置记录，不是回收授权。

验证：checks首先编译并实际执行debug/release的真实services 0x63生产分支及host退休hook；允许抽取原分支/函数并在fixture中明确stub硬件/内存边界，必须绑定源码SHA，不能只测新helper或文本存在。独立C oracle核对成功/部分失败/physical=0/无快照/copy_out失败、身份每字段错配、重入/重复请求、旧owner/新incarnation、token/root/各generation变化，以及reset失败与成功仍drain未知且无回收。至少两类实际坏源：删除申请err后的snapshot；允许后次覆盖旧owner/root。坏体须正常构建运行后按指定数值/轨迹断言拒绝，不以构建失败、崩溃或超时充数。有限边界不跑笛卡尔积。保存命令、退出码、输入前后SHA、stdout/stderr和真实坏体拒绝证据；零skip。
集成前由Codex独立复验：既有test_dma_lease/test_dma_alias/test_device_manager/test_virtio_quiesce/test_dma_release及完整services/device_host/memory依赖图编译；如修改退休时序，再定向核对test_user_domain/test_user_smp_services。worker仅跑声明checks，不运行OS/VM、不提交/推送、不改DB/index/任务书/他人文件，不自授验收/集成。docs/p5-recovery-context.md必须区分真实内核接线、宿主stub边界与未取得的guest/DMA drain证明。

交付位置与主线映射（以本段为准）：遵守新组件先放本人works的规则。只读main244b18c的kernel/user/device_host.dg和kernel/user/services.dg，各复制一份到cursor-works/src/p5/user/同名文件后修改；保持原module user.device_host/user.services及完整生产控制流，不剪掉原行为。主目录kernel/user文件不在worker可写范围。编译/测试把cursor-works/src/p5置于import roots首位，其余生产依赖只读来自主线完整闭包；记录两基线SHA和修改diff，不能复制整个lang掩盖替换。docs交付在cursor-works/src/p5/recovery-context.md，三个测试在cursor-works/tests/p5_recovery_context_fixture.dg、p5_recovery_context_probe.c、test_p5_recovery_context.py。验收后Codex将两个完整源码、文档和路径适配测试实际集成到主线，再登记integrated；不把works副本存在当生产已接线。checks仅运行discover:cursor-works/tests:test_p5_recovery_context.py，既有主线P5相关回归由Codex在集成时定向复验。

## 可修改文件

- `cursor-works/src/p5/user/device_host.dg`
- `cursor-works/src/p5/user/services.dg`
- `cursor-works/src/p5/recovery-context.md`
- `cursor-works/tests/p5_recovery_context_fixture.dg`
- `cursor-works/tests/p5_recovery_context_probe.c`
- `cursor-works/tests/test_p5_recovery_context.py`
- `cursor-works/deliveries/P5CTX1.md`

## 定向验收

- `discover:cursor-works/tests:test_p5_recovery_context.py`

交付：`cursor-works/deliveries/P5CTX1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
