# P2LIVE1 — [P2] 正常私有根上的活动大页事务与启动生命周期

负责人：codex。状态：待领取。

所属阶段：P2 CPU与内存扩展。用户明确授权Codex继续开发、测试、独立验收和真实本地集成，不建PR、不提交/推送；接续主线既有mm.paging/huge_page_plan大页机制，不恢复归档pool:P2HUGE1等旧任务，不重复组件实现。本项只闭环正常内核私有根的BSP/AP启动前活动WB/NX大页事务；不以本项宣称P2全部扩展、动态EXEC/WC消费者、多核大页/PCID已完成。

生产：复用paging.map_large_live/split_large_live/merge_large_live，为active_paging增加有完整Context窗口/帧范围/真实控制快照/计数溢出/Busy重入保护的map_large、split_large、merge_large；不改变既有Context/Stats ABI，不放开USER/EXEC/WC。大页整个512页都必须位于owned范围，拒绝错对齐/越界且失败不变；split必须完整同根失效后返回，merge隔离旧PT直到full-root flush完成才reclaim；不能把INVLPG单页当整个大页转换协议。保留既有4KiB与page_cache契约。

正常启动：新boot.large_memory从真实startup buddy持有order9块，窗口独立2MiB，运行在已经激活的正常私有根、保护位开启、IF0且AP尚未启动；真实硬件controls每步重读。不增加2MiB BSS或固件恒等别名。真实写读512页、split后替换子页证明CPU走新表、非均匀merge拒绝且失败不变、恢复后merge/失效/PT回收，再安全移除全部映射/完整根失效、最后才归还精确原order9块。最终allocator free_pages、paging used_tables、全树allowlist恢复基线。异常保持资源持有并明确返回错误，不能失败后提前free。启动钩子在既有memory_mutation_probe验证完成后实际调用，不是只加独立未调用probe；各runtime正常路径都执行。静态REPORT记录真实root/lease/phase/readback/counts，独立guest runner用只读QMP pmemsave读取实际链接物理字节，布局/ELF/源码/构建/命令/串口/清理/前后SHA留证，不写guest内存寄存器。

测试：新原生Dong+C独立raw页表/回调模型，debug/release及真实坏源（漏fullflush、merge提前reclaim、范围绕过）确定拒绝，成功回调中重入Busy、PT隔离未复用、AD/错误路径覆盖；旧test_active_paging和paging/P2planner回归，必要时仅修旧C probe缺失sfence builtin的Windows兼容边界，保持测试语义。实际QEMU由root协调者在冻结隔离副本运行（用户已授权），正常私有根至少debug/release或等价两构建，真实坏源guest负控确定拒绝；既有UEFI extension测试不能代替本项normalroot实测。host checks受限执行、不运行VM；真实guest证据独立审查后才能验收。七文件P5CTX2及其它既有dirty变更保留。

交付：准确边界、未执行项/原始失败保留，独立源码/契约/测试与真实guest审查通过、正式checks零skip来源稳定后accepted；实际主目录文件逐SHA核对真实运行来源后integrated。

## 可修改文件

- `kernel/mm/active_paging.dg`
- `kernel/boot/large_memory.dg`
- `kernel/memory_probe.dg`
- `kernel/memory_mutation.asm`
- `tests/active_large_probe.dg`
- `tests/active_large_probe.c`
- `tests/test_active_large.py`
- `tests/active_paging_probe.c`
- `tests/run_p2_active_large_qemu.py`
- `tests/test_p2_active_large_qemu.py`
- `docs/p2-active-large.md`
- `docs/p2-extensions.md`
- `PLAN.md`
- `codex-works/deliveries/P2LIVE1.md`

## 定向验收

- `module:tests.test_active_large`
- `module:tests.test_active_paging`
- `module:tests.test_p2_active_large_qemu`

交付：`codex-works/deliveries/P2LIVE1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
