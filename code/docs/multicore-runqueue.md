# P6 每核运行队列候选

候选位于 `build/test/p6-candidate/kernel/sched/multicore.dg`，模块名
`sched.multicore`。为避免更改正在验收的 P4/P5 镜像指纹，目前没有迁入正式
`kernel/sched`，也没有装入 AP 的入口或实际用户调度。当前 AP 在线、独立计算和
TLB 广播证据继续有效，这些证据不等于每核用户线程抢占。

候选保存 16 个 CPU、64 个线程、32 级优先级的独立 FIFO 队列、优先级位图和
当前 RUNNING 所有权。整个 Engine 为 12960 字节，应放在长期内核 arena，
不放在中断栈。Thread 为 64 字节、Cpu 为 552 字节。

接口如下，所有调用都需要本地 IRQ 排除，以及同一个调度域锁。多 CPU 不得
只各持本地锁就直接修改该 Engine。输出对象须由调用者拥有，并与 Engine 不重叠。

| 接口 | 行为 |
| --- | --- |
| `initialize(e, onlineMask)` | 初始化空对象，支持低 16 位非连续 CPU 集；拒绝重新初始化，避免旧 token 复活 |
| `admit(e,id,priority,affinity,frame,out)` | 将新线程放入允许 CPU 中负载最小的一核，尾插 FIFO；返回 56 位代际加 8 位槽号的 token |
| `acquire(e,cpu,out)` | 本地最高优先级 FIFO 优先；本地无工作时，从其它 CPU 有界窃取可运行 READY；只在该核空闲时创建 RUNNING 所有权 |
| `release(e,cpu,token,state,frame)` | 调用者已保存完整上下文后，将当前 RUNNING 放回 READY 或 BLOCKED；不执行上下文切换 |
| `wake(e,token)` | BLOCKED 线程重新按 affinity 分配到负载最小核，不允许重复入队 |
| `set_affinity` | READY 可迁到允许 CPU；RUNNING 排除当前 CPU 时返回 Busy，要求架构层先真正停止它 |
| `set_priority` | 重新排列 READY FIFO；RUNNING 只修改元数据，重调度 IPI 由架构层处理 |
| `rebalance(e,source,target,out)` | 负载差至少 2 时移动一个允许迁移的 READY，从源的低优先级尾部选择；返回是否需要目标核唤醒/抢占通知 |
| `remove(e,token)` | 拒绝 RUNNING；移除 READY/BLOCKED，保留其代际计数，旧 token 始终无效 |
| `audit(e)` | 独立核对双向队列、位图、数量、唯一 RUNNING/READY 所有权、affinity 和 token 数据 |

acquire 的窃取最多访问 16×32 个桶和 64 个互不重复的 READY 记录，跳过 pinned
及 affinity 不允许目标 CPU 的线程。零是最高优先级。同优先级 FIFO，yield 后
追加队尾。rebalance 保留源的高优先级工作，从较低优先级尾部迁一个线程。
它不会迁移仍在另一个 CPU 上执行的 RUNNING 上下文。

每个变更前执行只读结构审计与计数溢出预检。非法输入、陈旧 token、Busy、损坏
链表及溢出不会改变 Engine 或输出。成功但没有工作返回 false，输出也不变。
每个实际变更增加 sequence；56 位线程代际和 sequence 均拒绝回绕。

宿主独立 C 模型用时间序号重建期望 FIFO，不读取生产队列来决定答案。
两模式各通过 108770 项检查和 30000 次随机状态变换，包含完整 16 核配置、
64 线程、非连续 CPU 位图、不同优先级、跳过不可迁移高优先级线程、跨核
唤醒、移除后旧 token、损坏环/位图/数量/affinity 和溢出失败保持。
实际忽略窃取 affinity、固定复活旧代际、把 FIFO 头当尾的坏 Dong 实现均被拒绝。
debug/release 同时装配 ELF64/COFF；最大单函数栈 352 字节，正常调用链最大
752 字节，panic 不计入可返回链。测试不执行 CPUID、CR3、xstate 或 IPI。

执行 `python -m unittest tests.test_multicore_sched -v`。最新候选证据：
`build/test/p6-runqueue/run-cab9e73a8509/validation-summary.json`。

实际集成仍需每核独立 syscall/fault 入口、GS/TSS/IST 与受保护内核栈、完整
GPR/xstate 保存、用户根与 PCID 的逐 CPU 活跃历史、跨 CPU TLB 撤权/回收屏障、
抢占禁区和锁顺序、调度/唤醒 IPI、真实四核长期抢占与 pinned/迁移负控。
现有 `user.services` 仍为 BSP 调度，不能通过替换一个选人函数就允许 AP 同时进入
全局 CURRENT/endpoint/memory 逻辑。KVM 的 ≤0.5 秒启动门槛仍须单独实际验收。
