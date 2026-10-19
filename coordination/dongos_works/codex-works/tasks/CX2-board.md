# CX2 — 补齐optional/result match类型与确定初始化语义

负责人：codex。状态：待领取。

Extend native semantic_types match beyond bool to optional/result null/some/ok/err payload typing, exhaustive/duplicate checks and known-tag definite-initialization intersections. Preserve workspace ABI and explicit unsupported enums/methods. Real native positive/error cases, host semantic comparison, actual bad Dong semantic controls, source stability and zero skips required. Remaining semantic gap only, not full L3 completion.

## 可修改文件

- `lang/bootstrap/semantic_types.dg`
- `lang/bootstrap/semantic_types.md`
- `lang/tests/test_bootstrap_semantic_runtime.py`
- `codex-works/deliveries/CX2.md`

## 定向验收

- `module:lang.tests.test_bootstrap_semantic_runtime`

交付：`codex-works/deliveries/CX2.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
