# LM5 — 简单数据：12条UTF-8边界测试夹具

负责人：lmstudio。状态：待领取。

只生成一个小型UTF-8测试数据JSON，不写实现代码，不修改测试。文件lmstudio-works/fixtures/utf8-boundary-cases.json，顶层只有version/cases，version为整数1，cases恰好12项，每项只有id/hex/valid/scalar_count。
严格按下面顺序填写（hex为不含空格的小写十六进制，ASCII的41保留数字，不加0x）：empty:""；nul:00；ascii:41；han:e6b189；emoji:f09f9880；max:f48fbfbf；overlong:c0af；continuation:80；surrogate:eda080；too_high:f4908080；truncated:e282；bad_continuation:e228a1。
前六项valid为JSON布尔true：empty的scalar_count为整数0，其余五项为整数1。后六项valid为JSON布尔false，scalar_count为JSON null。这些是给定分类数据，不要新增案例、Unicode规范化或字符串转义字段，不把true/false/null写成字符串。不能声称已运行测试。
另在固定LM5交付里说明两个文件、实际未运行测试及限制。只有JSON和交付两个授权文件；结构及严格UTF-8校验由Codex提供，模型不得改测试。不自行验收、不提交推送，不运行OS/VM或业务命令。

## 可修改文件

- `lmstudio-works/fixtures/utf8-boundary-cases.json`
- `lmstudio-works/deliveries/LM5.md`

## 定向验收

- `discover:lmstudio-works/tests:test_utf8_boundary_cases.py`

交付：`lmstudio-works/deliveries/LM5.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
