# P2 设备发现与用户 SMP 交接

P2DISCOVERY22 将完整 PCI 硬件发现放在用户 SMP 交接前，避免首次设备枚举在一个持有 BKL 的调用内扫描全部总线。当前实现等待独立复验和真实四核硬件加速重跑；本文不记录修复已通过，也不将该前置修复计作 P2 或 P5 完成。

`services_run.asm` 先成功执行 `dong_services_prepare`，再根据实际拓扑进入 `user_smp_boot_begin`。桌面准备过程已经调用 `devices.initialize()` 和 `device_host.initialize()`，后者初始化内核私有 ledger；此时尚未向设备管理器授予设备角色或 DMA 租约。

`sched.user_boot.prepare()` 的顺序是：

1. 核实旧 live gate 的 phase、错误、队列已排空及完整 SMP steps、CPU 数量。
2. 核实全部旧 Context 的 self、logical_id、ONLINE，以及各 AP 的 current 和 timer_armed 均已排空。
3. 在 BSP、IF=0、旧共享内核根与旧 TLB 读者仍在线时，调用 `device_host.preflight_discovery()`。
4. 预检成功后才首次分配新 INFO、Domain、Bridge、Header 和用户入口栈；逐 CPU 构造前仍保留原 Context 身份/ONLINE 核验。后续激活与 AP publish 顺序沿用原协议。

新入口要求 `TABLE` 已初始化，并调用原 `discover()`：完整覆盖已准入 ECAM 的 first..last 总线、每总线 32 个 slot，以及真实 multifunction header 指示的其余七个 function。只有所有硬件读取、ledger 登记及最后 I8042 登记全部成功，原逻辑才设置 `ENUMERATED=true`。没有缩小总线覆盖、伪造硬件身份或将部分扫描标记完成。

预检失败通过 `try` 返回原错误码，发生在新 INFO 发布前。`dong_user_smp_boot_prepare` 仍返回该错误，ASM 进入服务错误出口，不会发布 AP 用户入口或继续使用部分扫描结果。失败不承诺回滚已有内核 ledger 或窗口映射；它们保持持有，不能把本次失败当成可继续启动或重试的成功凭据。

后续 `enumerate()` 保留原 `discover()` 调用：成功预检后读取完整缓存 ledger，原 1/2 CPU BSP 路径及未进入此交接的配置仍可按原语义首次发现。每条未撤销 PCI 枚举结果仍调用真实 `hardware()` 并核对身份；bind/revoke 的硬件验证和授权步骤不变。预检不调用 bind、admit、IRQ 路由或 DMA 分配，也不代替用户设备管理器的授权操作。

实现不修改锁等待期限、acquire deadline、PCID、计时器、ACK、Domain 或 legacy bridge 协议。实际发现仍调用生产配置窗口及每页 TLB barrier；提前执行只改变其发生在新 BKL 等待者出现之前。

## 已观测事实与首因推断

固定 pre-B `current-r3/source-root` 在 WHPX、`q35,kernel-irqchip=off`、CPU `host,-vmx,-mpx,-sgx,-sgxlc` 下真实启动四核，串口先出现 SMP_READY、PARALLEL_READY、ELF_LOADED 和用户 init 的 INIT_READY，随后出现旧域 `DONGOS_P6_TLB_FATAL=0x06030004`。这批记录是失败诊断，不是验收通过。

- R6 原始现场的旧 TLB epoch 为 27219，AP1/2 已 ACK，AP3 停在 27218，scope=0、VA=`0xffffc00000080000`，对应实际 PCI 配置窗口。三个 AP 的 RIP 均落在实际 ELF 的用户 SMP 失败停机路径；IF=0，不能把该现场描述为正常 idle 或仅凭 pending IPI 认定中断丢失。14 份原始物理读取的长度与 SHA 已独立核对。
- R7 使用真实 kernel root walker 读取 arena。214 份原始物理读取的长度与 SHA 已独立核对，记录 `newDomain.failed=1`、`Bridge.failed=1`、owner=0、lock=1、CURRENT=6。AP 均为 IDLE、Header.ready=2、PCID=1、Metrics.failed=1，且尚无用户入口或用户 timer；新域 sequence=completed=51、全部请求已 ACK。该次旧 TLB epoch=26478，不能与 R6 的轮次混用。
- 两次诊断均保留失败记录、输入稳定与所属 QEMU 已退出的记录。R7 回执 `legacy-failure.json` SHA256 为 `5d62eb6aedd24a8d14d27c221305031217c3c833c570a71124cdc06971e39026`。

源码显示 CURRENT=6 的首次 `dev.ENUMERATE` 会在同一 BSP+BKL 调用内执行完整发现，而 AP 的 acquire 期限从进入等待前计算，固定为一个 TSC 秒。已观测状态与“长扫描先使 AP 锁等待失败，继而旧 TLB 失 ACK”这一首因推断相符；现有回执没有记录最早返回的精确错误码和时间顺序，不能将推断写成已直接测得的唯一首因。

历史诊断位于 `build/test/p2-pcid-revision-review/current-r3/diagnostic-legacy-whpx-r6/` 与 `diagnostic-legacy-whpx-r7/`。正式复验仍需现有 normal activation 与 device manager 原生正反例、完整 fresh 构建及新的实际四核 WHPX 运行；host 通过不能替代 AP PCID、调度和真实 TLB ACK 证据。
