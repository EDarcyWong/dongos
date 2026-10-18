# LM2 — 简单文档：AI交付检查清单JSON

负责人：lmstudio。状态：待领取。

只生成一份简短中文JSON文档，不写业务代码。文件lmstudio-works/docs/handoff-checklist.zh-CN.json：顶层只有version和items，version=1，items恰好5个对象，各只有id/title/description。id顺序固定为scope、claim、test、delivery、review。title为1～12个字符，description为1～40个字符。五项分别说明只改授权文件；先领取并使用最新版本；只报告实际运行的测试；交付须附证据和限制；提交后等待独立复验，不能自行验收。不得声称测试通过，不含shell命令或模型配置。另在固定LM2.md写交付说明。测试由Codex提供，禁止修改。

## 可修改文件

- `lmstudio-works/docs/handoff-checklist.zh-CN.json`
- `lmstudio-works/deliveries/LM2.md`

## 定向验收

- `discover:lmstudio-works/tests:test_handoff_checklist.py`

交付：`lmstudio-works/deliveries/LM2.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
