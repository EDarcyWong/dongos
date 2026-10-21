# P2SMP3 — [P2] 共享内核根的大页同步事务与持久持有视图

负责人：codex。状态：待领取。

用户继续P2剩余开发并要求测试、独立验收、本地集成，不建PR/commit/push。本项接续P2SIZE2及P2LIVE1，真实补齐共享内核根/AP在线后的大页转换与持久持有布局，不重复paging机制/UEFI探针。保留原BSP active ABI与算法，通过新shared_paging有界Owner包装复用原map_large/split/merge/replace/unmap，绑定实际smp.tlb.Domain、root与全部已ONLINE且代际一致的读者，逐操作验证根域/IF0/BSP独占写者、Busy重入及512页/帧范围；硬件callback必须本地完整CR3失效并等待域内所有AP硬件ACK，失败直接fail-stop并保持lease/PT隔离，不允许回收后再发现失败。Owner可seal，禁止在调度/用户根接管后未经证明继续编辑。
正常生产：在现有SMP bringup/原报告完成、AP已上线而parallel/user调度未接管时执行；真实startup buddy order9块无HHDM可写重复别名，真实512首末读写，AP实际warm/read子页；拆分、替换5→6、AP看到新值、非连续merge精确拒绝并保持PDE/512PTE/统计/表数，恢复5、合并/全核失效后回收；再完整撤销/安全回收临时表以验证原基线，最后重新建立持久2MiB视图并seal，保留精确原lease而不free。最终正常内核根必须实际保留WB/RW/NX大页，buddy账本准确少512页、PT数及隔离计数准确，后续正常runtime7桌面/P5控制不回归。不是只运行未接线probe，也不增加2MiB BSS。严格范围：共享内核根的BSP单写/AP在线读者域；不凭此关闭用户多地址空间大页、EXEC或WC消费者。
验证：新native Dong+C raw oracle复用既有页表模型，debug/release实际执行shared适配、Domain无效/成员代际/root/全根失效/Busy/完整范围/失败不变/PT隔离与回收，真实漏同步和提前reclaim坏源必须正常构建运行并按目标断言拒绝。实际root协调者冻结正常4CPU和1CPU完整release runtime7构建/运行，另仅省略AP shootdown的真实坏副本应在预热大页→拆分/替换后AP读回精确失败，不以超时/编译失败记有效负控。只读QMP从链接ELF/布局读取实际Report、root/完整pool/buddy/Domain/mailboxes与CPU控制，独立重放归档，保留源码/命令/前后SHA/磁盘/清理和原失败，禁止guest写内存/寄存器。更新旧SMP oracle仅消除旧探针结束mailbox值固定假设，新断言需绑定P2持久视图和实际最终AP观察。受限正式checks无VM，零skip来源稳定；原P2及P5回归/真实guest与源码契约独审后accepted，主目录真实文件逐SHA同消费来源后integrated。文档保持范围和未执行项准确。

## 可修改文件

- `kernel/mm/shared_paging.dg`
- `kernel/mm/active_paging.dg`
- `kernel/smp/large_memory.dg`
- `kernel/smp/large_memory.asm`
- `kernel/smp/runtime.dg`
- `kernel/smp_runtime.asm`
- `tools/build.py`
- `tests/shared_large_probe.dg`
- `tests/shared_large_probe.c`
- `tests/test_shared_large.py`
- `tests/run_p2_shared_large_qemu.py`
- `tests/test_p2_shared_large_guest.py`
- `tests/run_smp_qemu.py`
- `docs/p2-shared-large.md`
- `PLAN.md`
- `codex-works/deliveries/P2SMP3.md`

## 定向验收

- `module:tests.test_shared_large`
- `module:tests.test_p2_shared_large_guest`
- `module:tests.test_smp`

交付：`codex-works/deliveries/P2SMP3.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
