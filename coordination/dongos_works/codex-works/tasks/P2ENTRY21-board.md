# P2ENTRY21 — P2精确EXEC受控异常adapter与默认关闭的CPL0入口

负责人：codex。状态：待领取。

用户先完成P2后P5。本项接续已独立通过的runtime_exec组件，只完成可审查的精确受控异常adapter/入口；services绑定和build导入后续统一接线，host不得声称真实PF完成。不碰B在途services/memory/domain/build，不修改IDT/异常帧ABI/一般异常、NMI/#DF或用户fault政策。仅user_entry现CPL0分支vector14/CS8/error3/IF0/正确GS来源/已注册固定probe RIP允许调用新adapter，除此保持原fail分派。默认未注册必须原fail，不引入任意RIP恢复。建议ASM提供一次trusted注册的callback+固定probe/after元数据（初始0，无新增未链接extern），新sched.runtime_exec_entry.dg记录已验证Context/Domain/Header身份，bind需真实CPU0/IF0/rawkernelCR3tag0/PGE0/BKL owner0/LOCKED/healthy domain，拒重复/坏callbackABI，后续service显式bind才能启用。adapter从ASM传入可信GS Header与raw CR3及原ExceptionContext，核合法原内核栈范围、无alias、cpu/domain/mode/active busy PROBE/currentrequest，构造Fault调用现handle_fault/consume_fault；任意失配/重放frame与ticket均不变，不ACK、不改CR3/flush、不改变权限。成功只获固定after，ASM精确核后只改saved RIP，完整pop CR2快照/GPR/vector+error后IRETQ恢复原RIP/CS/RFLAGS/RSP/SS；不能用raw+184推原RSP或ret，不硬编码SS。GS入口swapgs来源需记录并仅接受未交换的owned CPL0现场；成功不swapgs。不允许嵌套异常重新使用恢复栈。可通过所有精确门后使用已验证perCPU exception_top临时栈调用纯整数DG adapter，保留原frame指针恢复，不改IST；证明不碰SIMD/x87，不能用kernel_xstate覆盖实际现场。永久host真实DG+ASM双格式/独立C纯数据oracle，23qword原frame/guards、完整布局、成功恰好一次、逐字段破坏、栈范围/重叠/缺注册/别CPU/代际/原tag/IF错误精确拒绝；实际入口IRET/MSR/CR指令不在host执行。现有test_user_smp_entry保留并通过，避免新增未定义符号或改变旧实际字节测试。保留命令/raw/source/tool SHA/真实失败0skip回执。执行者不编译/测试/VM/提交推送/状态，由root独立复验和实际集成。

## 可修改文件

- `kernel/sched/user_entry.asm`
- `kernel/sched/runtime_exec_entry.dg`
- `tests/runtime_exec_entry_probe.dg`
- `tests/runtime_exec_entry_probe.c`
- `tests/test_runtime_exec_entry.py`
- `docs/runtime-exec-entry.md`
- `codex-works/deliveries/P2ENTRY21.md`

## 定向验收

- `module:tests.test_runtime_exec_entry`
- `module:tests.test_user_smp_entry`

交付：`codex-works/deliveries/P2ENTRY21.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
