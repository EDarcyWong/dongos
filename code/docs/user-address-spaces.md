# 用户地址空间、PCID 与回收

地址空间分配由 `kernel/user/memory.dg`、`kernel/user/entropy.dg` 提供；
`kernel/user/context.asm` 保留单 BSP 入口。调度后的用户多核入口另由
`kernel/sched/user_entry.asm`、`user_arch.asm`、`user_domain.dg` 和
`user_bridge.dg` 共同管理。正常 runtime7 策略在已验证的 3–16 CPU 拓扑上
接管用户调度；1–2 CPU 明确选择 BSP 用户运行。无效或未完成的拓扑拒绝接管。
这些代码路径的存在不替代实际 AP、CPL3、PCIDE/INVPCID 的客体执行证据。

`memory.Process` 保持 1288 字节、`memory.Frame` 保持 24 字节；200 字节的
`abi.Frame` 中 CR3 始终保存裸根 PA。最多 16 个进程。静态表池数量取自显式构建
输入 `build.storage_profile.STATIC_USER_POOLS`：构建器在 runtime5–7 使用 2 个，
其余使用 3 个，每池 32 页；其它槽从服务 arena 保留私有表池。普通槽仍为 32 页，
桌面 `enable_arena` 将 compositor 槽 3 扩为 128 页。表池长期持有并跨重启复用，
旧 PCID 的缓存翻译不能随物理表池或槽位一起继承。

`memory.load_random(id,image)` 取得两个独立硬件 DRNG 样本。CPUID 门控
RDSEED，最多尝试 32 次；不支持或耗尽后，再独立门控 RDRAND，最多尝试 10 次。
失败返回 `0x04080001`，不读 TSC 作为替代。PIE 加载基址有 12 个 64 KiB 粒度位，
范围 `0x10000000..0x1fff0000`；栈顶有 18 个 4 KiB 粒度位，范围
`0x7fbff01000..0x7ffff00000`，栈保持 16 KiB 和双保护页。
静态 ET_EXEC 保留其链接地址、bias 为零，仍要求硬件熵并随机化栈。
ELF 全段、重定位、W^X 和栈重叠验证继续执行。虚拟机 DRNG 的宿主可信度和
真实物理熵质量不是该代码能够证明的性质。

单 BSP 的 `user_run` 要求初始 PCIDE=PGE=0。只有 CPUID 同时提供 PCID 与 INVPCID 时，
才在该次用户运行内启用 CR4.PCIDE。每槽拥有 tag `id+1`，tag 0 留给可信内核根。
旁置表记录根、单调代际和是否已经装入。首次装入及新代际的 MOV CR3 操作数
bit 63 为 0；只有已绑定的同代根才设置 no-flush。未知根总是 tag 0 并刷新。
`user_pcid_invalidate_root` 使用 INVPCID type 1；共享监督别名变更和回收使用
`user_pcid_flush_all` 的 type 2。缺任何一项能力时保留原始 MOV CR3 刷新路径。
退出用户运行后恢复原 CR3/CR4，并清掉各槽的首次装入记录。

用户多核模式在每个 CPU 激活入口时独立核对 PCID 与 INVPCID 能力，并保持
PGE=0。`user_domain` 的每 CPU `seen` 记录 root/incarnation/valid；只有该 CPU
已见同槽同根同 incarnation 时，返回才允许 no-flush。首次使用、槽复用和全 tag
屏障后的首次返回均刷新。CPU 先切回可信内核根，完成私有 GPR/xstate 捕获，再
进行本地全 tag flush、清本 CPU 的 seen，最后发布 ACK。BKL 等待者在 IF=0 时
仍轮询失效请求。ENTERING/RETURNING 保持活动引用；RETURNING 看到待确认请求
必须取消返回并先轮询，不能直接装入旧快照。软件全局 `user_pcid_enabled` 只属于
旧 BSP 入口，不能代替当前 CPU 的 CR4 或每 CPU 状态。

`kernel/user/shared_barrier.asm` 的公开结果为 1 成功、0 失败。runtime7 先调用
`dong_user_smp_barrier`：0 表示活动 domain 已完成全核屏障，直接成功；仅 1
表示尚未激活，允许旧路径；其它值均失败，不能改走旧 BSP 失效。活动 domain 的
错误由 `user_bridge` 永久保持为 held。旧路径先执行本地失效；runtime6–7 随后
必须调用 `smp_invalidate_all(0,1)` 完成全翻译广播，runtime4 仅有本地路径。
本地或广播返回非零均拒绝成功。本地硬件实现读取实际 CR4：PGE=1 拒绝，
PCIDE=0 重新装入 CR3，PCIDE=1 使用 INVPCID type 2；纯
`user_shared_flush_mode(cr4)` 分别返回 2、0、1，不读取旧 BSP 软件 flag。

生命周期和内存写入仍必须由内核 BSP 独占，IF=0，先撤掉调度/IPC/能力引用。
多核模式另持 BKL，经 `user_bridge` 在有映射/能力/生命周期副作用的服务调用前后
等待全核屏障，退休前完成 `retire_begin`/全 ACK/`retire_finish`，再销毁根。
已知只读服务可由可信 policy 跳过屏障；未知调用保持完整屏障。单 BSP 入口用
`user_enter_kernel()` 切回可信内核根；新入口在进入服务前已经完成此切换。
`memory.destroy(id)` 拒绝当前活动根和持有 DMA 的进程。顺序为：

1. 取消 ready、原子撤销用户 PML4[0]，完成全 tag 失效。
2. 注销旧根/tag 绑定，保留其代际计数；注销失败时保持所有物理页。
3. 从被撤根仍保留的私有 USER 表项标记 owned RAM 候选，仅对这些候选查询其它存活根。
   早先所有者已退休、最后共享引用在本根的页也会成为候选，不按 creator 判断。
   仍有共享引用、DMA pin 或未在本根出现的其它 held 页继续保留。
4. 只有不存在 USER 引用时，才恢复代码页的监督 RW 别名，并完成监督别名失效。
5. 将无引用页放入本内存模块的回用池；下一次 fresh 先零化整页再映射。
6. 清理私有用户表、Space 和 Process。上半部共享内核表本体不销毁。

回用池继续独占这些页，不把它们退回单调 arena 或 buddy，也不释放 DMA 租约。
因此后续 arena 分配不会重新发放同一 PA。驱动故障前必须另行证明停止 DMA，
本接口会明确拒绝直接销毁已 pin 的驱动进程。表池和监督 alias 本身为长期保留资源。
装载事务允许恢复正常的资源/映射失败；
无法证明失效、alias 归属或权限恢复成功时仍是 fail-stop/持有。

运行时装载使用 `stage_random(id,image)`，也可用显式布局的
`stage(id,image,bias,stack)`。成功后候选根可供内核安装渠道、只读 Boot 页和
能力，但必须在完整构造及 `stage_commit(id)` 完成前保持不可调度。
旧 `load` / `load_random` 是自动 stage + commit 的兼容包装。单 BSP 同时只
允许一个事务；其间禁止销毁另一根。

事务用 u16 Frame 索引记录所有新分配和复用 RAM。桌面日志分配在 arena 元数据
末尾，最大 16384 项、32 KiB；有界静态配置为 512 项、1024B 日志。
新 Frame 在构建监督 alias 之前登记，因此 USER 叶冲突、稀疏页表容量耗尽、
以及尚未挂入任何 USER 根的 orphan 都不会漏出清理范围。
`stage_abort(id)` 先撤销候选 USER 分支、完成全 tag 屏障并注销已绑定 PCID。
它先核对整个日志中可回收页的监督 alias PA/缓存/权限，并保留其它存活根仍引用的页
与 DMA pin；再恢复代码监督写权限，最后零化并发布回用页。代际不回滚。
只有全部 alias 核对及权限恢复成功后才发布回用页，监督 alias 缺失、PA 不符或
unbind 失败会设置永久 `STAGE_FAILED`，保持候选资源，要求调用者停止用户运行。

`memory.owned_alias(id,virtual,write)` 供内核 BSP 借用已有 RAM 页。它先验证完整
单字节用户范围/权限，再查询映射并核对 owned Frame，返回监督 alias 加页内偏移。
写借用同时要求 USER 页项可写和 Frame 的监督别名可写。MMIO 和外部只读资源缺少
owned Frame，均返回 NotOwned，不会凭空制造 WB 或可写别名。缓存指针必须在进程
退休、映射替换或降权前撤回；借用期间不允许页表/进程生命周期并发变化。

`memory.share_at(source,target,sourceVA,targetVA,write)` 将一页已有 owned data
映射到另一根的独立虚拟地址。源和目标均必须覆盖完整对齐用户页；源必须 USER、
WB、NX，写共享还要求源 USER 页项和 owned Frame 都可写。EXEC、UC/MMIO、
外部资源和未持有 PA 均不能借此生成共享别名。目标已有映射时返回 AlreadyMapped，
不替换它；`map_live` 先完成缺页表/容量/冲突预检再原子发布，随后对目标 VA 和
目标 PCID 失效。原 `share` 是源/目标 VA 相同的包装。

实际生命周期 runner 采用固定 `0x44000000` 的暖翻译复用探针：同一进程槽第一代
映射 FS 长期持有的 A 页，下一代映射另一个 B 页，A 页继续保留旧参数。
waiter 真实 `volatile_load` 的 `PROBE_VALUE` 必须读到新参数；runner 同时读取
两代相同根 PA、不同目标 PA、旧页保留的旧参数和用户程序导出的实际加载值。
此结构用于检验实际 tag/根复用失效，不能由仅改变 ASLR 地址或回写同一物理页替代。
`--require-pcid` 另要求实际 BSP CR4.PCIDE、CR3 tag/根绑定及 no-flush 切换记录；
缺 PCID 的 TCG 只验严格 MOV CR3 fallback，不算 PCID 硬件分支验收。

故障转移桥 `user_resume_frame(Frame*)` 要求 GS 已切回内核，且调用者给出合法、
内核拥有的下一帧。它弃用异常 IST 栈，换回受保护的正常内核栈，验证/复制帧、
选择 CR3 后通过 IRETQ 恢复。它不会返回故障者原异常帧。异常归属、下一进程选择、
IPC 清理和能力撤回由服务管理集成负责。

宿主测试：`python -m unittest tests.test_user_context tests.test_user_address_spaces tests.test_user_reclaim tests.test_user_stage -v`。
覆盖地址策略、16 槽/10,000 代 PCID 操作数、DRNG 能力/CF/重试矩阵，以及
debug/release 的回收、owned alias 和双地址共享。
6,200 Frame 的普通退休 fixture 直接执行生产代码，仅对两个真正候选调用 referenced，
其余无关 held 页和 DMA pin 保持。测试只量化该扫描次数，不把它声明为客体耗时。
保留上一代 first-use 的实际坏汇编、错误 RDRAND 次数的实际坏汇编、忽略共享 USER
引用的实际坏 Dong 实现均被独立 oracle 拒绝。回收测试通过私有状态 fixture
直接执行生产 destroy/fresh/referenced 和 paging.protect；硬件失效桥以有序回调模拟，
所有未调用硬件桥使用 UD2，误走硬件路径立即失败。真实客体还需要验证随机布局、
暖 TLB tag 重用、故障隔离与程序重复创建/销毁。

事务原生 oracle 直接执行正式 ELF 验证、分页、load/stage/abort：合法 16 段稀疏
ELF 耗尽 32 页用户表池，连续十次重试保持 Frame 数量和物理 reserve 数不变；
随后普通 PIE 和静态 ET_EXEC 均可装载。还验证 late 叶冲突 orphan、只读 alias
恢复、随机静态栈、共享 survivor、DMA pin、unbind 拒绝及真实监督 alias 冲突。
忽略新 orphan 日志、忽略共享引用和跳过零化的实际坏 Dong 实现均由独立 C 检查拒绝。
这些是宿主内存和硬件桥模型，实际客体的异常、PCID 和 IRQ 仍需单独验收。

共享失效宿主门禁：
`python -m unittest tests.test_user_shared_flush tests.test_user_domain tests.test_user_smp_barrier -v`。
`test_user_shared_flush` 直接组装生产 `shared_barrier.asm` 的 runtime4/6/7
ELF64 与 COFF64 对象；执行时仅在私有副本中将 `user_shared_local_flush` 硬件
函数体替换为显式回调，生产 orchestration 和纯 selector 保持逐字。独立 C oracle
检查三态结果、active 不回退、inactive 才回退、local 先于 AP、失败不发布成功、
广播参数、SysV 调用栈/保存寄存器、PCIDE/PGE 组合和与实际 CR4 相反的旧 BSP flag。
三个真实坏 ASM 分别漏广播、将活动错误改为回退、接受 PGE，必须成功构建并正常
运行，再分别被 callback-order、result、selector 断言精确拒绝。缺工具、编译失败、
崩溃或超时均是门禁失败，不能充当成功负控，也不跳过。

每次执行在 `build/test/p2-user-shared-flush/run-*` 保存命令、原始 stdout/stderr、
对象及可执行文件 SHA、输入前后 SHA、失败 receipt 和 `validation-summary.json`。
这里执行的是实际 ASM 控制流和软件 selector；CR4 输入、MOV CR3、INVPCID 及 AP
执行边界由宿主回调代替。生产硬件函数体仅检查能否组装，不能据此声称实际读取了
CR4、执行了 INVPCID，或验证了 AP 暖 TLB。`test_user_domain` 和
`test_user_smp_barrier` 另执行真实 Dong 协议及桥，硬件失效仍是回调模型。

P2 的固定共享根 owner 仍有独立边界：`mm.shared_paging`、EXEC alias owner 和
WC owner 只在调度接管前、同一内核根、固定在线读者、PCIDE=PGE=0 下变更，并在
改变拓扑/CR3 策略前 seal；已 seal 的 owner 不能在用户多根调度后继续变更。
用户共享对象的全核屏障不扩大这些 owner 的准入范围。更广泛的调度后多 CR3
映射变更、真实 AP PCID/INVPCID 和暖翻译失效必须有相应消费者与客体证据；本宿主
门禁没有证明这些硬件效果，也没有启用 GLOBAL/PGE 页策略。

依据：[Intel SDM 系统编程卷](https://www.intel.com/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-system-programming-manual-325384.pdf)、
[Intel SDM 指令卷](https://cdrdv2-public.intel.com/671110/325383-sdm-vol-2abcd.pdf)、
[Intel DRNG 软件实现指南](https://www.intel.com/content/www/us/en/developer/articles/guide/intel-digital-random-number-generator-drng-software-implementation-guide.html)。
