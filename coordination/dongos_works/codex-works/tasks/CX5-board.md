# CX5 — 消除NASM vendor alignb宏警告栈不兼容并保持BSS对齐

负责人：codex。状态：待领取。

Actual shell native test fails before execution because installed NASM2.16.03 alignb macro expands unsupported [warning push/pop] under Wall/Werror. Emit explicit section-relative BSS padding and correct section base alignment instead of that macro; preserve full global alignment/zero fill. Test published ELF/COFF section alignment and native64-aligned globals plus existing global/alignment suites. Do not disable unknown-warning or other warnings. No OS/VM.

## 可修改文件

- `lang/dongc/emitter.py`
- `lang/tests/test_bss_compatibility.py`
- `codex-works/deliveries/CX5.md`

## 定向验收

- `module:lang.tests.test_bss_compatibility`
- `module:lang.tests.test_globals_native`
- `module:lang.tests.test_alignment_native`

交付：`codex-works/deliveries/CX5.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
