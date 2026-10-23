# P2 观察采集与负载活性进度

检查点：2026-10-23 06:32 +08:00。项目 dongos，顺序仍为 **P2 → P5**。
P2 保持 **partial**；P5 本轮尚未开始。本文只同步已存在的真实回执、源码审查和
在途返修，不宣布实际大页、EXEC/受控 PF/缓存事务、暖 PCID 或物理 WC 门通过。
[机器可读记录](2026-10-23-P2-observer-progress.json) 保存各回执及本文、六入口文档的 SHA256。
[05:42/05:55 历史记录](2026-10-23-P2-lock-diagnostics.md) 与旧失败归档保留。

## 当前任务与独立回执

以下为 MCP 的任务状态快照，不重算全项目任务总数。表内正式作业均由协调器在
独立副本执行，source_stable、process_stopped、execution_exited 均为 true。
各行测试数只适用于该作业的源码指纹；文档审查与 barrier 回归分别判断。

| 任务 | MCP 状态 | 正式作业与实际测试 |
| --- | --- | --- |
| SYNC31 | integrated rev9 | [6993211594444628822ab2e36b4b19d4](../../.local/runs/6993211594444628822ab2e36b4b19d4/result.json)，barrier 1 项、0 skip |
| GOP29 | integrated rev6 | [6e1f20d8758f4eca972db0e0f64997d7](../../.local/runs/6e1f20d8758f4eca972db0e0f64997d7/result.json)，framebuffer_gate/runtime_cache/panic_binding 各 1 项，共 3 项、0 skip |
| HARNESS28 | integrated rev6 | [28d623bb3fac4d468a05c2a7a870998d](../../.local/runs/28d623bb3fac4d468a05c2a7a870998d/result.json)，services 1 项、0 skip |
| BKL30 | integrated rev9 | R2 [d7273818c35049bd8b9f95bb627af90b](../../.local/runs/d7273818c35049bd8b9f95bb627af90b/result.json)，BKL 1 项、Domain 2 项，共 3 项、0 skip |
| OBS32 | submitted rev3 | epoch/bulk 改造已冻结提交，本机预检 29 项通过，尚无本轮独立通过回执 |
| LARGE16 | submitted rev16 | 原任务返修已提交；本机预检 20 项通过，完整独立 35 项待执行；R3 历史 31 项不等于当前源码或实际 guest 门通过 |

GOP29 的永久 Gate 以及真实绘图入口由宿主原生负控核验；这些回执不执行宿主
WBINVD/MSR，不证明 AP、真实 NMI 并发或物理 WC 性能。
HARNESS28 的真实 enable_smp/project、Catalog/Domain、poll 注册和 large_poll
由 22 次实际编译、26 次原生运行核验（debug/release 共 6 正常与 20 坏体）。
其 RAM 分配适配器具有真实所有权、对齐、边界与只清零一次检查；
LARGE 保持未启用，不能把此夹具当作大页事务或 AP 执行证据。
详见 [GOP Gate](../../../../code/docs/p2-framebuffer-gate.md)、
[services 夹具](../../../../code/docs/p2-smp-service-fixture.md)。

BKL30 R2 的[原始 summary](../../.local/runs/d7273818c35049bd8b9f95bb627af90b/workspace/build/test/user-bkl/run-9148ba4306c6/validation-summary.json)
记录 24 次真实 DG 编译、60 次原生运行、110 条命令及 756 个产物 SHA：
每模式 19 个正常场景 rc0、11 个真实坏源经 C 预言正常 rc1 拒绝。
真实 TLS 线程与 Domain poll/ACK 覆盖 FIFO 票序、重入竞争、RETURNING、
原 head Domain.Timeout、排队绝对期限、失败留票及 unlock 后交接。
意外 Dong panic、崩溃、编译失败不能作为有效坏体通过。
FIFO sidecar **尚未接入生产 Bridge**；宿主根/IF/TLB/时钟边界是明确标记的适配器，
没有证明 WHPX 超时消失、AP 用户执行或 P2 完成。见 [FIFO 文档](../../../../code/docs/p2-fair-bkl.md)。

BKL 首轮 [3be554a207994b029e7a60feffdce896](../../.local/runs/3be554a207994b029e7a60feffdce896/result.json)
整体 failed，1 项、0 skip。debug 正常 19 场景及前 7 个坏体已实际运行；
第九次编译在 clear-ticket-after-acquire-failure 坏源触发
`!void success requires return;`，release 与后续 Domain 当轮未执行。
返修仅把坏源的 u64 return 改为合法转发原 !void result，正常组件不改。
[首轮日志](../../.local/runs/3be554a207994b029e7a60feffdce896/output.log) 与
[首轮 summary](../../.local/runs/3be554a207994b029e7a60feffdce896/workspace/build/test/user-bkl/run-899f355da7a8/validation-summary.json)
继续保留，R2 不覆盖这段失败。

## R13 的真实观察与 AP 计时边界

[连续运行诊断结果](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/diagnostic-result.json)
来自实际 WHPX、4 CPU、`-cpu host,-vmx,-mpx,-sgx,-sgxlc`、
`-machine q35,kernel-irqchip=off`。首次暂停前连续运行 2 秒，之后不再 cont；
无 guest 内存或寄存器写入。归档仍为 diagnostic_only=true、acceptance=false、
passed=false，不把诊断成功读回改成阶段通过。
[采集脚本](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/diagnostic-script.py)、
[原始诊断](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/boot-1/smp-diagnostics.json)、
[物理读 manifest](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/boot-1/physical-manifest.json)
保留实际命令、寄存器/LAPIC 文本与 548 份物理读取。

Domain.failed=0，无首错；完整 16 槽、11 个 live 根的池审计通过。
暂停点 lock=1、owner=0，sequence/barrier=5238、completed=5237，
属于停止中的活跃屏障，不能在不再运行的情况下据此推断缺失 ACK 故障。
下表由实际 192B Metrics 原字节读回；switches 与 user_entries 在该归档数值相同。

| CPU | 用户进入/切换 | retained | 用户计时 | last_vector | failed |
| --- | ---: | ---: | ---: | ---: | ---: |
| BSP | 8016 | 2171 | 159 | 256 | 0 |
| AP1 | 161 | 76 | 0 | 256 | 0 |
| AP2 | 168 | 80 | 0 | 256 | 0 |
| AP3 | 213 | 103 | 0 | 256 | 0 |

原始 Metrics 分别为
[BSP](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/boot-1/physical-00503.bin)、
[AP1](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/boot-1/physical-00509.bin)、
[AP2](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/boot-1/physical-00515.bin)、
[AP3](../../../../code/build/test/p2-smp27-review/uninterrupted-whpx-r13/boot-1/physical-00521.bin)，
长度与 SHA 见 JSON。AP 新 Cpu 均为 IDLE、token=0、slot=16；
LAPIC LVTT=0x10040（masked one-shot/vector 0x40）、初值/当前值为 0，
符合空闲时主动停用 quantum timer 的源码路径。

源码解释有严格范围：

- [user_entry.asm](../../../../code/kernel/sched/user_entry.asm) 460–469 行只在
  CPL3 捕获路径且 vector=0x40 时增加 user_timers；365–389 行的 CPL0 IRQ/idle
  分支不增加此字段。因此该字段不是 AP 所有中断或全部 LAPIC 计时中断总数。
- [user_bridge.dg](../../../../code/kernel/sched/user_bridge.dg) 166–179 行在无选中
  frame 时关闭计时；有 frame 时调用
  [multicore.dg](../../../../code/kernel/sched/multicore.dg) 191–196 行 needs_quantum，
  只有该 CPU 存在优先级不低于当前任务的 READY 竞争者才请求 quantum。
- [user_bridge_arch.asm](../../../../code/kernel/sched/user_bridge_arch.asm) 85–88 行
  的 needed=0 路径写 masked LVT、初值 0；103–114 行的 arm 路径使用真实 timer_hz。
  [user_boot.dg](../../../../code/kernel/sched/user_boot.dg) 62–63 行把每个 AP 的真实
  校准率传给 configure；本次三个 AP header.timer_hz 分别为
  62679185、62658010、62630512，不能从空闲 masked 快照推断漏初始化。
- [user_arch.asm](../../../../code/kernel/sched/user_arch.asm) 87–93 行在真实用户返回前
  校验根和 RFLAGS.IF；本次暂停于 CPL0 的 IF=0 不能当成用户 IF 被关闭的证明。

R13 未运行五个 busy worker；归档没有完整 q.Engine 原始字节，因此不能重建
每次历史调度的 READY 竞争集合或断言全部历史计时都关闭。
现有证据没有证明 WHPX userspace irqchip 限制，也没有证明生产 timer 配置遗漏；
不据此延长原 absolute deadline，不削弱实际各 AP user_timers>0 门槛。

## 在途返修与下一真实门禁

旧采集在 stop 后做大量 QMP 物理校验再 settle/cont，WHPX TSC 可能继续推进，
从而使观察过程跨过原 absolute deadline。R13 的无恢复采集将这项风险单独隔离；
既往 R8–R12 失败仍是其对应归档的实际失败，锁不公平尚未成为已证首因。

[OBS32 任务书](../tasks/P2OBS32-board.md) 当前改造
[bulk/epoch helper](../../../../code/tests/p2_bulk_capture.py)、
[PCID runner](../../../../code/tests/run_p2_pcid_qemu.py) 与
[raw replay oracle](../../../../code/tests/p2_pcid_oracle.py)：
每次真实停止建立独立 epoch，原始 bulk 字节及寄存器文本绑定该次停止与 CPU，
严格 slice 引用和最终全盘复核；旧 synthetic fixture 只能生成 synthetic 结果。
这些源码已冻结提交，不能将未独立复验的 observer 当作实际正向 seal。
协调器实际 main 预检 bulk 10 项、pcid 19 项，共 29 项、0 skip、3.083 秒通过；
包括 500 次缓存读取零额外 pmemsave 和晚期文件篡改拒绝，仅宿主边界与真实 Python API。
该预检只有实际执行工具控制台返回，没有独立落盘 raw log；引用
[MCP 交付追加的协调器实测报告](../deliveries/P2OBS32.md)，不另造日志。
本次未启动 QEMU，实际 AP/PCID 门未证明，仍待正式独立 snapshot 及 fresh guest。

[LARGE16 任务书](../tasks/P2LARGE16-board.md) 在原 scope 返修
[services.large_request](../../../../code/kernel/user/services.dg)、
[正常运行门](../../../../code/tests/run_p2_runtime_large_qemu.py) 与
[准入负控](../../../../code/tests/test_p2_runtime_large.py)。此前只启动单个忙进程，
却在 large_try 实际事务开始前等待所有 AP 用户计时增长；缺少竞争可能使门一直不能触发。
现改为 cfg7..11 五个普通忙进程均经真实 shell spawn/提交，逐个核对独立
Catalog token/incarnation/config generation、memory generation、root/Frame 及 caller/BKL 身份，
扫描缺席成员仍继续检查其余成员，完整五个 committed 后才发起一次 request。
这是待独立复验的活性修复，不伪造计数、不放宽每 AP timer、原 deadline 或精确坏体断言。

协调器已在当前冻结 R4/R5 源码实际执行 RequestGateTests 1 项（36.570 秒）及
HostOracleTests 19 项（0.097 秒），共 20 项、0 skip 本机预检；不是完整独立 35 项。
[request 原始 summary](../../../../code/build/test/runtime-large-request/run-c8594a7955d0/validation-summary.json)
与同目录 18 组 assemble/link/native.json 记录 normal+8 个真实坏源、debug/release、
84 case 与五次逐步 commit；summary 明确 actual_guest_executed=false。
其 source_sha256 是 read_text 后 LF 正规化文本 SHA
`899b255fe9b28d83c91305bc12522d68a3d097af943fddeb30f9d59350602b3c`，
不同于 services.dg 原始文件 SHA
`5d3e5ba6d5e0a1af7a52b2d25e0d5f48392e9cc8e9fe94aaa72d9fdb966bfe4f`。
HostOracleTests 19 项只有执行工具控制台返回 0，没有独立落盘日志；这里引用
[MCP 提交交付追加的协调器实测报告](../deliveries/P2LARGE16.md)，不伪造 raw log。
完整 35 项独立复验、新正常/负控 OS 链接构建与实际 VM 均尚未执行。

R3 历史 [1edb5da569a54e5a8ff2a067e2ac1ee9](../../.local/runs/1edb5da569a54e5a8ff2a067e2ac1ee9/result.json)
通过 31 项、0 skip（runtime_large 1、guest harness 24、Domain 2、barrier 1、
buddy 1、paging 2），源码稳定、进程停止并退出。该源码下实际 normal 与
omit-ap-flush 构建均为 1,962,384B、loader 余量 134,768B，各 285 个产物；
后继 SMP27 v2 源码真实构建 1,966,480B、余量 130,672B。
[旧构建 SHA/预算记录](2026-10-23-P2-lock-diagnostics.json) 保留。
这些是历史构建与宿主回归，当前新源码需重新独立复验、fresh build 和真实 guest 正负控。

后续由协调器在源码冻结后执行独立宿主门，再使用完整记录停止/恢复时段及观察扰动风险的实际 guest
运行：普通 shell 启动并提交五个 busy worker，完整采集 Engine/Catalog/Frame/probe、
每 CPU header/metrics、原始寄存器和 LAPIC；真正事务前后状态、全部 AP 用户计时、
ACK/retire、精确负控和清理都需各自满足。EXEC/受控 PF、CACHE all-alias WC→UC→WC、
panic/NMI writer 接线、暖 PCID 与物理 WC 门继续开放；组件集成不替代这些实际证据。

## 本次文档验证范围

P2SYNC33 本轮仅编辑六个文档入口、本文/JSON 和交付单；保留 05:42/05:55 原段落。
本次执行静态 JSON、文件 SHA 和本地链接校验；没有自行编译、运行 unittest、
OS/VM 或修改 MCP 状态。任务声明的 barrier 独立检查由协调器后续执行，
本文不预写通过回执。
