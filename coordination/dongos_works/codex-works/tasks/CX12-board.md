# CX12 — [L3] 原生汇编器使用有界短位移编码以保持2MiB执行上限

负责人：codex。状态：待领取。

替代未实施CX11的平台检查误配。当前56MiB单arena/64KiB guarded栈原生自编译闭包已双stage ELF一致，但release2142264字节超既有2MiB EXEC上限；closed-call过滤后仍2121768。保持执行文件上限和64MiB不扩大。为x86_encode新增显式encode_compact API：base非RIP内存0/有符号disp8/disp32最短有效形式，RBP/R13零位移必须disp8零，RSP/R12需SIB，RIP始终disp32；现有encode字节契约完全不变。native_assembler内部采用compact，两遍长度稳定，禁止rel32隐式缩短/地址截断。永久NASM独立字节oracle与debug/release双格式、边界/输入输出canary、原始encode兼容、实际坏RBP与截断负控；同一跨平台测试直接执行nativeassembler并装载生成ELF运行验证，不能skip。旧Linux限定测试不作为本机正式规格。独立审查+正式稳定复验；闭包大小和固定点另记真实证据，不宣称guest完成。

## 可修改文件

- `lang/bootstrap/x86_encode.dg`
- `lang/bootstrap/native_assembler.dg`
- `lang/tests/test_bootstrap_x86_compact.py`
- `docs/l3-compact-x86.md`
- `codex-works/deliveries/CX12.md`

## 定向验收

- `module:lang.tests.test_bootstrap_x86_compact`

交付：`codex-works/deliveries/CX12.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
