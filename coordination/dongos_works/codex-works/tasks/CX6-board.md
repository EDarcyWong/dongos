# CX6 — [P0/L3] 修复NASM 3分组帮助的警告能力探测并复核集成入口

负责人：codex。状态：待领取。

所属阶段：P0工具链维护，关联L3整函数主线复验。源码核对发现lang/tests/test_dongc.py:nasm_flags只读取nasm -h；本机NASM3.02把reloc-rel-dword及reloc-abs-qword放在-h -w分组帮助中，主线C52测试在setUpClass组装时因合法RIP相对重定位被-Werror拒绝，0tests（build/test/bootstrap-nasm-u64-module/run-d0a567604d4b）。这是CX1能力探测在新帮助格式下的后继兼容修复，不重做已验收组件。仅改声明文件：按实际帮助格式探测两个完整警告名，兼容旧NASM不支持-h -w或未知参数的情况，保留-Wall/-Werror及其它警告；不得按版本硬猜、不无条件关闭未知警告、不吞真实探测失败。测试覆盖旧平铺帮助、新分组帮助、名字前缀误匹配、两个警告独立、真实失败传播，以及本机NASM合法RIP/绝对64位重定位实际组装与其它警告仍为错误。只跑定向兼容测试，不跑OS/VM。交付后须独立复验。

## 可修改文件

- `lang/tests/test_dongc.py`
- `lang/tests/test_nasm_compatibility.py`
- `codex-works/deliveries/CX6.md`

## 定向验收

- `module:lang.tests.test_nasm_compatibility`

交付：`codex-works/deliveries/CX6.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
