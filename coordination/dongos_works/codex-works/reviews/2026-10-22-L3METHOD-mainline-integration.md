# L3METHOD1 主线集成审查

项目 `dongos`；来源 `pool:L3METHOD1 accepted rev9`；接入任务 `codex:L3METHODINT1`。

## 已核实的实际文件集成

两份生产候选已逐字写入 `code/lang/bootstrap/semantic_types.dg` 与 `binding.dg`，SHA分别为 `d216531917467c1bd05601625ef18607337061f87649ab6399b5af9fbd5725ef` 和 `3822f0f132d680117ba457fbe046254309b86580ae4c0ad94f572ca4d2c203e1`。未另行重写已验收的实现。

方法文档接入 `lang/bootstrap/method-semantics.md`，旧的 `semantic_types.md` 已将方法前端与尚未接线的方法lowering分开。永久测试接入 `lang/tests/test_bootstrap_method_semantics.py`：

- 从当前源码树读取主线生产文件，构建debug/release快照，不依赖pool路径、project.json或原项目绝对路径。
- 保留原6项真实Dong方法检查，包括实际坏体、callee Info、seed对照及内存契约；运行期五池one-short全部覆盖。
- 增加9组既有正常运行时回归及完整frontend入口/诊断/方法成功失败集成检查。复用已编译语义对象，未重复执行无关的旧mutation套件。
- 本机Info观察器沿用既有构建器的操作系统后缀和Linux `-no-pie` 链接方式，未声称在Linux实际执行。

源码审查确认：Info指向所选FUNCTION，Type.unit/node标识真实声明；refs/AST不改写，失败不发布Graph。`lower_program`、`nasm_program` 均与接入前SHA相同，其METHOD明确UNSUPPORTED边界保留。原候选全部5路径仍逐项匹配accepted指纹，无在途任务写路径冲突。

## 预检与补充证据

- `py_compile`、源文件差异空白检查通过。
- 标准CI语言inventory-only成功：973项；新模块8项全部发现、恰好分片一次。此处只验证发现及分片，未运行其余语言测试或远端CI。
- 验证全部13个语义模块字节均等于上一轮正式R1冻结源码后，用该轮真实原生debug/release产物执行新接入测试中的9组既有运行时回归：每模式522案，共1044次原生语义检查，全部通过。此项复用产物来源明确，不冒充当前正式主线重编译。

补充结果：`code/build/test/l3-method-integration/runtime-preflight-db3e138c/summary.json`。接入前基线及备份：同目录 `before.json` / `before/`；主线SHA、候选不变、后端不变与CI清单核对见 `preflight.json`。完整映射及提交时的已执行/未执行项见 `codex-works/deliveries/L3METHODINT1.md`。

另用当前主线正式作业新编译的debug/release对象运行独立检查器 `L3METHOD-mainline-review.py`：42次源程序/声明签名观察及10次五池one-short全部通过，两个真实R0对象均被缺失callee类型检查拒绝。严格核对callee声明AST/符号/名称、receiver/每个参数/返回Info，包含跨模块重载。结果 `codex-works/build/L3METHOD-mainline-review/summary.json`，`graph_oracle_passed=true`。原R1复验的脚本和结果未覆盖。

已审查G5差分工具的 `known_gaps` 判定：其允许并记录明确的frontend/lower/backend失败，本项不会把仍由lower拒绝的方法误记为G5完整成功。没有修改或声称重新运行整个G5矩阵。

## 正式隔离复验

作业 `a30e5602466a47fd9b694f4868143904` 于2026-10-22T03:28:02Z完成 `module:lang.tests.test_bootstrap_method_semantics`：8项通过、0skip，退出码0，905.876秒（测试自身904.183秒）；`source_stable`、`process_stopped`、`execution_exited`均true。正式指纹与提交的5份主线源文件及交付一致，复验后submitted rev4。

本轮正式从主线重新编译的语义对象通过9组/每模式522案运行时回归，完整frontend两模式各通过27案既有pipeline/诊断及4案方法检查。正式两个summary均确认源稳定。最终重新逐项核对原候选5路径、主线5源文件及两个后端文件，全部与各自受审/基线指纹相符。结果 `code/build/test/l3-method-integration/result.json`。

实际文件接入、源码/契约审查与独立定向复验均通过，可登记接入任务验收/集成及原候选任务集成。

协调器已确认最终状态：`codex:L3METHODINT1 integrated rev6`；`pool:L3METHOD1 integrated rev10`。原候选验收指纹与历史均保留，没有手改协调库或派生索引。

本项仅集成方法前端，不生成方法IR/机器码，不代表整程序method或完整L3/G5完成。未启动OS/VM、未提交推送或建PR。
