# P5/P6 工程交接：设备恢复、输入 IRQ 与启动验证

快照截止：2026-10-20 12:11 UTC。本文是可以脱离聊天历史使用的工程入口，不是阶段验收结论。动态 CI 状态必须按下述精确 SHA 重新查询。

## 当前结论

- **P5 partial**：恢复账本与 DMA 整块记录已通过原生/完整 CI 并合入 main；未接入实际驱动故障恢复路径，不能宣称同次启动恢复或 DMA 回收完成。
- **P6 partial**：输入 IRQ 丢边沿修复已单独通过检查并合入 main；原实验 PR 保留 KVM 门禁失败证据。尚无成功的真实 Linux/KVM 启动计时。
- 原生模型、编译、TCG/QEMU boot 回归和 VMware 运行均不能替代真实 KVM 时间验收；局部通过不能关闭整个 P5/P6。
- 本文作为独立文档变更交付，**不得加入输入专用 PR #4 的五文件集合**。

## 仓库、基线与变更关系

仓库：[EDarcyWong/dongos](https://github.com/EDarcyWong/dongos)。2026-10-20 实时执行 `git ls-remote origin refs/heads/main`，main 为：

`208029b090c722e881e327daef94b3500bb269b8`

此 main 已包含输入 PR #4、交接文档 PR #6 和设备恢复前置条件 PR #5。它们最初共同基线是 `4aaf195c8a68b6549382d2490c6fc746052f8d4e`。

工作区分 `code/`（系统/语言源码）与 `coordination/`（协作控制台）。以下测试命令均在 `code/` 运行。先读根目录和 `code/AGENTS.md`，不要把本地派生索引当作验收状态，也不要为更新说明修改协调器状态。

### P5：独立恢复前置条件 PR

[PR #5](https://github.com/EDarcyWong/dongos/pull/5)，分支 `codex/p5-recovery-dma-journal`，最终 head `b4c82369907953b7eaf9cafbf250be241f35c470`，已正常合并，merge SHA `208029b090c722e881e327daef94b3500bb269b8`。专项原生 run `39413950477` 和完整 run `39413950440`（20 jobs，含汇总）均 SUCCESS。

实现分为恢复账本事务 `07c05e7e5883343d8558fe828a062b61c553111c` 与整块 DMA 记录 `2a739eb78725f0e83a5f71323c759ff0787a0c7c`，最终 head 新增强制 `RecoveryOps.stop` 回调（内部结构 32→40 字节），补齐先停止精确旧 owner 所有 CPU 执行/返回路径的前置条件及对应坏源负控。合计 11 个不同文件。原先本地 `ad07b25` / `d9fd037` 仅是历史内容来源，验收以远程最终 head 为准。

### P6：原实验 PR 与输入专用 PR

- [PR #3](https://github.com/EDarcyWong/dongos/pull/3)：`codex/p6-input-irq-kvm-validation`，未合并；head `ef3aaf0fdb688a2b2a3cc820dc08503eec20908f`。原实验包含输入、KVM runner、首次 DAG 结构观察与验证边界说明。KVM 门禁失败保留，不能豁免后声称 P6 完成。
- [PR #4](https://github.com/EDarcyWong/dongos/pull/4)：`codex/p6-input-irq-fix`，head `18543a2986034893da4536c3b45ff98f73549742`。专项及全部完整 CI 通过后已正常合并，merge SHA `3c60f250724c8ebc836bc2c741f8f0ba9baad5f0`。只交付输入子项，不携带 KVM 计时或整个 P6 完成承诺。

PR #3 最初七文件为 `.github/workflows/p6.yml`、`code/docs/p6-current-validation.md`、`code/services/drivers/input_service.dg`、`code/tests/input_service_probe.c`、`code/tests/test_input_service.py`、`code/tests/run_p6_kvm_qemu.py`、`code/tests/test_p6_kvm_runner.py`。后续增加初始 DAG runner/test，总计九文件；它与已合并 PR #4 有共享输入变更，后续集成应核对差集，不重复覆写已合入代码。

PR #4 恰好五个文件：

1. `code/services/drivers/input_service.dg`：修正 ACK 后 i8042 重查与背压状态保持。
2. `code/tests/input_service_probe.c`：独立硬件/队列模型和精确窗口注入。
3. `code/tests/test_input_service.py`：生产 Dong 执行与真实坏源码负控。
4. `.github/workflows/p6-input.yml`：独立输入/USB 回归入口。
5. `code/docs/p6-input-irq.md`：仅解释该输入子项及证据边界。

## P5：实现内容与未接线边界

候选五文件：`code/kernel/user/device_manager.dg`、`code/tests/device_manager_probe.dg`、`code/tests/device_manager_probe.c`、`code/tests/test_device_manager.py`、`code/docs/device-manager.md`。

新增 `user.device_manager.recover` 是内核内部账本事务，不增加 syscall，未从 `user.device_host` 调用。表布局仍为 4560 字节；公共 ABI 不变。可信内核调用者持有串行化锁，将精确旧设备 token、撤权后 generation、旧 owner/incarnation 和旧 DMA 租约绑定到回调上下文。

事务顺序固定为 `stop → quiesce → retire → reclaim → read → 发布未绑定新代际`：

- stop 在 HELD 后、任何 quiesce 前停止精确旧 owner 的所有 CPU 执行和返回路径；后续失败不能恢复已停止 owner。
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

`dma_snapshot` 是内核内部只读快照；无新增 syscall，Process/Frame 布局不变。当前没有 unpin/free/reuse 路径；内存根代际不等于设备 owner/incarnation，仍需可信 host 关联和硬件排空、全核退休。测试直接抽取生产 contiguous 与记录定义，覆盖 buddy/arena、1–32 页取整、每页登记/映射失败、容量与范围、重复/重入，及丢失取整尾部、未 PIN、提前 COMPLETE 三种真实坏源。专项 CI 已完成原生执行与坏源负控；这些是宿主执行证据，不是硬件排空或同 boot 恢复证据。

### 后续运行时 PR #7：复位后继续持有 DMA

[PR #7](https://github.com/EDarcyWong/dongos/pull/7)，分支 `codex/p5-virtio-reset-hold`，head `e2ae56ba1af8ef6201e6daf7e95ab563a42bdbbb`，未合并。生产涉及 `kernel/user/virtio_quiesce.dg`、`kernel/user/devices.dg`、`kernel/user/device_host.dg`（均相对 `code/`）：仅在真实 revoke_owner 完成永久停止之后隔离 PCI，由可信 ECAM/BAR 重发现现代 VirtIO，执行 byte status=0、full fence、最多 1024 次读回，并重检 identity、MSE=1、BME=0、INTx masked。尝试前 sticky HELD，错误不重试，成功记录 owner/token。

边界不变：DMA 仍 PINNED，没有调用账本 recover，没有销毁根、回收页、发布新 token 或重启驱动。原生四文件为 `tests/virtio_quiesce_fixture.dg`、`tests/virtio_quiesce_probe.c`、`tests/virtio_quiesce_probe.dg`、`tests/test_virtio_quiesce.py`；客体三文件为 `tests/p5_virtio_reset_fixture.py`、`tests/run_virtio_reset_qemu.py`、`tests/test_virtio_reset_guest.py`；加上工作流和 device-manager 文档，共 12 文件。

当前 head `e2ae56ba1af8ef6201e6daf7e95ab563a42bdbbb` 的专项 run `39418385170` 已 SUCCESS：native 与真实 TCG control/fault 两组均通过。故障组证据包含真实 UD2、四 CPU 退休、VirtIO status=0、BME=0、MSE=1、32 页 DMA 仍 PINNED。证据 artifact `12262367735`，SHA-256 `b265af3cd41f058510005c55d9f81f0e3c9a782776881b2e02396b6586072a24`；完整 CI run `39418385157` 仍待完成，PR 仍未合并。

这是受支持现代 VirtIO 的停止/复位后持有路径证明，不是 outstanding DMA 已排空的证明，不是 DMA 回收或驱动重启，也不关闭整个 P5。control/fault 的内核源码相同、故障通过块驱动源注入，但两次构建的内核 ELF hash 不同，**不能声称内核二进制相同**。

历史首次 guest 正常对照已到 desktop READY，但旧 decoder 预期 GUI flags=8、实际=9，因而失败且未执行故障副本；e2ae56b 修正 decoder 后通过上述实际两组验证。不要把这一历史观察器失败说成运行时复位失败。

### 其他待集成分支 PR #8

[PR #8](https://github.com/EDarcyWong/dongos/pull/8)，分支 `tasks/2026-10-20-c0-c2-integration`，远程修正 head `3a4704dbc1f84b90984dd0fcfeed8f53414ec49c`，双 parent 为原分支 `ca1373fb3db1576df080b4458f33002fb369a67a` 与 main `208029b090c722e881e327daef94b3500bb269b8`，当前 404 文件，尚未合并。范围包含编译器及约 185 个协调状态文件，不能因机械合并或 CI 某组通过宣称所有检查点独立验收完成。

已解决 memory 语义重叠：移除旧的未调用 `release_dma` 解 PIN 路径，保留 P5 精确租约记录和 hold，同时保留编译器栈 API。P5 独立核对 DmaLease、contiguous、snapshot、destroy、unshare 与已合入实现精确一致。4 项前端/静态聚焦检查通过；coordination 修正测试发现时的模块身份问题后为 149 项中 146 PASS、3 项 Windows-only SKIP。之前 7 errors 属于旧测试结果，不是当前状态。

本地缺 NASM，修正 head 的原生/boot 仍待 CI；未据此作编译器验收结论。后续以实际 head、差集审查、CI 与正常合并结果为准。

## P6：输入修复原理

i8042 已读空但 IRQ 尚未 ACK 时可能有新字节到达，导致边沿丢失。修复在 ACK 解屏蔽后重新 drain；若输出队列背压，保留 `RECHECK`，后续继续清空。读空后仍不进行空闲硬件轮询；USB-only 路径不增加 i8042 访问。

测试覆盖 ACK 窗口精确注入、背压、A 键 make/break、恢复后无空闲硬件读取。真实坏源码控制分别移除 ACK 前 drain、ACK 后重查以及背压重查义务。模型通过只证明上述局部契约，不证明真实桌面/USB 或整个启动流程。

## 验证记录：已通过、失败、未运行

### 已通过，但仅限所列证据范围

- P5 已合并 head：专项原生 run `39413950477` SUCCESS，完整 run `39413950440` 的 20 jobs SUCCESS。设备账本和 DMA fragment 实际原生执行、真实坏源控制及完整生产 memory 依赖图编译均有 CI 证据。本地缺 NASM 是此前环境限制，不再意味着远程原生测试未运行；仍无完整硬件恢复/回收证明。
- P6 输入候选本地：Dong debug/release 编译；静态栈 2224 B，小于 12288 B；C 严格语法检查。
- PR #3 较早 head `66c1603f608600e280af359811f941d89ca3bf90` 的 CI（run `39410917511` / job `118588180082`）：28 项测试通过，范围为原生输入/真实坏源、USB entry/USB-only、KVM runner 主机负控、trace oracle；run `39410917704` 中全部 9 个既有 QEMU boot 组通过。该次全量 host/language 检查后来因新提交正常取消，不能记录为全量 PASS，更不能自动套用到 PR #4。
- 新严格 KVM runner 及负控：25 项**主机测试**通过；不代表实际 KVM 客体运行。

### 已失败：KVM 环境前置条件

普通 CI runner 能看到 `/dev/kvm`，但没有读写权限。随后仅针对本次验证进程，尝试使用设备所属既有 `kvm` 组；检查确认设备确由该组拥有。然而：

`sudo -n -u runner -g kvm -- …`

返回 `sudo: a password is required`，见 PR #3 的 run `39411879213` / job `118591381873`。失败发生在客体启动之前：**没有启动 KVM guest，没有性能结果**。未实施 ACL/chmod/usermod、永久组成员变更或间接 root 操作。不要绕过这项失败，后续应使用执行身份本来就具备访问权限的 KVM 环境。

### 输入专项与文档已合并

- PR #4 专项 run `39412573598` / job `118593687024`：12 tests，303.650s，SUCCESS；完整 run `39412573501` 全部 20 jobs SUCCESS 后合并。专项实际 checkout 的 merge ref `5688f7fce89f2b750b91d6f6e77d2447aac5b832` 与 head 的 tree 同为 `bf0d596cca3369cb923ef227d7193d4a9ce58082`。原生证据：[artifact 12259369436](https://github.com/EDarcyWong/dongos/actions/runs/39412573598/artifacts/12259369436)。
- PR #4 合并后 main 的输入专项 run `39416934013` SUCCESS；完整 run `39416933994` 已知 9/9 boot 组通过，其余分片在最近核验时仍运行，不能自动算 postmerge 全通过。
- 首版交接文档 [PR #6](https://github.com/EDarcyWong/dongos/pull/6) head `ea659324a702679c9b9494695d5359a8f583095f`，完整 run `39413437487` 全部 20 jobs SUCCESS 后正常合并，merge SHA `1ac72a28101b6ea90b8e67703ba5905d59019b8f`。本次更新保留工程边界，替换旧的“待合并/待 native”状态。

### 初始 DAG 观察：真实失败尚未关闭

第一轮 PR #3 head `4dd3d362324892517fd7d9dfaf95843c3744757d` 的真实 TCG 运行，在 128 个首代候选中未捕获到两个 AP 同停于 CPL3，结构判据失败。客体实际运行且清理、源码指纹检查完成；这不是结构 PASS，也不是 KVM 时间结果。第二轮 head `ef3aaf0fdb688a2b2a3cc820dc08503eec20908f` 的 run `39418227325` 同样终态失败（artifact `12262417024`）：128 候选仍不足两个 AP 同停 CPL3；`actual_qemu_boots=1`、`all_started_guests_stopped=true`、`inputs_unchanged=true`、`init_cross_ap_proven=false`。当前应据 epoch/ACK 证据定位调度原因，而非把增加采样当作通过。主机观察器测试通过不能覆盖该真实门禁。

### 尚未完成的真实验收

- init 首代启动中跨 AP 依赖图的实际并行结构证据，而非启动完成后的 AP 活跃观察。工具已发布，两轮真实 TCG 观察均失败；不能写为该验收已完成。
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
2. 输入子项：PR #4 已合并；关注合并后回归结果，其他分支集成不得恢复旧输入行为。只将该结果记作输入子项完成。
3. P5：保留已通过的恢复账本/分配记录原生证据，随后分步接入可信硬件停止、全核退休和精确租约回收，最后做同 boot 客体故障恢复负控。未闭环维持 partial。
4. P6：完成 init 首代 DAG 实际证据与 GUI/USB 回归；为 KVM 选择已有合法读写访问的 Linux 环境，重新构建并运行时间门禁。遇设备权限拒绝就记录并停止该路线，不用 TCG/主机模型代替。
5. 仅当真实证据全部满足阶段契约，才提出阶段验收；文档、PR 草稿、某组测试通过均不是自动验收。

相关仓库文档：`code/docs/device-manager.md`、`code/docs/p6-current-validation.md`（实验分支）、`code/docs/p6-input-irq.md`（输入专用分支），以及现有 P6 integration/runtime/tickless/SMP candidate 文档。后者仅作接口背景，不替代本次精确提交上的执行证据。

## 快照历史

首版 2026-10-20 11:13 UTC 记录 PR #4/#5 尚待完整 CI、P5 本地缺 NASM，随 PR #6 保存。12:11 UTC 更新记录 PR #4/#5/#6 实际合并及 CI，通过与未完成项已在正文区分；本次还补入 PR #7 真实 control/fault PASS 与 PR #8 修正后的协调测试结果；旧状态不再是当前结论。历史内容可通过 Git 查看，无需重复保留逐分片进度。
