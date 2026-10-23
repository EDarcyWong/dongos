# P2LARGE16 — P2调度后多根WB大页事务及真实AP内核消费者

负责人：codex。状态：待领取。

用户顺序先完整P2后P5。P2ROOT13已integrated15，本项真实接续调度后多根WB/NX大页owner及内核AP消费者，不放宽旧active/shared/exec/cache owner准入，不修改旧WINDOW/seal/held租约，不另alloc order9。新窗口固定large_memory.WINDOW+2MiB同PML4/PDPT/PD，旧PDE0永久保留，拒绝需新顶层共享分支的情况，仍完整审kernel及所有user[1..511]。
新增memory只读0..15可信完整根快照/recheck，包含所有initialized/ready/pinned/preloaded未admit根，不按Catalog READY过滤；拒在途stage/failure，核实际静/动态32/128池、root/Frame.cr3/Space与memory generation。services另绑定真实Catalog配置/owner token/incarnation/配置generation、Domain的队列token/root/incarnation/frame/Cpu/queue，不将不同代际相等。由large_memory只读borrow提供旧512页WB/RW/NX held物理块并用buddy只读allocation审计确认order9 head/tails，不释放/改变旧所有权。
新runtime_large owner只支持固定NEW2MiB map/split/replace单页/拒非连续merge/恢复/merge/unmap生命周期。真实CPU0/IF0/kernel root/BKL owner0/LOCKED+active healthy Domain/PGE0为前提，逐CPU PCIDE0/1均只走新全tag协议。每个事务先全online quiesce barrier+recheck，再真实paging live，再新sequence全tag barrier；仅ACK完整后reclaim真实Retired。中途失败永久held/poison，保留lease/receipts，Domain/Bridge failed阻止用户返回，不rollback/fallback。retired/P2ROOT Scratch/根/别名/reader报告等使用arena，不增巨大BSS/帧、不扩4096帧或2MiB装载预算。
不改Domain/Cpu ABI布局，在user_domain增加一次注册的可信poll hook（默认null），仅CPU/IF0/kernel root/已完整捕获的IDLE/KERNEL/LOCKED状态执行；保持现有屏障/legacy/捕获/返回守卫。新reader ASM真实volatile读NEW+5page，记录actual CR3/CR4/CPU，独立request/ACK序号，不能以flush次数冒load。正常services BKL一次触发，必须每个online AP已真实user entries/timer/switch后再运行，不能塞入只读skip路径；读者为调度后kernel CR3真实内核消费者，绝不宣称CPL3高半部读取。
保留旧WINDOW及held所有512页内容；全CPU独立warm新alias页5=A，在内核root/BKLwait保持期间split+replace到held页6=B，二次全tag barrier后同CPU再次load B，不额外MOV CR3掩盖缺APflush。真坏体只省本owner替换窗口内一个AP的实际全tagflush而仍ACK，再真实load必须精准抓A!=B；其它启动/普通PCID逻辑保持。还需根遗漏/共享项/不同代际/漏ACK/错误CPU/RETURNING未收回/提前reclaim/旧WINDOW变化/非连续merge等原子拒绝。永久native真实DG/paging+C独立raworacle、debug/release真坏实现/两格式/guards、真实构建与只读guest runner/raw replay；实现者不测试/VM，协调者独立0skip复验并在实际文件主线集成后登记。普通执行者不OS/VM/AI CLI/commit/push；root在源码/host审查后可按用户P2授权跑准备好的受控隔离VM。物理WC/PGE/任意顶层分支不属于本项通过。

## 可修改文件

- `kernel/mm/runtime_large.dg`
- `kernel/user/memory.dg`
- `kernel/user/services.dg`
- `kernel/sched/user_domain.dg`
- `kernel/sched/runtime_large_reader.asm`
- `kernel/smp/large_memory.dg`
- `kernel/mm/phys_buddy.dg`
- `tools/build.py`
- `tests/runtime_large_probe.dg`
- `tests/runtime_large_probe.c`
- `tests/test_runtime_large.py`
- `tests/p2_runtime_large_build.py`
- `tests/run_p2_runtime_large_qemu.py`
- `tests/test_p2_runtime_large.py`
- `tests/test_user_domain.py`
- `tests/test_buddy.py`
- `docs/runtime-large.md`
- `codex-works/deliveries/P2LARGE16.md`

## 定向验收

- `module:tests.test_runtime_large`
- `module:tests.test_p2_runtime_large`
- `module:tests.test_user_domain`
- `module:tests.test_user_smp_barrier`
- `module:tests.test_buddy`
- `module:tests.test_paging`

交付：`codex-works/deliveries/P2LARGE16.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
