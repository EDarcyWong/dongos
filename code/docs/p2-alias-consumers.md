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

# P2ALIAS8 正常启动消费者（已集成）

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

原组件 P2EXEC1/P2WC1 已分别真实本地集成 rev18/rev10，P2ALIAS8 已
integrated rev6。正式作业 `808396a46c8b4c4d8b85962a52e41522` 的 7 项
测试零 skip、源码稳定；正常单/四核、两种精确硬件坏体、完整 raw replay
及四核桌面/P5 回归的原始证据见下方最终验证记录。该范围仍为调度前、
同一共享根、永久 seal，不证明调度后多根版 owner、AP PCIDE=1 或物理 WC
吞吐。2026-10-23 按用户顺序先继续 P2，完成后再推进 P5。

2026-10-23 调度后接续：EXEC19、CACHE20 及精确受控入口 ENTRY21 已分别
通过独立宿主复验并集成；当前仍需正常 services/build 接线、独立 GOP alias
ledger 和 panic/NMI 绘屏 gate，再完成实际 AP 42/43、受控写保护 PF 及全 GOP
WC→UC→WC 正负控。LARGE16 的实际运行曾被采集器不支持的 shell 命令阻断，
没有据此取得事务通过证据。不得把下文调度前的最终验证记录套用于上述余项。
详细状态见[本轮运行进展](../../coordination/dongos_works/codex-works/reviews/2026-10-23-P2-runtime-progress.md)。

## 接线边界

在 smp.runtime.large_begin 中先获取 EXEC startup buddy order0 帧（使旧大页报告反映真实新的free基线），再运行原 large.run，随后新 alias_memory.run。正常单BSP/IF0、全部AP在线同CR3、调度前运行并seal；不支持任意多用户根动态事务。Context/receipts/ranges 等通过 service_memory monotonic arena 实际分配并清零，无巨型静态BSS。受管EXEC物理帧只映射2个新WB别名，不映射HHDM，始终held，final alias A RO/NX、B RX。新代码必须实际执行P2EXEC1生产事务。保留原2MiB装载界限，预计新增所有者+planner代码会超过90544B余量，必须先实际测量，如不足另发布预算范围而不强行超限。

## 硬件桥设计

新增 alias_memory.asm 只提供受控指令和同步采集，不实现权限所有权算法。复用AP ping vector0xf1的新增hook，原ping语义保留。hook保存全部会被命令影响的GPR，不用SSE，不调用Dong；用专用固定16CPU mailbox序号/ACK，实际IDT/CR0/CR3/CR4/EFER/PAT/CPUID+MTRR读回。BSP使用Domain.cpus显式指针，不能假定其GS已是smp.Context；AP使用GS:self。每个CPU的Box由BSP公开到asm pointer数组，AP命令完成后mfence再ACK；所有hardware callbacks读真实结果。

Box计划为416B：u64 sequence,ack,command,virtual,value,result,fault,root,epoch,cr0,cr4,efer,pat,cap,default_type,bits（16字）；variable[32]u64（16对base/mask）；old_gate[2]u64；idt:u64；cpu:*Context。SIDT检查实际IDT与Context.idt，epoch取Context.online_epoch，真实CR3和CPUID APIC ID必须匹配Domain CPU。

命令：1读回，2实际读qword预热，3实际call仅mov-eax-immediate/ret的受管代码，4精确受控写探针，5本地全根CR3失效，6WBINVD，7PAT4更新（保留其它entries，实际CR0.CD/缓存维护/WRMSR/CR3/恢复CR0），8本地INVLPG。BSP写前清ack/result/fault，序号有界增长；AP等待实际IPI完成，不能写假ACK替代操作。WRITE探针临时只替换该CPU IDT[14] handler地址，保留原gate属性/IST；只在当前command4、精确探针RIP、精确CR2、present supervisor write错误位匹配时记录fault=1并跳到唯一after标签，其余异常fail-stop，结束恢复原gate。PF handler通过SIDT查16个Box的idt，不能依赖BSP GS。

## EXEC 正反例

A初始RW/NX、B初始RO/NX；实际写入返回42的6字节函数（b8 2a 00 00 00 c3），所有读者预热A可写及B NX。owner转换至B RX，先由同夹具WRITE(A,new99)验证精确#PF且物理代码保持42，再全部CPU实际执行42；再转换RW A写43，再转换RX B全部执行43，封存并验证后续拒绝。FLUSH_LOCAL仅BSP实际flush，SHOOTDOWN依赖owner真实tlb.broadcast后采集，不偷偷多flush掩盖漏同步，PUBLISH依赖owner真实目标VA广播+BSP失效。

负控单独冻结源码，只省略bootstrap.asm .full分支AP CR3写入，仍真实ACK且PUBLISH目标B INVLPG正常。AP缓存A RW保留，WRITE(A,99)实际成功、原始PTE却RO；由精确write mask/physical code/reader值证明拒绝并保持租约，不用泛panic/超时。正负均使用完全相同探针。

## WC 与正常桌面

GOP真实BootInfo全部页面，原内核HHDM UC alias由P2WC1 owner撤销→全读者TLB屏障→全读者WBINVD→全部CPU PAT4写WC并实际读回→WC重映射→第二屏障→seal。MTRR配置从每CPU实际MSR解码，目标必须全部>1MiB时固定低区不相交；仅保留相关variable ranges/实际default，按checked planner解析，不硬编码WB。每CPU ranges存储独立，原owner禁止ranges重叠。READERS初始化后保持不可变；callback对新硬件读回单独解码hash匹配，不伪造reader状态。

user.memory新增精确framebuffer WC入口（只允许已seal且正确物理范围），普通map_device拒绝与已迁移framebuffer交叠；user.desktop改用专门入口。其它device仍UC，普通WB用户复制/分享拒绝WC。不得保留WC HHDM与UC compositor的异类型别名。真实4核桌面及P5两观察必须回归。

PAT负控仅令一个AP省略PAT WRMSR，随后仍返回真实旧PAT；在owner PAT_UPDATE阶段回读拒绝，所有原alias保持撤销、完整held、禁止remap/free/reuse。TCG不证明WC真实性能。

## 最终验证记录

最新生产顺序的冻结快照已完成真实单核run-03eea1a2615f、四核run-7bfdf19983e5：全CPU预热写/受控写拒绝/执行42与43全部mask正确，EXEC/WC均seal，原始128表完整闭包、持有frame、2025页GOP撤销/回收/重映射与全部真实PAT/MTRR读回一致。四核实际桌面ready，pid2 arena完整32表、compositor128表和2025页USER/HHDM全WC一致；P5两次独立稳定观察通过。最晚采集器另从既有Box原始字节独立解码每个CPU全部variable MTRR，并逐GOP页解析重叠；不改档案、不写客体内存。

唯一漏AP全CR3失效的实际坏体run-37bd57542d1e在phase3精确拒绝：warm mask15，BSP写拒绝但AP仍可写，write-denied mask1，物理字节99，尚未首次执行42，frame held。唯一CPU3漏PAT WRMSR坏体run-492fd311f804在phase8/WCphase4被原owner以CALLBACK_FAILED7拒绝：实际PAT不同，2025页全部撤销/已回收而未重映射，held、不free/reuse，EXEC仍完整封存。两坏体均实际完整编译/启动，只变一个声明源文件，原生产源SHA保持。

四个最新现场均完整只读原始QMP归档/磁盘不变/源稳定，并由当前独立解码器离线复算通过，汇总reviews/2026-10-22-P2ALIAS8-final-raw-replay.json。旧失败PAT接线、漏kernel/build快照、旧探测顺序未抓到漏失效均保留，不计通过。正常最终kernel仍2MiB内，约1994448B；TCG只证明这些指令/寄存器/页表行为，不证明WC真实性能。正式宿主复验及验收记录由协调器另登记，组件与整个P2阶段边界保持区分。

## 开发实测记录（不计验收）

首次完整链接超窗32464B，O1仅缩4096B仍超28368B；均由原2MiB materialize拒绝。独立P2SIZE10显式storage2配置使既有pid2走相同arena动态分配路径，ELF真实测量省131072B；结合P2SIZE9实际完整release runtime7为1994448B/余102704B，源输入稳定。默认/诊断storage3不变。编译器Resolver不支持重复根，实际使用普通DG逐字复制且SHA登记的单一kernel快照，仅生成storage_profile配置；未放宽resolver或修改源码文字来伪造结果。

第一单核真实客体build/test/p2-alias/run-9f734648a950：实际warm_write_mask=1，exec42_mask=1，write_denied_mask=1，exec43_mask=1，EXEC已seal。WC完成2025页实际撤销/全根失效/回收/缓存维护，在PAT阶段正确以CALLBACK_FAILED=7拒绝，因为集成回调未将实际硬件PAT读回发布到CPU.Context.pat。原2025页未重映射，租约held，报告/串口/物理档案保留，明确未通过验收。修复接线只把真实Box.pat更新到同CPU描述符，错误PAT依然保持实测旧值并由原owner拒绝；不改已验收owner或伪造ACK。正常和真实坏体客体待重新执行。

正常framebuffer授权通过user.memory.setup-only unsafe publish_framebuffer复制经过seal的精确GOP范围，并再次核对完整内核PTE均WC，再允许后续compositor同范围USER WC映射；普通MMIO交叠拒绝。user.memory不导入多核硬件模块，早期runtime4诊断维持原依赖。
