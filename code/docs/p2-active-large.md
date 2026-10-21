# P2LIVE1：正常私有根上的活动大页事务

2026-10-21。最终 v2 的正常私有根单核、四核实测、真实坏源拒绝，以及完整 release runtime7 构建与四核桌面回归已完成。宿主独立复验 12 项、零跳过，另有既有 planner/paging 6 项回归；验收与实际文件集成由协调器分别留证。

本项在正常内核已经激活的私有 CR3 上，由 BSP 在 AP 启动前短暂执行一个 2 MiB WB/NX 映射的完整生命周期。结束后恢复原有 4 KiB 页表布局、页表槽位和 buddy 空闲账本。它没有把系统长期运行布局改为大页，也不提供多核共享根大页事务、动态执行或 WC 消费者。

## 生产接线

`kernel/mm/active_paging.dg` 新增 `map_large`、`split_large`、`merge_large`，直接复用现有 `paging.map_large_live`、`split_large_live`、`merge_large_live` 与 `huge_page_plan`，不重复实现页项转换算法。原有 Context 为 128 字节、Stats 为 24 字节，布局和旧 4 KiB 接口不变。

三个接口都验证真实控制快照、绑定根、完整 512 页窗口和必要的 2 MiB 对齐。映射时完整 512 个物理页必须位于 Context 的 owned frame 范围；拆分、合并前逐页检查现存映射的物理归属及 WB/NX 权限。flags 仍只接受 `0` 或 `WRITE`，拒绝 USER、EXECUTE、UC、WC。无效参数、范围、控制值、计数溢出或错误页表在提交前拒绝。

Busy 覆盖页项发布、整根失效和回收全过程。map、split、merge 均同步调用完整同根失效；不能以单页 INVLPG 代替大页转换协议。merge 先把旧 PT 隔离为 metadata=2，保持其内容与 used_tables 计数，等 flush 回调完成后才 reclaim、清零和释放槽位。失败路径不把未失效的表页重新发布为空闲。

`kernel/boot/large_memory.dg` 使用真实 `startup.allocator_pointer()` 获取 order9 的 512 页块，独占窗口 `0xffffa80000000000`。它不把 PA 或 `HHDM+PA` 当作自由 RAM 的可写指针；先映射、失效，再通过窗口初始化和访问。HHDM 仅用于独立读取已经受信的保留页表池。

`memory_probe.dg` 导出 `dong_memory_large_run`；`memory_mutation.asm` 在既有活动修改 verify 成功后实际调用它。`large_memory_flush` 是既有 `memory_live_flush` 的同代码标签，不增加另一套硬件失效算法。该钩子属于正常启动路径，在各 runtime 的 AP 启动前执行，旧 mutation/cache/ACPI 标记和断言保留。

最终 v2 将有限的实际读写循环放到同一汇编桥内，避免突破原有 2 MiB 内核装载边界；分配、权限、owned 范围、控制快照、页项事务与回收授权仍在 Dong 中。三个纯循环助手的模式参数及返回值均为 u64，地址参数为 64 位地址或指针，不写页表或控制寄存器：

- `large_memory_data` 初始化或逐个验证全部 512 页的首、末 u64，执行真实 MOV 读写。
- `large_memory_raw` 独立读取受信页表池，检查父项和完整 512 个 PTE，或核对大页 PDE；也能在故意非连续的拒合并状态下只读取合法 PT parent，以及在清理后确认该窗口的 PML4 槽为 0。池要求 base 小于 4 GiB、end 不大于 4 GiB、1～128 页且自然对齐，所有被解引用的表地址都必须位于该池内；父项及叶项仅放行规定的地址/权限和硬件 A/D 位。
- `large_memory_pt` 将全部 512 个原始 PTE 照录到已持有、已映射且已预热的窗口子页 509，拒合并后逐项精确比较，再恢复该页已知的首末 tag。它没有采用 hash，也不再使用一个额外的 4 KiB 全局快照数组；该页其余原本未定义的 payload 字节不作为数据契约。

`mutate` 在每一次真实 active 操作前重新读取硬件 controls，包括全部 512 次清理 unmap。PTE 快照页没有增加物理申请或别名，仍属于原 order9 块，且在清理完成前持续持有。

## 启动生命周期

1. 读取真实 controls、root、buddy free_pages 和 used_tables，申请实际 order9 块并绑定完整 owned 范围。
2. 建立大页；逐个访问全部 512 页的首、末 u64，并独立验证实际大页 PDE。
3. 拆为 512 个 PTE，整根失效后重新验证全部原始 PTE 与实际数据。active 的 owned 检查保留逐页 query；启动演练不再重复执行一轮相同软件 query。
4. 将虚拟子页 5 替换为同一块内的物理子页 6；实际读取必须从 tag5 变为 tag6，证明 CPU 使用拆分后的新页表。
5. 在已持窗口子页 509 照录全部原始 PTE；对非连续映射尝试 merge，必须返回 `NotMergeable=0x02030007`。独立 raw parent 读取核对 PDE 精确不变，逐项比较全部 512 个 PTE，used_tables 和 Stats 也保持不变，随后恢复 tag509。
6. 恢复子页 5 的原物理页，重新核对数据；merge、完整失效、回收旧 PT，随后再次验证大页数据与原始 PDE。
7. 再次 split，逐个 unmap 全部 512 页。每次 unmap 都完整失效，最后撤链的三个中间表在失效后回收。
8. 独立确认窗口的 PML4 槽为 0，因此其覆盖的全部窗口页已不可达；验证 used_tables 恢复基线、原控制状态不变及 startup 全树 allowlist 通过，随后才归还原始 physical/order9 租约。

页 i 的首 u64 为 `0x1122334400000000 | i`，末 u64 为 `0x8877665500000000 | i`。成功报告的 sample_first/sample_last 为第 0/511 页的首字，split_value/restored_value/merge_value 为第 5 页首字，replacement_value 为第 6 页首字；首末两组完整数据都由循环实际检查。

该 Context 的最终累计值为 `invlpg=2`、`full_flush=516`、`retired_tables=4`：四次大页事务的完整失效，加上 512 次 unmap；merge 回收一个 PT，最终窗口清理回收三个中间表。这些是本项 Context 的计数，不能与此前普通活动页演练计数混加。

## 报告与失败边界

实际链接符号 `boot.large_memory.REPORT` 是 39 个 u64、312 字节、8 字节对齐的静态 Report。含非零初值，不能假设其必定位于 BSS。字段顺序为：

```text
version attempted complete phase steps
root window physical pages order
free_before free_held free_after
tables_before tables_mapped tables_split tables_merged tables_after
sample_first sample_last split_value replacement_value restored_value merge_value
merge_error invlpg full_flush retired_tables held
cr0 cr3 cr4 efer rflags pat error_code
large_entry split_entry merged_entry
```

成功必须同时满足 `attempted=1`、`complete=1`、`phase=10`、`steps=1023`、`held=0`、`error_code=0`；free_after/tables_after 分别等于真实基线。large_entry、split_entry、merged_entry 是实际页表读取结果，允许硬件 A/D 位；拆分后的 parent PA 必须仍属于受信页表池。

arena 能容纳原表池和栈，不代表必然存在连续 order9 块。v2 在该实际申请调用现场捕获 OutOfMemory；此时尚无租约，phase/steps/physical/held 均为 0。独立重读 buddy 与页表账本并确认未变后，记录 `attempted=1 / complete=0 / error_code=0x02000007`，保留原正常启动行为，不自动重试。这是明确的 unsupported/未执行结果；guest gate 必须拒绝把它算作大页通过。之后任何阶段的 OOM 均不会进入该分支。

其他错误直接返回并保持尚未安全释放的资源，不进行猜测式清理或提前 free。只有窗口消失、失效完成、表槽与 allowlist 恢复后才允许归还精确的 order9 块。

## 2 MiB 装载边界与修正

首次完整 release runtime7 构建在 materialize 阶段失败，PT_LOAD 末端为 `0xffffffff80201e50`，超过原 2 MiB 窗口 7,760 字节。v1 去除全局快照页并整理重复代码后仍超出 3,664 字节。这两次失败保留，不能算作正常 runtime7 构建或集成通过。

v2 复用已持页 509 保存精确快照，将上述完整循环移入紧凑汇编助手，并共用重复的控制捕获与报告样板。原 2 MiB 装载 ABI、39 字段报告、512 页/512 项验证、失效顺序和 `516/4` 计数均未放宽。快速重链预检后，最终 r2 从完整冻结源码重新执行原构建器 runtime7/release/test=False，276.390 秒退出 0；实际 kernel.bin 为 2,096,720 字节，剩余 432 字节。最终 guest 也已启动该完整产物；原失败记录未覆盖，后续增加代码仍须重新检查这项尺寸边界。

## 已完成的宿主验证

- `tests.test_active_large` 与既有 `tests.test_active_paging` 共 3 项通过。新 Dong/C 原生探针实际执行 debug/release 的生产代码，独立遍历原始表和 metadata，验证完整范围、失败不变、A/D、回调重入 Busy、隔离旧 PT 未复用及回收顺序；Context/Stats ABI 保持不变。
- 三类真实坏 Dong 源在两种模式下均正常构建、链接并运行，再按明确断言拒绝：漏完整根失效、merge 提前 reclaim、只检查范围首个页。构建失败或崩溃不充当坏实现拒绝证据。
- 协调者复跑既有 P2 planner 与 paging 共 6 项，通过；没有以大页功能重写这些已验组件。
- 最终独立 host 复验覆盖上述新旧 active 3 项及原始 Report/buddy/页表池/离线门禁 9 项，共 12 项通过、零跳过。每种原生模式执行 2,587,089 次检查、23 个场景和 26 次回调；含 9 个计数溢出拒绝场景。证据：`coordination/dongos_works/reviews/2026-10-21-P2LIVE1-independent-host-final.json`。

## 最终正常客体证明

最终冻结源码位于 `coordination/dongos_works/.local/p2live1-debaba97c9cd/{a2,b2,m2,r2}-source`；9 个关键文件指纹保存于同目录 `source-freeze-v2.json`。三个 runtime0 镜像分别从完整源码重新构建，原构建器无 runtime0 manifest，因此协调包装器在真实构建前后核对全部 1,299 个输入，并记录实际命令、工具和产物 SHA；不是从旧镜像补写构建成功。

| 最终副本 | 实际 QEMU 结果 |
| --- | --- |
| a2：正常根、4 vCPU | PASS，3.969 秒；`run-2122b0c5a9894ff18ce34cd4b1ce3ec3` |
| b2：独立重建、1 vCPU | PASS，4.516 秒；`run-aefcb4bd99cb4dd29e3cec5b537a37eb` |
| m2：仅删除 `split_large_live` 的 PDE 挂接原子写 | 确定拒绝，3.438 秒；`run-3224eb1fa2524cc6ab2237b3c31de744`；实际 Report 为 phase=2、steps=3、held=1、error=0x020f0001 |
| r2：完整 release runtime7、4 vCPU | PASS，22.687 秒；`run-a9cef0e3c79d`；实际桌面 READY、启动大页 Report 完整成功及既有 P5CTX2 正常设备上下文两次快照检查通过 |

`tests/run_p2_active_large_qemu.py` 复用正常构建，使用只读 QMP 物理转储读取实际链接的 312 字节 Report、完整 Workspace、128 页表池和 buddy metadata；独立复算 free lists/完整原 order9 归还、受信池和栈仍被保留、全部最终叶的 PA/权限/cache allowlist、撤链表已清零及演练窗口已消失。还绑定原完整 startup/cache/hardening/ACPI 报告、当前 CR3 和正常 HLT 位置，记录串口、寄存器、所有转储、ELF/布局/构建指纹和 QEMU 退出清理；没有写 guest 内存或寄存器。

两次成功归档均已复制到独立目录 `portable-a2` / `portable-b2`，运行同一 CLI `--replay` 均通过，复验无需原源码或 ESP。独立审查重新跑完整解码：78 个 Report 逐字段错误均拒绝；复制真实归档并重新计算所有受影响 hash 后，非法 USER 叶和 buddy state=4 仍分别被语义检查拒绝。结果及索引见 `a2-guest.json`、`b2-guest.json`、`m2-guest.json`、`portable-replay-v2.json` 和 `reviews/2026-10-21-P2LIVE1-independent-guest.json`。

r2 使用构建器原生正常 runtime7 build-inputs，实际串口到达 `DONGOS_P7_DESKTOP_READY` 后，以只读 QMP 记录两次设备/上下文快照和实际链接 Report。两次 P5CTX2 正常控制均通过，其原始归档也经既有 P5 `replay_evidence` 全量复算通过；源码全部 1,299 项前后一致、64 MiB 一次性数据盘 SHA 不变、QEMU 干净退出。索引为同目录 `runtime7-guest-index.json`，实际构建日志为 `r2-build.log/json`；该次只把 P5 作为正常回归，不声称重跑崩溃、drain 或 DMA 复用验收。

实际 order9 OOM 的 unsupported 分支未制造真实固件碎片环境客体实测，host gate 已验证该报告不能被算作成功。本项 buddy 审计检查实际空闲链、尾状态、计数与租约归还，不声称是全部已分配/保留区的通用分区证明。详细交付为 `coordination/dongos_works/codex-works/deliveries/P2LIVE1.md`，独立审查和最终本地文件指纹为 `coordination/dongos_works/reviews/2026-10-21-P2LIVE1-independent-review.md` 与 `coordination/dongos_works/reviews/2026-10-21-P2LIVE1-integration.json`，均从工作区根定位。

本项不运行生产页的 USER/EXEC/WC 转换，不改变 PAT/MTRR，不延伸到 AP 在线后的大页 shootdown 或 PCID。没有建立 PR、提交或推送；本地验收与实际文件集成由协调者分别登记。
