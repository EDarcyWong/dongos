# P5CTX2：真实客体 DMA 持有上下文核验

日期：2026-10-21。项目 `dongos`，任务 `codex:P5CTX2`，依赖已集成的 `cursor:P5CTX1` rev7。按用户要求直接在本地完成实施、测试、独立审查与集成流程，不建 PR、不提交或推送。

## 实现与实际文件

- 新增 `code/tests/p5_recovery_context_guest.py`：严格核对 424 字节 DmaContext、128 字节 Device、64 字节 DmaLease 和 Binding 的完整 ABI，递归解码嵌套字段。
- 扩展 `code/tests/run_virtio_reset_qemu.py`：control/fault 均强制读取并核验上下文；独立对照 Catalog、memory、真实 ledger/Binding 和 ECAM 硬件；保存两次稳定观察、全部物理转储、ELF、布局及来源指纹，支持不启动 QEMU 的完整离线重放。
- 新增 `code/tests/test_p5_recovery_context_guest.py`，保留并扩展 `code/tests/test_virtio_reset_guest.py`；`code/tests/p5_virtio_reset_fixture.py` 仅将相对路径哈希键规范化为 POSIX 格式，确保 Windows 源清单与构建清单一致。
- 使用说明与证明范围见 `code/docs/p5-recovery-context-guest.md`。本文件为第七个授权交付路径。

以上文件已实际写入主工作区。内核生产算法与公共 ABI 未因本任务修改。P5CTX1 本地生产源码保持：`device_host.dg` SHA256 `823fc27763560ff880dd26b9e4da236a92cf55174d3e4a86bf0b234592ba95ce`；`services.dg` SHA256 `548c6dafa0f2e515bcefeba51ae28c754e68273c979275862c32b60b6a76fa65`。Git HEAD 保持 `28fae186eade64aac9eec17fcc2fb30913b948f6`，其它既有工作区变更未并入本项。

## 实际宿主与原生测试

`python -m unittest -v tests.test_p5_recovery_context_guest tests.test_virtio_reset_guest`：21 tests，通过，零 skip。覆盖完整字段 raw bytes 篡改、短读、严格布局/整数类型、身份/代际/partial lease/phase/drain、两次各自有效但整体更换身份或租约的拒绝、离线读盘顺序与边界、来源互核。新增前端编译回归从实际四种生产结构生成清单，与手写完整 ABI 比较，防止校验器和手写测试共同采用错误结构。

独立审查者另行实际执行同一命令，完整命令、输出、退出码及八个来源文件前后 SHA 保存在 `reviews/2026-10-21-P5CTX2-independent-host.json`。宿主模拟 archive 编排明确为 `actual_qemu_executed=false`，不充当真实客体证据。

`python -m unittest tests.test_p5_recovery_context -v`：1 test / 6 个实际 native 场景，通过，零 skip。debug/release 各自执行生产路径及 lost-error-snapshot、replace-old-owner-root 变异，生产路径退出 0，两类变异按指定断言退出 1。日志见下述运行根目录 `native-regression.log`，细节在 `code/build/test/p5-recovery-context/run-{62fc148ae6cc,2384b235802f,a4a02c748e71,73ea81ad771f,cab5ea8d640d,fd0775619e4c}`。

## 完整构建与真实客体

证据运行根目录：

`D:/projects/2026/dongos/coordination/dongos_works/.local/p5ctx2-20261021-193555`

`initial-copy.json` 封存基线及原始源指纹；`harness-freeze.json` 封存最终五个测试/观测文件。`control-source` 和 `fault-source` 为独立冻结副本，后者仅在块驱动 setup 成功后注入现有 UD2；`p5-reset-fixture.json` 保证只有 `services/drivers/block_service.dg` 不同。

两个副本分别运行完整 `build(stage="p1", runtime_level=7, test=False, output=Path("build/p5-reset").resolve())`，正常与故障构建分别 296.469 / 284.469 秒，均退出 0；`graphics_case=None`，构建前后来源稳定，运行前后再次检查来源和产物。精确命令、cwd、退出及日志 SHA 见 `control-build.json` / `fault-build.json`。

真实客体命令分别在对应冻结副本中执行：

```text
python tests/run_virtio_reset_qemu.py --reuse-esp build/p5-reset/esp --control
python tests/run_virtio_reset_qemu.py --reuse-esp build/p5-reset/esp
```

QEMU TCG、4 CPU、独立新建普通 FAT 数据盘、匹配的独立 OVMF NVRAM。正常组 40.015 秒，故障组 43.109 秒，runner 退出码均为 0。两次运行均 `actual_qemu_executed=true`，清理后 `qemu_returncode=0`、`process_alive=false`、`cleanup_completed=true`；源码与数据盘前后 SHA 相等。完整 QEMU 命令、工具/固件 SHA、输出及退出见 `control-guest.json` / `fault-guest.json`。

| 场景 | result 路径（相对于运行根） | 原始物理转储 | result SHA256 |
|---|---|---|---|
| control | `control-source/build/test/p5-reset-guest/run-f030641e4b73437a8ed14bc6e3c08000/result.json` | 1050 块 / 1505774 bytes | `2128dee3708c029535182009bdf7c38a8532d2ab235ea3a62043774719f8f6d8` |
| fault | `fault-source/build/test/p5-reset-guest/run-9a248717c827418089ddb0165e93e4b2/result.json` | 1049 块 / 1461994 bytes | `f120c1891430f2184cf10046f9e8c1f8e3083ecc93b3d8cc63983051e6838cbd` |

两组均取得两次完整稳定观察：owner=`0x300000001`，旧 token=259、旧设备 generation=1、memory generation=1，69632 字节请求/4096 对齐，完整 32 页 lease、held=1、drain=UNKNOWN。正常组 owner 存活且无退休回执；故障组在链接 UD2 处发生 #UD，Catalog 终止、全四 CPU 旧调度引用退出并有现有 ACK，stop/route/isolation=1、reset=2，真实 ledger generation=2 且已撤权。两次间原上下文身份和完整租约保持相同。

两份证据已另复制至 `offline-control` / `offline-fault`，其中不含原 ESP 和数据盘。从主工作区执行 `python tests/run_virtio_reset_qemu.py --replay <portable/result.json>`，完整未模拟 replay 分别 6.781 / 6.469 秒，均退出 0；重新解码逐读 PA/长度/角色/SHA 和全部页表，并与两次原 snapshot 完整相等。命令和结果见 `offline-replay.json` 与 `*-offline-stdout.json`。独立审查者另外审查并重放原始证据，结论及实际 raw 篡改负控见 `reviews/2026-10-21-P5CTX2-independent-review.md` 和同名 JSON。

## 保留的失败与修正

首次 NASM 3 构建因现有构建脚本的分组告警能力探测不兼容而失败，尚未启动客体；`control-build-attempt1.{json,log}` 原样保留。后续使用隔离下载的官方 NASM 2.16.03，保留 `-Wall -Werror`；工具下载 SHA、URL 在 `toolchain/download.json`，没有修改生产构建脚本。

首次 control/fault 观测均在 QEMU 启动前被严格 ABI 校验拒绝：测试将源 `usize` 直接当成 manifest 类型，而实际编译器规范化为 `u64`。已严格修正并增加真实生产结构清单回归；原 `*-guest-attempt1-layout.{json,log}` 和失败 result 保留。修正后真实运行和离线重放均通过，未覆盖或伪造失败记录。

## 验收与本地集成边界

正式受限 checks 由协调器独立排队运行；实际最终验收/集成状态与 rev 以协调器 `codex:P5CTX2` 记录及 `reviews/2026-10-21-P5CTX2-integration.json` 为准。只有独立源码/契约/测试及真实 raw 证据审查通过、正式 checks 零 skip 且主目录指纹与验收来源相同，才登记 accepted/integrated。

P5 仍为 partial：本项证明成功申请 DMA 后的 initialized-queue UD2 故障终态与两次持有状态稳定性。DmaContext 没有逐步时间戳，调用顺序由生产源码与 P5CTX1 native 轨迹核对；现有 ACK 位于撤映射之前，不是撤映射后 TLB 退休证明。VirtIO reset 不证明 outstanding DMA 排空；不声明 drain/free/unpin/reuse/新 token 发布/驱动重启。分配错误、partial mapping、physical=0 的 guest 注入未执行，相关证据仍仅来自 P5CTX1 native 测试。


## AI交付 2026-10-21T11:54:43+00:00 · codex-mcp-6fe7be60df984d37

P5CTX2七个授权路径已实际写入主工作区；没有PR/commit/push。21项host控制及独立host复验零skip通过，P5CTX1 native debug/release生产路径及两类真实mutants回归通过。完整runtime7 control/fault构建成功；真实4CPU TCG control/fault分别40.015/43.109秒exit0、两次稳定原始观察、source/disk前后SHA一致、QEMU clean exit0。两份不含原ESP/数据盘的portable archive完整未stub replay均通过。证据根coordination/dongos_works/.local/p5ctx2-20261021-193555，详细交付/范围/保留失败见本报告正文，独立审查和最终指纹回执见reviews/2026-10-21-P5CTX2-*。正式隔离checks及最终独立raw审查后再登记accepted/integrated。P5仍partial，held=1/drain UNKNOWN，无DMA回收/复用/新token/重启；现有ACK不等于撤映射后TLB证明。
