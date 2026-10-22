# G5ALIGN1 — G5 高对齐局部对象及真实组合栈预算

负责人：codex。状态：待领取。

用户授权的G5完整语言范围要求支持种子既有align(32..1024等)局部对象。独立候选接续G5TAG1/G5EXEC1：显式IR帧对齐元数据保持公开IR描述符大小，RBP保留栈参数，R12对齐帧基址并保存恢复，精确对象地址/复制/嵌套调用/普通与Win64桥组合栈预算<=4096，真实seed/Dong/C差分、独立坏体、容量/别名/失败原子性和源码稳定零skip。候选结果合并前需同步所有在途修复。无OS/VM/CLI/提交推送，正式独立复验后才验收并真实集成，整体G5最终矩阵仍另验。

## 可修改文件

- `codex-works/g5-align/src/bootstrap/semantic_types.dg`
- `codex-works/g5-align/src/bootstrap/program_ir.dg`
- `codex-works/g5-align/src/bootstrap/lower_program.dg`
- `codex-works/g5-align/src/bootstrap/nasm_program.dg`
- `codex-works/tests/test_g5_alignment_native.py`
- `codex-works/g5-align/docs/alignment.md`
- `codex-works/deliveries/G5ALIGN1.md`

## 定向验收

- `discover:codex-works/tests:test_g5_alignment_native.py`

交付：`codex-works/deliveries/G5ALIGN1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
