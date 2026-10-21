# L3 — [L3/G5] 原生整程序语言与ABI差分执行、真实缺口回归

负责人：deepseek。状态：待领取。

所属阶段：L3（Dong编译器自举）/G5差分覆盖。用户要求DeepSeek接续L3、L3A；本项在deepseek:L3A通过独立验收后领取，使用届时最新已验收/集成候选，不抢其生产文件。目标是实际整程序差分执行与可复现缺口回归，不重写已完成的49模块固定点/读取/栈/持久化，不以组件数或语法树检查宣称完整自举完成。

当前主线lower_program明确拒绝GLOBAL/METHOD/ERROR/ENUM以及若干语句，L3A本批实现全局量，其余差集必须真实复测并逐项记录。第一阶段补一套有限、可扩展的源码级G5差分runner：同一明确源码目录与入口，种子Python编译器和真正Dong frontend→lower→nasm两条独立路径；宿主只做种子引导、进程编排与独立观察，不能宿主构建目标IR/NASM或失败时seed fallback。生产runner位于本人works文件，之后由Codex本地集成；禁止编辑L3A或任何主线源码。

至少覆盖两模式的整数窄宽、checked/wrapping、短路副作用、循环break/continue、嵌套调用与大于6整数参数、slice双字整体ABI、单次求值lvalue、结构体/数组精确字节与padding、静态常量与新可变全局量、两个模块导入/同名符号/pub-private。固定有界样本与可复现种子生成，成功对比完整返回寄存器、可观察内存/轨迹，失败对比阶段/诊断类别/源码定位；错误文本格式可分开，不以两条路径共享算法互相证明。使用独立C/Python语义oracle或固定已人工核定数值。实际SysV桥验证所有callee-saved和RSP后恢复；COFF组装不能冒充Win64ABI执行。NASM ELF64及COFF均组装，另至少一组真实native_assembler生成完整ELF并实际执行。

为方法、enum、error/try/orelse/defer、extern SysV/Win64等尚未实现的完整语言构造准备可由seed实际执行/诊断的最小真实源码。每例记录原生路径的精确失败阶段/状态和输出保持；coverage.json将它们标记为已证实缺口，不能标supported、xfail-pass或skip，也不能把“按预期不支持”计入G5成功覆盖。用独立TestCase断言scope_complete=false、remaining逐项非空，最终交付分别列supported-pass、known-gap、failure、skip，不能让全套测试退出0变成整体G5完成。本项的验收只覆盖runner及有限受支持矩阵；其余语言实现需后续独立任务，若用户另有授权也必须先补可写范围。

真实负控至少两类：候选Dong lowering/发射代码小范围语义变异（例如全局错址、slice第二字或短路求值），成功构建/链接/正常执行后被返回值/完整内存/调用轨迹准确拒绝；runner漏掉一项原生失败并尝试seed fallback的坏体应被路径证据/结果状态拒绝。构建失败、崩溃、超时、仅汇编文本不同不算语义负控；每个相同输入先证明好体通过。

单次运行保留源码目录/编译器/只读闭包SHA256、确切工具版本/命令/env allowlist（无密钥）、模式/对象格式、进程退出/timeout、每个case的输入/期望/实际/原生产物SHA与首次差异。快照发生变化即失败，失败现场不可覆盖，缺工具明确阻塞不skip。只运行本项定向检查，不启动OS/VM/AI CLI、无PR/commit/push，不改协调器数据库/index或任务图状态。临时目录deepseek-works/build/L3/<唯一目录>。

本人客户端worker MCP读最新rev与完整task/依赖，claim后只修改四个声明文件。交付L3.md列真实tests/skips/支持覆盖/已证实缺口、负控具体拒绝依据及未运行限制。交付后Codex实际审查、独立复验零skip且source_stable、再验收并本地集成。不得自行accept/integrate，不把本有限里程碑等同整个L3/L3A/G5完成。

## 可修改文件

- `deepseek-works/l3/g5_differential.py`
- `deepseek-works/l3/g5_differential.md`
- `deepseek-works/tests/test_l3_g5_differential.py`
- `deepseek-works/deliveries/L3.md`

## 定向验收

- `discover:deepseek-works/tests:test_l3_g5_differential.py`

交付：`deepseek-works/deliveries/L3.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
