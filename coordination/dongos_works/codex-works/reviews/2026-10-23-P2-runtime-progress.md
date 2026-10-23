# P2 调度后运行接续

检查点：2026-10-23T04:56:52+08:00。用户顺序：**P2 完成后再完成 P5**。
P2 整体仍为 partial，P5 本轮实现尚未开始。主线 HEAD 为
`db4ea7c9a74839d95a5e80a0bbf8468a4bfa0d73`，实现位于未提交工作树；没有提交或推送。
本记录由 P2SYNC26 接续，不改写此前 02:55/03:20 的冻结检查点。
逐项机器状态见[同名 JSON](2026-10-23-P2-runtime-progress.json)，实时 rev 以 MCP 为准。

## 已完成的独立组件验收

下列正式作业均零 skip、source_stable，受测进程已停止并退出。数量按作业列示，
存在重复回归，不合并为“不同测试”总数。

| 任务 | 本地集成 rev | 正式作业 | tests | 通过范围 |
|---|---:|---|---:|---|
| P2FLUSH11 | 6 | `64cf4d5d11454dfebd38a28ec54136b8` | 3 | 原生失效选择/控制流；硬件边界替身 |
| P2PCID12 | 13 | `b893487745444470ada6ec46686c7f0a` | 33 | 严格新构建、原始 CPU/根/tag/代际采集准备 |
| P2ROOT13 | 15 | `688d4e6524cc4711b057277f22cba22e` | 4 | 完整内核/用户根及 alias 闭包 |
| P2WC14 | 10 | `771f1364dcae4599970d908643969e73` | 5 | 完整 GOP 采集；实际 TCG 备份/恢复，不证明物理吞吐 |
| P2HARNESS17 | 6 | `2676654ed39c4bd8ad28e4484a4b62db` | 7 | 独立副本测试输出目录准备 |
| P2MASK18 | 6 | `91bb571d06604d46a889b6ab8a1cd0ad` | 4 | 硬件物理地址宽度与私有池边界 |
| P2EXEC19 | 12 | `33aa513f0cca4706b80adbfc2bac7105` | 3 | 真实 DG/ASM 组件；特权动作及 PF 用替身 |
| P2CACHE20 | 9 | `ac7fe821d9b44c2b8bd854e30218d121` | 3 | 真实 DG/cache gate、完整森林/回执及坏源 |
| P2ENTRY21 | 6 | `f3f29865ca4b48ad9b946e65877f431e` | 2 | 精确登记、原异常帧与仅 RIP 恢复；未实际执行 IRQ/IRET |
| P2DISCOVERY22 | 6 | `c6d05731305847e599981387aaef81ea` | 5 | 新调度域发布前完成设备 inventory，保留 deadline/ACK |

ENTRY21 保留 55 条真实命令、32 份 ELF/COFF 对象、8 份 EXE、14 次原生执行，
三类真实坏源和两模式错误 callback ABI 均准确拒绝；生成回调栈上界 1120B。
DISCOVERY22 的 normal activation 及 device manager 原生控制均通过；它的
实际 WHPX 修复效果仍须新运行确认。EXEC/CACHE/ENTRY 尚需统一服务与构建接线。

## 在途实现与实际失败

- LARGE16 已返修并领取 rev11。正式 `9fb3005cc48e4b97b63c41bc01751ad6`
  的前四模块共21项通过，但 buddy 模块因测试输出源根缺失 E0202 而失败，
  paging 未运行，整个作业不通过。root 已修测试 resolver 并诊断执行该项
  1 test/0 skip/1.541s 通过，仍须正式全套复验。新 normal runtime7 链接成功，
  raw kernel 为 **2,077,072B，距 2MiB 余 20,080B**。
- LARGE 的此前 `normal-r1` 在真实 UART 收到 `stop terminal / unknown command`
  后失败，尚无事务 before/after/launches。405 份原始物理片段没有覆盖 LARGE
  指针，不能补造事务结论。拥有的 QEMU 已正常退出并清理。
- HARNESS24 rev2 正在修复真实 `ps / kill token` 收尾，保留新鲜回执和 Catalog
  身份/代际检查。另需解决 desktop 后自动触发与 before 基线的竞争，不能放松
  `attempted==0`，不能修改 guest RAM/寄存器制造现场。
- SIZE23 rev2 正在将 runtime7 静态池 2→1，同步严格 profile 和真实动态 slot1
  身份。runtime5/6 仍为2、默认仍为3；2MiB、16384 USER 帧与32/128表池不扩大。
  预计少131072B静态存储，增加32页实际 service arena 持有；尚非实测余量。
- WHPX R7 已真实 PCIDE=1，但在 AP 首次用户执行前收到旧 TLB fatal
  `0x06030004`。原始域/桥/CPU/IRQ资料与“ECAM长枚举耗尽绝对 acquire deadline”
  的源码路径一致，第一原因仍为推断；不能计作 AP 暖 tag/复用通过。
- 新 WHPX R8 使用包含 DISCOVERY22/ENTRY21 的上述 fresh normal 构建，已
  到达桌面；但三个 AP 的 user_entries/timers/switches 均0，Domain/Bridge
  failed，sequence/barrier=1925、completed=1924，故仍不通过。root 逐一核验
  700份物理读取的长度/SHA，QEMU正常退出0且清理完成。采集器另准确暴露了
  错把 BootInfo 当两个32位字段的 schema 错误；真实 ABI 是160B的20个u64，
  开头依次 magic/version/size。该采集修正由 LARGE16 R3 接续。
- SMP27 rev2 记录实际 Bridge 首错及具体阶段，再以新构建复现 AP 停点；
  不延长 deadline、放松 ACK/PCID 或以桌面 ready 代替 AP 进入证明。
- HARNESS24 的 root 直接诊断18项/0 skip/0.109s通过，尚待正式独立队列，
  不将直接诊断冒作组件验收。

## 关闭 P2 前仍需完成

1. LARGE 的稳定原始前后快照、全部事务/回收及指定 AP 漏失效的精准 A/B 负控。
2. EXEC/CACHE 的 services/build、完整独立 GOP alias ledger、绘屏 gate 与真实
   AP 42/43、写保护 PF、WC→UC→WC、PAT/MTRR 不变及有效负控。
3. 支持环境中 AP PCIDE=1 的暖 tag 和跨代复用正负控；回退不算通过。
4. 新完整 runtime7 的装载、service arena 及 kernel 表池实际余量。
5. 真实显示硬件 WC 吞吐；TCG/WHPX 虚拟计时不替代物理结果。PGE继续拒绝。

G6DOC1 保持 paused rev2；G5 已完成的语言/宿主闭包范围保持，不据此扩大为新
G6 guest 或整个 L3 完成。P2 实际门禁全部关闭之后再推进 P5 的 DMA 安全恢复。
