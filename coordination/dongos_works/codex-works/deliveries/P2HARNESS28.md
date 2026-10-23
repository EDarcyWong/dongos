# P2HARNESS28 交付

任务：`dongos/codex:P2HARNESS28`，实施依据为 rev2 完整任务书；仅修改声明的
`tests/test_user_smp_services.py`、`docs/p2-smp-service-fixture.md` 及本交付文件。

旧回归抽取新的生产 `enable_smp/project` 后，缺少 LARGE 类型和分配/轮询依赖，
独立作业 509fef4db16648e3af0557212591fe9d 在解析 resources.Block 时失败。
本次补实际生产 LargeTicket/Storage、RootSnapshot、Block 声明和实际
runtime_large.Context 导入，保留真实 enable_smp/project、large_poll、服务
回调及 Catalog/Domain/queue。真实 register_poll 只允许首次注册；夹具明确
不启动 LARGE，request/ready/attempted 三个非零状态必须返回 Protocol。

新增宿主 C 独占 RAM 分配：仅 BSP/BKL、一次、精确 Storage 页数、最多 128 页、
页对齐、逐字节清零与双保护页核验。它是受限合成硬件边界，不是生产分配器或
LARGE 成功模型。原 10 项实际坏源码和 debug/release × exit/fault/gui 共 6
正常执行全部保留；预期 22 次实际编译、26 次原生执行、零 skip。既有 BSP、
Frame/代际权限、退休前全 ACK、IRQ 和角色掩码预言不变。

每次唯一 run 目录保留失败回执、实际 staged 源图/layout、原始命令和输出、
对象/EXE/全产物 SHA，以及完整源码和 Python/NASM/CC 前后 SHA；晚期变化必须
同时否决回执与 unittest。所有回执明确 LARGE/AP CPL3/QEMU/OS 未执行。

待协调器独立检查：`module:tests.test_user_smp_services`。实施者未运行编译、
测试、OS/VM，未提交/推送，未修改任务状态或归属外文件；不登记通过或验收。
静态检查与最终文件 SHA 由交付消息附报，正式通过状态以协调器独立作业为准。


## AI交付 2026-10-22T21:32:23+00:00 · codex-mcp-daece153b59c4bd5

已完成声明三文件。root实际审查了完整Python差异及文档：生产enable_smp/project/large_poll/服务回调和真实Catalog/Domain/queue保留；LargeTicket/Storage、RootSnapshot、Block均抽取生产声明，真实runtime_large.Context，单次精确页数且≤128页的受guard对齐清零RAM边界。LARGE仅未启用夹具边界，request/ready/attempted三拒绝，原10实际坏源码和2mode×3正常仍保留。新增完整重枚举源码/工具前后SHA、实际命令raw stdout/stderr、对象/EXE及失败finally回执。git diff --check静态通过，尚未执行编译/测试/VM；等待协调器独立定向复验，不以实现完成冒充验收或实际LARGE/AP通过。
