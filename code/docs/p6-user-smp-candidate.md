# P6 用户态多核所有权与退休协议候选

`build/test/p6-user-candidate/manifest.json` 冻结了真实运行队列、用户进程所有权、
入口缓冲区、BKL 等待轮询、退休与每 CPU PCID 缓存协议，以及 raw 硬件辅助操作。
生产树没有接入它，未执行 AP 或 CPL3 多核。它也不把既有四核固定计算或 CPL0
调度候选当作用户态多核验收。

## 已实现

`sched.user_domain` 以 63,040B arena 持有 16 CPU、16 物理进程槽、真实
`sched.multicore.Engine` 及每 CPU 两份 Frame(200B) / xstate(1,024B)。所有元数据
显式循环初始化，没有大 BSS 或整个 Domain 的巨大静态 EMPTY 常量。物理
Process1288 / Frame200 ABI 不变，进程保存帧与 xstate 是外部传入的可信内核地址。

CPU 状态为 IDLE / USER / ENTERING / KERNEL / LOCKED / RETURNING。入口先在 CPU
私有位置捕获 GPR，再 `begin_entry`，切可信内核 root，`complete_entry` 保存私有
xstate。只有完成捕获的 KERNEL/IDLE/LOCKED 状态可以确认失效；ENTERING 与即将
IRET 的 RETURNING 都保留活动引用。入 BKL 后 `drain` 比对 token / incarnation，
只有仍绑定的进程才能收到私有捕获。延迟到达的旧入口不会覆盖同槽新进程。

`admit / release / select / wake` 调用真实 32 优先级、affinity / FIFO / steal 队列。
select 在持锁期间复制进程 Frame / xstate 到 CPU 私有返回区并发布 RETURNING，
unlock 后 `commit_user` 只使用该快照。返回要求 bound root、IF=1、现有硬件捕获
Frame validator 及零 FS/GS。每 CPU 保留独立的 root/incarnation/valid 标签元数据；
另一 CPU 的首次使用、槽复用与全 tag barrier 之后不能继承旧首次使用状态。
release READY 只唤醒其他 IDLE CPU，避免每次 timer/IPI dispatch 又相互发 IPI 的
循环；实际 admit/wake 转换通知所有 eligible CPU。空队列可 park 后进入 raw
STI/HLT，按需计时 adapter 需在后续入口接线中共用。

`retire_begin` 在 BKL 内标记 RETIRING 并发布所有在线 CPU 的新失效序号。持锁者
与 BKL 等待者都能执行 `poll`：先证明自己已经在内核 root 且不在未完成捕获或
RETURNING 状态，再执行本地全 tag flush、清自己的 seen 缓存，最后发布 ACK。
等待 BKL 时 IF=0 仍会轮询该 mailbox，避免持锁 CPU 等待一个无法接收可屏蔽
IPI 的锁等待者。`barrier_finish` 必须收到本序号所有 ACK；`retire_finish` 随后
脱离 RUNNING 所有者并从队列移除。之后调用方才可撤权、destroy 和复用槽位。
同槽 incarnation 必须严格增加。超时、flush、IPI 或切 root 故障永久保持 failed。

raw `user_arch.asm` 提供 tag 切换、全 tag flush、IPI f4、IF0、锁、复制、时钟、
xstate save 和 Frame 校验。PCID 启用同时核对当前 CPU 的 PCID 与 INVPCID 能力，
PGE 必须为零；fallback 始终普通 MOV CR3，不能宣称实际执行了 retained PCID。
这些 privileged 操作只通过了汇编检查，原生测试使用独立 CPU/MMIO 回调模型。

## 证据

`python -m unittest tests.test_user_domain -v`

最终证据 `build/test/p6-user-native/run-c1351b76db34/validation-summary.json`：
debug/release 各 1,295 项主流程断言，加五个独立 fail-stop 场景；12 种实际坏
Dong 源码变体均被拒绝。覆盖旧 capture 延迟、RETURNING 撤权、三轮代际退休、
IF0 BKL 等待者在没有 IPI 交付时确认 mailbox、同 root 页表更新后的新失效序号、
跨 CPU 标签首次使用、最后退出、空闲唤醒及繁忙 CPU 不循环收 IPI。硬件辅助
对象分别汇编为 ELF64 和 COFF64。

裸 release 目标文件（无测试 wrapper）queue+protocol text=40,840B、rodata=808B，
BSS/data=0；其中相对已经存在的 queue 额外 text=18,919B、rodata=80B。raw ASM
text=589B。见候选 `size/sections.json`；不包含尚未实现的入口/资源 builder，
不能据此保证完整内核仍在 2MiB 内。

## 接入前仍须完成的具体工作

1. 准备所有 CPU 的独立、带双 guard 的内核入口栈、7 项 GDT（用户 0x2b/0x33）、
   TSS.RSP0、IDT 以及 EFER.SCE/STAR/LSTAR/FMASK。现有 AP GDT 只有五项，不能直接
   IRET 到 0x33；现有 AP 没有初始化这些 SYSCALL MSR。
2. 原 `context.asm` 的 UserCpu、original root/MSR/GDTR、continuation/root_frame
   必须 per CPU。候选 `user_smp.inc` 定义原 64B UserCpu 前缀之后的 SmpContext
   指针、Domain、logical id 和在线 Context 数组。激活该 GS 前缀时同步更换
   ping/stop/TLB/exception/timer/IPI handler；现有 handler 把 GS 直接当作
   SmpContext，不能只改 SYSCALL 的 GS。NMI/DF 分支也不能盲目解引用用户 GS。
3. 新 SYSCALL/硬件入口只把数据写到 CPU 私有捕获区；保存完整用户 GPR、DF/RF
   和 xstate 后才进行 BKL ACK。中断恢复使用 IRET 与硬件 Frame mask；普通
   SYSCALL 输入仍用严格 mask。恢复 xstate 必须在最后一个 Dong 调用之后。
4. 持 BKL 才可给现有 `services.CURRENT` 赋当前 slot，执行 perform 和所有
   STATE/IPC/capability/device/catalog/memory 操作。perform 返回的 next 只作
   提示；调度必须用实际 RUNNING 所有权和 STATE.waiting 投影，不能把另一个
   CPU 已运行的 Frame 再返回。无 READY 进程是正常 idle，不能误记 syscall
   协议错误。IRQ 状态投递也必须经 BKL。
5. retire 在撤任何共享 GUI/设备别名和 destroy 之前执行上述全核 quiescence /
   detach。memory 的 bind/unbind/invalidate/fullflush 不能继续只调用 BSP 本地
   PCID helper；用户 SMP 激活后要改走持 BKL 的全核 mailbox barrier。bootstrap
   期间尚未激活用户 SMP 的单核 loader 路径单独保留。
6. raw 返回遇到 pending request 时取消 RETURNING，保持 kernel root、poll 后
   重新入锁。若原进程仍在运行队列，按其当前状态 release/select；若已退休，
   丢弃旧 ticket，不能直接使用旧 Frame/root。禁止 barrier 完成前解锁并调度。
7. 实际四核 guest 必须证明普通 CPL3 进程可被 timer 抢占、跨 CPU 恢复、FS/GS
   与 xstate 不串扰；同时执行 IPC wait/reply/cancel、服务重启、GUI 共享撤权、
   固定 VA 暖 PCID 槽复用及退出压力。故意漏 xstate/漏 ACK/旧 ticket 的硬件
   负控须出现真实错误；仅原生模型通过仍不能完成 P6 用户态多核验收。
