# L3：C49 / C50 主线文件集成与组合验证

日期：2026-10-19。基线：`e5c97d4`。

本轮关闭两个已验收组件尚未进入主线源码目录的缺口。这里的“文件集成”指本地文件与可重复验证，不表示已提交、推送或修改协调器的验收/集成登记。

## 来源和文件

协调 CLI 的 `dongos status` 快照中，`claude:C49` 与 `claude:C50` 均为 `accepted rev10`；原交付、任务书、历史和状态不变，C52 / CR40 的 submitted 队列不变。

| 原交付 | 主线源码 | 主线永久测试 |
| --- | --- | --- |
| C49 | `lang/bootstrap/nasm_u64_select_function.dg` | `lang/tests/test_bootstrap_nasm_u64_select_function.py` |
| C50 | `lang/bootstrap/nasm_u64_forward_function.dg` | `lang/tests/test_bootstrap_nasm_u64_forward_function.py` |

两个 `.dg` 及同名 `.md` 从 `coordination/dongos_works/claude-works/src/bootstrap/` 逐字节复制。原生产源码 SHA256：

- C49：`9468a3e4ff93fe91a62a2e0e882e33336e33b1a3705ce4ce78aa36e06146eb65`
- C50：`579df059d1737f64c1c8ffded8c4cab00b161118d92e015eda619e3875982857`

永久测试仅调整 ROOT、SOURCE、DOC 和构建产物目录，保留原输入、独立 oracle、真实坏 Dong 和 R1 寄存器观察逻辑。原组件说明中的协作测试路径是历史来源；主线复现命令见下方。验收指纹中的 delivery Markdown 与当前文件只有 CRLF/LF 差异，恢复 CRLF 后 hash 精确匹配；被复制的六个文件本身与验收指纹完全相同。

## 新增真实组合

`lang/tests/test_bootstrap_select_forward_integration.py` 复用两个永久测试的真实 Dong emitter 构建入口，并单独构造一组端到端调用链：

1. Dong `forward.emit` 生成六入参包装函数，重排并丢弃两个哨兵实参。
2. 包装函数直接调用本次 Dong `select.emit` 生成的比较/双出口函数。
3. 同一 NASM 单元内每个函数有不同符号，每个分支块有全文件唯一 ID。
4. 独立 C oracle 根据原始入参与映射实现十种比较。每种条件各一真一假，共20个向量，覆盖0、最大u64、符号边界和不同高位返回值。signed比较用翻转最高位后的无符号排序，避免实现定义的有符号转换。
5. 手写桥从独立静态观察地址和宿主栈锚记录真实RAX、RBX/RBP/R12～R15、调用前后RSP、对齐和栈canary；捕获完后才恢复宿主状态，不依赖被测RBX或返回RSP寻找观察区。

另有两类错误接线负控：交换返回值参数映射，以及反转比较条件。它们仍由真实Dong emitter生成、组装和链接，正常调用/返回后由C数值oracle拒绝；不是编译失败、崩溃或文本差异，也不把输入接线变异称为生产源码变异。两模式各20条错误链都出现20个数值错误、0个ABI错误。

## 验证

工具：Python 3.12.14、Debian GCC 14.2.0、官方Debian NASM 2.16.03-1。NASM仅解包到测试环境临时目录，未安装到系统。测试中两模式均真实运行Linux x86-64 SysV；ELF64与COFF均组装，COFF组装不等于Windows原生执行。

在 `code/` 运行（NASM/GCC需在PATH，或使用已有的NASM/CC环境变量）：

```sh
python3 -m unittest \
  lang.tests.test_bootstrap_nasm_u64_select_function \
  lang.tests.test_bootstrap_nasm_u64_forward_function \
  lang.tests.test_bootstrap_select_forward_integration -v
```

主线两组件各4项、新组合1项，共9个不同测试通过、0 skip。保留容量/原子性、只读页、完整输入尾部别名、十类比较、真实callee调用、两出口RBX及其他既有真实坏Dong负控。组合6次可执行程序（2模式×好接线/错误映射/错误条件）全部满足预期。

最终将上述9项与模块加载、布局CLI、优化CLI、NASM兼容性22项合并执行：**31项通过、0 skip，122.423秒**。相邻C48直线函数4项、C51表达式AST→IR六项、D24循环三项也逐项通过。首次相邻回归命令误用了循环测试模块名，导致该命令保留一个ImportError；其余32项通过。随后使用正确的 `lang.tests.test_bootstrap_nasm_u64_loop_function` 单独补跑，3项通过、0 skip，64.526秒；不把首次失败命令写成整体通过。这些仍是定向检查，不替代全语言回归。

组件产物分别保存在 `build/test/bootstrap-nasm-u64-select-function/run-*/` 和 `build/test/bootstrap-nasm-u64-forward-function/run-*/`。组合产物在 `build/test/bootstrap-select-forward/run-*/`，包含生成汇编、ELF64/COFF对象、独立C源码、进程输出及summary.json。最终组合运行的输入指纹在编译前采集，覆盖两组件、完整只读依赖、宿主编译器、测试文件；编译/执行后完全一致。

## 边界

- 未改活动Python后端、原组件生产实现或任何在途任务。
- 组件为受限整函数发射器；callee存在且签名匹配、全文件block ID唯一仍由调用方保证。
- 本次未运行完整语言回归、OS/VM、QEMU、Windows原生或真实机器门禁；未执行stage1/stage2自编译或DongOS内编译/FLUSH/同盘重启。
- `build.py doctor` 的整机链仍缺LLVM lld-link/ld.lld和QEMU；UEFI固件未核对。本次宿主验证不需要它们，也不据此关闭L3。
- 原协调器状态保持accepted，后续发布和集成登记应按协调流程单独办理。
