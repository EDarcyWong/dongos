# L3METHOD1 — 原生前端方法声明及接收者调用语义

本项闭合 Dong 自举前端对 `method` 的声明与调用检查，不改 `lower_program` / `nasm_program`，不代表整程序 method 完成。

## 范围

- 候选覆盖：`semantic_types.dg`、`binding.dg`（其余 bootstrap / `lang/dongc` 只读主线）。
- 接收者限定为**指向 struct 的原始指针**（`*S` / `*const S`）。枚举接收者、非指针、非名义类型在原生侧明确失败（比 Python seed 更严）。
- 成功时 Graph 发布真实 types / refs / Info；失败不发布；源 AST 不可变。

## 与 seed 对齐的规则

| 规则 | 行为 |
| --- | --- |
| 声明模块 | 方法必须声明在接收者 struct 所属模块（含同模块 alias 指向本模块 struct） |
| 唯一性 | 同一 pointee 类型上同名方法唯一（`*S` 与 `*const S` 同名视为冲突） |
| 字段冲突 | 方法名不得与 struct 字段同名 |
| 函数式调用 | `get(p)`：binding 留下 `METHOD_CANDIDATE`，语义按**精确**接收者指针类型选型 |
| 接收者调用 | `p.get()` / `(&s).get()`：`DEFERRED_MEMBER` 上按 pointee 查方法，实参逻辑为 `[receiver]+args` |
| 选中 Info | 成功后在 callee 表达式（`call.a`）写入选中方法的 `FUNCTION` 类型；`Type.unit`/`Type.node` 定位声明；refs/AST 仍保留候选组，不改写 |
| 可见性 | 跨模块仅 `pub` 方法；选型后再检查，不把候选首项当作已选中 |
| unsafe | 方法带 `unsafe` 时调用点必须在 unsafe 内（`Type.flags&2`） |
| 同名自由函数 | 自由函数 / const / global 同短名优先，不进入 method 候选 |
| 参数/返回 | 非 receiver 参数数量与类型、调用点返回类型、方法体返回类型与既有自由函数检查一致；指针/切片签名允许 |

## binding

`METHOD_CANDIDATE` 仍表示同名方法候选组（首项索引），不表示已选定；可见性与精确接收者匹配由 `semantic_types` 完成。成功调用的可写语义输出（Info）保存选中 FUNCTION，与候选 refs 分离。

## 验证

`discover:pool-works/tests:test_l3_method_semantics.py`：临时 import 根覆盖两候选，真实 Dong debug/release 前端与 Python seed 比较接受/拒绝；直接观察两类调用与同名不同 receiver 的选中 callee Info；容量 exact/one-short、别名、guard、源不变及错误候选负控。
