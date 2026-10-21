# P2SIZE9

已正式领取rev2，新增三文件；采用现有后端策略，未修改编译器/ABI或2MiB窗口。实际检查与构建结果待追加，未验收/集成。

## 实际验证

python -m unittest lang.tests.test_optimization_cli lang.tests.test_ssa_effects lang.tests.test_ssa_memory lang.tests.test_ssa_native -v：16tests/0skip/exit0，7.835s，真实SSA差分、坏DCE读fault、phi循环、callee ABI及两种对象格式均按既有测试通过。

O1单独只缩4096B，仍超28368B，已保留拒绝日志code/build/p2alias8-o1/build.log；不据此声称解决预算。与P2SIZE10独立显式存储profile组合，实际正常release runtime7完整构建191.188s通过：1994448B/余102704B，SHA 705a23c8db0068c0c6fd65949f9a699379181cff477f8912c2d0bca4ae593f85，source_unchanged=true，实际SSA/L1计数{'l1': 1036, 'ssa': 66}，生成IR及存储配置已按SHA绑定build-inputs。完整记录reviews/2026-10-22-P2SIZE9-P2SIZE10-build.json。

调用接线位于P2ALIAS8授权tools/build.py，本文三文件未更改编译器/默认ABI、loader或2MiB窗口，services编译未选O1。真实硬件及P2ALIAS8仍在验证，未冒作客体通过，当前待正式独立复验和源码审查。


## AI交付 2026-10-21T17:45:10+00:00 · codex-mcp-6fe7be60df984d37

正式服务kernel显式使用已有function_sections+O1策略，源码编译器/默认ABI/services/loader2MiB不变。真实CLI优化/SSA effects/memory/native 16tests/0skip/exit0 7.835s。O1单独只缩4096B仍超28368，拒绝日志保留；独立P2SIZE10存储profile组合后实际完整release runtime7 1994448B/余102704B，source_unchanged，IR真实SSA与L1fallback及所有输入/生成配置/产物SHA绑定；记录reviews/2026-10-22-P2SIZE9-P2SIZE10-build.json。正常客体尚待P2ALIAS8，未虚称通过。请求正式定向复验及实际源/契约审查。
