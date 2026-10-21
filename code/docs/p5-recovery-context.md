# P5CTX1：真实 DMA 申请与退休的持有上下文

本次交付为后续可信回收保留前置记录。它不提供回收授权，不完成 P5 设备恢复，也不证明设备 DMA 已排空。

Codex 已将通过独立验收的两份完整生产源码复制到本地 `kernel/user/`，并将测试放入 `tests/`；本文件为 `docs/p5-recovery-context.md`。原始 works 交付及 SHA 保留供追溯，主线集成复验和协调登记见 `coordination/dongos_works/reviews/2026-10-21-P5CTX1-integration.md`。

## 基线与交付位置

两份完整生产源码从主线 `244b18c` 复制，保留 `user.device_host`、`user.services` 模块名及原有控制流，仅在本人 works 的 `src/p5/user/` 内修改。主线集成需由协调者实际复制文件并单独登记，works 副本存在不代表主线已经接线。

| 原文件 | 复制前 SHA256 |
| --- | --- |
| `kernel/user/device_host.dg` | `4a5b7766d2de334f725b4d2966eb663be62c851614048a27bf949f88e4a067da` |
| `kernel/user/services.dg` | `2c6dacb8267e2727aef1fd960271b9789afb856f707628268e781c672260a1e7` |

没有修改 `memory.dg`、`devices.dg`、`device_manager.dg` 或 Process/Frame 布局。

## 真实 0x63 路径

现有 capability 检查与输出范围检查仍先执行。它们失败时不新建上下文。存在 Catalog 时，在真实 `devices.dma_acquire` 前检查 Catalog 已初始化、当前 slot/configuration 的双向关系、进程 token、incarnation 范围与 STARTING/READY 状态，再由 `device_host.dma_begin` 核对原角色 attachment、原设备 token/generation、可信 ledger 身份、实时 ECAM 硬件身份以及当前 memory Process 的 ready/root/独立 generation。

固定记录包含 slot/configuration、owner/incarnation、旧设备 token/generation、完整硬件 identity、memory root/generation 和本次 bytes/alignment。Catalog incarnation、设备 generation、memory generation 分别保存，不能互相代替。驱动 ABI 中 `blk.Lease.token=1/2/3` 不作为恢复身份。

每个物理 slot 最多保留一个内核私有 `DmaContext`，总计 16 条。首次可信请求在进入真实 allocator 前封存。已有上下文的重复、重入或新 incarnation/root 请求返回 Busy，不再进入 allocator，不更换旧身份或旧租约；首次错误 bytes/alignment 造成的无快照记录也保持封存。这是本次采用的保守、sticky 策略。建立前若已有真实 `memory.dma_snapshot`，拒绝把既存租约收编为新申请。TABLE 为空、未支持的 slot、没有原角色 attachment 的路径不新建记录，继续原有设备策略。

真实 `dma_acquire` 的成功和 err 分支都调用 `dma_finish`，随后才执行原有 `copy_out` 或传播原错误。错误传播使用只转发已求值 error union 的 `dma_result`，不会重复调用 allocator。每条上下文仅采集一次实际内存回执，并先锁定 `acquire_done`，重入或后次调用不能覆盖。

| `snapshot_status` | 含义 |
| --- | --- |
| 0 | 已封存请求，尚未完成实际申请/采样 |
| 1 | 实际 `dma_snapshot` 返回错误，无内存租约回执；记录原错误码 |
| 2 | 保存实际 `memory.DmaLease`；不以全零结构伪造租约 |

真实回执完整保存 physical/virtual/pages/root/generation/attempted/mapped/state。`physical=0` 且 state=HELD 是有效的分配失败持有回执；部分 own/map 的 HELD 和 COMPLETE 同样保存。pages 保留 allocator 的完整舍入块，包括未映射尾部。回执 root/generation 或基本状态错配仍保留原始回执并设置 `context_error`，不将它解释为回收许可。`copy_out` 失败不会删除或重采成功申请的回执。

## 真实退休与撤权

`services.retire_one` 在原 SMP bridge 退休成功的实际位置记录 stop/detach ACK；bridge 错误记录原错误。UP 路径在 `procs.terminate` 成功后记录该 owner 永久停止，SMP 路径随后附 Catalog 退休结果。身份错配仅设置 sticky 上下文错误，所有退休观察函数均不抛错，不阻止既有 quarantine、撤权或错误传播。

SMP ACK 的范围是 `smp_bridge.retire` 原有的 `retire_begin`、barrier 等待、`retire_finish` 和挂起事件清除。这个 ACK 位于共享别名撤销、普通内存销毁等操作之前，不能冒充撤映射后的全核 TLB 退休证明。本次不改变这些操作的先后顺序。

真实 `device_host.revoke_owner` 附加 MSI route 退休、quarantine 隔离、block reset 和 ledger 撤权的实际结果。真实 manager `device_host.revoke(token,generation)` 也附加隔离与 ledger generation；该路径没有 owner 永久停止证明，不调用 reset。固定 `device_generation` 为原申请身份；`generation_after` 只在真实 ledger 撤权成功后从表内读取。退休匹配仅允许原 generation 且未撤权，或原 generation+1 且已撤权；其他值设置上下文错误，仍执行原有隔离行为。

route/isolation 的后续失败单调升级为错误并保留首个错误码，不能由后续成功清除。reset 记录首次实际结果：0 未知、1 没有该现代 VirtIO reset 结论、2 RESET_CONFIRMED、3 失败/不确定。reset 成功只表示现有 modern VirtIO reset helper 成功；AHCI/NVMe、tablet、XHCI 不借用此结论。上下文 `drain` 始终为 UNKNOWN（0），`held` 始终为 1。

现有失败返回和硬件隔离算法不变。MSI/quarantine/reset 失败可能使现有退休流程提前返回，记录说明已经实际走到哪一步；未走到的撤权不伪造完成。观察记录本身不创建重试、令牌再发布、驱动重启或自动恢复路径。

## 验证边界

定向 checks 为 `discover:cursor-works/tests:test_p5_recovery_context.py`。测试绑定候选生产源码 SHA，抽取真实 services 0x63 分支、真实退休函数和 host 观察/撤权函数，在 debug/release 编译并实际执行，由独立 C oracle 检查字段和轨迹。硬件配置读取、allocator/snapshot/copy 边界、MSI/隔离/reset 及调度/Catalog 边界在宿主 fixture 中明确 stub；它们不构成 guest 中的硬件实验。

要求的坏源证据是正常构建运行的生产分支变体：删除申请 err 后快照，以及允许后次覆盖旧 owner/root。oracle 需要按数值或轨迹断言拒绝它们，构建失败、崩溃、超时不算拒绝证据。命令、退出码、输入前后 SHA 和 stdout/stderr 由测试保存在 build evidence 中，实际通过情况与具体证据路径由交付和协调者独立复验记录给出。

协调者在实际主线集成前还需独立复验现有 DMA/alias/device-manager/VirtIO-quiesce/release 回归和完整 services/device_host/memory 依赖闭包。宿主结果不能证明真实 guest SMP 或控制器 DMA drain。此次没有运行 OS/VM，没有清 PINNED、释放或零化 DMA、恢复 token，也没有调用 ledger.recover/reclaim。
