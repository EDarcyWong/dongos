# LM1 交付说明

## 实现
- 文件：`lmstudio-works/src/task_text.py`
- 函数：`collapse_whitespace(text: str) -> str`
- 逻辑：
  1. 显式类型检查：若 `text` 不是 `str`，抛出 `TypeError`。
  2. 使用 `text.split()` 按任意 Unicode 空白分割，自动去除首尾空白并将连续空白视为分隔符。
  3. 使用 `" ".join(...)` 以单个 ASCII 空格重新连接。
  4. 空字符串或全空白字符串返回空字符串。

## 限制
- 仅实现该单一函数，不扩展接口。
- 无 I/O、网络、副作用或额外依赖。
- 不截断内容，保留非空白字符及其顺序。
- 未自行运行测试；测试由协调器执行。

## 待协调器执行的测试
- 测试文件：`lmstudio-works/tests/test_task_text.py`
- 建议命令：`python -m pytest lmstudio-works/tests/test_task_text.py -v`
- 覆盖点：
  - 普通字符串空白折叠
  - 首尾空白去除
  - 连续多空白折叠为单空格
  - 空字符串返回空字符串
  - 全空白字符串返回空字符串
  - 非 str 输入抛出 TypeError
  - Unicode 空白处理

## 状态
- 待复验
