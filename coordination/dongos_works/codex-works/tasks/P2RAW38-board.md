# P2RAW38 — 受控 EXEC 异常的永久 caller-owned 原始帧记录

负责人：codex。状态：待领取。

用户顺序P2软件/本机→P5软件/本机→硬件待验留档→GitHub完整推送并验证→关机，执行不询问。ENTRY21 integrated6、EXEC19 integrated12原组件已通过；本项仅增加caller-owned真实pre-ASM PF RawTrace，不重新开发ENTRY/PF/IDT/IST/GS/Domain/GOP。与B R9四路径及SYNC40九路径无共享写集，允许并行实现，但所有writer冻结前root不排新verification snapshot。原任务书/契约先完整读P2ENTRY21、P2EXEC19及本书，原Raw23Q/184B、Header256B、Snapshot、bind及callback必须精确等于dispatch、once-only注册和原所有硬件/owner/root/票据检查保持。新增bind_trace(Context*,records:[]RawTrace,storage_base:u64,storage_bytes:u64)!void或等价明确窄API，在trusted re.bind后、ENTRY.bind和run前一次绑定永久caller-owned32槽(16CPU×两payloadPROBE)；旧不绑定trace宿主行为保持，后续C/D生产必须实际绑定。预检所有align/extent/capacity/溢出、来源Context准确、合法caller持有Block范围及与Context/Domain/Cpus/Headers/四种stacks/实际pool/source-dest不交，错误在任何全局发布/trace写前拒；不引入boot服务循环依赖，caller持有范围由生产绑定和actual raw provenance核实，不能仅自比两份数组冒所有权。离线槽不能假充online。BSS仅固定小pointer/count，完整32record在arena，4KiB原帧与16KiB异常闭包限制不扩。
每CPU两槽分别对应CODE42和CODE43两次真实PROBE，不是前后两个Raw帧。真实record保存完整Raw23Q、原frame VA/所属stack范围、实际传入rawkernelroot/Header/generation、reader.request/ack/action_sequence/command/payload、FaultTicket8Q消费前后、实际dispatch返回after和commit。编译layout冻结字段，源PA只由host按原frameVA及真实kernelpool走表推导，PF内不加walker/hardware读，tracecopyPA不能冒sourcePA。dispatch Raw保持*const；先检查对应空slot且所有原准入成功，保留小beforeTicket，调用原handle_fault，只有成功才固定整数copy原Raw/前后Ticket并commit-last。失败不改Raw/ticket不发布成功trace；重复/满/第三次/错payload绝不覆盖旧证据。dispatch只返回after，唯一原user_entry.asm随后写savedRIP；不宣称记录post-RIP或证明IRET完成。无新clock/MSR/allocator/ACK/flush/opaque callback/日志格式化、无SIMD/x87/递归，不改assembly/user_entry.asm；外层Action未来另存TSC。once bind无reset/unbind，失败held原策略保留。
永久有效native扩原runtime_exec_entry_probe.DG/C与test_runtime_exec_entry：真实production DG+原production ASM，debug/release、ELF64/COFF、-Werror；32slot与canary/twoPROBE一次、逐CPU/header/gen/root/Raw/票据/after/重放/错storage/重叠/overflow/原子性，Raw所有字节除原ASM apply唯一RIP不变，native apply明确不执行IRET。独立C逐字段重算与真实DG坏源(编译成功且正常rc1，panic/crash/编译错误不算拒)。原测试/负控全留不删弱；新helper白名单仅固定整数copy/commit，禁新增间接call/外部硬件/浮点/递归，保守总栈<16KiB，完整实际两格式汇编仍强制。作者只实现六声明路径、冻结SHA/交付，不编译测试VM、不自己submit/accept/integrate/commit/push；root源码/契约/坏源有效性独立复验0skip/stable/exited后分accept/integrate，实际C/D消费另任务不能用native冒actual。
参考仅build设计产物cd-task-book-draft.md和cd-ledger-harness-notes.md，原TASK/本授权优先。若确需别的路径先报告root补明确书，不私改。

## 可修改文件

- `kernel/sched/runtime_exec_entry.dg`
- `tests/runtime_exec_entry_probe.dg`
- `tests/runtime_exec_entry_probe.c`
- `tests/test_runtime_exec_entry.py`
- `docs/runtime-exec-entry.md`
- `codex-works/deliveries/P2RAW38.md`

## 定向验收

- `module:tests.test_runtime_exec_entry`
- `module:tests.test_user_smp_entry`

交付：`codex-works/deliveries/P2RAW38.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
