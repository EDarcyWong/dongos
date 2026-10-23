# P2HARNESS28 — 更新实际 SMP 服务回归夹具以覆盖 LARGE 接线依赖

负责人：codex。状态：待领取。

P2SMP27 独立作业 509fef4db16648e3af0557212591fe9d 的 diagnostics/entry 已通过，旧 test_user_smp_services 抽取新 services.enable_smp/project 后缺少 resources.Block/LargeStorage/large_poll/large_try 夹具依赖，解析即失败。仅更新该旧回归夹具：仍抽取真实生产 enable_smp/project/callbacks 和真实 Catalog/Domain/queue，保留十项真实坏源码、exit/fault/gui 场景和 BSP/BKL/Frame/退休前撤销约束；补真实 LargeTicket/LargeStorage/Context/large_poll 类型及受限、对齐、清零的 RAM resources.allocate 边界。LARGE 事务本回归不启用；任何请求/ready 非零须失败，回执明确该边界及不证明实际 LARGE/VM。不得改生产代码、公共probe、copy_graph或放宽独立预言/编译告警。采集源码/工具前后SHA、命令原始输出及对象/执行文件SHA，零skip。执行者不运行编译、测试、VM，由协调器独立复验后验收集成。

## 可修改文件

- `tests/test_user_smp_services.py`
- `docs/p2-smp-service-fixture.md`
- `codex-works/deliveries/P2HARNESS28.md`

## 定向验收

- `module:tests.test_user_smp_services`

交付：`codex-works/deliveries/P2HARNESS28.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
