# L3METHOD1 独立复验与返修依据

项目 `dongos`，任务 `pool:L3METHOD1`，审查版本 submitted rev3，负责人 Cursor。

已读原任务书、交付、两份候选生产源码、候选文档和测试，并对照只读 Python seed / frontend Graph 契约。未修改候选生产实现，未集成主线。

## 阻断验收：成功方法调用未发布选中方法的 Info

任务要求成功 Graph 发布真实类型、refs、Info。候选 `semantic_types.dg` 的 `rt_call` 在 819–839 行选中方法后直接调用 `rt_finish_method_call`；后者只返回方法返回类型，没有将选中方法的 FUNCTION 类型写入 callee 节点的 Info。两条路径均跳过普通调用的 `rt_expr(c,n.a,...)`。

最小复现：

```dong
module a;
struct S{x:u64}
fn(self:*S)get(x:u64)u64{return x;}
fn f(p:*S)u64{return p.get(1);}
```

把 `p.get(1)` 改为 `get(p,1)`，问题相同。debug / release 均返回成功，call 的结果类型是 u64，但 `info[call.a].typ == 18446744073709551615`（NONE）。普通自由函数对照则有合法 FUNCTION callee 类型。两个 struct 同名方法调用都仍保留首候选索引，callee Info 同样为空，因此输出未保存可直接定位选中声明的类型信息。

这不是参数接受/拒绝错误，也不是要求本项实现后端 lowering。缺陷在本项声明要交付的前端语义元数据。保留不可变候选 refs 是允许的；应在可写语义输出中保存选中 FUNCTION 类型及其声明定位（可通过 Type.unit/node），并明确调用节点、callee、receiver 和参数的对应关系，无需改源 AST 或 lower_program。

## 独立追加观察

审查脚本 `L3METHOD1-review.py` 从协调器隔离复验作业实际编译的 debug / release 对象链接 C 观察器，未修改生产对象或运行副本。先核对两份对象所用候选源码与当前交付字节一致，结果记录对象及源码 SHA256。

16 个源程序 × 2 模式，共 32 次原生调用，参数数量、参数类型、调用返回类型、方法体返回类型、不同 struct 同名方法、自由函数同名优先、指针/切片参数返回的接受/拒绝均与 seed 一致，guard 检查通过。其中 10 条成功记录（含同名方法的两个调用）未发布 callee Info；两个自由函数对照均正确。

证据：`codex-works/build/L3METHOD1-review/summary.json`，`graph_oracle_passed=false`。正式作业为 `1158f00b230f4c3b96ce0c0daadf9d14`；其结果另在下方补记。

复现命令（项目根目录）：

```powershell
python coordination/dongos_works/codex-works/reviews/L3METHOD1-review.py D:/projects/projects3/2026/dongos/coordination/dongos_works/.local/runs/1158f00b230f4c3b96ce0c0daadf9d14/workspace/pool-works/build/L3METHOD1/run-17e3f3b90d27
```

## 原负责人返修要求

1. 两种调用均发布选中方法的合法 FUNCTION 类型与声明定位，保留正确 call/receiver/argument Info、不可变 refs/AST 和失败不发布契约。
2. 永久测试直接观察成功语义输出，核对同名不同 receiver 的两个调用确实指向各自声明；不能只检查 status，也不能把候选首项当作已选中。
3. 将本次通过的非 receiver 参数数量/类型错误、调用及方法体返回类型错误、指针/切片签名和自由函数优先检查纳入永久测试；当前提交测试未覆盖这些明确任务要求。
4. 明确容量测试中默认精确容量成功与 one-short 失败的对应关系，补齐 RuntimeWorkspace 各相关池的边界，保留 alias/guard/输入不变及真实坏体负控。

保持原任务和现有正确实现，只修上述缺口并按声明的 write_paths 交付。复验通过前不验收，不集成，不宣称完整方法编译完成。

## 正式复验结果

协调器作业 `1158f00b230f4c3b96ce0c0daadf9d14` 已于 2026-10-22T02:19:25Z 完成：5 项通过，0 skip，进程退出码 0，`elapsed_seconds=636.781`，`source_stable=true`、`process_stopped=true`。正式复验后任务为 submitted rev4。

现有测试通过，但独立追加的语义 Graph oracle 失败（脚本明确退出码 1、10 条记录缺少选中 callee 类型），源码/契约审查不通过，应按原编号交回 Cursor 返修，不能验收或集成。

已于 2026-10-22T02:19:52Z 通过协调器以最新 rev4 登记 R1 返修：任务现为 `rework rev5`，负责人仍为 Cursor，详细复现和修复要求已写入 `review_note`。正式作业历史保留，无验收或集成操作。
