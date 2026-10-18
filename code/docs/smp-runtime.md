# P6 四核与共享根 TLB 域

2026-10-17：INIT/SIPI、每核 GDT/TSS/IDT、四种私有栈、IPI 应答及共享内核页表失效屏障已在实际四 vCPU 客体复验。每核执行 2,097,152 轮，共 8,388,608 轮，GPR/SSE 检查无误，四段执行时间存在共同交集。AP 保持 ONLINE，不在证明结束后停机。

正式证据：`build/test/p6-smp/qemu/run-07420339c5b0/result.json`。两次启动分别写入和读取真实 FAT32 文件，每次独立核对四个 vCPU 的 CR0/CR3/CR4/EFER、GS、GDT/IDT/TR、24 个 AP 栈保护页、TSS 的 RSP0/IST、实际 IPI 门及物理 mailbox；原 P5 的 111 次物理检查继续通过。

TLB 实验先让各 AP 读取 A，再替换为 B，通过 INVLPG IPI 后进行不自带失效的读取，最后全域失效后回收三张页表。后续 BSP map/protect/unmap 的 wrapper 同样等待全部 AP 应答。失败保持 pending，wrapper 不返回，禁止回收。PCID/PGE 仍关闭，仅一个 BSP 修改者；不是任意多写者页表协议。

实际反例证据：`build/test/p6-smp/no-invalidate/run-563328f8ca43/result.json`。测试版真正省略 AP 的 INVLPG，12 次命中；三个 AP 均从已经暖过的地址读取旧 A，而 expected 为 B。客体报 `0x06030006`，domain 保持 pending=1，回收零张页表，没有进入 P5 或成功出口。前两次宿主断言适配失败的历史结果保留。

AP INIT 会复位 QEMU MTRR 默认类型。启动代码在 CD=1、WBINVD 后复制 BSP 的 variable/fixed MTRR 和 DEF_TYPE，逐 MSR 读回，然后设置 PAT、恢复缓存。这不是忽略差异。低地址 SIPI 页来自原始 UEFI ConventionalMemory，保持保留；其 identity 和临时高别名在应答屏障后撤销。

复跑：`python -m unittest tests.test_smp -v`，`python -m tests.run_smp_qemu`，`python -m tests.run_smp_negative_qemu`。所有客体与内核构建串行、独立目录。后续图形扩容把私有用户页表池从 24 页增至 32 页，因此新 runner 按 32 页核对；上述历史镜像的 24 页证据保持原值。

P6 完整阶段未关闭：每核通用运行队列、负载均衡、并行服务 DAG 尚待实现。四核计算证明不等于 AP 抢占调度。当前 Windows TCG 环境不能验证原 KVM 引导器至 shell ≤0.5 秒门槛；没有替换门槛或将含固件耗时冒充该指标。
