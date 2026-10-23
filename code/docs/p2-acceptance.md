2026-10-23 09:40 +08:00 有界检查点（P2SYNC40，尚待独立文档门）：**P2软件仍partial，P5本轮未实施**。
OBS36 submitted rev12：正式71项零skip；历史R5仅诊断observations_completed，acceptance/passed均false。
B R8正式44项零skip、两份fresh各1109source/staged与286产物、kernel1966480B；
实际normal-r8仍false（B已complete、后续service barrier pending），omit-r8首ps超时且未触发B，不是精准负控。
**B R9 in_progress rev36，未测/未通过**；normal v2区分后续pending，negative原门保持，验收/集成待后续。
C/D接线、PCID实际复用/wrongtag及真正WC仍未闭；P5CTX1/2旧组件保留。
暂无真机，待验留档不阻断P2软件及本机门完成后进入P5；全部软件/本机复验后上传GitHub并关机，末端操作尚未执行。
详见[09:40证据与边界](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-historical-progress.md)、[来源JSON](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-historical-progress.json)。
以下07:50及更早正文逐字保留，仅代表当时范围，不被本检查点改写。

---

# P2 核心阶段验收与剩余清单

2026-10-23 07:50 +08:00 检查点：最终范围为 **P2、P5 全部软件工作及本机复验**。
暂无真机，物理 WC 等待验项留档；P2 软件及本机门完成后可进入 P5，不能写成真机通过。
完成后完整代码上传 GitHub 并关机已获授权，末端操作尚未执行。
**OBS32/SYNC33/OBS34 integrated rev6**；OBS34 正式 36 项零 skip，仅集成 IO 证据组件。
LARGE16 的 R6 正式 37 项零 skip 与新源两构建通过，但实际 normal-r4 首个 ps 仍超时：
暂停内审计 4453ms、总 stop→cont 4688ms；cont 后落盘有效，原 1 秒期限问题未闭。
**LARGE16 in_progress rev26、OBS36 in_progress rev2**，接续历史镜像/R7 适配尚未测试。
P2 软件仍 partial，P5 本轮只读准备、尚未开始实现；原失败和中断不覆盖。
详见[有界进度与证据](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-deferred-capture-progress.md)、
[来源 JSON](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-deferred-capture-progress.json)。
下方 06:32/05:55/05:42 均为各自源码和授权范围的历史记录。

2026-10-23 06:32 +08:00 检查点：**SYNC31 integrated rev9、GOP29 integrated rev6、
HARNESS28 integrated rev6、BKL30 integrated rev9**，各正式独立回执均零 skip、
源码稳定且进程已停止/退出。BKL R1 失败保留；R2 为 3 项通过，FIFO 组件尚未接入 Bridge。
**OBS32 submitted rev3，LARGE16 submitted rev16**：修复采集 epoch 与五个忙进程
实际提交后才发起一次 request 的活性条件；OBS 29 项、LARGE 20 项本机预检通过，
完整独立复验未执行。
旧 31 项及构建仅属各自历史源码。
R13 的 AP 空闲/屏蔽计时快照不构成 AP 用户计时门通过，也不能据此认定硬件限制。
P2 仍 **partial**，P5 本轮尚未开始；实际大页/EXEC/受控 PF/缓存接线、暖 PCID 与
物理 WC 门继续保留。详见[本次状态与原始证据](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-observer-progress.md)
及[机器可读记录](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-observer-progress.json)。下方 05:55/05:42 为历史快照。

2026-10-23 05:55 +08:00 追加：**SIZE23 integrated rev6，SMP27 v2 integrated rev9**。
R13 在首次暂停前连续运行2秒、之后不再恢复，Domain.failed=0、无首错，三个AP
实际用户进入161/168/213次，完整16槽（11个live根）池审计通过。旧采集在大量
QMP读取后恢复，存在WHPX绝对期限被观察过程扰动的风险；先修采集方法，不能
直接归责生产锁。AP计时仍0，暖PCID及实际事务余项未关闭，P2仍partial，完成后
再进入P5。详见[05:55追加与原始证据](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-lock-diagnostics.md)，下方05:42状态为历史快照。

2026-10-23 05:42 +08:00 检查点：继续按 **P2 → P5** 执行，P2 保持 partial，
P5 本轮尚未开始。SIZE23 已正式独立 99 项零 skip，LARGE16 已正式独立 31 项
零 skip；正常/负控两份实际构建均为 1,962,384B，但实际 WHPX 仍出现获取
内核锁超时，AP 用户进入/计时/切换仍为零，故两任务尚未验收/集成。
HARNESS24 已集成；SMP27 时间诊断 v2、HARNESS28 夹具、GOP29 永久绘图
Gate、BKL30 FIFO 组件继续复验或实现。完整 C/D/ledger 接线、实际大页/受控
PF/缓存迁移/暖 PCID 与物理 WC 门禁仍须通过。详见[锁诊断与当前状态](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-lock-diagnostics.md)。
下方旧检查点、任务数量及“当前/未运行”保留各自日期和源码范围，不覆盖本次状态。

2026-10-23 接续：用户顺序为 **P2 完成后再完成 P5**，P2 整体仍为 partial。
根闭包 ROOT13/MASK18、失效桥 FLUSH11、PCID12 严格采集准备、WC14
采集器，以及调度后 EXEC19/CACHE20 组件均已各自独立复验并本地集成。
ENTRY21 的精确受控异常入口已通过 2 项零 skip，DISCOVERY22 的设备枚举
预处理已通过 5 项零 skip，均 integrated rev6。组件通过不代替实际 AP/PF 验收。

LARGE16 正在返修；此前实际运行在采集器发送不支持的 `stop terminal` 后
失败，没有事务前后证据。HARNESS24 修复真实 shell 收尾，SIZE23 调整 runtime7
静态池并严格绑定新 profile；保持原 2 MiB 装载窗及私有池容量。完整 C/D 服务、
alias ledger、绘屏 gate 与构建接线、实际多根事务正负控、AP PCIDE=1 暖 tag/
跨代复用及物理显示 WC 吞吐仍待完成，PGE 继续拒绝。
新 WHPX 已到桌面，但三个 AP 的用户进入次数仍0且域失败，SMP27 正在补精确
首错诊断。本轮逐项作业、真实失败与范围见[运行进展](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-runtime-progress.md)。
下文保留 2026-10-17 核心验收的原始范围与证据。

2026-10-17，结论：**P2核心阶段验收通过；P2扩展清单未完成**。原阶段标准已由当前版本的直接实测和综合门禁达成，下一主线可进入P3。

本文记录P2验收时的源码、哈希和实测结果。随后P3启动链已加入ACPI发现与持久清单，最新构建、正式启动和回归证据见[ACPI记录](acpi-discovery.md)；下文“当前版本”均指本次P2验收版本。

## 验收范围

[PLAN.md](../PLAN.md) 阶段表的原标准保持不变：**故意缺页显示 panic 屏，保护位全开**。本轮核对当前版本的正式启动、活动根下的真实缺页、原分项门禁和剩余实现；没有把测试版 CPL3 探针当成生产用户进程，也没有把尚未实现的扩展勾成完成。

核心范围为单 BSP、四级私有根、独立固定内核栈与三组 IST、终止异常诊断、buddy/定长对象缓存、静态 W^X/guard、活动 WB/NX 数据页修改与本地 TLB 失效/回收，以及按 CPUID 启用和实际验证 NX/WP/SMEP/SMAP/UMIP。unsafe 存储独占、真实控制快照、同步可信硬件失效回调仍是接口契约的一部分。

## 当前版本的直接证据

正式版按 `build(test=False, stage="p1")` 独立构建，在 `q35 / TCG / max,+smep,+smap,+umip / 4 vCPU / 2 GiB` 下实际启动，仅 BSP 执行。完整 CPU、L1、内存准备、CR3/固定栈交接、hardening、活动映射、对象缓存及屏幕绘制链通过，最后停在链接符号对应的 HLT。

生产固件没有测试版强制的坏 map key；本次实际 EBS retry 为 0。采集器按实际 0～7 次 retry 调整旧解析器的**预期标记**，原串口字节完全不改，其余字段、阶段顺序和资源/生命周期断言照常验证。正常正式版没有测试退出码33；观察完成后由宿主 QMP 主动退出，不作为超时或客体自行退出计数。

QMP 对当前 CPU0 的独立读回为 `CR0=0x80010033`、`CR3=0x400000`、`CR4=0x300e68`、`EFER=0xd00`，证明 WP/NXE 与 SMEP/SMAP/UMIP 实际开启。CPU 停在 CPL0 的正常 HLT，IF/DF/VM/AC 清零。正式内核的装载字节与已验收权限版本相同，无故障注入助手。

缺页画面使用既有 `cache-unmap` 测试镜像：先完整运行当前对象缓存生命周期，撤销及失效后读取原窗口，真实产生 `#PF/vector14/error0`、`CR2=0xffffb00000001000`。原独立门禁核对精确 ELF RIP、184字节 IST 上下文、CS/SS/GPR/标志和四帧受信回溯；当前控制位仍全部开启。移除测试退出设备后停留在原 panic HLT，未修改异常或绘图源码。

两张实际 QMP 截图均为 **640×480**，已用本地图片工具目视检查：正常屏幕末行可见，panic 的向量、错误码、地址、全部 GPR、四条回溯及停机提示可读，无截断。

| 观察 | 结果与证据 |
| --- | --- |
| 正式启动 | [原串口](../build/test/p2-acceptance/production/serial.log)、[硬件寄存器](../build/test/p2-acceptance/production/registers.txt)、[正常画面](../build/test/p2-acceptance/production/screen.png) |
| 全保护位真实缺页 | [原串口](../build/test/p2-acceptance/page-fault-screen/serial.log)、[硬件寄存器](../build/test/p2-acceptance/page-fault-screen/registers.txt)、[panic画面](../build/test/p2-acceptance/page-fault-screen/screen.png) |
| 图像及进程终态 | [boot-visual.json](../build/test/p2-acceptance/boot-visual.json)，明确记录宿主观察完成后退出 |

首次采图未显式指定 VGA，QEMU 报告 VGA globals 未使用，引导器在进入内核前因 GOP 校验失败而拒绝启动；该次未通过，不计作核心启动成功。完整失败证据保存在 `build/test/p2-acceptance/production-initial-gop-rejected/`。采集器明确配置标准 VGA 后，两项观察通过；正式启动和内核源码未因该问题改变。

## 综合门禁与证据复用

前轮刚通过的524项宿主测试（201系统、323语言/标准库）对应211个源码与测试文件。本轮逐一复核 SHA-256 相同，直接复用，避免把重复执行计作新增覆盖。本轮新执行此前明确排除的原九项 std-arch 真实 QEMU 套件：正常实现退出33，八个坏实现均退出35并由原断言拒绝，全部零 skip。合计 **533 项不同测试**；其中这九项内部实际运行 QEMU。

本轮主线在独立目录串行执行与统一 test 入口主线同集合的48个用例，分别调用原 runner，再补回两项既有全保护位活动 TLB 故障，共 **50项全部通过**。最终使用当前门禁重解析全部串口/ELF，正式源码哈希保持一致：

| 用例组 | 数量 | 覆盖 |
| --- | --- | --- |
| P0/P1 | 5 | 正常交接与镜像篡改、截短、缺失拒绝 |
| 早期 CPU | 8 | INT3、UD2、GP、PF、坏RSP、DF、除零、坏RBP |
| 内存/活动页表 | 15 | 正常链、七类预检拒绝、五类权限/guard、两项预热后撤权/撤销 |
| 能力模型 | 5 | 全特性、分别缺SMEP/SMAP/UMIP、全缺特性 |
| 缓存 | 3 | 全/无特性生命周期、撤销后真实缺页 |
| USER/CPL3权限 | 12 | SMEP/NX、SMAP AC/关闭对照、五条UMIP拦截与关闭后执行 |
| 全保护位活动故障 | 2 | 开启三种CR4特性后的预热RO降权和unmap精确故障 |

自动矩阵与图像观察分开计数：主线50、std-arch9、正式启动/缺页观察2，另保留首轮GOP配置失败1；本轮实际共 **62次客体**，全部串行。此前权限轮的三个坏客体及其它 native 负控保留原版本证据，本轮不冒充重新执行。

证据入口：[矩阵](../build/test/p2-acceptance/matrix.json)、[原九项补验](../build/test/p2-acceptance/std-arch-summary.json)、[复用宿主结果](../build/test/permissions/host-regression-summary.json)。复现脚本与完整日志在 `build/test/p2-acceptance/`；原常规入口仍为 `python tools/build.py test`。

## 仍未交付的扩展

下列项目继续保留未完成状态。本次公开拆分原聚合清单，给出启用前条件，不视作实现或历史验收。

| 扩展 | 归属与完成条件 | 当前状态 |
| --- | --- | --- |
| 动态执行别名 | **P2扩展**；先建立物理别名W^X/所有权及撤权同步契约，再提供动态EXEC；P4加载用户代码前复核 | 未实现，活动API仍拒绝USER/EXEC |
| 大页/拆分 | **P2扩展**；独立实现与验证2MiB/4KiB转换、失败不变、TLB及回收 | 未实现，私有树保持4KiB |
| PCID | P2扩展与P4地址空间项关联；多地址空间启用前完成tag复用与精确失效验证 | 未实现，PCIDE关闭 |
| SMP shootdown | P2扩展与P6 AP启动关联；多个CPU共享根前完成IPI、确认与回收屏障 | 未实现，仅BSP，本地失效 |
| PAT写合并 | P2扩展，本次明确排期为图形阶段使用WC之前；先验证PAT/MTRR、缓存类型迁移和冲突别名 | 未实现，保留已验证WB/UC，不重编程PAT |

下一主线可依据已通过的原阶段标准进入 **P3 ACPI/APIC/定时与线程**；本次完成P2核心阶段验收，扩展清单未完成，P3尚未开始。P2上述扩展仍需交付，不能因核心验收通过而删除或勾选。

DeepSeek D1～D11保持原独立验收结论，本轮未重开、改实现或分配新编号。未执行远程CI、真机、SMP、性能目标或一般生产用户态验收。

范围与实现独立审查见 [scope-audit.md](../build/test/p2-acceptance/scope-audit.md)、[implementation-audit.md](../build/test/p2-acceptance/implementation-audit.md)、[test-audit.md](../build/test/p2-acceptance/test-audit.md)。最终计数及源文件哈希见 [validation-summary.json](../build/test/p2-acceptance/validation-summary.json)。
