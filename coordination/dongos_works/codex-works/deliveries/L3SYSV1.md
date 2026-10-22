# L3SYSV1 — 原生 SysV 接线

项目 dongos，2026-10-22。仅修改任务声明文件，未提交、推送或启动 OS/VM。

lower_program 接受显式 SysV 定义，无体 SysV 声明不生成函数/栈帧/桩；Win64 仍返回 UNSUPPORTED。nasm_program 为无体声明生成真实 extern/调用符号，支持默认名称、extern 名称和 export 名称；定义保留模块内符号并发布同地址别名，ASCII 链接名使用 NASM `$` 转义。跨模块同名声明可绑定不同外部函数。SysV 调用继续复用已有整数参数规划、窄返回规范化及栈参数路径。G5 的显式 SysV 定义样本改为真实 seed/Dong 执行比较，其余样本保持失败诊断，remaining 根据实际 gap 记录生成。

本机已执行：

- `python -m unittest lang.tests.test_l3_sysv_native -v`：首版 6 项全部通过、0 skip，532.562 秒；证据 `code/build/test/l3-sysv/run-101b923e70f5/summary.json` 与 `differential/sysv-coverage.json`。debug/release 均实际执行 SysV 定义、C 外部链接、八参数/窄值/指针写入、跨模块同名隔离、G5 SysV/Win64迁移检查和错误链接目标的真实 Dong 负控；每个成功发射均经过 L3A 桥的 exact/one-short、descriptor/input 别名、完整 guard 及 graph/source/IR 不变检查。
- `python -m unittest lang.tests.test_g5_runner_entry -v`：2 项通过、0 skip。
- `python -m unittest lang.tests.test_l3_escaped_symbols -v`：4 项通过、0 skip；转义符号/重定位/实际 ELF 执行见 L3SYSVASM1。
- Python 编译检查及本次修改的 `git diff --check` 通过。

首轮后增加了永久测试自身 SHA 记录、原旧 Win64 无体声明负例的精确源文本，以及真实 Dong 后端输出到原生汇编器再执行的第7项测试。这些最终变更交由协调器隔离复验，不将首轮 6 项冒称为最终 7 项结果。正式日志以协调器作业为准。

必要配套任务：L3SYSVREG1 同步旧测试预期；L3SYSVASM1 使原生汇编器接受 `$identifier`，避免现有自举导出别名回归。

范围：现有前端支持的 scalar/pointer 外部声明及显式 SysV 定义。Win64、函数指针调用、foreign data、原生 ELF 汇编器中的未解析 extern 链接及完整语言/ABI覆盖仍未完成；未执行完整 G5 矩阵或 OS/硬件验收，不能据此关闭 L3/L3A/P9。

## R1：正式复验中的夹具路径修正

首轮正式作业9cd564b664de4cdf843e83248926bcf0实际运行7项，0skip/source_stable；新增能力、真实错误调用目标负控及原生ELF端到端执行均通过。最后一项中新增的旧负例文本声明module unsupported，却在新测试里以bad.dg作为catalog路径，导致两模式先在frontend因模块名不匹配而失败，未抵达期望lower UNSUPPORTED。修正仅把该负例catalog路径改为unsupported.dg，生产实现不变。

已复用首轮冻结的真实原生编译器独立执行5份拒绝源×2模式，10次均得到正确阶段/拒绝码且输出保持；实际记录code/build/test/l3-sysv-path-fix/run-fcb75936c1cb/path-fix.json。另在code/build/test/l3-sysv-reuse/run-1c8f3b7f3e7d/end-to-end.json记录了两模式真实Dong输出→原生汇编器→ELF→宿主执行返回204。最终修正文件再次申请正式隔离复验，保留首轮失败，不冒称R1已正式通过。


## AI交付 2026-10-22T01:15:41+00:00 · codex-mcp-8c76f5a25c8d4b71

本轮实现及真实本机检查已完成，具体结果与未执行范围见本任务交付。最终文件已冻结，申请协调器独立隔离定向复验；submitted不等于验收。


## AI交付 2026-10-22T01:28:10+00:00 · codex-mcp-8c76f5a25c8d4b71

R1只修正新永久测试中legacy模块源的catalog路径；生产实现不变。首轮正式7项运行保留实际失败，真实能力/负控/端到端均通过。局部复用冻结原生编译器的10次拒绝检查及两模式端到端已实际通过，路径/结果见交付R1。最终文件重新冻结，申请隔离定向复验。
