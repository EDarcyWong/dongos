# P5/P6 工程交接：设备恢复、输入 IRQ 与启动验证

快照截止：2026-10-20 11:13 UTC。本文是可以脱离聊天历史使用的工程入口，不是阶段验收结论。动态 CI 状态必须按下述精确 SHA 重新查询。

## 当前结论

- **P5 partial**：已有 fail-closed 设备恢复账本候选；未接入实际驱动故障恢复路径，不能宣称同次启动恢复或 DMA 回收完成。
- **P6 partial**：输入 IRQ 丢边沿修复已单独拆分；原实验 PR 保留 KVM 门禁失败证据。尚无成功的真实 Linux/KVM 启动计时。
- 原生模型、编译、TCG/QEMU boot 回归和 VMware 运行均不能替代真实 KVM 时间验收；局部通过不能关闭整个 P5/P6。
- 本文作为独立文档变更交付，**不得加入输入专用 PR #4 的五文件集合**。

## 仓库、基线与变更关系

仓库：[EDarcyWong/dongos](https://github.com/EDarcyWong/dongos)。2026-10-20 实时执行 `git ls-remote origin refs/heads/main`，main 为：

`4aaf195c8a68b6549382d2490c6fc746052f8d4e`

工作区分 `code/`（系统/语言源码）与 `coordination/`（协作控制台）。以下测试命令均在 `code/` 运行。先读根目录和 `code/AGENTS.md`，不要把本地派生索引当作验收状态，也不要为更新说明修改协调器状态。

### P5：独立恢复前置条件 PR

[PR #5](https://github.com/EDarcyWong/dongos/pull/5)，草稿，分支 `codex/p5-recovery-dma-journal`，基于上述 main，包含两个远程提交：

- `07c05e7e5883343d8558fe828a062b61c553111c`：设备恢复账本事务，五文件。
- `2a739eb78725f0e83a5f71323c759ff0787a0c7c`（head）：生产 memory 整块 DMA 记录与测试/专用 CI，七文件。

两次变更合计 11 个不同文件（共享 `device-manager.md`）。对应本地候选提交为 `ad07b25e111d336e114bd693b341ac174d999705` 和 `d9fd03749b4f5d13bce1caa3036539c1dc4ea3d3`，内容树相同，远程提交身份不同；交接和 CI 一律以远程 SHA 为准。尚未合并，专用 CI 正在运行，不能写为 native 已通过。

### P6：原实验 PR 与输入专用 PR

- [PR #3](https://github.com/EDarcyWong/dongos/pull/3)：`codex/p6-input-irq-kvm-validation`，草稿；当前报告 head `4622a41b8d46855981fe47709e516fbd10b4fc26`。含输入修复、KVM runner/负控、工作流及验证边界说明。保留失败门禁，不应通过豁免 KVM 门禁宣称 P6 完成。
- [PR #4](https://github.com/EDarcyWong/dongos/pull/4)：`codex/p6-input-irq-fix`，草稿；head `18543a2986034893da4536c3b45ff98f73549742`。从同一输入修复拆出的窄范围交付，**不携带 KVM 计时或完整 P6 完成承诺**。尚未合并，必须等待该 SHA 自己的检查结果，不能借用 PR #3 的绿灯。

PR #3 七文件：`.github/workflows/p6.yml`、`code/docs/p6-current-validation.md`、`code/services/drivers/input_service.dg`、`code/tests/input_service_probe.c`、`code/tests/test_input_service.py`、`code/tests/run_p6_kvm_qemu.py`、`code/tests/test_p6_kvm_runner.py`。新增 DAG 文件尚未发布，不属于该已发布集合。

PR #4 恰好五个文件：

1. `code/services/drivers/input_service.dg`：修正 ACK 后 i8042 重查与背压状态保持。
2. `code/tests/input_service_probe.c`：独立硬件/队列模型和精确窗口注入。
3. `code/tests/test_input_service.py`：生产 Dong 执行与真实坏源码负控。
4. `.github/workflows/p6-input.yml`：独立输入/USB 回归入口。
5. `code/docs/p6-input-irq.md`：仅解释该输入子项及证据边界。

## P5：实现内容与未接线边界

候选五文件：`code/kernel/user/device_manager.dg`、`code/tests/device_manager_probe.dg`、`code/tests/device_manager_probe.c`、`code/tests/test_device_manager.py`、`code/docs/device-manager.md`。

新增 `user.device_manager.recover` 是内核内部账本事务，不增加 syscall，未从 `user.device_host` 调用。表布局仍为 4560 字节；公共 ABI 不变。可信内核调用者持有串行化锁，将精确旧设备 token、撤权后 generation、旧 owner/incarnation 和旧 DMA 租约绑定到回调上下文。

事务顺序固定为 `quiesce → retire → reclaim → read → 发布未绑定新代际`：

- quiesce 必须证明 DMA 已停止/排空或完成受支持控制器复位；仅关闭 PCI BME/MSI 不够。
- retire 必须完成旧 owner 能力、映射及所有 CPU 调度/地址翻译引用的退休。
- reclaim 只能回收精确旧租约，不能触及其他 owner 的页。
- read 由内核重读硬件身份，拒绝替换设备；随后仍需正常 BIND 复验才能发放新权限。
- 第一个回调前进入 `RECOVERY_HELD`。失败、重入、身份变化不得提前发布 token；可能已有副作用的失败保持 HELD，不自动重试或重复回收。
- 保留 IRQ serial，拒绝旧 token 复活和 generation 耗尽后的不安全发布。

**尚未实现/接入**：可信控制器停止与排空；全核 owner 退休；与 `user.memory` pinned frame 一致的精确租约回收；`user.devices`/`device_host` 旧授权清理；驱动新代际及依赖服务恢复；同 boot 客体故障注入、旧句柄/旧 DMA/旧 IRQ 负控及持久化回归。当前故障后 DMA 仍按既有路径持有。回调未实现前不得调用候选入口。

### P5：DMA 整块分配记录

第二提交修改 `.github/workflows/p5-recovery.yml`、`code/docs/device-manager.md`、`code/kernel/user/memory.dg`，新增 `code/tests/dma_lease_adapter.dg`、`code/tests/dma_lease_fixture.dg`、`code/tests/dma_lease_probe.c`、`code/tests/test_dma_lease.py`。

生产 `user.memory.contiguous` 已接入整块申请记录：分配前保留每槽唯一记录并置 PINNED；分配成功、首次 `own_frame` 前记录完整向上取整块的物理地址和页数，避免映射中途失败后尾部失去归属记录。记录包含 DMA VA、根、内存代际、已开始登记页数和已完成 USER 映射页数；失败不擦除记录、不允许重入或重试覆盖。全部映射和根失效完成才标记 COMPLETE，但 COMPLETE 不授权回收。

`dma_snapshot` 是内核内部只读快照；无新增 syscall，Process/Frame 布局不变。当前没有 unpin/free/reuse 路径；内存根代际不等于设备 owner/incarnation，仍需可信 host 关联和硬件排空、全核退休。测试直接抽取生产 contiguous 与记录定义，覆盖 buddy/arena、1–32 页取整、每页登记/映射失败、容量与范围、重复/重入，及丢失取整尾部、未 PIN、提前 COMPLETE 三种真实坏源。原生执行尚未运行，不能将这些覆盖目标记作已通过硬件证据。

## P6：输入修复原理

i8042 已读空但 IRQ 尚未 ACK 时可能有新字节到达，导致边沿丢失。修复在 ACK 解屏蔽后重新 drain；若输出队列背压，保留 `RECHECK`，后续继续清空。读空后仍不进行空闲硬件轮询；USB-only 路径不增加 i8042 访问。

测试覆盖 ACK 窗口精确注入、背压、A 键 make/break、恢复后无空闲硬件读取。真实坏源码控制分别移除 ACK 前 drain、ACK 后重查以及背压重查义务。模型通过只证明上述局部契约，不证明真实桌面/USB 或整个启动流程。

## 验证记录：已通过、失败、未运行

### 已通过，但仅限所列证据范围

- P5 候选：设备账本和 DMA fragment 的 debug/release 前端编译与 ABI 检查；两个 C fixture 严格语法检查；完整生产 `kernel/user/memory.dg` 依赖图 debug/release 编译。本地当前未找到 NASM，原生链接执行和真实坏源执行尚未取得成功证据。
- P6 输入候选本地：Dong debug/release 编译；静态栈 2224 B，小于 12288 B；C 严格语法检查。
- PR #3 较早 head `66c1603f608600e280af359811f941d89ca3bf90` 的 CI（run `39410917511` / job `118588180082`）：28 项测试通过，范围为原生输入/真实坏源、USB entry/USB-only、KVM runner 主机负控、trace oracle；run `39410917704` 中全部 9 个既有 QEMU boot 组通过。该次全量 host/language 检查后来因新提交正常取消，不能记录为全量 PASS，更不能自动套用到 PR #4。
- 新严格 KVM runner 及负控：25 项**主机测试**通过；不代表实际 KVM 客体运行。

### 已失败：KVM 环境前置条件

普通 CI runner 能看到 `/dev/kvm`，但没有读写权限。随后仅针对本次验证进程，尝试使用设备所属既有 `kvm` 组；检查确认设备确由该组拥有。然而：

`sudo -n -u runner -g kvm -- …`

返回 `sudo: a password is required`，见 PR #3 的 run `39411879213` / job `118591381873`。失败发生在客体启动之前：**没有启动 KVM guest，没有性能结果**。未实施 ACL/chmod/usermod、永久组成员变更或间接 root 操作。不要绕过这项失败，后续应使用执行身份本来就具备访问权限的 KVM 环境。

### 当前尚待结果

PR #4 精确 head 的输入/USB 回归 run `39412573598` 已 SUCCESS。完整 build/boot run `39412573501` 在 11:11:56 UTC 核验时：9 个 boot 组中 8 个 SUCCESS，memory 仍运行；语言分片 5 成功，其余语言和 4 个宿主分片仍运行。尚无所见失败，但**不能记为全量通过或已合并**。合并/交付前必须重新读取最终 conclusion。

### 尚未完成的真实验收

- init 首代启动中跨 AP 依赖图的实际并行结构证据，而非启动完成后的 AP 活跃观察。窄范围 DAG 捕获工具及测试已在本地实现，9 项主机测试通过，仍在审查、未发布，且没有真实 VM 证据；不能写为该验收已完成。
- 新正常镜像的完整 GUI、键鼠和 USB 实际回归。
- Linux/KVM 上真实 loader→interactive shell ≤500 ms：绑定源码、产物、真实 KVM 与独立时钟证据。
- P5 同次启动设备故障恢复与安全 DMA 回收的真实闭环。

## 复验入口与证据保存

先核验远程 SHA，再在隔离 checkout 运行；不要在其他人正在编译的副本切分支。构建/原生测试需要 Python、NASM、GCC；完整镜像/QEMU 验证还需仓库工作流列出的 LLD、QEMU、OVMF 等依赖。缺依赖记录为未运行，不把编译替代执行。

```sh
git ls-remote origin refs/heads/main refs/heads/codex/p5-recovery-dma-journal refs/heads/codex/p6-input-irq-fix refs/heads/codex/p6-input-irq-kvm-validation
git rev-parse HEAD
git status --short
cd code

# P5 候选：编译/ABI 与完整原生回归是两种不同证据
python3 -m unittest tests.test_device_manager.DeviceManagerTests.test_recovery_frontend_both_modes -v
python3 -m unittest tests.test_dma_lease.DmaLeaseTests.test_frontend_actual_fragment_both_modes -v
gcc -std=c11 -O2 -Wall -Wextra -Werror -fsyntax-only tests/device_manager_probe.c tests/dma_lease_probe.c
python3 -m unittest tests.test_device_manager tests.test_dma_lease -v

# P6 输入专用分支
python3 -m unittest tests.test_input_service tests.test_usb_input_entry tests.test_usb_input_usbonly -v

# 以下仅在含对应 runner 的 P6 实验分支
python3 -m unittest tests.test_boot_trace_oracle tests.test_p6_kvm_runner -v
python3 -c "from tests.run_p6_kvm_qemu import preflight; print(preflight())"
python3 -c "from pathlib import Path; from tools.build import build; build(runtime_level=7, output=Path('build/test/p6-kvm/build'))"
python3 -m tests.run_p6_kvm_qemu --reuse-esp build/test/p6-kvm/build/esp --output build/test/p6-kvm/actual --timeout 120
```

以上是复验命令，不表示本文编写时全部执行成功。KVM 命令仅在执行身份已具备设备访问权限的环境运行；不默认复制失败的 sudo 提权尝试。

严格 KVM runner 使用新构建正常 runtime7 镜像，重算完整源码清单和 ESP 五个精确产物；首次 `cont` 前读取真实 `query-kvm`，不允许降级 TCG。初始启动不插入观测暂停，shell 与四客户就绪后才读取内核代码及封存 trace。保存整个 `build/test/p6-kvm/`，以 `actual/result.json` 和原始证据判定，不能拿单元测试中的合成 KVM 标志充数。此 runner 本身不证明 init 首代跨 AP DAG。

原生证据通常写入 `build/test/device-manager/host/`、`build/test/dma-lease/`、`build/test/input-service/`、`build/test/usb-input-entry/`、`build/test/usb-input-usbonly/`。移交时连同精确 SHA、命令、退出码、source-before/source-after、负控日志一起保存。缺少 artifact 时明确标记，不据描述重建“通过”记录。

## 接手顺序与停止条件

当前优先完成 P5；P6 的待查结果和真实门禁保持未完成状态。本文不启动或扩展 P7 工作。

1. 重新获取 main、PR #3/#4/#5 head 和 CI 最终结果，更新本文快照；先确认目标是输入子项还是整阶段。
2. 输入子项：只审查 PR #4 五文件，等待该 SHA 全量 build/boot 和输入/USB 检查成功；失败则修复并在新 SHA 重跑，不借用旧结果。通过后也仅交付输入子项。
3. P5：先审查恢复账本契约和失败负控，在有 NASM 的环境完成实际原生执行。随后分步接入可信硬件停止、全核退休和精确租约回收，最后做同 boot 客体故障恢复负控。未闭环维持 partial。
4. P6：完成 init 首代 DAG 实际证据与 GUI/USB 回归；为 KVM 选择已有合法读写访问的 Linux 环境，重新构建并运行时间门禁。遇设备权限拒绝就记录并停止该路线，不用 TCG/主机模型代替。
5. 仅当真实证据全部满足阶段契约，才提出阶段验收；文档、PR 草稿、某组测试通过均不是自动验收。

相关仓库文档：`code/docs/device-manager.md`、`code/docs/p6-current-validation.md`（实验分支）、`code/docs/p6-input-irq.md`（输入专用分支），以及现有 P6 integration/runtime/tickless/SMP candidate 文档。后者仅作接口背景，不替代本次精确提交上的执行证据。
