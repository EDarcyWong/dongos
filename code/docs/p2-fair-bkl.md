# FIFO BKL 准入 sidecar

`sched.user_bkl` 是独立的新组件，本任务尚未接入 Bridge。它只决定哪个 CPU
可以调用原 `user_domain.acquire`，Domain 的 lock 仍为 0/1，owner、Cpu.mode、
Frame、队列和全 tag ACK 均由原 Domain 实现维护。Domain/Cpu 仍各为 120B。
组件不新增硬件 extern，不修改 bootstrap、Bridge、Domain 或汇编。

P2 的实际 R9/R10/R11 观察到 BKL 获取超时，持锁者可不同；FIFO 可以防止后来
请求反复抢先，不能据此证明这些观察的首因，也不能消除长临界区、宿主调度
停顿或保证原绝对期限内一定获锁。实际 AP/PCID 门禁仍需后续接线及 fresh build。

`bind(d)` 在 Header GS 激活前执行，只读取结构，不调用 CPU/root/IF0/clock
或 poll。要求有效且未 failed 的 ready Domain、lock=0、owner=16、barrier=0
及有效的 CPU/engine/online 字段。ready 以 CAS 从 0 到 2，绑定永久 Domain 后
发布 1；第二次绑定相同或其它 Domain 均拒绝，无重置或重新启用接口。

`pointer()` 返回 `*const State` 供以后 guest 原始采集。State 按 64 对齐、共
192B，八字节字段偏移依次为 ready@0、domain@8、next@16、serving@24、owner@32、
wait[16]@40，末尾为 24B 对齐填充。next/serving/owner/wait 均通过原子访问维护。
ready=2 为绑定中，不可当成可用状态。State.owner=16 表示没有已成功获取 Domain
锁的 sidecar owner；头票正在等待 bootstrap 原锁时，它仍可能为 16。

每个 wait 的 0 表示空闲，MAX 表示原子 claim 后尚未发布完整票，其余值为
ticket+1。CAS 分配 next，第一张不能分配的票为 MAX-1；MAX-2 是最后有效票。
达到边界就保留 claim 并报 Overflow，不做加法溢出后恢复，不回卷任何计数器。

`acquire(d,cpu,limit)` 先检查绑定和允许的 IDLE/KERNEL 模式，调用真实 poll
验证当前 CPU、IF0、online、failed，再原子 claim 本 CPU 的 wait，拒绝重复请求。
它在票 CAS 前记录所观察到的前驱，避免前驱在首次等待读取前恰好释放而抹掉
已经发生的排队。未轮到时持续执行真实 `ud.poll`、检查同一个 absolute limit、
再 pause；CAS 冲突重试也如此。owner/sequence/ACK 的变化不会刷新期限。

已经排队的票即使刚到头，也再核原期限，不能利用原 Domain 的空闲 fastpath
接受过期请求。没有观察到排队的头票仍原样调用 `ud.acquire(d,cpu,limit)`；
例如首票等待 bootstrap 原锁时，原 `Domain.Timeout=0x06090005` 保持不变。
仅 FIFO 等待超时使用 `BKL.Timeout=0x06230004`。其它本模块错误为
Invalid=0x06230001、Held=0x06230002、Overflow=0x06230003。

poll 本身不拒绝 foreign CR3：它只在 kernel root 下完成 legacy/pollhook/ACK。
真正获准的头票必须继续调用原 acquire，由它检查 kernel root；不能用 poll
返回成功证明 CR3，也不能把合成宿主 root 当硬件 CR3。原 acquire 的错误码原样
传播，失败不清 wait、不改 owner、不推进 serving。所有错误都需要未来调用者
走原 Bridge held 路径封闭全域；此独立组件不擅自释放、取消票或恢复 failed。

`unlock` 先核本 Domain、owner、wait、serving、实际 Domain lock/owner，以及
LOCKED 或 RETURNING 模式。它先调用原 unlock；原调用失败，全部 sidecar 字段
不变。成功后先清旧 wait、再清 sidecar owner，最后发布 serving。下一位在最后
一步后才可获准，旧 owner 随后没有任何清理可覆盖新 owner。实际 Domain 解锁
仍决定 LOCKED→KERNEL，或保留选中用户 Frame 的 RETURNING 模式。

后续最小生产接线是 Bridge initialize 的纯 bind、两处 acquire 与 choose 的
两处 unlock。bootstrap publish 继续使用原 Domain acquire/unlock，第一张票
等待其真实释放；retire/global_barrier 复用外层已持有 BKL，不二次排票。
该接线未在本任务实施。

## 独立宿主门禁

`module:tests.test_user_bkl` 真编译 sidecar、Domain、队列和 DG probe，在
debug/release 各运行 19 个正常/拒绝场景及 11 个实际坏 DG 源，共 24 次编译、
60 次原生进程。C 仅替代硬件：CPU/root/IF0 为 TLS，try_lock/unlock 和全局
单调 clock 为真实原子操作；Windows 使用 CreateThread，POSIX 使用 pthread。
FIFO、Domain 状态迁移和 poll/ACK 不在 C 中重写。

三线程强制 owner 票 0、等待票 1/2，然后旧 owner 重入取得票 3，独立记录
实际获锁顺序必须为 0/1/2/3，且 C 临界区计数不能同时出现两位 owner。票 0
调用真实 barrier_begin/wait，要求票 1/2 在等待中经实际 poll 写 ACK，三个
CPU 的实际 ACK 和 flush 计数均核对。硬件 unlock 边界还核 serving、owner、
wait 未提前发布，独立检查交接顺序。

其它场景覆盖纯结构绑定、bootstrap 原锁首票、空队列多轮、真实 admit/select
产生的 RETURNING、foreign Domain、错误 CPU/IF0/root、同 CPU 重入与并发 claim、
排队超时、到头时锁已空闲但期限已过、原头票 Domain.Timeout、unlock 失败、
已有 failed、MAX 与最后有效票。测试中的故意错误不代表可以在生产继续运行：
并发重复请求的 caller poison 由夹具明确设置，既有票必须留在原位置。

11 个私有坏 DG 源分别破坏 FIFO、等待 poll、serving 发布顺序、owner 清理
顺序、原期限、原 acquire 错误传播、溢出保护、失败票保留、原 unlock 错误传播、
RETURNING 支持、原子 CPU claim。每处源替换要求唯一；必须真实编译/链接成功，
再由独立 C 预言 rc=1 拒绝，不能以编译失败或进程超时冒充反控通过。
溢出坏体把 guard 错误改为放行 MAX-1，并运行该边界场景；next+1 与 ticket+1
均只到 MAX，不触发算术溢出，必须由 C 核对 Overflow 返回码和原始侧状态而拒绝。
意外 Dong panic 使用独立 `USER_BKL_DONG_PANIC` 前缀及退出码 97；Python 显式
拒收该前缀、panic、信号或进程崩溃，不能把它们归入 rc=1 的 C 预言拒绝。

每次使用独立 `build/test/user-bkl/run-*`，失败也保留 summary、实际 staged
源图/layout、原始 argv/cwd/stdout/stderr、对象/EXE 及全产物 SHA；完整源和
Python/NASM/CC 工具字节在前后核对，最后变化同时否决回执和 unittest。
每个正常场景另外保存真实宿主 State(192B)+Domain(120B)+16 Cpu(1920B) 的
2232B 原始快照并由 Python 独立解包完整 u64，包含完整 MAX 边界值。
成功回执明确 actual_native_threads=true、synthetic TLS/hardware=true、
bridge_integrated=false、actual_ap_cpl3_executed=false、actual_qemu_executed=false。

另一必需回归是 `module:tests.test_user_domain`。实施阶段未运行编译、测试或
VM，不声称宿主门禁通过；正式结果由协调器独立复验记录。

## 首次正式复验与坏体返修

协调器不可变作业 `3be554a207994b029e7a60feffdce896` 的首模块实际执行失败，
1 test、0 skip、17.578 秒，source/tool 稳定。原始回执
`run-899f355da7a8/validation-summary.json` 显示 debug 正常版已真编译、汇编、
链接，19 个正常/拒绝场景全部 rc0；此前七个坏体也各自真编译/链接并由 C
预言 rc1 拒绝，没有 panic。共完成八次编译/汇编/链接与 26 个原生进程。
这是局部事实，不是整项通过；release、其余坏体和后续 Domain 回归尚未执行。

第九次 debug 编译在 `clear-ticket-after-acquire-failure` 坏体失败：err(e)
中的 e 是 u64，直接 `return e` 不能作为 `!void` 错误返回，触发 E0301
`!void success requires return;`。返修只把该坏体改为清票后转发原来的完整
`!void result`，保留其实际 Domain 错误；独立 C 仍必须因失败票被错误清零而
rc1 拒绝。正常组件、DG probe、C 预言和编译器未修改，19/11 数量不变。
返修未编译/执行，仍需新正式全轮复验；旧作业与原始产物保留，不覆盖失败。
