# G5TAG1 — G5 optional/result/error/enum 全流水线与差分闭环

负责人：codex。状态：待领取。

用户授权继续补齐G5。独立候选补齐optional/result的表示、隐式包装、null/try/orelse/错误值、enum构造与match，并保持已有方法/defer/for/SysV语义；运行真实Dong frontend→lower→NASM与独立seed/C oracle，debug/release、内存/ABI/控制流/失败原子性及真实编译链接正常运行语义坏体。前端候选以当前主线为基准，和DeepSeek的L3EXTUNSAFE1独立，不改对方文件；后续合并必须保留其已验收修复。只运行定向测试，无OS/VM/commit/push，保留输入/命令/产物SHA和零skip独立复验。此项完成后仍继续Win64、函数指针、内存内建/atomic/asm和全矩阵，不提前宣布G5整体完成。

## 可修改文件

- `codex-works/g5-tag/src/bootstrap/semantic_types.dg`
- `codex-works/g5-tag/src/bootstrap/program_ir.dg`
- `codex-works/g5-tag/src/bootstrap/lower_program.dg`
- `codex-works/g5-tag/src/bootstrap/nasm_program.dg`
- `codex-works/tests/test_g5_tagged_native.py`
- `codex-works/g5-tag/docs/tagged.md`
- `codex-works/deliveries/G5TAG1.md`

## 定向验收

- `discover:codex-works/tests:test_g5_tagged_native.py`

交付：`codex-works/deliveries/G5TAG1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
