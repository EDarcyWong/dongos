# L3：CR39 / D25 短路与switch文件集成

日期：2026-10-19。远端基线 `e5c97d4`，叠加本地前三轮提交 `214cc51`。

## 来源与边界

CR39 accepted rev7、D25 accepted rev5；联合23个只读依赖均已 integrated，验收指纹精确匹配或仅CRLF/LF转换。生产和说明逐字节复制自 `coordination/dongos_works/cursor-works/src/bootstrap/` 与 `deepseek-works/src/bootstrap/`，组件永久测试只适配根目录、源码路径和构建目录。

| 组件 | 主线生产 | 永久测试 |
| --- | --- | --- |
| CR39 | `lang/bootstrap/nasm_short_circuit_function.dg` | `lang/tests/test_bootstrap_nasm_short_circuit_function.py` |
| D25 | `lang/bootstrap/nasm_i64_switch_function.dg` | `lang/tests/test_bootstrap_nasm_i64_switch_function.py` |

生产SHA256：
- CR39：`cf85babe6cf5f43a135284dbdd34e5e733735706ff8f35671e62be965906d89c`
- D25：`71bbe445d7a36d4e72ccd539c8ccecba447a0155d9c00d6a879e08cc998cf0c4`

CR39生成真正零参BOOL函数，完整64位非零为真，按AND/OR决定是否调用右目标。D25生成以i64 selector分发并返回完整u64结果的函数。这里只集成已验收受限整函数模块及组合检查，不新增AST/CFG降级，不宣称完整后端或自举完成。原交付、协调器状态、C52/CR40在途队列不变。

## 新增真实组合

`lang/tests/test_bootstrap_short_switch_integration.py` 建立：真实Dong短路函数→可观察调用thunk→真实Dong switch函数。

测试thunk只设置selector、记录调用和返回值，并原样把RAX交回短路函数；分支、真假规范化、switch分发及返回块全部来自Dong生产实现。每个thunk调用前对齐SysV栈，返回后重新取得独立观察指针，不依赖caller-saved寄存器跨调用保存日志地址。

每模式16条固定链覆盖AND/OR全部真假路径、无序MIN/MAX/−1/0/完整高位selector、左右default，以及0x100、最高位、MAX等完整非零返回。C oracle独立用字典式完整位模式比较计算switch结果，再计算短路规则。

独立检查：

- 按实际调用序号记录的左右先后顺序和总次数。
- 每个被调用thunk的完整64位RAX，避免非零→另一个非零的错误关联被最终bool掩盖。
- 真实最终BOOL必须精确为0或1。
- switch调用前后的动态callee-saved寄存器/RSP/对齐/canary，以及外层短路函数的完整ABI状态。捕获真实状态之后才恢复宿主/调用者状态。

三个真实生产负控均正常返回：

1. 反转CR39短路分支：16条链的调用轨迹全部错误，8个BOOL错误、8个完整值日志错误。
2. 只交换CR39两个实际调用目标，重放3条AND/双方均真链：BOOL、完整返回值及ABI均仍正确，只出现3个调用顺序错误。它专门证明顺序检查的敏感性。
3. D25把Arm结果轮换到下一Arm，重放6条OR链：完整值日志6项全部拒绝，调用轨迹4项错误，但BOOL仅1项错误，直接证明不能只验最终bool。

独立审查发现初版日志按左右固定槽写入不足以证明调用顺序；已在最终测试前改为按实际计数记录并加入第2项负控。初版通过记录不是最终顺序证明。

## 复现

在 `code/` 内运行，NASM/GCC需在PATH，或设置NASM/CC环境变量：

```sh
python3 -m unittest \
  lang.tests.test_bootstrap_nasm_short_circuit_function \
  lang.tests.test_bootstrap_nasm_i64_switch_function \
  lang.tests.test_bootstrap_short_switch_integration -v
```

产物在 `build/test/bootstrap-nasm-short-circuit-function/`、`build/test/bootstrap-nasm-i64-switch-function/`、`build/test/bootstrap-short-switch/run-*/`。summary记录全部生产/说明/永久测试/传递依赖/宿主编译器前后SHA，以及实际汇编、ELF64/COFF对象、独立C oracle、进程输出SHA。

本轮组件首次在仓库顶层误启动，找不到lang而在导入阶段失败；更正为code目录后7项通过、0 skip（141.858秒）。最终四组受影响回归合计56个不同测试全部通过、0 skip：C49/C50及公共检查31项（121.026秒）、CR42/D27与组合8项（226.319秒）、CR38/CR41与组合9项（220.892秒）、本轮CR39/D25与修正后组合8项（240.818秒）。四组并行运行，未将时长相加当作墙钟耗时。本组合最终8次原生观察覆盖两模式及三个真实生产负控，全部按预期；输入指纹稳定，产物SHA已复核。真实运行是Linux x86-64 SysV，COFF仅组装；未运行Windows、OS/VM、完整语言回归或stage1/stage2自举。

本轮结束后，本次已确认的安全候选C49/C50、CR42/D27、CR38/CR41、CR39/D25均已完成主线文件接入；不是对所有项目任务的完成声明。GitHub发布403、submitted C52/CR40和完整后端/整机门禁继续跳过。未重试发布、未部署、未同步用户电脑。
