# LM7 交付说明

## 任务范围
- 仅完成固定数据任务：新增 `lmstudio-works/fixtures/decimal-known-vectors.json`。
- 不写实现、不写测试、不承担编译器修复。
- 不运行 OS/VM、不执行全回归、不提交推送、不自行验收、不修改索引。

## 交付文件
1. `lmstudio-works/fixtures/decimal-known-vectors.json`
   - 顶层字段：`version`（整数 1）、`cases`（数组，恰好 8 项）。
   - 每项字段：`id`、`width`（整数）、`signed`（布尔）、`raw`（字符串）、`text`（字符串）。
   - 顺序与内容严格遵循任务书指定，未增删项目或字段。
   - `raw` 与 `text` 均为十进制字符串，未改写为 JSON 大整数，无前导零、空白或加号。

2. `lmstudio-works/deliveries/LM7.md`
   - 本交付说明文件。

## 测试状态
- **测试未运行。**
- 未执行 `discover:lmstudio-works/tests:test_decimal_vectors.py` 或任何相关测试命令。
- 不虚构测试通过结果。
- 测试由协调器另行运行，本交付不自行验收。

## 限制声明
- 未声称后端或自举完成。
- 未修改任务书、README 或调度器状态。
- 未访问或修改原项目目录。
- 未运行 OS/VM 或全回归。
- 未提交或推送任何内容。

## 状态
- 待复验。
