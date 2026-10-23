# G5METHODFIX1 — G5主线方法回归调用链同步完整支持契约

负责人：codex。状态：待领取。

G5INT1集成审查发现test_l3_method_native仍调用已拆分的旧Win64拒绝方法并期待五个已关闭gap。仅更新永久方法测试的G5完整路径断言及SysV测试调用，保留全部真实CPU/坏体oracle。由G5INT1完整51项冷复验和集成聚合门禁实际执行同一借用方法；本任务另用runner入口检查确认主线可加载，不重复冷构建。独立审查后结合G5INT1正式结果登记验收及集成。用户范围内必要关联修复，不新增功能，不运行OS/VM。

## 可修改文件

- `lang/tests/test_l3_method_native.py`
- `codex-works/deliveries/G5METHODFIX1.md`

## 定向验收

- `module:lang.tests.test_g5_runner_entry`

交付：`codex-works/deliveries/G5METHODFIX1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
