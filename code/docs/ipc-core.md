# 句柄与 IPC 核心

本层是供 CPL3 系统调用桥调用的内核对象策略，代码位于 [handles.dg](../kernel/ipc/handles.dg) 与 [core.dg](../kernel/ipc/core.dg)。所有存储由调用者持有，大小固定，不分配堆内存，不执行硬件访问，不保存用户缓冲指针。根入口的任务/系统调用层负责可信当前任务身份、句柄表选择、copyin/copyout、IRQ 锁、调度阻塞和唤醒；这些接入完成前，宿主策略通过不等于整个 P4 已完成。

所有接口都是内核 unsafe API。输入结构必须按声明对齐并具有完整可访问范围；对象初始值使用相应 `EMPTY_*`，初始化后不能清零以绕过生命周期。输出和输入 payload 必须与正在操作的对象、句柄表及其他输出互不重叠。对象和表的生命周期覆盖所有引用它们的句柄。所有修改在外部 IRQ 关闭的同一临界区完成；NMI 不得访问这些对象。

## 句柄

`handles.Table` 为 1296 字节，包含两个 u64 头字段和 32 个 40 字节 `Entry`；每项是 `{generation,kind,object,rights,live}`。`View` 为 24 字节，包含 `{kind,object,rights}`。句柄编码为 `(generation << 8) | (slot + 1)`；零无效，slot 必须在 1..32。关闭会清除对象/权限并递增代数，旧 token 随即失效。到达 56 位代数上界的槽永久退休，不能回绕复活旧 token。

对象种类为 endpoint=1、notification=2、shared=3。权限位是 READ=1、WRITE=2、TRANSFER=4、WAIT=8、SIGNAL=16、CALL=32、REPLY=64、MAP=128。endpoint 允许读/写/转移/等待/调用/回复；notification 允许转移/等待/通知；shared 允许读/写/转移/映射。`install` 只供可信内核创建能力，用户不能通过指定对象编号自行安装权限。

主要接口如下，错误通过 Dong 的错误联合返回，值与错误码不混用。

| 接口 | 作用 |
| --- | --- |
| `init(table)` | 只初始化一次 |
| `install(table,kind,object,rights)!u64` | 安装非零对象和有效权限，返回 token |
| `lookup(table,token,kind,required,out)` | 验证代数、种类和所需权限，失败保留 out |
| `close(table,token)` | 撤销本表的一项能力 |
| `duplicate(source,target,token,rights)!u64` | 要求源 TRANSFER，仅缩减权限，保留源项 |
| `transfer(source,target,token,rights)!u64` | 安装目标成功后撤销源项，失败保留两表 |

duplicate/transfer 支持同表，目标没有空槽时不会先删除源项。丢弃 TRANSFER 后不能再次转移。关闭一个副本不会撤销其他副本；对象级关闭由对象自身的 live 状态阻止所有旧句柄继续使用。对象编号由可信内核分配，生命周期内不得复用到另一对象。句柄是当前任务表的局部名字，不能据此选择其他任务的表。

句柄错误命名空间为 `0x0401xxxx`：InvalidArgument=1、InvalidHandle=2、Denied=3、NoSpace=4、AlreadyInitialized=5、NotInitialized=6。

## 短消息与同步调用

`Message` 为 80 字节：`peer,length,bytes[64]`。长度允许 0..64；完整正文复制到对象内，未使用尾部清零。`Endpoint` 为 552 字节，含四项 FIFO 和一个独立的同步调用槽。队列满或空返回 WouldBlock，失败不改变对象或输出。endpoint 的 owner 是唯一接收者，消息中保留可信发送 peer。

`endpoint_init(endpoint,identity,owner)` 绑定非零的 32 位对象 identity 和非零 owner。初始化只能发生一次，关闭后不能重新初始化。四项 FIFO 的 `send` 与 `receive` 是复制式短消息接口，异步排队与同步调用槽互不覆盖。

同步调用严格执行以下状态：

`IDLE → call → PENDING → accept → ACCEPTED → reply → REPLIED → take_reply → IDLE`

`call` 拒绝 owner 对自己调用，返回 `(endpoint.identity << 32) | sequence`。sequence 是单调的 32 位计数，到上界后拒绝新调用。`accept` 只允许 owner，返回请求与回复 token。`reply` 同时验证 owner、ACCEPTED 状态和精确 token；不能在 accept 前回复，也不能重复回复。`take_reply` 只允许原 caller，核对 token 并复制回复后释放调用槽。尚未回复时保留输出并返回 WouldBlock。

`cancel(endpoint,caller,token)` 可撤销尚未取走的调用，清除请求、回复和有效 token；旧服务端 token 随即失效。`detach(endpoint,peer)` 删除该 peer 的 FIFO 项并取消它发起的调用；owner 退出会关闭整个 endpoint、清空所有队列并撤销调用。桥接层必须在任务销毁路径调用 detach，并唤醒受影响的线程，使其观察 Closed 或取消结果，不能留下永久等待者。

core 的 WouldBlock 是调度决策输入。系统调用桥需要把调用线程挂到相应等待队列；收到消息、回复、通知或 peer 退出时，在同一 IRQ 临界区修改对象并唤醒。core 本身不切换栈，因此调用者仍可为非阻塞系统调用直接返回 WouldBlock。

## 通知与共享对象

`Notification` 为 24 字节 `{initialized,live,bits}`。`signal` 对非零 bits 执行 OR，重复位合并；`take_bits(mask,out)` 返回并仅清除实际匹配位，其余位保留，没有匹配则保留 out 并返回 WouldBlock。`notification_close` 撤销对象并清除位。系统调用桥必须先检查 notification 句柄的 SIGNAL 或 WAIT 权限。

`MemoryObject` 为 48 字节 `{initialized,live,identity,base,size,rights}`。构造时拒绝零大小、算术溢出、非 canonical 地址或跨越 canonical 空洞的范围，底层权限只允许 READ/WRITE。它描述已经由内核管理的 backing，不能自行创建映射或借此访问任意用户地址。

`shared_view(table,handle,memory,offset,length,rights,out)` 先核对 shared 种类、所需读写权限和 MAP，再核对对象身份、对象 live 与底层权限。长度必须非零，使用减法检查 `length <= size - offset`；返回 24 字节 `{address,length,rights}`，不访问正文。句柄权限和 backing 权限均不能提升。`memory_close` 使旧句柄访问该对象返回 Closed；物理释放和 TLB 生命周期由内存所有者处理。

IPC 错误命名空间为 `0x0402xxxx`：InvalidArgument=1、Closed=2、WouldBlock=3、Denied=4、InvalidToken=5、AlreadyInitialized=6、Exhausted=7。来自句柄查验的 `0x0401xxxx` 错误原样传播。

## 宿主证据与接入边界

[test_ipc.py](../tests/test_ipc.py) 在 Dong debug/release、ELF/COFF 下编译，使用独立 C 状态和字节 oracle。每种模式验证 2048 轮句柄生命周期与完整逐槽记账、双表失败快照、权限缩减和代数退休；再检查 FIFO、64 字节上界与零尾、同步请求/回复/取消/peer 退出、通知位及共享范围。对象、表、输出和正文有独立守卫或完整快照。隔离副本在短消息尾部实际写入坏字节，必须构建成功并在 native 执行中被拒绝。

当前定向执行为三项通过、零 skip，正常每模式 104850 条独立检查；两模式坏尾部实现均实际拒绝。证据保存在 `build/test/p4-ipc/host/run-f3b2c924ef8e/`。这些结果验证对象核心；真实 CPL3 调用、copyin/out、调度唤醒和用户服务需要主线另外验收。推荐 syscall 编号预留为 handle `0x10..0x12`、endpoint `0x20..0x25`、notification `0x30..0x31`、shared view `0x40`，具体用户 ABI 以主线桥接实现为准。
