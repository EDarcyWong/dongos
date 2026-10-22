# L3METHOD1 交付：原生前端方法声明及接收者调用语义

- 任务：`pool:L3METHOD1`，owner `cursor`，agent `cursor-mcp-3e7917854bd14ac8`；R1 返修 claim 后 rev 6，`in_progress`。
- 阶段：L3/G5 — 原生前端 method 声明与接收者调用语义（不改 `lower_program` / `nasm_program`）。
- 交付状态：R1 返修已实现、已本机真实编译执行定向测试；`submitted` 不是验收或集成。

## 1. 生产实现

只修改本项声明的五个文件：

- `pool-works/l3-method/src/bootstrap/semantic_types.dg`：声明期 `check_method`/`check_methods`；运行期函数式 `METHOD_CANDIDATE` 选型与接收者 `DEFERRED_MEMBER` 方法查找；**成功选型后在 `call.a` 写入选中 FUNCTION 的 Info**（`Type.unit`/`node` 定位声明）；精确指针接收者、可见性、unsafe、参数/返回检查；失败不发布 Graph；refs/AST 不可变。
- `pool-works/l3-method/src/bootstrap/binding.dg`：保留 `METHOD_CANDIDATE`；自由函数/const/global 同短名优先；跨模块 method 可见性留给语义阶段（本轮未改）。
- `pool-works/l3-method/docs/method-semantics.md`：范围与 seed 对齐规则；补选中 Info 与参数/返回约定。
- `pool-works/tests/test_l3_method_semantics.py`：临时 import 根覆盖两候选；debug/release 与 seed 接受/拒绝对照；**直接观察两类调用与同名不同 receiver 的选中 callee Info**；补非 receiver 参数数量/类型、调用与方法体返回、指针/切片签名、自由函数优先；容量 exact/one-short；坏 Dong 负控；源不变。
- 本交付文件。

未修改主线 `code/lang/bootstrap` 生产路径、`lower_program`/`nasm_program`、协调器数据或其它任务文件。未提交/推送，未运行 OS/VM。

### R1 返修要点

审查阻断：成功方法调用未发布选中方法的 Info（`info[call.a].typ==NONE`）。修复：`rt_call` 在 `METHOD_CANDIDATE` / `DEFERRED_MEMBER` 选型成功后执行 `*rt_info(c,n.a)=Info{typ:callee,...}`，再进入 `rt_finish_method_call`。候选 refs 仍指向候选组首项；可写语义输出保存选中 FUNCTION。

### 契约摘要

- 接收者限定为指向 **struct** 的原始指针（`*S` / `*const S`）；枚举接收者原生拒绝（seed 仍可接受）。
- 声明：同模块所有权、字段名冲突、同一 pointee 上同名唯一（`*S` 与 `*const S` 同名冲突）。
- 调用：函数式 `get(p)` 与接收者 `p.get()` / `(&s).get()`；精确接收者指针匹配；跨模块仅 `pub`；`unsafe` 方法须在 unsafe 内。
- 成功发布真实 types/refs/**选中 callee Info**；失败 counts 为 0；源 AST 不可变。

## 2. 来源 SHA256（成功跑测前后一致）

| 文件 | SHA256 |
| --- | --- |
| `pool-works/l3-method/src/bootstrap/semantic_types.dg` | `d216531917467c1bd05601625ef18607337061f87649ab6399b5af9fbd5725ef` |
| `pool-works/l3-method/src/bootstrap/binding.dg` | `3822f0f132d680117ba457fbe046254309b86580ae4c0ad94f572ca4d2c203e1` |
| `pool-works/l3-method/docs/method-semantics.md` | `14e399d6c4b526f2c4c1aa9103082827a236a44038f202db611d365c1e97fb94` |
| `pool-works/tests/test_l3_method_semantics.py` | `72d1e78cd42e4c2ac0ca16e98aa44c4178ea904400088d6062b9c0e16dc5d3e3` |

## 3. 实际测试

命令（在 `coordination/dongos_works` 下，Windows 11）：

```text
python -m unittest discover -s pool-works/tests -p test_l3_method_semantics.py -v
```

结果：**6 项通过，0 失败，0 skip**，用时 **736.861 s**。证据目录 `pool-works/build/L3METHOD1/run-e43dbd9465c4/`（gitignore，未提交），含 `summary.json`（`mainline_stable=true`，`candidate_stable=true`）。

工具链：Python 3.13.7、主线 `lang.dongc.compile_source`/`compile_file`、NASM（WinLibs）、gcc（MinGW-W64 x86_64-ucrt）。

覆盖：

- 对齐 seed：mutable/const 接收者、函数式与接收者调用、同模块 alias、自由函数/const 优先、非 receiver 参数数量/类型错误、调用与方法体返回类型错误、指针/切片签名、同名不同 receiver、声明/调用拒绝、unsafe 边界、跨模块 pub/private。
- **选中 Info oracle**：自由函数对照、`p.get`/`get(p)`、同名不同 receiver 两类调用；核验 `callee_type!=NONE`、`type_kind==FUNCTION`、`Type.unit/node` 定位，同名两调用指向不同声明。
- 原生更严：enum 接收者 seed 接受、native `TYPE`。
- 容量：默认精确容量成功；runtime pools 24..28 零容量失败；initialized/snapshot（26/27）one-short；每案 harness 描述符/别名等无效预检。
- 真实坏 Dong 负控（debug/release）：去掉 struct 门禁 / 字段冲突 / 重复方法 / 跨模块 private 选型 → 诚实候选仍拒，坏候选被 status 断言拒绝。
- 主线 bootstrap 与候选文件 SHA 测试前后稳定。

## 4. 限制与未执行

- 未运行 OS/VM；未验收、未复验、未集成（由 Codex 完成）。
- 未改 `lower_program`/`nasm_program`；本项只闭合方法前端语义，不代表整程序 method 或 L3/G5 完成。
- `pool-works/build/L3METHOD1/run-*` 仅为本地证据，不属于声明交付文件。


## AI交付 2026-10-22T02:42:19+00:00 · cursor-mcp-3e7917854bd14ac8

R1 返修已完成并本机跑通定向测试；submitted 不是验收/集成。

阻断修复：rt_call 在 METHOD_CANDIDATE / DEFERRED_MEMBER 选型成功后写入 *rt_info(c,n.a)=Info{typ:callee}，再 rt_finish_method_call；refs/AST 仍为候选组，可写语义输出保存选中 FUNCTION（Type.unit/node 定位声明）。

仅 write_paths：
- semantic_types.dg：上述 Info 发布；保留既有声明/选型/可见性/unsafe/参数返回检查。
- binding.dg：本轮未改（METHOD_CANDIDATE 契约不变）。
- method-semantics.md：补选中 Info 与参数/返回约定。
- test_l3_method_semantics.py：直接观察两类调用与同名不同 receiver 的选中 callee Info；补非 receiver 参数数量/类型、调用与方法体返回、指针/切片、自由函数优先；容量 exact/one-short 说明。
- deliveries/L3METHOD1.md。

未改主线 bootstrap、lower_program/nasm_program、协调库；未提交/推送；未跑 OS/VM。

SHA256：
semantic_types.dg d216531917467c1bd05601625ef18607337061f87649ab6399b5af9fbd5725ef
binding.dg 3822f0f132d680117ba457fbe046254309b86580ae4c0ad94f572ca4d2c203e1
method-semantics.md 14e399d6c4b526f2c4c1aa9103082827a236a44038f202db611d365c1e97fb94
test_l3_method_semantics.py 72d1e78cd42e4c2ac0ca16e98aa44c4178ea904400088d6062b9c0e16dc5d3e3

测试（coordination/dongos_works）：
python -m unittest discover -s pool-works/tests -p test_l3_method_semantics.py -v
结果：6 通过，0 失败，0 skip，736.861s。证据 pool-works/build/L3METHOD1/run-e43dbd9465c4/。

限制：仅前端语义；不代表整程序 method 或 L3/G5 完成。
