# D5 — DeepSeek 新任务

负责人：DeepSeek。状态：已验收（Codex，2026-10-17）。

## 最新验收结论

独立汇编回调补测已复验，原要求关闭。D5/D6 定向 4 项通过，完整回归通过 353 项宿主测试和 5 次 QEMU 启动，见 [复验记录](../reviews/2026-10-17-D5-D6-recheck.md)。下方保留原任务和历史补测要求，不代表仍待处理。

## Codex 复验与补测要求

独立复跑 `python -m unittest lang.tests.test_std_fmt -v`，2 项通过（1.202s）。实现暂未发现功能缺陷；原任务要求的独立回调 ABI 验证尚未覆盖，最终验收前请补齐：

- 当前回调目标 `host_sink` 也由 Dong 编译器生成，C 只观察最外层返回结果。新增独立 NASM 回调，检查切片的 RDI/RSI 参数、原始 UTF-8/NUL 字节、调用次数，并返回显式 RAX/RDX 成功/失败结果。可由 NASM 调用导出的 Dong 包装函数传入该回调，避开本机 GCC 函数指针 ICE；不要因此修改编译器的 extern 类型限制。
- 用一个不同于 `BufferTooSmall` 的测试错误号验证 `emit` 原样传播，且与导入的 `core.errors` 同时链接。该错误只定义在测试临时模块，不新增无用途的公共库错误码。
- 保留原有整数极值、容量失败不写入与重叠复制测试，重跑 debug/release 原生测试及 ELF64/COFF 组装；在 `deliveries/D5.md` 追加实际记录，状态改为“已补测，待 Codex 复验”。见 [D5 审查记录](../reviews/2026-10-17-D5.md)。

## D5：实现 `core.fmt`

编译器侧错误结果与 try 已通过最终验收，本任务现在可执行。模块为 `core.fmt`，依赖共享模块 `core.errors`：

```text
// core.errors: 本次明确分配的标准库错误编号，其他库须导入复用。
pub error BufferTooSmall=0x0100_0001;

// core.fmt:
pub fn decimal(value:u64,output:[]u8)!usize
pub fn signed_decimal(value:i64,output:[]u8)!usize
pub fn hexadecimal(value:u64,output:[]u8)!usize
pub fn write(bytes:[]const u8,output:[]u8)!usize
pub unsafe fn emit(bytes:[]const u8,sink:fn([]const u8)!void)!void
```

- 返回实际写入字节数，不附加 NUL；十六进制使用小写，不加 0x，不补零，0 输出一个 0。有符号十进制要正确处理 i64 最小值。
- 容量不足返回共享模块中的 BufferTooSmall，并保持输出缓冲区不变；先计算容量再写，禁止部分写入后报告成功或截断。
- write 按字节复制，保留 UTF-8 和内嵌 NUL，明确源目标重叠契约；可复用 D1 的 move 语义。
- emit 调用调用者提供的有效 SysV 回调，传播其错误；无全局输出设备、隐式分配、可变参数或格式字符串解释器。
- 测试包括各整数极值、每种容量边界、空输出、错误编号传播、回调次数与原始字节一致性。用 C/汇编独立核对双字返回值与回调 ABI；同时验证与其他模块链接后错误编号仍唯一。



## 执行与交付约束

- 完整协作边界与通用验收要求见 [总清单](../deepseek-work-list.md)；只修改本任务分配的标准库、测试与说明文件。
- 不修改 `lang/dongc/`、P1 内核或构建入口；发现编译器缺陷时提交最小源码和实际诊断。
- 真实运行 debug/release 原生测试及 ELF64/COFF 组装；未执行的部分明确列为未验证。
- 完成后新增 `deepseek-works/deliveries/D5.md`，记录文件、命令、结果与限制，再更新本任务和总清单状态。
- 不覆盖其他任务或既有交付记录，不提交或推送。
