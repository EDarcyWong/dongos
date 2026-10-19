# C41/C42 真实SysV调用与返回接线

C41正式独立作业b84d388fd1fc495fac65217c9e83c127：4项零skip、53.940秒；C42正式作业3b870bba474c4a7e9fc90c370b5524a1：5项零skip、27.333秒。已审查源码、任务/交付、预检夹具、全部测试与只读依赖；验收前最新四文件指纹一致。

C41实际委托C34 setup、C25 call、同一stack_bytes cleanup、C40 capture，先完整预检再局部1536字节拼接/一次发布。真实Dong产出执行显式SysV call，覆盖0/6/7/16 word、寄存器/栈参数、PAIR、原始名字边界、返回与源槽重叠、入口对齐/栈恢复、完整帧。实际不同合法callee与PAIR槽互换按返回数值拒绝，八处完整输入尾部别名选择性坏体准确命中15..22，容量提前写原子性有效。

C42实际委托C39装载、CR11尾声/ret，extent与原frame/mask分开传递；只允许局部区返回槽，拒绝保存区/底部padding。真实CR11 prologue与组合exit构成call/ret，覆盖全部kind、odd/even/全saved_mask、最大extent、边界槽、RAX/RDX与callee-saved/rsp恢复。四个local窗口坏体与两个out别名负控独立可达，语义坏体正常返回后数值拒绝。

验收后真实复制两模块.dg/.md及永久test_bootstrap，仅适配路径。主线同9项零skip、80.579秒，生产/测试/完整只读依赖/编译器与NASM helper前后指纹稳定，已登记两项integrated。详细映射、SHA与回执见同名JSON，本地完整日志`.local/reviews/C41-C42-20261019/mainline-unittest.log`。

尚非完整编译器：调用函数体仍是测试手写代码，完整AST/IR到这些组合模块的连接、语义/CLI与stage1/stage2/客体自举门禁仍须继续。未运行OS/VM、全语言回归、模型CLI或提交推送。
