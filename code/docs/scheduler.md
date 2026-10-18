# BSP 抢占线程与上下文

当前实现由 [调度策略](../kernel/sched/core.dg)、[运行桥](../kernel/sched/runtime.dg)、[可恢复汇编入口](../kernel/sched/context.asm)、[IRQ 锁与等待桥](../kernel/sched/sync.dg) 和 [布局常量](../include/sched.inc) 组成。它服务于单 BSP、同一内核 CR3 的线程；用户线程、每线程 FS/GS 基址和跨 CPU 迁移由后续 P4/P6 接口接入。

`core.Engine` 为 448 字节，最多八个线程；每个 `Thread` 为 48 字节，含状态、优先级、时钟记账、切换记账、保存帧和等待链。优先级零最高，等优先级按槽位循环，量子决定轮转。所有策略修改都要求本 CPU 中断关闭。嵌套禁止抢占期间继续记时并保留 pending；允许抢占后由下一次真实时钟中断执行请求。

`WaitQueue` 为 24 字节，维护 FIFO 头、尾和代数。调用者在同一 IRQ 关闭区检查条件和代数，再入队阻塞。`wake_one` 总会增加代数，空队列通知也有效；过期代数拒绝入睡。链条循环、越界或非阻塞成员会在修改前拒绝。`sched.sync.wait` 在入队后通过相邻 `STI;HLT` 等待真实中断，恢复后返回 IF=0；调用者随后恢复自己的 IRQ token。等待时不能持有自旋锁。

`sched_lock_irqsave` 使用原子 compare-exchange 获锁，在获取前关闭 IRQ；释放以普通对齐 32 位 store 完成，再按原 token 恢复 IF。token 必须来自本 CPU、相同嵌套层。BSP IRQ 不得获取自己可能已持有的锁。原标准库自旋锁的契约保持不变，内核路径需要使用这里的 IRQ 包装。

## 可恢复入口

根入口安装 vector `0x40`、DPL0 中断门，IST 必须为零。硬件帧加所有整数寄存器和 CR2 后，与现有 `ExceptionContext` 的 184 字节布局相同。共享 IST 栈不能承载被切出的可恢复线程帧，因此现有 DF/NMI/致命异常入口继续使用自己的 IST。

入口保存整数寄存器与当前扩展状态，清 DF 和运行时 AC 后调用 `dong_sched_tick(engine, frame)`。策略返回槽位；入口检查所属栈范围、内核文本 RIP、CS/SS 和 RFLAGS，调用一次 `platform_timer_rearm`，确认其成功，再调用一次 `apic_eoi`。之后恢复选中线程的扩展状态、CR2、全部整数寄存器，以 `IRETQ` 返回。此路径不分配内存、不写串口、不调用活动映射事务。

64 位中断无条件保存 SS:RSP，64 位 `IRETQ` 也无条件恢复它们；即使没有 CPL 变化，不能省略这两个槽。参见 [Intel SDM Volume 3A，64 位中断栈与 IRET](https://cdrdv2-public.intel.com/812386/253668-sdm-vol-3a.pdf)。

## 扩展状态与内存

`sched_xstate_init()->u64` 必须在第一份 P2 MMU 控制快照前执行，且 IF/DF/AC=0。成功返回 1。FXSR/SSE/SSE2 是基线；清 CR0.EM/TS，设置 MP/NE、CR4.OSFXSR/OSXMMEXCPT。无 XSAVE 时使用 512 字节 FXSAVE64/FXRSTOR64；存在 XSAVE 时先验证 CPUID leaf D 支持 x87/SSE，设置 OSXSAVE、XCR0=3，并真实读回。只启用 x87/SSE，拒绝启用区尺寸超出 1024 字节的结果。后续活动映射对象绑定的是同一份 CR4，运行期间不再改变这些控制位。

每槽扩展区为 1024 字节、64 字节对齐；XSAVE 标准头初始清零，初始化 x87、MXCSR 和全部 XMM 后复制独立初始状态。选择 eager save/restore，不使用 CR0.TS 懒保存。依据 [Intel SDM Volume 3A，扩展状态上下文切换](https://cdrdv2-public.intel.com/812386/253668-sdm-vol-3a.pdf) 与 [Intel XSAVE/XRSTOR 指令契约](https://cdrdv2-public.intel.com/843855/334569-sdm-vol-2d-dec-24.pdf)。

两个工作线程各占 16 KiB BSS 栈。`sched_guard_ranges` 导出两对 `{low_guard, high_guard}`，`sched_guard_count` 是值为 2 的 qword；`sched_stack_ranges` 导出两对正文 `{bottom,top}`。根入口验证 BSS/页对齐，在 P2 自检后逐页取消四个保护页映射并完成全 CR3 失效，再开启 IRQ。仅有 guard 符号不能形成硬件保护。

Dong 编译器明确不使用 red zone，普通 Dong 代码不使用 SIMD。异步 IRQ 的 C/Dong 调用栈从当前线程自己的帧下方分配。致命异常仍使用原可信栈审计；未来一般线程回溯需要将线程栈绑定到可信元数据，不能信任用户 RBP。

## 最小真实证明与验证界限

`sched_start()->u64` 是一次性的 BSP 证明入口，要求平台已安装中断门、取消 guard 映射并装载定时器。首次真实中断保存并阻塞 bootstrap；两个工作线程持续检查全部整数种子、16 个完整 XMM、x87 控制/ST0 与 MXCSR，各自递增计数，不调用 yield、软件 INT 或 HLT。量子为 2；第 129 次时钟中断唤醒 bootstrap，其余两个线程各记 64 tick，共 65 次上下文切换。函数在原调用栈、IF=0 返回；root 立即停表。

`sched_report` 为 30 个 u64、240 字节，字段顺序见 `SchedReport`。`steps=7` 仅在两个计数非零且错误计数均为零时发布；入口检测失败会以 `steps=0xbad` 终止。测试应同时独立核对真实 timer/EOI 计数、CPUID 与控制读回、ELF 帧/栈/guard 所属及实际页表权限，不能仅依据 PASS 文本或等待超时。

[宿主测试](../tests/test_sched.py) 对 debug/release、ELF/COFF 验证布局和完整汇编，用独立 C 模型逐字段比对 4096 次策略推进，检查等待/唤醒与失败快照，并在真实宿主硬件上交替执行生产 FXSAVE 和可用时的 XSAVE 帮助函数。遗漏 FX 恢复的隔离副本必须构建成功后被实际状态检查拒绝。客体执行由 root 串行管理；最终客体数量和结果以本阶段验证汇总为准。
