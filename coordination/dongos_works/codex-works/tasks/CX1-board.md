# CX1 — 按NASM实际警告能力检测原生测试兼容参数

负责人：codex。状态：待领取。

本机NASM 2.16.03回移了reloc-rel-dword警告，当前仅按major>=3设置参数，C38独立复验在汇编前中断。仅修公共测试工具的能力检测，保留-Wall/-Werror及其它警告；为包含警告的新2.x与不支持警告的旧版本添加有意义回归，并实际复跑C37/C38定向测试。不得改组件生产/测试来掩盖失败，不运行OS/VM/全语言回归。

## 可修改文件

- `lang/tests/test_dongc.py`
- `lang/tests/test_nasm_compatibility.py`
- `codex-works/deliveries/CX1.md`

## 定向验收

- `module:lang.tests.test_nasm_compatibility`

交付：`codex-works/deliveries/CX1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
