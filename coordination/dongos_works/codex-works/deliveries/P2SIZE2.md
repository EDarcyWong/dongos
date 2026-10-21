# P2SIZE2 交付

2026-10-21。P2后续必要构建前置；用户要求不建PR、不提交/推送。未把本项计为多核大页/EXEC/WC功能完成。

- 编译API/CLI新增显式函数分节，默认关闭；开启时清单记录，-g组合明确拒绝。完整函数/Win64桥保持一节，函数体和布局不改。
- 仅runtime>=5的release内核开启分节与真实linker GC，不扩大2MiB装载窗口；其它默认编译及服务路径保持原样。
- 新增3项真实原生/ELF测试通过：直接调用、静态函数指针、Win64桥保活、未引用函数回收、512次实际ABI调用、原kernel/linker.ld入口/权限/边界；原24项函数ABI和真实GDB回归通过。
- 完整冻结release runtime7构建99.078s exit0；kernel.bin 1,990,224B，余106,928B。原P2LIVE1为2,096,720B/余432B，释放106,496B。
- 实际4CPU TCG正常桌面/P5CTX2 control两快照/P2Report通过23.859s；源码和一次性数据盘前后稳定、QEMU exit0/clean。P5完整原始归档离线重放通过，无新增内核或设备算法。

证据根：`coordination/dongos_works/.local/p2size2-add2a00421`。`release-build.json/log`保存完整实际构建命令、NASM2.16.03/LLVM工具SHA、全部冻结源码及前后稳定记录；构建器原生build-inputs记录function_sections/gc=true和全部实际产物。客体索引`runtime7-guest-index.json`，实际result `release-source/build/test/p2live-runtime7/run-fd17e16aa8af/result.json`。详细接口、限制及字节数见`code/docs/p2-kernel-budget.md`。

首次新测试包含两个观察器错误：函数数量误数为6而实际5，CLI命令日志与待检manifest同名覆盖；均修正后3项实际通过，未修改编译算法来迎合测试。最初失败和原生子命令证据在`code/build/test/function-sections/`；未引用类的测试导入导致重复收集也已消除。冻结runtime副本中旧CLI测试不被kernel构建消费，生产编译/构建输入全部与当前主目录一致，主机测试以最终主目录及正式受限复验为准。

正式独立复验、源码/契约及原始ELF/客体证据审查后登记accepted，主文件SHA实际核对后再登记integrated。最终回执见`reviews/2026-10-21-P2SIZE2-integration.json`。P2剩余消费者继续推进，不重复旧组件，不恢复归档派单。


## AI交付 2026-10-21T13:44:26+00:00 · codex-mcp-6fe7be60df984d37

函数分节和release内核真实GC前置落盘。3新增原生/ELF/CLI检查通过，24既有ABI/GDB回归通过；完整runtime7构建0/99.078s，1990224B余106928B；真实4CPU桌面/P5CTX2 control两观察/P2Report及完整离线重放通过23.859s，清理/source/disk稳定。保持原2MiB ABI、默认输出及P5生产源码。首次新测试观察器计数/manifest路径覆盖错误保留，最终测试已修正；旧冻结测试不属于内核构建输入。详见正文及docs/p2-kernel-budget.md，不扩称P2剩余消费者完成。请求正式声明3项独立受限复验；实际源码/契约/原始证据核对和主目录SHA确认后分别验收/本地集成。无PR/commit/push。
