# LM6 交付说明

## 状态
待复验

## 交付内容
- `lmstudio-works/fixtures/leb128-known-vectors.json`：固定12条LEB128已知向量。

## 测试命令
```bash
python -m pytest lmstudio-works/tests/test_leb128_vectors.py
```

## 限制与说明
- 本交付仅包含固定测试数据，不包含实现代码。
- 未运行测试，未进行自举验证。
- 未修改测试文件、任务书、README或调度器状态。
- 未提交、推送，未运行OS/VM。
- 等待协调器独立复验。
