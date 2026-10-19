# CR27 memmove 独立复验与返修依据

正式作业 `836614ca3684496496d1482ee4d5dfef`：3项通过、零skip、24.406秒，source_stable。已实际阅读完整任务书、源码、说明、交付和全部测试。当前方向选择、count0提前跳转、反向CLD、263字节上界/512 scratch及一次发布正确，未发现生产算法缺陷；但以下测试契约未关闭，不能验收。

1. 主原生测试 `test_dong_assemble_and_native_memmove` 使用 `text=expected_text(FWD,END)`，实际执行Python手写模板。实际Dong产出只用于文本/对象组装，不能据此认定其memmove语义、方向指针终值和保持已原生复验。语义负控好侧也使用Python模板，须改各模式正式Dong实际产出、相同输入先通过。
2. 正常非零路径仅检查RDI-RSI差；count0非NULL路径直接pass；前/反向精确终值检查也都是pass。应在C端保留入口真实地址，立即输出或断言：count0均保持；前向各入口+count；反向各入口-1。终值仅作整数比较，不能解引用。
3. 当前仅观察RAX/R8/R9保持，尚缺RDX/R10和其它应保持GPR的显式观察。桥自己的R11元数据指针也不能靠片段保留才能安全捕获错误；应在独立安全位置保存观察器地址，保护宿主callee-saved/栈，正常执行后按准确寄存器断言拒绝。保留全缓冲独立入口快照oracle、双端guard、RCX和DF。

独立真实坏Dong实证：未修改原四文件。私有源码在最终end标签后追加 `lea rdi, [rdi + 1]` 与 `lea rsi, [rsi + 1]`，完成debug/release实际Dong编译、ELF64/COFF组装及本机链接执行。相同输入先运行正式实际Dong好体，再运行坏体，两模式在dst=src+1,count8及count0非NULL两夹具全部通过现有原生断言。全内存正确而两指针终值确实偏移，证明差值/空pass漏检；不声称整个精确文本测试套件接受额外指令。源脚本 `.local/reviews/cr27_independent.py`，输出与完整编译/链接/实际输出在 `.local/reviews/CR27-20261019/independent-result.json` 所指唯一目录。

仅原四文件完善测试、说明/交付，不重写正确算法、不修改其它组件/IR。保持主要原生向量合计<=24，保留方向强制前拷贝按全内存拒绝、删CLD由安全桥先捕获DF再立即CLD后按DF拒绝、容量提前写原子性拒绝。新增精确指针终值坏Dong对照，所有好坏侧使用实际产出和相同输入。独立复验后再验收/真实集成；本轮未复制CR27到主线。正式状态回执见同名JSON。
