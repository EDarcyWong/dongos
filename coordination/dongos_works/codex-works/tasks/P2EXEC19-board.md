# P2EXEC19 — P2调度后多根EXEC事务owner与精确硬件reader组件

负责人：codex。状态：待领取。

用户先P2后P5，平行完成C核心组件；正常service/PF入口接线与受控VM另随B完成后统一声明并验收，不将本组件host通过当整体完成。本任务只新增文件，不碰P2LARGE16当前独占的memory/services/domain/build。新runtime_exec依赖paging/runtime_roots/user_domain/buddy，实现可信CPU0/IF0/kernel tag0/BKL/healthy domain/PGE0闭合事务，允许逐CPU PCIDE0/1只走全tag协议。Config完整caller roots+cookie身份recheck、held order0真实buddy审计、旧sealed EXEC锚不变；固定新alias=0xffffa90000002000与3000，同旧A/B parent，拒新顶层分支、隐藏HHDM/USER/large/任何第三方alias和非WB。所有Scratch/Retired/perCPU tickets caller arena，失败poison/domain failed保留frame/receipt，4KiB帧和2MiB装载预算不变。
真实page map/write CODE42→撤所有写(RO/NX)→全CPU alltag ACK+逐CPU序列化→只授唯一EXEC(所有物理alias无write)→发布；allCPU真实执行返回42，撤所有EXEC→全tag/序列化→授RW并写CODE43→再次撤写/ACK/EXEC发布→allCPU43。最后全部撤权/unmap/全ACK后reclaim；是否释放frame必须新完整forest零alias证据与线性lease规则，否则保持held不冒称回收。每个授权/变更前后重check完整根身份与alias闭包，输出精确phase/seq/ack/actual root/CPU/cr0/cr4/值，不以flush计数冒硬件结果。
新runtime_exec_reader.asm提供真实读/调用/受控写attempt和序列化，perCPU FaultTicket精确绑定cpu/request generation/rawkernelCR3/RIP/CR2/error3/CPL0+IF0；新增纯匹配/消费函数供后续user_entry窄PF分支调用，仅匹配固定owned probe instruction与after RIP，armed ticket恰好一次，任意其它fault必须拒绝。当前任务不改IDT gate或真实handler，不把未接线/未实际writefault说通过。未来真实负控只在撤写后省一个AP的真实flush，warmRW TLB紧贴prebarrier后/撤权前，不被额外CR3/flush掩盖，要求stale-write精确拒绝。
永久host用真实DG/paging/完整forest与独立C raw oracle，debug/release、两格式、guards/原子前置拒绝；特权CPU边界明确mock，actualreader ASM只组装不执行特权。至少真实坏源码漏撤冲突alias/漏全ACK/提前EXEC grant或提前reclaim各精确拒绝，ticket mismatch/重放/别CPU/kernel非零tag/PGE/隐藏USER别名/过期身份反控。留全commands/raw/artifacts/source+tool stable/0skip回执。实现者不测试/compiler/OS/VM/AI CLI/commit/push、不改状态，由root独立审查复验和实际文件集成。

## 可修改文件

- `kernel/mm/runtime_exec.dg`
- `kernel/sched/runtime_exec_reader.asm`
- `tests/runtime_exec_probe.dg`
- `tests/runtime_exec_probe.c`
- `tests/test_runtime_exec.py`
- `docs/runtime-exec.md`
- `codex-works/deliveries/P2EXEC19.md`

## 定向验收

- `module:tests.test_runtime_exec`
- `module:tests.test_paging`

交付：`codex-works/deliveries/P2EXEC19.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
