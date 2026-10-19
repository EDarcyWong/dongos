# CX3 — 按NASM实际能力允许合法64位静态指针重定位

负责人：codex。状态：待领取。

NASM vendor 2.x supports reloc-abs-qword but compiler assembly warning guards use major>=3. Native semantic suite fails before executing on valid static Unicode.VERSION pointer dq. Extend existing warning capability probe to selectively permit supported absolute qword relocations, retain Wall/Werror and avoid unknown options; meaningful capability tests and actual native semantic rebuild prove it. No semantic failures may be counted as passing.

## 可修改文件

- `lang/tests/test_dongc.py`
- `lang/tests/test_nasm_compatibility.py`
- `codex-works/deliveries/CX3.md`

## 定向验收

- `module:lang.tests.test_nasm_compatibility`

交付：`codex-works/deliveries/CX3.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
