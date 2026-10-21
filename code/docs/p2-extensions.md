# P2 扩展：大页、跨别名 W^X、PAT 写合并

2026-10-21 更新。本文区分既有扩展机制、UEFI 探针和正常内核接入。PCID 生命周期与 P4 多地址空间共享契约，不在这里重复实现。

## 结论

| 扩展 | 状态 |
| --- | --- |
| 大页/拆分 | P2LIVE1 的 AP 前临时生命周期与 P2SMP3 的 AP 在线、调度前共享根同步事务均已验收并本地集成；后者最终保留封存的 WB/RW/NX 大页视图，真实 1/4 核及漏 AP 失效负控通过，见 `p2-shared-large.md` |
| PAT 写合并 | `mm.paging` 新增 `WRITE_COMBINING`；PAT/MTRR/有效类型（Intel SDM Table 14-7 逐格）/迁移顺序；QEMU 实测 |
| 动态执行别名 | 跨别名 W^X 检查与撤权顺序；QEMU 双 CPU 实测过期 TLB 确实存在、SHOOTDOWN 后消除、两个 CPU 都执行新生成的代码 |

P2LIVE1 已把大页事务接到正常内核启动路径：`mm.active_paging` 新增完整 owned 范围的大页 map/split/merge；在 BSP、AP 启动前，从真实 startup buddy 持有 order9 块，于当前私有 CR3 下完成短暂演练，再恢复原有 4 KiB 树及分配账本。最终独立宿主及正常根实际客体均已通过，见 [P2 活动大页记录](p2-active-large.md)。

接续 P2SMP3 已通过正式 5 项零 skip/source_stable 复验并本地 integrated rev6。
它在原 SMP 计算/TLB 证明之后、调度器接管之前执行大页映射、拆分、替换、
拒绝合并、恢复、合并、拆分和完整撤映射；临时表归还后再建立长期持有的
2 MiB 视图并永久 seal。四核本轮完成 524 次广播及 1,572 次 AP 应答，
原 512 页租约始终持有；全表池、buddy 元数据、全部页数据和读者上下文的
只读物理转储已独立离线复算。单核、四核正常启动及只省略 AP 失效调用的
真实负控通过；四核正常桌面与 P5 两次持有上下文观察回归通过。
这不扩大为调度后任意用户 CR3 的并发修改，详见 [共享根验收范围](p2-shared-large.md)。

最终 v2 保留 Dong 中的授权、事务与完整失效协议，用三个纯汇编助手执行实际 512 页首末访问、受信池原始表检查和 512 项精确快照比较；快照放在同一持有块的窗口页 509，比较后恢复该页 tag，不增加全局 4 KiB 快照或别名。初版完整 runtime7 装载超出 2 MiB 窗口 7,760 字节，v1 仍超 3,664 字节；v2 最终完整 release runtime7 构建为 2,096,720 字节、余 432 字节，原装载 ABI 不变，实际四核桌面及 P5CTX2 正常控制回归通过。两次失败与中间尺寸预检原始证据保留。

上述 2,096,720B/余 432B 是 P2LIVE1 的历史预算。P2SIZE2 函数节/链接 GC
释放 106,496B 后，P2SMP3 最终完整 release runtime7 为 2,006,608B、余
90,544B，原 2 MiB 装载 ABI 保持，实际 316 个构建输入与主目录 SHA 一致。
新增代码仍需重新核对预算，见 [构建预算](p2-kernel-budget.md)。

活动数据 API 仍只允许 WB/NX，拒绝 USER/EXEC/WC。下面的历史 QEMU 探针挂在
固件根下，不能替代正常消费者验收。共享根大页范围已由 P2SMP3 接入；
通用动态执行和图形 WC 消费者分别由 Claude P2EXEC1/P2WC1 接续候选实现，
后续仍须实际接线、客体测试及独立验收，不能提前记完成。

## 组成

| 模块 | 作用 |
| --- | --- |
| `kernel/mm/huge_page_plan.dg` | 2 MiB PDE 与 512 个 4 KiB PTE 的纯数据转换（PAT 位 bit 12 ↔ bit 7，A/D 规则，失败不变） |
| `kernel/mm/alias_policy.dg` | 同一物理页多别名的 W^X 检查；转换顺序 `REVOKE → FLUSH_LOCAL → (多核时 SHOOTDOWN) → GRANT` |
| `kernel/mm/cache_type_plan.dg` | PAT 校验与索引、MTRR 重叠求解、PAT×MTRR 有效类型、别名类型一致性、迁移顺序 |
| `kernel/mm/paging.dg`（扩展） | 2 MiB 叶子与写合并标志，见下 |
| `kernel/mm/active_paging.dg`（P2LIVE1） | 保持既有 ABI 的 WB/NX 大页事务；整根失效后才回收旧 PT |
| `kernel/boot/large_memory.dg`（P2LIVE1） | 正常私有根/AP 启动前的真实 buddy order9 完整生命周期；成功后恢复原布局 |
| `kernel/memory_mutation.asm`（P2LIVE1） | 正常调用钩子、既有整根失效桥及三个有限纯循环助手；不承担页项授权或修改 |
| `kernel/mm/shared_paging.dg`（P2SMP3） | 固定读者域的 live 事务适配；每次发布前检查 root/online epoch，完成全部读者屏障，seal 后永久只读 |
| `kernel/smp/large_memory.dg` 与 `.asm`（P2SMP3） | AP 在线、调度前的实际大页事务与硬件失效桥；最终长期持有原租约及封存视图 |

### `mm.paging` 的变化

- **2 MiB 叶子**：遍历在 PD 级识别 PS=1，按自己的位规则校验（地址 2 MiB 对齐、bit 13..20 为 0、缓存位只允许 WB/UC/WC、W^X、内核半区不得 USER）。`query` 返回大页内的正确物理地址。
- 新接口：
  - `map_large` / `map_large_live`：映射 2 MiB 叶子。
  - `split_large_live`：用 `huge_page_plan.split` 填好一个新页表，再用一次原子写把它挂上。调用者随后必须整根失效。
  - `merge_large_live`：用 `huge_page_plan.merge` 生成 PDE，原子替换后把页表放进回执隔离。调用者整根失效后才能 `reclaim`；`reclaim` 这时才清零并释放该页表。
- 4 KiB 的 `unmap`/`protect`/`*_live` 碰到大页覆盖的地址，返回 `LargePage`（0x0203_0006），要求先拆分。不可合并返回 `NotMergeable`（0x0203_0007）。
- **写合并**：`WRITE_COMBINING = 16`。4 KiB 页设 PAT 位（bit 7），2 MiB 页设 bit 12，选中 IA32_PAT 第 4 项；调用者先把该项设为 WC，并按迁移顺序操作。WC 与 UC 不能同时设置。
- 原有 `tests/paging_probe.c` 里有三处按旧契约断言"标志 16 非法""WB 页项带 bit 7 是畸形"。这些现在都合法（表示 WC），已改为新契约下仍然非法的"UC 与 WC 同时设置"。

### PAT × MTRR 有效类型

按 Intel SDM Vol. 3A Table 14-7（订单号 325384-093，CR0.CD=NW=0）逐格实现，共 30 格。测试中还单独转写了 Xen `hvm/mtrr.c` 的 `mm_type_tbl` 作交叉核对，两者 30 格完全一致。

SDM 注明，其中几格在旧版里曾是"未定义"，现在所有同时支持 PAT 和 MTRR 的处理器都按表执行：MTRR WC+PAT WT/WP→UC、MTRR WT+PAT WP→WP、MTRR WP+PAT UC-→WC、MTRR WP+PAT WT→WT。Bochs 在 MTRR WT+PAT WP 一格取了较小值（WT），与 SDM 不符；这一格作为坏实现负控保留在测试里。

## 验证

### 宿主（离线契约）

`tests/test_p2_extensions.py`：真实 dongc 以 debug/release 编译，链接成 DLL，经 ctypes 调用。期望值来自独立 Python 模型，所有缓冲区带 guard。9 个真实坏 Dong 均被拒绝。`tests/test_paging.py`（含上述三处契约更新）与 `tests/test_page_cache.py` 通过。

### QEMU 启动验收

`tests/run_p2_extensions_qemu.py`（永久包装 `tests/test_p2_extensions_qemu.py`）构建一个 CPL0 UEFI 程序，在 `q35 / TCG / -cpu max / 2 vCPU / 512 MiB` 下运行，链接真实的 `mm.*` 模块：

1. 建立 `mm.paging` 私有树，开启 EFER.NXE。
2. 映射真实 2 MiB 叶子，把私有树的 PML4 第 384 项挂进固件根，整根失效后读出 512 页中的样本；`query` 正确；4 KiB 操作返回 `LargePage`。固件把页表映射为只读，所以只在写这一项时临时关闭 CR0.WP。
3. 拆分后读出不变。把第 5 页替换为另一物理帧后读到新数据，**证明 CPU 确实在走新页表**；此时合并被拒（`NotMergeable`）且内容不变；换回后再合并。
4. 合并并整根失效后 `reclaim`，页表计数回到拆分前，4 KiB 操作重新返回 `LargePage`。
5. 两个虚拟别名指向同一帧：可写别名写入 `mov eax,42; ret`，按 `alias_policy` 计划依次撤权、失效、授予执行，**每一步之后都重新检查 W^X**，最后真实调用新代码得到 42。
6. 读取 IA32_PAT 与 MTRR：该帧 MTRR 类型 WB，与 PAT WC 合并后的有效类型为 WC。按迁移顺序执行 TLB 失效、WBINVD、把 PAT 第 4 项写为 WC、建立 WC 映射、再次 TLB 失效；核对 PAT 读回、页项类型与读写数据；最后撤销映射并恢复原 PAT。
7. 第二个 CPU（UEFI MP Services 启动一次，常驻在邮箱循环里，TLB 在多次命令之间保持）：
   - 读取一个映射，使其被该 CPU 缓存。
   - BSP 替换物理帧并只做本地失效后，第二个 CPU **仍读到旧帧**（日志 `…8001`），证明在这台模拟机上过期 TLB 是真实存在的。
   - 在第二个 CPU 上执行 INVLPG 后，它读到新帧。
   - 再按 `cpus=2` 的别名计划完成一次"可写→可执行"转换：计划第 3 步必须是 `SHOOTDOWN`，由第二个 CPU 执行，之后两个 CPU 都调用新代码得到 43。
8. 从固件根摘除私有树。

结果：debug 与 release 均退出 33，全部步骤标记齐全（约 4 秒）。4 个坏实现均退出 35：拆分后不挂页表（第 3 步）、转换不先撤权（第 5 步）、遍历器不识别大页（第 2 步）、双 CPU 计划漏掉 SHOOTDOWN（第 8 步）。

### 回归

改动后的 `mm.paging` 重新跑了既有的内核 QEMU 用例：内存/活动页表矩阵 15 项（正常启动、7 类预检拒绝、5 类权限/guard 真实故障、2 项 TLB 变更）全部通过；对象缓存生命周期 3 项全部通过。

2026-10-20 的历史回归曾因本机 mingw 头文件缺少 `__builtin_ia32_sfence` 无法编译 `test_active_paging`，原版亦同样失败。P2LIVE1 本轮新旧 active 原生共 3 项、host gate 9 项，以及 P2 planner/paging 共 6 项实际通过；旧 C probe 无需修改。最终正常私有根 1/4 核、真实漏挂拆分表坏源、完整 release runtime7 四核桌面/P5CTX2 正常控制回归已实测，原始归档独立复算通过；该历史失败不代表本轮仍排除旧 active 回归。

本机工具：QEMU 11.1.0（项目内 `code/.tools/qemu`，带 edk2 固件），LLVM 23.1.3（winget 安装，需设置 `LLD_LINK`/`LD_LLD` 或加入 PATH）。

## 已知限制

- **固件恒等映射**：UEFI 探针运行在固件页表下，固件把所有内存恒等映射为 WB，因此第 6 步的 WC 帧必然还有一个 WB 别名。`check_aliases` 正确地把它报为 `CONFLICT`，探针也断言了这一点。内核自己的私有根里没有这个别名；这一步验证的是机制，不是无冲突配置。
- **TCG 不模拟缓存类型**：QEMU TCG 不会体现 WC 的实际写合并行为。这里验证的是 PAT/页项编码、MTRR 求解、顺序和数据正确性，不是性能。
- **历史探针 CPU 范围**：本节 UEFI 扩展探针只测两个 CPU；P2SMP3 的正常内核证明另含真实单/四核和漏 AP 失效负控，不混用两组证据。
- **正常根大页范围**：P2LIVE1 在 AP 前恢复 4 KiB 树；P2SMP3 在 AP 在线、调度前同步所有读者，最终保留一个封存的大页视图。后者不支持调度后任意多用户 CR3 修改。最终正常 runtime7 余 90,544B；碎片化 order9 OOM 专项另见 [拒绝证明](p2-fragmented-large.md)。
- **生产消费者仍有边界**：图形 WC 和通用动态执行尚未接入活动 API；原静态用户 ELF 装载不能替代通用动态执行验收。
