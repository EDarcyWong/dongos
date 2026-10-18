# CR2、CR7、D14～D18 与 LM7 集成

2026-10-18，通过已安装的 coordination stdio MCP 查询、定向复验和登记。Cursor 新交付 CR7 正式3项、LM7正式1项均通过、零skip、指纹稳定，人工审查后已验收；其余CR2和D14～D18沿用已验收的最新实物及回执。

## 主线实物与验证

七个模块及同名接口说明按验收hash原样复制到 `code/lang/bootstrap/`：nasm_rodata、sysv_return_plan、rel32_patch、string_table、data_pool_layout、cfg_postorder、phi_copy_plan。各有 `code/lang/tests/test_bootstrap_<模块>.py` 永久测试，只适配源码/构建路径。LM7固定JSON逐字节回写LM工作区及主线 `lang/tests/fixtures/decimal-known-vectors.json`，独立结构/补码检查成为永久测试 `test_bootstrap_decimal_vectors.py`。旧候选、交付、返修与验收历史保留。

首轮主线执行发现四项观察器的私有源码根与新增主线同名模块冲突，已保留失败日志与回执 `mainline-initial-*`。仅修永久测试导入路径：只暂存声明的只读依赖（CR1字节编码、C7节点类型、C9调度），无依赖的CR7不再添加整个lang根。原源码、观察断言、输入、负控协议均未改。

最终主线9个测试模块共24项通过、0skip、指纹稳定。包含22项七组件测试、LM7数据1项及新增原生组合1项；与正式验收重复的路径复跑不算新增功能。主线语义核心 semantic_types.dg 和既有 nasm_bytes.dg hash 保持不变。

组合测试 `test_bootstrap_data_backend_integration.py` 实际用DFS后序选择前驱，经phi复制及C9消环执行、SysV双字规划、字符串表去重标签、rel32回填、对齐原始常量池，最后用CR2/CR1发射NASM。debug/release原生执行、ELF64/COFF组装均通过，两模式真实NASM bin还原精确11字节 `a5fbffffffa500000b0a0c`，包含对齐填零。对外容量不足时缓冲区/计数不变、成功尾部和双端guard也通过。

## 状态范围

真实文件集成并通过验证后，才通过MCP登记8项integrated。这里指可导入主线组件、数据、永久测试及实际组合调用；生产Python编译器未替换为Dong，完整L3后端、CLI、stage1/stage2和客体自编译仍未完成。不启动Cursor CLI，不新增派单，没有OS/VM、全回归、提交、推送或关机。

## 证据

[最终主线回执](../.local/reviews/integration-7eb4d05e4fa8/mainline-result.json)、[日志](../.local/reviews/integration-7eb4d05e4fa8/mainline-unittest.log)、[逐文件映射与hash](../.local/reviews/integration-7eb4d05e4fa8/integration-files.json)。

- cursor:CR2：正式回执 `7d5997a9866e4351bda1934013ecf911`。
- cursor:CR7：正式回执 `798d88c0ddcd4579b9e3f691ba07d4d8`。
- deepseek:D14：正式回执 `111a0824e66c43d2890176d6e217cc3d`。
- deepseek:D15：正式回执 `0496c5fa74e54c44bc1fc2aa5ed1438c`。
- deepseek:D16：正式回执 `c958aa44304d48dcbf45b076e39bc81e`。
- deepseek:D17：正式回执 `fd991ffccdaa41b092ec318317f2f67e`。
- deepseek:D18：正式回执 `4be885fe70824013b046ef553a777c76`。
- lmstudio:LM7：正式回执 `987b960603354200accdb518c9091634`。
