# LM8 交付说明

## 任务
最简单固定数据录入：8条NASM基址位移文本。

## 交付文件
1. `lmstudio-works/fixtures/memory-operand-known-vectors.json`
   - 顶层字段：`version` (整数 1), `cases` (数组，8项)。
   - `cases` 中每项包含：`id`, `base` (整数), `disp` (字符串), `text` (字符串)。
   - 数据严格按照任务书要求录入，`disp` 保持为字符串格式，未进行数值转换。

2. `lmstudio-works/deliveries/LM8.md`
   - 本交付说明文件。

## 测试状态
**未运行测试。**

根据任务要求，本任务仅进行固定数据录入，不编写实现或测试代码。独立检查由 Codex 维护，测试命令 `discover:lmstudio-works/tests:test_memory_operand_vectors.py` 由协调器另行运行。本交付不包含任何测试执行结果，禁止编造通过或自举完成。

## 限制与说明
- 仅修改了允许的两个文件路径。
- 未修改主线、他人文件、索引、任务书、README 或调度器状态。
- 未运行 OS/VM、AI CLI、全回归、提交推送或自行验收。
- 数据仅供后续可选补充，不依赖 Cursor 任务。

## 状态
待复验。
