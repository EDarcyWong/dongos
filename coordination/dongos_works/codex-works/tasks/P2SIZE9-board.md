# P2SIZE9 — [P2预算接续] 正式服务内核启用现有可选O1后端

负责人：codex。状态：待领取。

P2ALIAS8首次完整实际链接后kernel PT_LOAD span=2129616B，超现有2MiB 32464B；tools.elf_image已正确拒绝，未运行超限客体，证据reviews/2026-10-22-P2ALIAS8-budget-overflow.json。保持镜像/loader/2MiB窗口及默认Dong编译ABI，禁止扩大上限或修改语义。仅提供显式正式kernel编译flags策略：runtime_level>=5使用现有function_sections和可选release O1 SSA后端，诊断/独立用户态保留原策略；其不支持的函数由现有编译器先完整拒绝SSA再原L1 fallback，内存volatile/atomic/cleanup等不新放宽。默认compile_file/CLI及services编译不改变，不新增优化算法。

与在途P2ALIAS8路径不重叠：本项新tools/kernel_budget.py策略和说明/交付；P2ALIAS8负责人在本人已声明tools/build.py中显式调用该策略。编译器Python与bootstrap/DeepSeek任务全部只读，不修改在途正式测试输入。实际运行既有CLI优化、SSA effects/memory/native正负例定向0skip，核对策略确实被正式kernel调用、编译产物含真实SSA与L1fallback manifest；真实新完整release kernel必须回到2MiB以内并记录span/SHA/所有输入/对象/命令，仍可能需要进一步实现收敛则如实保留，不凭flags宣称预算通过。协调者随后由P2ALIAS8执行真实1/4CPU及负控/桌面/P5验收，不能用通过本任务宿主回归替代硬件消费者验收。独立源码审查+正式复验0skip/source稳定+真实文件落盘才分别accept/integrate。仍不建PR，全部任务完成前不推送/关机。

## 可修改文件

- `tools/kernel_budget.py`
- `docs/p2-kernel-budget-o1.md`
- `codex-works/deliveries/P2SIZE9.md`

## 定向验收

- `module:lang.tests.test_optimization_cli`
- `module:lang.tests.test_ssa_effects`
- `module:lang.tests.test_ssa_memory`
- `module:lang.tests.test_ssa_native`

交付：`codex-works/deliveries/P2SIZE9.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
