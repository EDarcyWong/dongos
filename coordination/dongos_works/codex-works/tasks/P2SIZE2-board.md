# P2SIZE2 — [P2前置] 内核函数分节与真实链接回收释放装载余量

负责人：codex。状态：待领取。

用户授权继续P2剩余开发、测试、独立验收和真实本地集成；不建PR、不提交/推送。P2LIVE1已集成且完整runtime7仅余432B，新增多核大页/执行/WC消费者前必须解决原2MiB预算；本项仅是必要构建前置，不把它当P2剩余功能完成。保留现有编译默认与所有P5/P2源码和dirty。新增显式function_sections选项：按完整函数分独立ELF代码section，函数体/ABI/控制流/布局清单不变，Win64桥与函数体同节，静态函数指针重定位与外部调用必须保活。默认不启用；仅正常kernel runtime>=5 release编译开启并用linker --gc-sections，用户服务/原runtime0与语言默认输出保持原行为，不扩大2MiB装载ABI，不引入后处理删汇编/手改ELF。CLI/API参数类型与清单如实记录。使用真实NASM/LLVM链接以独立ELF遍历证明未引用代码可回收、直接调用/跨节调用/静态函数指针/Win64桥保活并实际原生执行（必要坏链接负控明确拒绝）；相关既有编译接口回归。冻结完整runtime7源码，执行原完整构建和真实四核桌面/P5CTX2正常控制/P2Report回归，核对ELF/materialize及来源与清理；NASM2工具保持原警告严格，原NASM3探测问题另列不混入。通过声明的受限独立复验及源码/契约/原始客体审查后accepted，主文件真实SHA核对后integrated。验收报告明确DCE不改变算法语义及下游P2消费者仍待实现。

## 可修改文件

- `lang/dongc/compiler.py`
- `lang/dongc/emitter.py`
- `lang/dongc/__main__.py`
- `tools/build.py`
- `lang/tests/test_function_sections.py`
- `tests/test_kernel_link_gc.py`
- `docs/p2-kernel-budget.md`
- `codex-works/deliveries/P2SIZE2.md`

## 定向验收

- `module:lang.tests.test_function_sections`
- `module:tests.test_kernel_link_gc`

交付：`codex-works/deliveries/P2SIZE2.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
