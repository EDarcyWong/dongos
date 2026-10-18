# LM5 交付说明

## 交付文件
1. `lmstudio-works/fixtures/utf8-boundary-cases.json`：UTF-8 边界测试夹具数据。
2. `lmstudio-works/deliveries/LM5.md`：本交付说明文档。

## 数据内容
- 顶层字段：`version`（整数 1）、`cases`（数组，恰好 12 项）。
- 每项字段：`id`、`hex`、`valid`、`scalar_count`。
- 前 6 项 `valid` 为 `true`，`scalar_count` 为整数（empty 为 0，其余为 1）。
- 后 6 项 `valid` 为 `false`，`scalar_count` 为 `null`。
- `hex` 为不含空格的小写十六进制字符串，无 `0x` 前缀。

## 测试命令
```bash
python -m pytest lmstudio-works/tests/test_utf8_boundary_cases.py -v
```

## 限制与说明
- 本交付仅生成测试数据文件，未编写实现代码，未修改测试文件。
- 未运行测试，未进行自行验收。
- 结构及严格 UTF-8 校验由 Codex 提供，模型不得修改测试。
- 不提交、不推送、不运行 OS/VM 或业务命令。
- 状态：待复验。
