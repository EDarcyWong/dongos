# LM4 交付说明

## 交付内容
- `lmstudio-works/docs/bootstrap-components.zh-CN.json`：七个后端组件中文导航，顶层仅 `version` 与 `items`，`version` 为整数 1，`items` 恰好 7 项，顺序固定，每项仅含 `module`/`title`/`summary`/`source`。

## 限制
- 仅按给定能力编写导航说明，不声称完整后端、完整 ABI、性能达标或 L3 自举完成。
- 不含命令、模型配置或虚构测试通过声明。
- 实际未运行测试；测试由 Codex 提供，禁止修改。
- 不自行验收、不提交推送、不运行 OS/VM。

## 测试命令
- `discover:lmstudio-works/tests:test_component_glossary.py`（由协调器另行运行）

## 状态
- 待复验