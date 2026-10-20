# P5 恢复契约离线实现（2026-10-20）

## 背景与范围

用户要求“查看整体任务中的 P5 阶段剩余任务，完成它”。`progress-map.md` / `roadmap.json` 中 P5 剩余两项为：

1. 同次启动内通用设备恢复
2. 故障 DMA 安全回收、重分配与设备重授权

协调器中没有对应的已发布任务；本轮按 P2 离线扩展的既有做法，直接在主线的独立模块中实现**可独立验证的恢复契约**，不修改关键运行时。该项不是 P5 完成的替代证据。

## 交付文件

| 文件 | SHA256 |
| --- | --- |
| `code/kernel/user/device_recovery.dg` | `c33395e6eff9b373f89c2bdb97df60f6c83d684c5225b5db43e9041cd7f99de4` |
| `code/tests/device_recovery_probe.dg` | `6269169e301a21c151c61499226c19d60e41e53d946df752be20c83759fe96c4` |
| `code/tests/test_device_recovery.py` | `e1a35ff0c0d4000a2e8ba029bab365dd00c117410b4fb1a9017bd6f76a74b86f` |
| `code/docs/device-recovery.md` | `b0afd8f14d5521a10cc6591f19d8ee8d5eb82ddf67fc213d85b6a7602a046281` |

另更新 `code/PLAN.md` P5 设备管理项、`progress-map.md` / `roadmap.json` 的 P5 完成项、剩余项与说明：只登记“离线契约已实现并测试”，两项仍保留未关闭。

## 契约内容

`user.device_recovery` 是纯状态机：不读 PCI 配置空间、不写 MMIO/MSR、不映射/失效页表、不分配/清零内存。

状态转换固定为：

```text
ACTIVE -> FAULTED -> SAFE -> QUIESCED -> RECLAIMED -> RESET -> ACTIVE
```

- `fault` 依次要求/发出 `MASK_IRQ`、`DISABLE_BME`、`RETIRE_OWNER`；
- `confirm_safe` 必须同时观察到 IRQ 已屏蔽且 BME 读回 0；
- `quiesce` 要求在途 DMA 与映射计数均为 0；
- `reclaim` 要求页已清零，回收后设备代际 +1，租约令牌永久失效；
- `lease_check` 是每次 DMA 提交前的门：只有当前代际/owner 的 HELD 租约允许新操作，隔离后拒绝、回收后旧令牌 STALE；
- `reset_device` 要求复位成功且硬件身份未变；
- `reauthorize` 再 +1 代际，角色/owner/incarnation 重新校验，最多 3 次成功恢复；
- `retire` 是唯一终止路径，租约永久保持隔离；
- 拒绝路径不写输出、不改表；租约令牌 `serial<<8|slot` 单调、不复用。

## 实际测试

```text
cd code
python -m unittest tests.test_device_recovery -v
python -m unittest tests.test_ci_inventory -v
```

结果（2026-10-20 本机）：

- `tests.test_device_recovery`：4 项，debug/release 双模式，0 skip，OK。本机最近一轮 18.487 秒；
  此前负载下同一套用例记录 71.2/238.5 秒，时长随并行负载变化。
- `tests.test_ci_inventory`：2 项，OK。
- 真实 dongc 编译 + NASM 汇编 + GCC 链接 DLL，Python ctypes 调用 SysV 导出；固定核对 Table/Device/Lease 布局 568/80/56 字节。
- 覆盖完整状态机、PS2 无 DMA 路径、终止后租约隔离、全部跳步/观察/清零/身份/代际/尝试门禁。
- 1,600 步随机操作逐步对照独立 Python 状态模型（状态码、步骤、令牌、整表）；确定性用例覆盖七种状态。
- 8 个真实坏 Dong（正常编译/链接/运行）全部被检查拒绝：提前回收、跳过清零、重授权不换代、忽略在途 DMA、只查 IRQ 不查 BME、尝试不设上限、租约序列不递增、租约门忽略隔离态。
- 每次拒绝均检查表、步骤缓冲、`written`、输出令牌和 guard 字不变。

## 未完成与限制

- **未接入内核**：`user.devices`、`user.device_host`、`user.device_manager`、`user.memory` 未改；现有运行时仍只撤 BME/MSI 并永久持有 DMA，`device_manager` 仍永久退休令牌。
- **未运行 OS/VM**：没有 QEMU/VMware 启动、真实 AHCI/NVMe/xHCI 故障注入、页回收/清零实际执行或同盘重启。
- 仍需内核接线：可信硬件重读、撤销全部用户别名、清零并回收页、重绑 IRQ/DMA、重启驱动服务与 FS/shell 依赖；失败走 `retire`。
- 不覆盖热拔插/设备替换；替换设备需新的启动代登记流程（当前未实现）。
- 本轮没有发布/领取/提交协调器任务，没有自行验收或集成；独立复验与真实集成仍应由协调者完成。
- P5 阶段仍未关闭；本记录不改变 P5 的 `partial` 状态。
