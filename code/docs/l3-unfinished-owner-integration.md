# C52 / CR40 未完成交付接管与真实组合

## 范围和来源

用户在 2026-10-19 明确要求直接处理其他负责人未完成的任务。接管前只读核对远端 main 仍为 `e5c97d43bdee50902b98229fba49bbad68e44c99`，本地已有四个集成提交完整保留；协调器仅 C52 rev7 与 CR40 rev12 处于 submitted。原负责人源码、交付和历史均保留，未直接改变协调器状态。

本次不是重新实现已完成的修复：C52 的 review_note 指向旧的“非法名字数量仍先读正文”问题，但当前 R1 交付已经先检查所有名字 1..64 / IR 至多 64，再允许重复名和 C48 正文预检。复用这份有效实现。CR40 也已有正确的真实清理接线；本次关闭独立复验、测试证据和主线可导入性缺口。

主线新增：

- `lang/bootstrap/nasm_u64_module.dg/.md` 与 `lang/tests/test_bootstrap_nasm_u64_module.py`。
- `lang/bootstrap/nasm_pair_cleanup_function.dg/.md` 与 `lang/tests/test_bootstrap_nasm_pair_cleanup_function.py`。
- `lang/tests/test_bootstrap_cleanup_module_integration.py`。

两份生产 Dong 源均保持当前交付字节；测试和说明只做集成路径、可运行性、观察与边界覆盖修补。

## 实证问题及修补

C52 原测试的 POSIX 读取观察分支此前没有在 Linux 运行。原 `gcc -std=c11 -Wall -Wextra -Werror` 编译确实因未启用 feature-test macro，无法识别 `siginfo_t` / `struct sigaction` / `SA_SIGINFO` 等而失败。主线夹具补齐特性声明，不修改生产逻辑。

原读取观察只返回触页和 work 脏字节；work 长度为零使该保持检查没有意义，也未对本分支的 Function 表、out、written、正文和完整 guards 独立断言。主线增强为：有效/非法 module、item、IR 各页校准；所有 handler/保护操作必须成功；合法正控必须按预期读取每一角色，非法数量所有页必须未读；非零短工作区及全部输入/输出区域逐字保持。删除生产数量预检的真实 Dong 坏体仍须正常返回 INVALID，但必须被“提前读取”观察拒绝。SIGSEGV 仅作为受控页面首次读取观察，预留实际可读内存并解除保护后继续同条指令，崩溃不算通过。

CR40 主线测试补充一字节 item、八层链、十六个全二十位 ID、独立非法父图/不可达路径、合法只读输入重叠等边界；保留原四项与真实 RDX、注册顺序、提前发布和 RBX 坏体。补齐缓冲/栈上界说明与产物指纹。

## 新增真实组合

C52 实际生成一个完整八函数模块；输出直接写为独立 NASM 输入，不由 Python 改写 bits/section/global/函数体。CR40 实际生成清理整函数，链接到只负责适配与观察的零参数 thunk；每个 thunk 真正调用对应 C52 导出。模块涵盖 ADD/SUB/XOR/IMUL、高位整数、同 module 或 item、1/64 字节与非 ASCII 名字。

11 个主要组合向量，每模式 45 次真实清理调用：空计划、单项、逆序、三级链、兄弟不在路径、重复 ID、16 次注册、8 层最深链、同图从根退出、空内层、共享注册区间。独立 C 按原始 scopes/ids 反向树遍历计算轨迹，并使用无符号 C 运算核对每次模块导出真实 RAX；不以生产输出作 oracle。

thunk 记录完整 chronological ID / 实际 RAX / 入口对齐，故意破坏 RDX 和其他 caller-saved/flags 后返回。外层必须得到原始 RAX/RDX 双字值。内外两层独立静态观察地址、栈锚与 canary，先捕获实际 RSP 和全部 callee-saved，再恢复宿主；不依赖被测 RBX/RSP 找回观察区。完整观察缓冲两端另有 canary。16 槽安全环形日志同时保留未掩码真实次数，额外调用不会写越界且仍被拒绝。

四类真实坏 Dong 均正常编译、组装、链接、返回，并精确按对应证据拒绝：

1. CR40 清理后覆盖 RDX=17：11 个 pair failures，轨迹/导出值/ABI 均不失败。
2. CR40 调用 C36 前只交换局部 ID 副本：复用两项注册用例，仅 1 个 trace failure。
3. C52 生成阶段将 return_slot 换为已初始化槽 3：10 个非空计划的 export-value failures，双字/轨迹/ABI 均不失败。
4. C52 使用真实 C48 坏副本，在 ret 前将 RBX 加 8：10 个非空计划的 ABI failures，双字/轨迹/导出值均不失败；内层先捕获损坏再恢复，额外校准这一观察器。

## 复现和限制

命令从 `code/` 执行，需 Python、NASM 和 GCC；本云端使用 `NASM=/tmp/dongos-tools/usr/bin/nasm`。

```sh
python3 -m unittest lang.tests.test_bootstrap_nasm_u64_module -v
python3 -m unittest lang.tests.test_bootstrap_nasm_pair_cleanup_function -v
python3 -m unittest lang.tests.test_bootstrap_cleanup_module_integration -v
python3 -m unittest lang.tests.test_bootstrap_nasm_u64_function lang.tests.test_bootstrap_nasm_scope_cleanup lang.tests.test_bootstrap_cleanup_plan -v
python3 -m unittest lang.tests.test_bootstrap_select_forward_integration lang.tests.test_bootstrap_slice_memory_integration lang.tests.test_bootstrap_checked_narrow_integration lang.tests.test_bootstrap_short_switch_integration -v
```

最终定向27项全部通过，0失败/0skip：C52 6项（72.232秒）、CR40 4项（57.931秒）、新组合1项（57.763秒）、依赖相邻12项（54.466秒）、此前四条组合4项（195.153秒）。独立复核校验真实原生输出与源码/产物指纹。新组合首轮的坏返回槽构造曾误伤启动预检而退出99（整体1项失败，60.015秒）；已限定到slot_count=4且return_slot=2的合法夹具后完整重跑通过，旧失败日志保留，未把启动失败算为语义负控。详情见最终交付报告和各build/test唯一目录内summary.json。两模式真实 Dong 编译、ELF64 与 COFF 组装，Linux x86-64 SysV 原生执行。COFF 组装不等于 Windows 原生 ABI 执行。未运行完整后端、全语言回归、stage1/stage2、OS/VM 或部署；本组件集成不代表 L3 完成。GitHub 写入的既有 403 继续跳过，没有重复尝试或替换写入口。
