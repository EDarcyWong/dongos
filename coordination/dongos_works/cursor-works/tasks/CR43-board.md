# CR43 — [P5] 按工程交接制定可信恢复接线方案和逐步实现契约

负责人：cursor。状态：待领取。

## 发布后交接复核（2026-10-20）

工作区已前进至 `345570f`，应先读该版本 `code/docs/p5-p6-engineering-handoff.md` 的最新正文，以下原发布段落中的 `208029b` 及旧交接描述保留为当时基线。PR #4/#5 已合并且交接已记录专项/完整 CI 结果，不能重复将其列为待合并。

先核对 PR #7 `e2ae56ba1af8ef6201e6daf7e95ab563a42bdbbb` 的 VirtIO reset-hold 差集：交接记录其 native 与真实 TCG control/fault 通过，证明四 CPU 退休、status=0、32 页 DMA 仍 PINNED；不证明 outstanding DMA 已排空或允许回收。该实现尚不在本地主线，不重复开发同一停止/复位后持有路径。另核对 PR #8 `3a4704dbc1f84b90984dd0fcfeed8f53414ec49c` 已移除旧 release_dma 解 PIN 路径并保留精确租约记录的集成边界。本项优先规划在这些已有变更之上的缺口：可信排空证明、持续 owner 排除、精确租约回收及恢复发布；远端合并/CI 动态只按执行时的精确 head 另核，不把交接快照当实时查询。

## 原发布契约

所属阶段：P5基础服务 → 同次启动设备恢复与安全DMA回收的实现前置设计。先完整读取code/docs/p5-p6-engineering-handoff.md、device-manager.md、kernel/user/{device_manager,memory,services,device_host,devices}.dg、smp目录user_bridge及AHCI/NVMe实际驱动；按最新源码校正交接中仍称PR#4/#5未合并、缺stop的历史快照。当前main 208029b已包含恢复账本和DMA整块记录，但device_host未调用recover；memory DMA_PINNED仍永久持有。不得重复实现已有账本或造布尔模型冒充硬件证明。

只交付一份可据以直接派实现的设计文档及真实交付报告，先不改内核/驱动/权限。明确选择首个受支持控制器并说明源码依据；列清旧device token+撤权generation+Catalog owner/incarnation+内存root/generation+精确整块DMA租约如何由内核可信上下文绑定；不得接收用户函数指针或复位成功标志。把stop→quiesce→retire→reclaim→read→发布未绑定新代际拆成可独立审查步骤，stop必须跨全部CPU排除旧owner继续运行/返回用户态并持续到事务结束，复用既有retire_begin/barrier_wait/retire_finish能力而非重复写退休算法。quiesce必须有可信MMIO读回/排空、有限超时和失败保持HELD，关闭BME/MSI不足作证明；CPL3驱动私有stop_port/wait_ready不能直接当可信回调。

明确现有DmaLease缺owner/incarnation关联，PINNED/rounded pages/recycled/根与代际的精确所有权核对、回收顺序、各步副作用与不可重试边界、无效/替换设备/旧句柄/旧DMA/旧IRQ负控。列出每个后继实现的精确write_paths（依据源码真实位置）、只读依赖、ABI和布局约束、能验证该步骤的主机真实Dong测试/坏源控制、最后同boot客体故障注入/持久化及回归门禁，区分H/V/E；不能把主机模型当真实DMA停止或整个P5验收。说明为何选择的步骤不会与既有实现重复，哪些共享文件要求顺序执行。P6 DAG/GUI/USB/KVM和L3继续保留各自门禁，不在本项扩大范围。

先通过worker MCP读取最新rev、完整任务后领取，Cursor客户端手动执行；临时产物仅本人works/build/CR43唯一目录。checks为当前主线P5基线定向测试，目的确认设计所依赖的实现可复验，不代替设计本身的独立源码/契约审查；依赖CX6修复公共NASM探测后运行。仅可写两文件，不修改其它任务/主线、不运行OS/VM/全回归/模型CLI、不自行验收或集成。测试未跑须如实写未运行。设计审核通过后另发真实接线实现任务，不能本项关闭P5。

## 可修改文件

- `cursor-works/docs/p5-recovery-implementation-plan.md`
- `cursor-works/deliveries/CR43.md`

## 定向验收

- `module:tests.test_device_manager`
- `module:tests.test_dma_lease`

交付：`cursor-works/deliveries/CR43.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
