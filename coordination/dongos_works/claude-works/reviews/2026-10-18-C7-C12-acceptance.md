# C7–C12 独立组件验收

2026-10-18，结论：六项均通过独立验收，状态为 accepted；尚未集成到 code/lang，不代表 L3 自举完成。

## 源码与契约审查

- C7：先验证全部节点范围及被引用的边（含不可达部分），再检查容量和工作区；每个节点仅入栈一次，out 标记只为 0/1。未引用的边尾部不参与解释。
- C8：INTEGER 标量/双字的寄存器分配与整体回退符合任务书，双字上栈不消耗余下的单寄存器；机器字总数及栈大小先检查，最终栈区按 16 对齐。不扩展为完整 SysV ABI。
- C9：唯一目标检查在写输出前完成；按输入下标确定顺序，循环借用固定临时位置，并更新所有相关源；逐步符号执行检查原始位置均符合并行语义。O(n³) 小组算法的限制已说明。
- C10：逐槽预跑 end=align_up(cursor+size,alignment)，随后按 16 取整最终帧；溢出/非法对齐/容量不足不泄漏部分输出。零大小槽仍参与显式对齐规则。
- C11：完整描述符与别名预检后依次检查容量、工作区；在 work 中非递归堆排序并判重，再写 out/used。有符号排序、值与标签配对及重复值检查符合追加的错误优先说明。
- C12：所有作用域父链均验证到根，含不可达环；目标须为当前/祖先/函数退出哨兵。由内到外、层内逆注册顺序，排除 target；预检全部结束后才写输出。

六项均检查完整声明区间、自然对齐、元素长度及地址溢出、可写区间别名和失败原子性。输入/输出/结果对象保护区及真实只读输入由 C 观察器逐次检查。已审查 Python 期望、原生观察器及坏源码控制，不以编译失败、崩溃或超时充当预期断言拒绝。

## 独立执行

协调器在各自独立副本串行复跑六个定向 unittest，共 18 tests、0 skip；debug/release 原生运行，ELF64/COFF 组装，受测文件指纹稳定。18 类坏源码控制在两个模式分别编译、链接、执行后被指定断言拒绝，共 36 次。

| 任务 | 定向复验 | tests / skip | 回执 |
| --- | --- | --- | --- |
| claude:C7 | 通过，文件稳定 | 3 / 0 | [result.json](../../.local/runs/a7e35a2c50d148c2844b70edd8532a2c/result.json) |
| claude:C8 | 通过，文件稳定 | 3 / 0 | [result.json](../../.local/runs/654bf2ea23da440c87fc74aa42a12c86/result.json) |
| claude:C9 | 通过，文件稳定 | 3 / 0 | [result.json](../../.local/runs/74ddf78d631b4fe08994f18d789cba4e/result.json) |
| claude:C10 | 通过，文件稳定 | 3 / 0 | [result.json](../../.local/runs/2d06720bfcfd45ab9009bb37ac1b6415/result.json) |
| claude:C11 | 通过，文件稳定 | 3 / 0 | [result.json](../../.local/runs/22f1551bf04b41adb5efc1933bf7b4a3/result.json) |
| claude:C12 | 通过，文件稳定 | 3 / 0 | [result.json](../../.local/runs/7079e2a16f1e47a7bd88b0f8dd0be59f/result.json) |

另复用本轮新编译的原生程序，追加 10,216 次两模式案例：全部三节点有向图及三个入口（1,536/模式）、长度 0～10 的全部 INTEGER 参数序列（2,047/模式）、四位置全部部分复制映射及精确确定性轨迹（625/模式）、全宽栈槽尺寸/有符号分支/任意重编号父树（各 300/模式）。新增种子 0xC0DE1817，正式实现和测试未修改。证据：[Codex追加复验回执](../../.local/reviews/batch3-7776fff6c0f9/result.json)

未运行 OS/VM 或完整回归；ELF64 在本轮仅组装，不声称 Linux 原生运行。原交付和历史验收保留，无提交/推送，后续主线集成另行执行。

## 验收文件指纹

| 文件 | SHA256 |
| --- | --- |
| `claude-works/deliveries/C7.md` | `c7f7cbce1e0e37401090ff405c52d385ced5fda338bb614d10ee80b397d6e47d` |
| `claude-works/src/bootstrap/cfg_reachability.dg` | `efe2caddefd9b6634d0d3b1633b4caa992b077debc674a942d47920ae4bbc5a3` |
| `claude-works/src/bootstrap/cfg_reachability.md` | `9d3dd6e9f2baa997e77018f4db5764da982e0fcd261bfb553200c01dd8df027d` |
| `claude-works/tests/test_cfg_reachability.py` | `736a53af6d7d6051d418ce1d598c97dcb29c4dbcb5142680f22eb77684680365` |
| `claude-works/deliveries/C8.md` | `c49dd86f6ed3dabf8fcf61b55512d4d3c53d7f5139bd9542bd507e817ac71fe9` |
| `claude-works/src/bootstrap/sysv_integer_args.dg` | `75c4ab5fd07d586684eb753958654e6e6658ff90e4d77f2a1ea96cb110573204` |
| `claude-works/src/bootstrap/sysv_integer_args.md` | `e019998826a2007980a2b4e843b1e01cc546492c6a9fd0226de71a9a77ecf700` |
| `claude-works/tests/test_sysv_integer_args.py` | `c1c889d9f312758970308bcabb3bc7df2f82532e7ce5743af7ab5484f3755e59` |
| `claude-works/deliveries/C9.md` | `6428b14d1d08e20c886d0be281db9cf15a7bf185ffd7d0b90ee44b71f1448e47` |
| `claude-works/src/bootstrap/parallel_moves.dg` | `f6e6563e9a7994f788f0ef00eb5cf47f194d05961067b4ce20e5fd3663a6c8eb` |
| `claude-works/src/bootstrap/parallel_moves.md` | `821319fca07c84beda9011b800ee7c29d5b0dbcf28914a9e0ef69a4c714a3302` |
| `claude-works/tests/test_parallel_moves.py` | `007d5c4fae1bee927c6758bcf342ed787c92a938680b44170d5146ec1f5a1fdc` |
| `claude-works/deliveries/C10.md` | `83ee93197b2e87210fa4865d9231093bd95162b80220727c9d0ddf9772ef87dc` |
| `claude-works/src/bootstrap/stack_slots.dg` | `eb6d21cf8e1099725d86048926efee272845404be3361dc809bf0121f4918312` |
| `claude-works/src/bootstrap/stack_slots.md` | `3ffea4a2e737ef00661f80ca05678f3a8fd1c12875728e90189cab8f93cc83fd` |
| `claude-works/tests/test_stack_slots.py` | `100f9057a7209796a7b67249d6a27108cd1a30e9cc7ee34ec99e08e01ca302c6` |
| `claude-works/deliveries/C11.md` | `03238f7e368e497f315a43a965a833347cfc8bbfab5647cd296634f6fe379091` |
| `claude-works/src/bootstrap/switch_cases.dg` | `b7c37bc138c0eb1903167cb0df5a9e8b416e98bfa8de4ee22e8ff3234a738887` |
| `claude-works/src/bootstrap/switch_cases.md` | `0a3533a0b2e31aafb0c2bb5ea9042976821dfba1f573da3ad246c6cbdb49e99f` |
| `claude-works/tests/test_switch_cases.py` | `b26d569df81c5236db2871cacf68db35035fd6406b730018f7fdf17f14d5108a` |
| `claude-works/deliveries/C12.md` | `be0a1586efe41c2157d1ee50e368a8038e68d7d07395a9a4ac32d4b5edb10346` |
| `claude-works/src/bootstrap/cleanup_plan.dg` | `655b2a50fbfd68b5af3593eb97d0e9c50e6efad09f9f8a0798a857df61b8f8d9` |
| `claude-works/src/bootstrap/cleanup_plan.md` | `cf26ddca3b148666eb39472fbe63d93ca7ae5ebcf9b8d634ff732b7d5cb02147` |
| `claude-works/tests/test_cleanup_plan.py` | `470192cb176ba8ed66ae1626a2089c2d7d4966df9dd7e849a7cd79a10a576e1d` |
