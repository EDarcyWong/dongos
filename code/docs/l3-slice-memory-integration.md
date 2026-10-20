# L3：CR42 / D27 切片与索引访存文件集成

日期：2026-10-19。远端基线：`e5c97d4`；本轮叠加在本地 C49/C50 提交 `f4d39e5` 上。

本轮将已验收但尚未进入主线源码目录的 CR42 切片视图构造和 D27 有界索引访存整函数模块复制到 `lang/bootstrap/`，并增加永久组合回归。原交付和协调器状态不变；文件集成不等于 GitHub 发布、完整 L3 或自举完成。

## 来源

协调 CLI 状态快照：`cursor:CR42 accepted rev7`、`deepseek:D27 accepted rev5`。23 个只读依赖均已 integrated，源码与验收指纹精确一致或只有 CRLF/LF 差异。C52、CR40 的 submitted 队列未修改。

| 组件 | 主线生产与说明 | 主线永久测试 |
| --- | --- | --- |
| CR42 | `lang/bootstrap/nasm_slice_view_function.dg` / `.md` | `lang/tests/test_bootstrap_nasm_slice_view_function.py` |
| D27 | `lang/bootstrap/nasm_indexed_memory_function.dg` / `.md` | `lang/tests/test_bootstrap_nasm_indexed_memory_function.py` |

生产和说明逐字节复制自 `coordination/dongos_works/cursor-works/src/bootstrap/` 与 `deepseek-works/src/bootstrap/`。两个生产 SHA256：

- CR42：`3147e80a27705c2f2797e32f9ac1ed40b57678b823af49799dd651154d6e1145`
- D27：`2d040bfe6e59b522fdafcfee8155af791fa44937698233b1e6acee5d3b3a6194`

永久测试仅调整根目录、生产路径和构建产物目录；保留原容量/原子性、只读页、别名、真实坏 Dong 与完整原生 ABI 观察。原说明中的协作测试路径为历史来源，主线复现命令见下文。

## 真实组合及安全边界

`lang/tests/test_bootstrap_slice_memory_integration.py` 从实际 Dong emitter 产生完整函数，再将 CR42 返回的指针和长度直接传给 D27。手写汇编桥仅是测试接线，不是新的生产后端 lowering，也不宣称源语言切片表达式已经接入完整 Dong 后端。

必须区分两种 Pair：CR42 成功返回 `{base,length}`，失败返回 `{0,UINT64_MAX}`；D27 返回 `{value,0}` 或 `{0,1}`。桥检查 CR42 的失败哨兵，直接映射为 `{0,1}` 并跳过访存调用，不能把 `{0,MAX}` 当作有效大切片。合法 NULL 空视图 `{0,0}` 可进入 D27，并应被其索引门禁拒绝。

每模式24个主要向量覆盖：

- 七种 LOAD 宽度/符号组合与四种 STORE 宽度，非零子视图起点、首/末合法元素、低位截断与符号扩展。
- 四种 STORE 在 `index == subview.length` 拒绝，即使该地址仍处于父数组真实分配内。
- 空非 NULL / NULL 视图、逆序范围、超父范围、非空 NULL、长度乘法溢出、完整父视图终点溢出。
- 独立 C oracle 检查中间 Pair、最终 Pair、访存调用次数，以及整个320字节父缓冲区（包含左右保护区）。
- 独立观察地址和宿主栈锚捕获两次调用后的 RBX/RBP/R12～R15、RSP、对齐与 canary；捕获后才恢复宿主状态。

两种负控均正常原生返回，不以崩溃或编译失败作为证据：

1. 在隔离副本中将 CR42 的 `hi-lo` 真实生产表达式发射改为 `hi+lo`，只执行四个物理安全的父数组 STORE 向量。错误长度会放行子视图边界外、父分配内的写入，独立 oracle 同时检测中间 Pair、最终 Pair 和完整内存错误。
2. 对五个失败视图错误映射为成功状态，但仍跳过访存。oracle 应检测全部五个最终 Pair 错误、零内存改动与零访存调用。此项是测试接线负控，不称作生产源码变异。

## 复现和验证

在 `code/` 内运行，NASM/GCC 需位于 PATH，或使用测试支持的 NASM/CC 环境变量：

```sh
python3 -m unittest \
  lang.tests.test_bootstrap_nasm_slice_view_function \
  lang.tests.test_bootstrap_nasm_indexed_memory_function \
  lang.tests.test_bootstrap_slice_memory_integration -v
```

两组件合计7项通过、0 skip（162.879秒），新增组合1项通过、0 skip（59.142秒）。另跑模块加载、布局CLI、优化CLI、NASM兼容性与前轮forward→select组合，共23项通过、0 skip（16.815秒）。本轮三次有效命令合计31个不同测试通过；并非一次完整语言测试。独立审查未发现阻塞问题，组合46项输入指纹稳定、60项产物SHA均复核匹配。

测试在 debug/release 两模式真实执行 Linux x86-64 SysV；同时组装 ELF64 和 win64 COFF。COFF 组装不代表 Windows 原生执行。

组件产物在 `build/test/bootstrap-nasm-slice-view-function/` 和 `build/test/bootstrap-nasm-indexed-memory-function/`；组合在 `build/test/bootstrap-slice-memory/run-*/`，包括实际汇编、对象、独立 C oracle、进程输出、输入前后 SHA 与产物 SHA 的 `summary.json`。输入指纹覆盖生产、说明、永久测试、完整导入闭包和 Python 编译器，编译前与执行后对比。

## 未覆盖与发布状态

- 原组件 unsafe 契约仍有效：有效索引的实际映射、读写权限和足够父分配由上游保证。CR42 的地址检查不证明操作系统内存权限。
- 未改变活动 Python 后端或其它负责人任务；未登记协调器 integrated。
- 未运行完整语言回归、stage1/stage2 自编译、DongOS/VM、QEMU 或真实机器启动。LLVM 链接器/QEMU 等整机依赖仍缺失。
- GitHub 发布已明确受阻：命令行无可用 GitHub 凭据，连接器返回403权限不足。按用户要求跳过，不重试其它写入端点、不绕过保护；本地提交和补丁不是远端合并证据。
