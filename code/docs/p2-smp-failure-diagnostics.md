# P2 SMP 首次失败诊断

P2SMP27 只增加定位证据。WHPX R8 已到正常桌面，但 AP 的 user_entries/user_timers/switches 均为零，Domain/Bridge 已 failed；这仍是实际失败。旧归档的 BSP 正在 init 启动首个 GUI 的路径上，barrier/completed 不相等。该现象不能直接归因为 timeout，本改动不调整 deadline、PCID、ACK、BKL、Frame、异常恢复或成功条件。

当前时间诊断为 version 2。`sched.user_bridge.FAILURES` 是十六个独立的首错槽，每槽 `Failure` 为 224B；`PROGRESS` 每槽 48B。加上三个永久身份指针，新增声明存储为 4376B，比 version 1 多 768B。它们独立于旧 ABI；Bridge 仍为 64B、Domain/Cpu 仍各为 120B、Header 仍为 256B、Bridge arena 仍要求 1536B。无动态分配、串口热点或大型局部对象。实际链接尺寸和装载余量须由协调器的新完整构建确认。

每个真实当前 CPU 只写自己的索引。调用参数中的 CPU 另存为 `argument_cpu`，不能选择要写的槽。首次错误以 CAS 把 `published` 从 0 变为 2，写完数据后再原子发布为 1。观察者仅接受 `published == 1`；2 是未完成记录。后续错误不覆盖首错，无清零或重新启用接口。缺少 ACTIVE、ACTIVE 身份变化或实际 CPU 超出 0..15 时拒绝记录，原错误返回保持不变。Domain/Cpu 读取仅使用初始化时已验证位于永久 Domain arena 内的指针；身份不再匹配时 `domain_available` 为零。

字段按八字节依次排列：published、version、cpu、argument_cpu、entry、vector、stage、error_code、detail_code、clock、domain_available、domain、sequence、owner、lock、mode、requested、acknowledged、barrier、completed、published_kernel_root、raw_root_available、raw_root、normalized_root_available、normalized_root、wait_started、deadline、acquired。`version` 为 2；末三字段偏移为 200/208/216。Progress 依次为 entry/vector/stage/wait_started/deadline/acquired，末三字段偏移为 24/32/40。生产观察应从当前 ELF 符号和 `dong_layout.json` 获取地址与布局，再归档实际物理字节；不能只采集派生 JSON。version 1 的 200B/24B 历史记录不能按当前 stride 解包。

每个 event/idle 路径仍只计算一次原 absolute deadline，并先执行原 poll。紧接 acquire 前，仅当前 CPU 记录一次现有 `user_bridge_clock()` 到 wait_started，并抄录实际 limit；acquire 成功后再读一次同一时钟到 acquired。没有重算、延长或清除被传入 ud.acquire 的期限。wait_started 可以已大于或等于 deadline，这恰是要观察的事实；acquired=0 表示本次入口未记录成功获锁。checked/poll/commit 等未到 acquire 的错误三字段为零。每个新入口清除旧等待字段，成功嵌套 barrier 恢复完整外层 Progress；首错发布将匹配当前入口的三字段一并冻结。Progress 本身为当前 CPU 的进行中观察，不是原子完整快照，读者仍以 published=1 的 Failure 为首错证据。

`error_code` 是实际传播到原 held 路径的 Dong 错误码。project/service 回调的非零状态原来被转为 Bridge.Held，仍保留该返回语义，同时把回调原值放入 `detail_code`。诊断在原 `held()` 前发布，随后仍执行原有 Bridge/Domain failed、IPI 和 MAX 返回。诊断函数本身不调用 Domain acquire/poll/flush，不写 requested/ACK、队列、Frame 或注册状态。

entry 为 1:event、2:idle、3:return、4:shared barrier。主要 stage 为 1:checked、2:capture、3:deadline、4:poll、5:acquire、6:drain、7:choose、8:project、9:select、10:timer、11:service 前 barrier、12:service、13:service 后 barrier、14:release、15:commit、16:cancel、17:shared barrier、20:unlock、21:park。stage 在进入对应操作前发布；成功的嵌套 shared barrier 恢复外层 Progress，避免把后续 project/service 错误误标为 barrier 入口。字段是在错误点的有限读取，不声称跨 CPU 的整个 Domain 快照具有原子一致性。

没有新增硬件读取 ABI。raw_root_available/raw_root 和 normalized_root_available/normalized_root 均为零；`published_kernel_root` 仅是 Domain.kernel_root 的发布值，不能证明实际 CR3 或 tag。协调器后续必须从同次实际 guest 的 QMP 原始寄存器归档绑定硬件 CR3。clock 使用已有 user_bridge_clock，不能单凭它推断其他 CPU 已执行用户态。

新增宿主门禁 `module:tests.test_user_smp_failure` 在 debug/release 真编译 Dong Bridge/Domain/queue，并链接原有 entry/legacy ASM；特权 entry 路径只汇编，不由宿主执行。硬件输入明确为 synthetic。原十种调用场景及七个坏体保留；时间增量另覆盖进入 acquire 前原期限已经过期（只改变合成时钟，仍核实际原 limit）、idle 成功获锁、真实 begin/complete entry 后 capture 成功获锁，以及新入口清除旧时间字段。共十三种场景；十个私有源码坏体在原七项上增加丢期限、丢成功时间和伪造更新后期限的观察，必须由独立 C 断言拒绝。原有 entry/services/barrier 三项回归继续保留。每次门禁保留 Python/NASM/CC 的绝对路径和前后 SHA、源码前后 SHA、实际命令及对象/EXE 和其它生成文件 SHA；失败也保留回执。

## 历史真实观察与范围

首轮正式宿主作业 `509fef4db16648e3af0557212591fe9d` 的 version 1 failure 门禁为 1 test/0 skip，通过；entry 门禁为 1 test/0 skip，通过。services 门禁随后真实失败（0.641s），整体作业不通过，barrier 门禁未执行。两项局部通过不能替代完整四模块验收；本轮增量尚未执行。

同一实际 WC 构建的 WHPX R9/R10 仍是失败观察，归档位于 `build/test/p2-smp27-review/actual-whpx-r9` 和 `actual-whpx-r10`。R9 首错槽 CPU2、CPU1 为 Timeout(0x06090005)@ACQUIRE，clock 分别 46237029027/46237029107；CPU3 随后为 Held(0x06090004)@UNLOCK，clock 46237083431；CPU0 后为 Timeout@capture ACQUIRE，clock 46237199395。当时 owner=3、lock=1，sequence=completed=requested=ACK=1922、barrier=0。CPU0 token=257 对应 shell；BSP user_entries/switches=3671，三 AP 相应计数仍为零。R9 原始 FAILURES/PROGRESS 已独立解包核对，SHA 分别为 `e073dc4926812d481d0d9d4342963ccac73828ed3b2b29f157e31a495df270b6` 和 `ce83b9e7c31e764b5970dca7c5eee6e6c30db1fe7e2acfaab9a3a4802c490329`。root 已核该轮 519 份原始物理读取的长度与 SHA。

R10 则为 CPU1/2/3 Timeout@ACQUIRE，clock 50781141370/50781141376/50781141470，owner=0、lock=1，sequence=completed=1931、barrier=0；CPU0 尚无首错记录。BSP user_entries/switches=3670，AP 仍为零；root 已核 538 份原始物理读取的长度与 SHA，并记录清理退出成功。两轮 deadline_ticks 均为 3417959746（现有 1s 额度）。R10 的通用池附加审计因空 Process 与保留 Space/root 身份而拒绝，是否为尚未提交的 GUI stage 仍待核实，不能据此兼容接受该状态。

两轮持锁者不同；已观察到的是等待超时及后续 fail-held，不能归责 CPU3，也不能仅凭 endpoint 判断某次持锁多久、期限在哪一步老化，或排除 MMIO/宿主调度停顿。version 1 没有等待起点、实际 limit、成功获锁时钟，因此本轮只补这三项证据，不实现公平锁、不刷新 deadline、不放松 ACK，也不把根因推断写成结论。

实现阶段未运行编译、测试或 VM。正式宿主结果由协调器另行产生；宿主通过也不证明 AP 进入成功。下一轮实际复现必须保留正常失败回执、首次 FAILURES 原始字节、对应 Progress、每 CPU 原始寄存器、Header/Domain/Cpu/Seen 和源码/工具/镜像前后 SHA，并确认 QEMU 清理。
