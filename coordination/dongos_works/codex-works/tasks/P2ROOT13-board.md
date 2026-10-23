# P2ROOT13 — P2调度后内核共享分支与用户私有根闭包审计

负责人：codex。状态：待领取。

用户先完成P2再P5；为真实调度后多根事务补必要闭包组件，不放宽旧shared_paging/EXEC/WC owner。新增只读有界runtime_roots模块，直接读取pg.inspect产生的真实kernel/最多16用户Space PoolView；按生产load_candidate精确规则核每个用户root的PML4[1..511]逐项等于唯一kernel root对应分支（仅允许硬件A/D合法变化），只遍历各用户私有slot0，kernel完整树只遍历一次。核所有private child在自己pool/唯一parent/无cycle，metadata与reachable/used一致；foreign引用只准root共享分支，不能任意放行外部PA。物理及虚拟pool/metadata/描述符/输出存储需无冲突、边界/溢出/对齐预检，输出失败原子；pending退休metadata2无完整线性receipt时明确拒绝并保持隔离。对指定持有物理区间枚举实际kernel/USER别名及有效权限/缓存/2MiB交叠；隐藏额外别名必须出现在结果中，不能只检查调用方两条列表。此模块审计给定可信枚举集合，不能单凭数组证明已枚举所有memory/Catalog/domain根；信任边界及后续真实消费者集成义务须明确。本项不把组件当P2整体验收。
永久host测试实际编译新模块+生产paging，debug/release用真实Space建立kernel及多用户private树，再复制真实shared1..511；C独立raw oracle和guard验证别名、parent/A-D/overflow/capacity/同PA多根/坏root/private foreign/cycle/metadata2保持、输出重叠拒绝。真实坏Dong忽略共享分支/foreign私有指针/忽略隐藏别名须正常编译执行并精确拒绝；不能只grep。保存原始源/命令/receipt/SHA/0skip稳定。普通执行者不运行测试/OS/VM/CLI/commit/push；协调器独立复验+源码契约实审后真实主目录集成。

## 可修改文件

- `kernel/mm/runtime_roots.dg`
- `tests/runtime_roots_probe.dg`
- `tests/runtime_roots_probe.c`
- `tests/test_runtime_roots.py`
- `docs/runtime-roots.md`
- `codex-works/deliveries/P2ROOT13.md`

## 定向验收

- `module:tests.test_runtime_roots`
- `module:tests.test_paging_view`
- `module:tests.test_paging`

交付：`codex-works/deliveries/P2ROOT13.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
