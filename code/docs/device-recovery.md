# P5 恢复契约：同启动设备恢复与故障 DMA 回收/重授权

本文记录 P5 剩余两项的**离线契约组件** `user.device_recovery`（`kernel/user/device_recovery.dg`）。
它是纯状态机与步骤规划器：不读 PCI 配置空间，不写 MMIO/MSR，不映射/失效页表，不分配或清零内存，也**没有接入**
`user.devices`、`user.device_host`、`user.device_manager` 或内存回收路径。它定义"恢复时允许做什么、按什么顺序做、
下一步之前必须观察到什么"，真正启用仍要由内核接线完成，并通过 QEMU/VMware 的实际故障注入验收。

当前 P5 的两项仍保持未关闭：

- 同次启动内通用设备恢复
- 故障 DMA 安全回收、重分配与设备重授权

既有行为是驱动故障后撤 MSI/BME 与旧 owner 能力，但**DMA 永久持有**。本组件补上安全回收所需的门禁，
避免把仍可能被设备/CPU 写入的页回收后重新分配。

## 状态机

```text
ACTIVE ──fault──► FAULTED ──confirm_safe──► SAFE ──quiesce──► QUIESCED
  ▲                                                              │
  │                                                            reclaim
  │                                                              ▼
  └──reauthorize── RESET ◄──reset_device── RECLAIMED ◄───────────┘
```

每一步返回本次要执行的步骤（`Step{kind,arg}`），顺序固定，调用者不得合并或重排：

| 转换 | 前置条件（全部满足才前进） | 返回步骤 |
| --- | --- | --- |
| `fault` | 令牌/代际精确匹配、`ACTIVE`、步骤容量≥3 | `MASK_IRQ`、`DISABLE_BME`、`RETIRE_OWNER` |
| `confirm_safe` | `FAULTED`；IRQ 已屏蔽且 BME **读回** 0；容量≥2 | `WAIT_QUIESCE`、`FLUSH_MAPPINGS` |
| `quiesce` | `SAFE`；在途 DMA=0、映射=0；租约已隔离 | `ZERO_PAGES`（无租约时无步骤） |
| `reclaim` | `QUIESCED`；有租约时所有页已清零；代际未耗尽 | `RECLAIM`；代际+1，旧令牌立即失效 |
| `reset_device` | `RECLAIMED`；复位成功；硬件身份与登记值相同 | 无（复位本身由内核执行） |
| `reauthorize` | `RESET`；角色一致、新 owner/incarnation 非零、尝试次数未满 | `REBIND_DEVICE`、`REAUTHORIZE`；代际再+1 |

`retire` 是唯一终止路径：设备变为 `DEAD`，**租约永久保持隔离**，后续分配/回收/重授权全部拒绝。身份变化、
复位/重授权结果不确定或尝试次数耗尽时必须调用它，不能猜测回收。

## 不变量

- **先撤权后回收**：`MASK_IRQ`、`DISABLE_BME`、`RETIRE_OWNER` 先于等待在途 DMA；`WAIT_QUIESCE` 之后才允许清零。
- **零化后才回收**：存在租约时 `zeroed!=1` 的 `reclaim` 拒绝；清零发生在映射全部失效之后。
- **每次回收/重授权都换令牌**：`reclaim` 与 `reauthorize` 各消耗一个代际，设备令牌为 `generation<<8|slot`；
  旧能力、旧 IRQ、旧租约令牌不会再通过检查。
- **租约令牌永不复用**：租约令牌为 `serial<<8|slot`，`serial` 单调递增；已回收租约占用的槽位可以复用，
  但令牌不同。设备被 `retire` 时租约不回收。
- **尝试有界**：每个设备最多 3 次成功恢复；下一次故障直接进入 `DEAD`，不会无限重试。
- **失败无副作用**：所有拒绝路径不写输出、不修改表；`tests/test_device_recovery.py` 对每次拒绝同时检查
  表、步骤缓冲、`written`、输出令牌和 guard 字。
- 每个 DMA 描述符提交前必须调用 `lease_check`：只有当前设备代际/owner 的 `HELD` 租约允许新操作；
  故障隔离后返回 `STATE`，回收后旧租约令牌返回 `STALE`。
- 指针参数检查非空、8 字节对齐、跨度不溢出、与表/步骤/输出互不重叠。

## 接口

模块 `user.device_recovery`，状态码 `OK/INVALID/DENIED/BUSY/STALE/CAPACITY/STATE/IDENTITY/RETIRED`。

| 函数 | 作用 |
| --- | --- |
| `initialize(t)` | 初始化固定容量表（4 设备、4 租约），重复初始化拒绝 |
| `register(t,generation,role,identity,owner,incarnation,out)` | 登记唯一角色（BLOCK/TABLET/PS2/XHCI）的启动代 |
| `allocate(t,token,generation,owner,pages,physical,zeroed,out)` | 创建私有 DMA 租约；要求已清零、页数 1..32、物理页对齐 |
| `fault/confirm_safe/quiesce/reclaim/reset_device/reauthorize` | 上述状态转换 |
| `retire(t,token,generation)` | 终止并永久持有租约 |
| `lease_check(t,lease,device,generation,owner)` | 每次 DMA 提交前的授权门；隔离/回收后拒绝 |
| `inspect_device/inspect_lease` | 只读快照，用于内核/测试核对 |

角色常量与 `lib.device_abi` 一致（BLOCK=1、TABLET=2、PS2=3、XHCI=4）；PS2 无 DMA，但仍走同一恢复门禁。

## 已落盘的 DMA 释放原语（2026-10-20）

`kernel/user/memory.dg` 新增 `release_dma(id)`，作为“故障 DMA 安全回收”的底层原语：

- `contiguous()` 现在记录每个进程唯一的 pinned 连续区间（`PINNED_BASE/PINNED_PAGES`），并拒绝重复 pin；
- `release_dma` 只接受该记录中的区间，要求进程 ready、非当前根、确实 pinned；
- 参数检查通过后才清除 `PINNED`，随后复用既有 `unshare_range`：逐页复核 USER/可写/内核别名、unmap、等待翻译屏障、清零、标记可复用；
- 任一失败置 fail-stop（`UNSHARE_FAILED`），进程不销毁、页不复用；成功后才清空区间记录；
- 该函数已通过真实 Dong 的 debug/release 原生测试与真实坏实现负控，但**尚未被 `services.revoke_loaded` 调用**，因此故障路径仍保持“只隔离、不回收”。

## 测试

```text
cd code
python -m unittest tests.test_device_recovery -v
python -m unittest tests.test_dma_release -v
```

`tests/test_dma_release.py` 把测试夹具追加到 `memory.dg` 的私有副本，真实执行生产 `release_dma`：

- 4 个 owned 帧映射到 `0x6800_0000`，填入 0xA5；先验证当前根/未 ready/非 pinned 拒绝且不改变状态；
- 成功释放后逐字节检查 4 页全零、`recycled=1`、`PINNED` 与区间记录清零，随后 `destroy` 才能成功；
- 再次释放被拒绝；
- debug/release 双模式，2 个真实坏实现负控（保留 pin、释放前丢失区间）。

`tests/device_recovery_probe.dg` 由真实 dongc 以 debug/release 编译，NASM 汇编后与 C shim 链接为 DLL，
Python 通过 ctypes 调用 SysV 导出。表/设备/租约布局在测试中固定核对为 568/80/56 字节。

覆盖：

- 完整状态机：故障→撤权→观察→静默→清零→回收→复位→重授权；PS2 无租约路径；终止后租约保持隔离。
- 每个门禁的负控：跳步、BME/IRQ 未确认、在途/映射非零、未清零、身份变化、代际耗尽、尝试耗尽。
- 1,600 步随机操作与独立 Python 状态模型逐步对照状态码、步骤、令牌、整表（含失败不变式）；
  测试要求至少观察到 `ACTIVE` 与 `DEAD`，确定性用例另行覆盖全部七种状态。
- 8 个真实坏 Dong（均正常编译、链接、运行，只靠检查拒绝）：提前回收、跳过清零、重授权不换代、
  静默忽略在途 DMA、只检查 IRQ 不检查 BME、尝试不设上限、租约序列不递增、租约门忽略隔离态。
- 当前实测：4 项测试、debug/release 双模式，0 skip。本机最近一轮 18.487 秒；此前负载下同一套用例
  记录 71.2/238.5 秒，时长随并行负载变化。同轮 `tests.test_ci_inventory` 2 项通过。

## 未完成与限制

- **未接入内核调用点**：`services.revoke_loaded` 仍在 `dma_pinned` 时只 quarantine 后 return；`release_dma`
  已就绪但尚未调用。CX10 已集成，接线会改变其已验收指纹，需作为新的审查/复验变更处理。
- **未运行故障注入**：没有执行 QEMU/VMware 启动、真实 AHCI/NVMe/xHCI 故障注入或同盘重启；
  生产 P5 镜像可以构建，但本文不宣称故障路径已验收。
- 真正完成还需要：确认 quarantine 后调用 `release_dma` 并 `destroy`；处理驱动进程 relaunch/重授权
  （block/fs/shell 为静态 preload，当前没有通用故障后重启）；然后跑实际 driver-exit/双启动门禁。
- 不覆盖热拔插/设备替换：`register` 角色唯一，替换设备必须先走终止与新的启动代登记流程（当前未实现）。
- P5 阶段仍未关闭；本记录不改变 P5 的 `partial` 状态。
