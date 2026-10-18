# init 与通用进程接口

`services/init/main.dg` 是可独立链接的 CPL3 ELF。它使用同一份 `lib.process_abi` 与 `lib.process` 用户库调用内核，按受信配置启动服务、消费真实就绪/退出/异常事件，并在依赖失效或启动超时时请求终止进程。配置和授权由内核确认，init 不能凭名称或 PID 自造设备权限。

本文件先冻结接口和宿主执行证据。完整客体接线、实际启动及资源回收的结论由整合验收补充；宿主 syscall 模型不等于已经运行过 CPL3 客体。

## 公共 libasm 契约

现有 `lib.sys` 和 `services/lib/syscalls.asm` 使用 SysV 整数调用约定。普通 syscall 最多六个 `u64` 参数，`RAX` 返回零或状态码；`RCX/R11` 由 SYSCALL 破坏。64B IPC 消息和128B只读 Boot 保持原有布局。`lib.process_abi` 是无 syscall 链接副作用的数据模块，内核可安全导入；`lib.process` 是用户封装，所有指针指向调用者地址空间。

| syscall | 名称 | 参数 |
| --- | --- | --- |
| 0x80 | CONFIG | manager capability, 配置索引, Config*, 可选 Snapshot*, 0, 0 |
| 0x81 | SPAWN | manager capability, 配置索引, 期望前代 generation, argument, Snapshot*, 0 |
| 0x82 | WAIT | manager capability, 已消费 sequence, Event*, flags, deadline TSC, 0 |
| 0x83 | KILL | manager capability, 不透明 process token, status, 0, 0, 0 |
| 0x84 | READY | 自身 endpoint capability, 自身 generation, 0, 0, 0, 0 |
| 0x85 | EXEC | manager capability, ELF bytes pointer, byte length, argument, Snapshot*, 0 |
| 0x86 | INCARNATION | 自身 endpoint capability, 0, 0, 0, 0, 0；返回当前进程 incarnation |

WAIT flags 为0时非阻塞，无新事件返回 `WouldBlock`；1为阻塞。deadline=0表示无超时，非零是绝对 TSC 截止时间，超时返回 `Timeout`。成功输出需完整验证可写范围后发布；失败不发布部分结构。CONFIG 可同时输出配置与快照，不能先复制配置再发现第二个输出指针无效。EXEC 必须先把 ELF 数据复制进内核稳定缓冲区，再验证、随机布局和装载；它只能创建受限普通程序，不能请求驱动角色或物理地址。

Config 为128B：前8个u64依次是 version/id/dependency mask/restart limit/timeout ticks/flags/image id/name length，后接32B名称和4个必须为零的u64。id 为0至 count-1的连续索引，dependency mask 的第id位引用同表服务，最多16项。flags 为 AUTOSTART=1、RESTART=2、ESSENTIAL=4、ORDINARY=8。名称由1至32个 ASCII 字母、数字、横线或下划线组成，尾部字节必须为零。image id 仅引用内核白名单，不能据此提升权限。

Snapshot 为64B，8个u64：version/configuration/process token/generation/state/status/sequence/argument。启动成功返回 STARTING 快照；存活进程的 generation 和 token 非零。终止后的 CONFIG 快照 process=0，保留 generation 和终止状态。Event同为64B：version/sequence/configuration/generation/process token/state/status/flags。终止事件仍携带该次存活时的 token，方便拒绝跨代事件；flags当前必须为零。状态 STOPPED=0、STARTING=1、READY=2、EXITED=3、FAULTED=4、KILLED=5。WAIT交付 READY 与终止事件，不把 STARTING 当作可用依赖。

服务管理器 Boot 使用 reserved0 管理能力、reserved1 配置数、reserved2 自身 generation、reserved3 TSC Hz。其它角色不据此获得管理权限。init 先调用 READY，再扫描 CONFIG 的实际快照；已经由内核启动的服务按快照接纳，不能据此宣称它们均由 init 启动。扫描时内核不主动让出 CPU，已有状态和 event sequence 来自同一串行上下文。

## 依赖与失败策略

`init.policy` 先验证所有字段、重复名称、越界/自身依赖、自动服务对手动程序的依赖及依赖环，再发布管理状态。Kahn 消除法有界执行，不递归。只有依赖均 READY 才提出 SPAWN。内核还必须独立核对依赖并按角色分发能力，防止绕过 init 直接调用 SPAWN。

一个配置最多初次启动加8次重试，重试配额跨 READY 保留，避免反复短暂就绪形成无限崩溃循环。已死依赖的消费者先被终止，旧世代能力由内核撤回后才能重启。开始运行不代表已就绪；STARTING 超过其绝对截止时间请求 KILL。终止回报只更新相同 generation 和 process token 的当前实例，旧世代或重复事件不能将新实例提前标为就绪。

init 每轮先以非阻塞 WAIT 排空待消费事件，再决定超时/依赖终止，避免尚未处理的退出通知导致错误操作。随后阻塞等待下一事件或最早启动截止时间。关键服务重试耗尽只记录一次诊断并继续处理其它生命周期事件，不把失败依赖伪造为 READY。DMA 驱动不得仅凭普通重试配置自动复用原租约；设备失效必须先由设备管理/内核隔离，安全回收条件由设备模块另行核验。

## 宿主证据

`python -m unittest tests.test_init_lifecycle -v` 在 debug/release 两模式实际执行 Dong 的生产 `service_main`、用户 syscall 封装及策略。独立 C 模型枚举65536张4节点依赖图，核对16节点边界、错误配置不变、就绪推进、依赖死亡级联终止、超时、三次有界重试、陈旧事件与真实快照接纳。launcher 模型实际观察3次 SPAWN、1次超时 KILL及所有事件消费。

两个真实坏副本分别移除依赖失效终止和世代校验，在两模式中都必须被同一独立模型拒绝。测试保存完整输入哈希、汇编、链接/执行命令、退出码及 stdout/stderr；正常与负控结果分开记录。单独 `tools.user_services.build_service` 已成功链接 init 的 debug/release PIE，完整 OS 构建和客体由整合窗口串行运行。
