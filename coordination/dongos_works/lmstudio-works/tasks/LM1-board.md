# LM1 — 单函数：任务标签空白规范化

负责人：lmstudio。状态：待领取。

实现纯Python函数 collapse_whitespace(text: str) -> str，位于lmstudio-works/src/task_text.py。将任意连续Unicode空白替换成单个ASCII空格，去除首尾空白；保留其它字符与顺序。空字符串/全空白返回空串；非str抛TypeError。不要截断、不要添加依赖、I/O、网络或副作用。推荐仅使用str.split与join和显式类型检查。只做这个函数，不扩展接口。交付说明写lmstudio-works/deliveries/LM1.md，说明实现、限制、待协调器执行的测试，不能声称已经跑测试。测试由Codex编写且禁止修改。

## 可修改文件

- `lmstudio-works/src/task_text.py`
- `lmstudio-works/deliveries/LM1.md`

## 定向验收

- `discover:lmstudio-works/tests:test_task_text.py`

交付：`lmstudio-works/deliveries/LM1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
