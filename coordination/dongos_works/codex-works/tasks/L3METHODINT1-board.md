# L3METHODINT1 — [L3/G5] 已验收方法前端语义主线集成

负责人：codex。状态：待领取。

按用户明确集成要求，将pool:L3METHOD1 accepted rev9的两份生产候选逐字接入主线；先核对最新rev及正式受审指纹，无冲突才修改。永久迁入6项真实Dong方法测试，适配主线根/构建产物路径与本机链接，保留真实坏体/Graph Info/seed对照/guards/输入不变并补全5池one-short。复用同一新编译原生语义对象执行既有非mutant运行时类型/流程/切片/内存intrinsics/tagged回归；另外真实重建完整frontend入口执行既有pipeline/diagnostics与两类方法成功、错误参数和私有方法拒绝、arena/graph不变检查。文档接入并更正旧的method一律UNSUPPORTED描述，清楚限定仅前端，不修改lower_program/nasm_program或宣称整程序method/G5完成。原候选5文件保留且匹配accepted指纹；主线两个生产文件与候选SHA相同，独立定向复验零skip/source_stable并审查后验收/集成，实际文件接入完成后登记原任务集成。只写声明文件，不提交推送或运行OS/VM；完整交付映射/实际测试/限制。

## 可修改文件

- `lang/bootstrap/semantic_types.dg`
- `lang/bootstrap/binding.dg`
- `lang/bootstrap/semantic_types.md`
- `lang/bootstrap/method-semantics.md`
- `lang/tests/test_bootstrap_method_semantics.py`
- `codex-works/deliveries/L3METHODINT1.md`

## 定向验收

- `module:lang.tests.test_bootstrap_method_semantics`

交付：`codex-works/deliveries/L3METHODINT1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
