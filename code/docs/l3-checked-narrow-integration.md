# L3：CR38 / CR41 受检与窄位宽算术文件集成

日期：2026-10-19。远端基线 `e5c97d4`，叠加在本地前两轮提交 `3b586bc` 上。

## 来源与范围

CR38（accepted rev9）和 CR41（accepted rev7）的生产与说明从 `coordination/dongos_works/cursor-works/src/bootstrap/` 逐字节复制到 `lang/bootstrap/`。原测试仅适配主线根目录、源码路径、构建目录。联合21个只读依赖均已 integrated，验收指纹精确匹配或只有 CRLF/LF 差异。原交付、协调器状态、C52/CR40 的 submitted 队列不改。

| 组件 | 主线生产 | 主线永久测试 |
| --- | --- | --- |
| CR38 | `nasm_checked_u64_function.dg` | `test_bootstrap_nasm_checked_u64_function.py` |
| CR41 | `nasm_narrow_arithmetic_function.dg` | `test_bootstrap_nasm_narrow_arithmetic_function.py` |

生产 SHA256：

- CR38：`01549469a9af6202521e35b05ef1e6145230c9794541f7f8213c3915775ab466`
- CR41：`3bfb8998a8fc01509d1679ec3050c74cdf18c1242bcab3fdc390ab5d211a96aa`

CR38生成 `Pair f(a,b)`，提供有/无符号64位 checked ADD/SUB/MUL 和 signed NEG。CR41生成8/16/32位 ADD/SUB，支持 checked 和 wrapping。两者返回 `{value,0}` 或 `{0,1}`，错误是正常函数返回，不是 panic 或硬件异常。

## 新增跨组件回归

`lang/tests/test_bootstrap_checked_narrow_integration.py` 编译真实 Dong emitter，并将其生成的两个完整函数放入同一 NASM 单元。手写测试桥实际把 CR38 的成功 RAX 传给 CR41，宽运算失败时保留 `{0,1}` 且不调用第二阶段。符号和块号在汇编单元内唯一。

关键语义：CR41在运算之前规范化两个输入，最后才对窄算术结果检查范围或回绕。因此本链是“宽受检计算→窄输入规范化→窄算术”，**不是宽到窄的checked转换**。例如宽乘积得到 `2^width` 后，CR41先将它规范为0；再无符号减1时，checked应失败，wrapping应返回该宽度最大值。

每模式24个主要向量：

- 每个8/16/32位宽度六条链，覆盖 signed上界ADD的checked/wrapping对照、unsigned规范化后SUB借位的checked/wrapping对照、signed下界SUB失败、带高位杂值的RHS规范化和跨零成功。
- 六个宽阶段失败，覆盖unsigned ADD/SUB/MUL、signed ADD/MUL/NEG。每条都必须跳过窄阶段。
- 独立C oracle使用有符号128位精确数学、无符号128位乘法，以及显式位掩码/符号扩展。避免宿主有符号溢出和实现定义的u64→i64转换，不调用生产oracle。
- 检查中间/最终Pair、第二阶段调用次数；从独立观察地址和宿主栈锚捕获两阶段保存寄存器、RSP、对齐和canary，捕获后才恢复宿主状态。

两个正常返回的安全负控：

1. 隔离副本里把CR41 checked路径的真实 `narrow.emit` 改成 `cast.emit`。九条窄范围错误链应被最终Pair断言逐条拒绝，中间宽Pair仍正确。
2. 测试桥忽略宽阶段错误，只在六条纯算术失败链上继续执行。最终Pair与调用计数都必须拒绝。该项是路由负控，不称作生产源码变异。

## 复现

在 `code/` 目录运行，NASM/GCC需在PATH，或设置测试支持的NASM/CC环境变量：

```sh
python3 -m unittest \
  lang.tests.test_bootstrap_nasm_checked_u64_function \
  lang.tests.test_bootstrap_nasm_narrow_arithmetic_function \
  lang.tests.test_bootstrap_checked_narrow_integration -v
```

测试产物分别在 `build/test/bootstrap-nasm-checked-u64-function/`、`build/test/bootstrap-nasm-narrow-arithmetic-function/` 与 `build/test/bootstrap-checked-narrow/run-*/`。组合 summary 记录编译前/执行后全部输入SHA、实际汇编/对象/C oracle/进程输出SHA和六次原生观察。

正式组件8项通过、0 skip（155.915秒）；新组合1项通过、0 skip（49.801秒）；模块加载、布局CLI、优化CLI和NASM兼容性22项通过、0 skip（1.017秒）。三次有效命令共31个不同测试通过。组合44项输入前后稳定，60项产物SHA已逐项复核。独立审查未发现必须修复项。只运行定向宿主检查，不代表完整语言回归、L3后端、stage1/stage2自举或系统启动完成。ELF64/Linux为真实运行平台，win64 COFF仅组装；不据此声称Windows运行。

首次组合命令误从仓库顶层执行，因找不到 `lang` 而在导入阶段失败，未运行测试；随后改从 `code/` 执行。这次启动失败与正式测试结果分开保留。

GitHub发布仍受403权限阻塞，按用户要求跳过，不重试其它写入端点；本地文件或提交不表示远端已合并。未修改用户电脑或部署。
