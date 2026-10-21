# P2SIZE9：正式内核预算接续（验证中）

P2ALIAS8首次完整链接实际PT_LOAD span=2129616B，超2097152B窗口32464B，原materialize正确拒绝。此前P2BUILD5正常内核2006608B/余90544B。禁止扩大loader或镜像上限。

新tools.kernel_budget.kernel_flags仅对runtime_level>=5的release kernel选择已有function_sections与O1。源码编译器默认、诊断debug镜像、普通services编译均不变；现有O1支持的scalar/pointer函数通过SSA，unsupported整函数回退L1，volatile/atomic/cleanup保持原后端。没有新建优化算法或放宽内存/ABI。P2ALIAS8在原授权build.py显式接此策略。

既有CLI、SSA effects/memory/native定向复验、真实完整镜像大小/SHA/对象/输入、真实SSA/L1fallback比例待实际验证。真实P2正常1/4核、语义坏体和4核桌面/P5回归仍由P2ALIAS8验收，不以宿主通过冒充客体通过。当前未验收/集成，不声称所有任务完成。


## 实测结果

既有优化CLI/SSA effects/memory/native：16tests/0skip/exit0，7.835s。实际首次O1完整链接仍有2125520B（超28368B），只缩4096B，明确不能独立关闭预算问题。组合独立P2SIZE10显式static2存储profile后完整release runtime7构建通过：kernel.bin=1994448B，余102704B，SHA=705a23c8db0068c0c6fd65949f9a699379181cff477f8912c2d0bca4ae593f85，source_unchanged=true。真实编译IR记录backend计数{'l1': 1036, 'ssa': 66}，不是仅传flags。构建、输入及生成profile/IR/ELF/镜像SHA见build/p2alias8-storage2/build-inputs.json与reviews/2026-10-22-P2SIZE9-P2SIZE10-build.json。Loader/镜像窗口仍2MiB，普通services默认编译不变。

当前只证明构建与宿主回归，正常硬件验收仍由P2ALIAS8进行；尚未正式验收/集成。
