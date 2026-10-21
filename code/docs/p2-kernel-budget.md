# P2 后续消费者的内核装载预算

2026-10-21，P2SIZE2。P2LIVE1完整runtime7内核为2,096,720B，距原2MiB装载上限仅432B；本项提供必要构建前置，不代表P2多核大页、EXEC或WC消费者已经完成。

新增显式编译选项`function_sections=True` / CLI `--function-sections`，把每个完整函数放入独立代码节。函数体、ABI、跨节调用、静态函数指针重定位、类型布局不变；Win64入口桥与对应SysV函数体保持同节。ELF使用明确RX代码节属性，COFF使用对应code节属性。默认关闭，默认汇编和manifest保持原样；开启时manifest明确记录。当前不支持与DWARF `-g`同时使用，组合请求明确拒绝，不输出错误调试范围。

`tools/build.py`仅在runtime>=5的release内核编译打开分节并调用链接器`--gc-sections`。普通runtime0诊断镜像、用户服务编译、其它语言编译默认路径不变。链接器依据真实引用关系保留函数，未采用文本删汇编或手改ELF，也未扩大原2MiB装载ABI；静态数据节仍保守保留，未宣称全程序最小化。

原生验证：真实NASM ELF/COFF汇编、LLVM链接与独立ELF遍历确认未引用函数被回收，直接调用、仅由静态函数指针引用的函数、Win64桥与私有函数体保活；debug/release每种实际执行256次精确ABI调用。真实kernel/linker.ld另验证入口、静态重定位、页对齐、PT_LOAD无W+X及materialize边界。默认函数体和类型布局逐字比较相同，CLI/API错误参数明确拒绝。共3个新增宿主测试通过，另24个既有函数ABI/真实GDB回归通过。

完整冻结runtime7/release/test=False重建99.078秒退出0；kernel.bin=1,990,224B，装载余量106,928B，较之前释放106,496B。实际四核正常桌面/P5CTX2正常设备上下文两观察/P2完整Report回归23.859秒通过，原始归档完整P5离线重放也通过；没有用小模型替代正常内核构建或运行。

运行根为`coordination/dongos_works/.local/p2size2-add2a00421`，完整构建命令、工具/源码前后SHA见`release-build.json/log`，实际结果为`release-source/build/test/p2live-runtime7/run-fd17e16aa8af/result.json`。单个主机CLI测试在冻结后修正了“命令记录覆盖测试自身manifest输出”的观察器路径错误；该测试文件不属于内核构建输入，冻结内核实际消费的编译器/构建器及全部生产输入与主目录相同。失败测试日志保留，最终测试在主目录及协调器受限环境执行。

后续新增P2消费者仍需各自的生产接线、原生坏源、实际多核/缓存/权限验证及独立验收；106,928B余量只解决装载约束。没有PR、提交或推送。
