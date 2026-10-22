# L3METHOD1 R1 独立复验

项目 `dongos`，任务 `pool:L3METHOD1`，受审版本 submitted rev7，负责人 Cursor。原R0拒验记录及原作业 `1158f00b230f4c3b96ce0c0daadf9d14` 保留；本记录只描述R1。

## 源码与契约审查

已核对原任务书、R1交付、返修意见、两份候选生产源码、文档、永久测试，以及原R0隔离副本。生产R1相对R0只增加说明及两条 `Info{typ:callee,flags:0,length:0}` 写入：

- 函数式调用按实际receiver精确选中方法后，写入 `info[call.a]`。
- 接收者调用在选中方法并通过可见性检查后，同样写入callee Info。

callee 指向原有真实 FUNCTION 类型，`Type.unit/node` 可定位声明。未改输入refs或AST，仍保留候选组与member引用。写入在调用参数检查前发生，但失败仍仅改变调用者scratch，Result发布计数保持0；这与既有失败不发布契约相符。未改主线、lower_program或nasm_program。

永久测试增加了直接观察callee类型/声明位置的检查；原有方法语义、unsafe、可见性、指针精确匹配、同名自由函数优先、错误实参数量/类型、调用及方法体返回错误、指针/切片签名与两个receiver同名方法均已逐项检查。原容量默认值就是运行期各池的精确要求；候选永久测试保留各池0容量及26/27 one-short，下述独立检查另覆盖全部五池one-short。

## 独立追加原生检查

脚本 `L3METHOD1-r1-review.py` 只读取本轮协调器隔离编译的原生对象，另外链接C观察器，不改候选实现或运行副本。证据 `codex-works/build/L3METHOD1-r1-review/summary.json`。

- 21个源程序 × debug/release = 42次原生检查，与seed的接受/拒绝对照全部通过。包括前次16案，以及receiver同名重载、const、alias、unsafe和“首候选private但实际receiver选择另一pub方法”的跨模块调用。
- 所有成功调用均检查：callee类型在已发布范围内且为FUNCTION；`unit/node` 是真实函数AST及符号，声明node_types与callee一致；调用名等于选中符号名；选中方法receiver类型、每个显式参数Info和call返回Info均与声明签名一致。自由函数对照核对其GLOBAL目标。
- 两个同名重载分别定位不同的正确声明；跨模块两类调用均定位模块1的同一pub方法，不误用候选首项。
- runtime池24..28各自one-short，两个模式共10案：均CAPACITY、types/fields/limbs计数0、全部guard及只读输入检查通过。池24为info、25为initialized、26为snapshots、27为breaks、28为loop_seen。
- 额外将同一观察器链接上轮正式R0的真实debug/release对象：两者都在语义调用成功后被 `callee-type-missing-or-out-of-range` 明确拒绝，退出103。新R1检查器退出0。这是原真实缺陷的正反对照，没有伪造Graph或更改源实现。

共52次补充检查通过，另2个真实R0负控均被拒绝，`graph_oracle_passed=true`，无缺失callee Info。

## 受审指纹

| 文件 | SHA256 |
| --- | --- |
| semantic_types.dg | `d216531917467c1bd05601625ef18607337061f87649ab6399b5af9fbd5725ef` |
| binding.dg | `3822f0f132d680117ba457fbe046254309b86580ae4c0ad94f572ca4d2c203e1` |
| method-semantics.md | `14e399d6c4b526f2c4c1aa9103082827a236a44038f202db611d365c1e97fb94` |
| test_l3_method_semantics.py | `72d1e78cd42e4c2ac0ca16e98aa44c4178ea904400088d6062b9c0e16dc5d3e3` |

当前补充探针为Windows本机原生执行；候选正式构建还组装ELF64/Win64对象。不据此声称已在Linux运行，或方法整程序后端、完整L3/G5已完成。未启动OS/VM、未提交推送。

## 正式复验与结论

作业 `ebc1fdf7a24744858bb7e141809fafe8` 已于2026-10-22T03:01:49Z完成声明的 `discover:pool-works/tests:test_l3_method_semantics.py`：6项通过、0skip，退出码0，709.748秒（测试自身707.534秒）；`source_stable=true`、`process_stopped=true`、`execution_exited=true`。正式指纹与上述R1四文件及delivery一致，复验后submitted rev8。

源码/契约、52次独立追加检查、两个真实R0负控及正式6项全部通过，原阻断修复成立，可验收当前候选前端语义组件。当前未修改主线，不登记集成；原R0审查与失败证据继续保留，不把本项写成整程序method或完整L3/G5完成。

已通过协调器按最新rev8登记验收，返回 `pool:L3METHOD1 accepted rev9`。未执行integrate操作。
