# LM4 — 简单文档：七个后端组件中文导航

负责人：lmstudio。状态：待领取。

只编写简短中文组件导航JSON，不写业务代码。文件lmstudio-works/docs/bootstrap-components.zh-CN.json：顶层只有version/items，version是整数1，items恰好7项，各只有module/title/summary/source。title为1～16字符中文，summary为1～48字符简短中文。
模块固定顺序和能力：cfg_reachability（控制流图合法性与可达性）；sysv_integer_args（仅SysV INTEGER标量及双字参数的位置规划，不是完整ABI）；parallel_moves（将并行复制转换为含临时位置的顺序复制）；stack_slots（向下增长栈帧的槽位布局）；switch_cases（有符号分支值排序和重复检查）；cleanup_plan（作用域退出清理顺序，不执行清理体）；nasm_bytes（原始字节编码为NASM db文本，不是完整后端）。module字段为bootstrap.加上述名字；source字段为lang/bootstrap/加上述名字再加.dg，路径相对code。严格按七项列出，不增删模块。
只按给定能力写导航说明，不声称完整后端、完整ABI、性能达标或L3自举完成，不含命令、模型配置或虚构测试通过声明。另写固定LM4交付说明，明确实际未运行测试。只允许JSON与交付两个文件；测试由Codex提供，禁止修改；不自行验收、不提交推送、不运行OS/VM。

## 可修改文件

- `lmstudio-works/docs/bootstrap-components.zh-CN.json`
- `lmstudio-works/deliveries/LM4.md`

## 定向验收

- `discover:lmstudio-works/tests:test_component_glossary.py`

交付：`lmstudio-works/deliveries/LM4.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
