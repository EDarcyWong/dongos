# L3METHOD1 — 原生前端方法声明及接收者调用语义

L3METHOD1 闭合 Dong 自举前端对 `method` 的声明与调用检查；后续 L3METHODLOW1 将已解析的结构体指针方法接入 `lower_program` / `nasm_program`，覆盖两种写法的整程序编译执行。完整 L3/G5 仍有其它语言缺口。

## 范围

- 主线实现：`semantic_types.dg`、`binding.dg`，逐字接入已验收的 `pool:L3METHOD1` R1。
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

在 `code/` 执行 `python -m unittest lang.tests.test_bootstrap_method_semantics -v`：从主线快照构建真实 Dong debug/release 前端，与 Python seed 比较接受/拒绝；直接观察两类调用与同名不同 receiver 的选中 callee Info；覆盖五个运行期工作池的 exact/one-short、别名、guard、源不变及真实错误实现负控。

同一新编译语义对象还运行既有运行时类型/流程、切片、内存intrinsics、optional/result等正常回归；另外重建完整frontend/arena/diagnostics入口，验证既有诊断及方法调用成功/失败时Graph发布、只读输入和arena生命周期。标准语言测试发现和CI分片会自动纳入此模块。

## 整程序后端接线（L3METHODLOW1）

`python -m unittest lang.tests.test_l3_method_native -v` 从当前主线构建真实原生编译器，将 Dong 源码经 frontend→lower→NASM 后汇编、链接并执行；Python seed 只提供初始编译器及独立差分基准。方法体采用普通函数 IR；接收者为首参数，接收者式调用只求值一次且先于其余实参。调用目标来自 callee Info 中 FUNCTION 的 unit/node，不使用不可变 refs 中的候选组首项。

符号以模块/方法名加 `_t` 及接收者名义结构体名的十六进制编码区分，与同名自由函数、其它类型或其它模块的方法互不冲突。类型别名沿用目标名义结构体。测试覆盖真实调用值、内存 canary、窄值、递归、切片双字返回、栈参数和先前 SysV/全局/聚合路径。错误 Dong 变体改用候选组首项，必须成功编译链接执行，再由独立结果 oracle 拒绝。G5 的原 method 夹具保留并改为必须原生通过；未降低其它缺口的判定。
