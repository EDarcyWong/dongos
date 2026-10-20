# LM9 — 最简单固定数据：C48 u64 IR的8个操作码

负责人：lmstudio。状态：待领取。

只做最简单固定数据录入，写一个JSON及交付两个文件，不写实现或测试。文件lmstudio-works/fixtures/u64-ir-operation-codes.json。
顶层恰好version/operations两个字段且按此顺序，version为整数1；operations恰好如下顺序8项，每项恰好name/code两个字段且按此顺序，name为字符串，code为JSON整数：
CONST 0
COPY 1
ADD 2
SUB 3
AND 4
OR 5
XOR 6
IMUL 7
UTF-8 JSON，不增删字段/项目，不改顺序，不把code写成字符串。独立检查已由协调者维护（lmstudio-works/tests/test_u64_ir_operation_codes.py），不修改检查文件；数据仅供后续可选补充。另写lmstudio-works/deliveries/LM9.md，说明固定数据录入，未运行测试明确写未运行，禁止编造通过或自举完成。
通过自己的worker MCP查看最新rev、领取、实际落盘后提交；没有文件工具则说明并释放，不能以聊天正文冒充文件。LM Studio同时仅一项最简单任务。不改主线/他人/索引，不运行OS/VM、AI CLI、全回归、提交推送或自行验收。

## 可修改文件

- `lmstudio-works/fixtures/u64-ir-operation-codes.json`
- `lmstudio-works/deliveries/LM9.md`

## 定向验收

- `discover:lmstudio-works/tests:test_u64_ir_operation_codes.py`

交付：`lmstudio-works/deliveries/LM9.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
