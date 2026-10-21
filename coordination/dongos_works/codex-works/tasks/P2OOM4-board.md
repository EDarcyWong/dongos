# P2OOM4 — [P2] 真实碎片化order9 OOM拒绝、无发布证明与文档校准

负责人：codex。状态：待领取。

接续P2SMP3 integrated rev6，用户继续推进P2且不建PR。Claude P2EXEC1在途、P2WC1待领取，均不抢占。只修改声明7文件；生产kernel/既有P2SMP3指纹保持。新fixture只在协调者生成独立副本中向kernel/smp/large_memory.dg注入真实buddy操作：先占第二个order9块，持有第一半所有剩余368个order0页，归还order9，取其中一个order0页作为hole，再归还此前368页。形成实际free879>512但无order9的碎片状态，之后原生产buddy.alloc9必须真实返回OutOfMemory，未绑定/映射/失效/回收，也不改动原共享owner。不是mock返回OOM，不写 guest memory/register，不修改原目录kernel。fixture源码与生产树差异严格唯一目标文件、明确源码身份。正常baseline不变及2MiB加载ABI保持。宿主用相同Dong片段及真正buddy执行验证对照独立C原始metadata/free-list oracle，正确连贯基线分配成功，hole好体碎片OOM且分配失败前后完整账本不变；真实坏体归还hole或错误归还块由精确分配/状态断言拒绝，均正常构建执行。actual release runtime7 1/4CPU故障客体精确serial OOM和phase0/held0/complete0，实际allocator metadata/free heads、Space/table_meta/完整rootpool、Domain/owner为空/无window leaf及寄存器终止点通过只读QMP归档与离线复算；原有AP前proof报告/316构建身份绑定明确，不能以编译失败/超时/通用panic算预期OOM。正常最终P2SMP3主线/已有原始客体证据仍独立复算，不重建已验收planner或AP事务。实际碎片由独立fixture构造，不宣称覆盖全部真实固件碎片拓扑，TCG不能证明WC硬件性能。文档修正已完成共享根/封存持有与新90544B余量，旧结果按历史保留；P2 EXEC/WC与任意调度后多CR3仍待原负责人和正常消费者验收。交付后独立raw/C oracle审查+正式隔离定向复验0skip/source_stable，再accept与实际本地integrate分开登记。无提交/推送/PR、不启动AI CLI；只有根协调者执行明确授权的可丢弃QEMU验证。

## 可修改文件

- `tests/p2_fragmented_fixture.py`
- `tests/run_p2_fragmented_qemu.py`
- `tests/test_p2_fragmented_fixture.py`
- `docs/p2-fragmented-large.md`
- `docs/p2-extensions.md`
- `docs/remaining-plan.md`
- `codex-works/deliveries/P2OOM4.md`

## 定向验收

- `module:tests.test_p2_fragmented_fixture`

交付：`codex-works/deliveries/P2OOM4.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
