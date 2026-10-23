# G5INT1 — G5完整语言候选与有界自编译闭包主线集成及永久回归

负责人：codex。状态：待领取。

用户明确授权：G5FULL1/G5CLOSURE1独立复验及源码契约审查通过后真实主线集成并同步状态和进度文档。等待两候选accepted且冻结；复制6个G5模块+compiler_job、runner和永久full/closure/组件测试，修正测试主线路径。保留真实机器oracle、失败原子性、源稳定、语义坏体与预算，不以旧UNSUPPORTED/UD2期待冒充正确行为。更新受影响的旧semantic/runtime/native/compiler/ABI/global/ELF测试以正确目标panic和新支持契约验证，不删除有效负控；集成聚合门禁执行这些实际永久测试。主线完整矩阵、debug/release完整ELF固定点及相关旧门禁均须零skip/source_stable，源/工具/产物SHA和独审复算保存。56MiB arena/64KiB guarded stack/2MiB ELF保持。阶段文档在真实结果通过后记已完成G5宿主完整语言/固定点范围，旧G6客体证据仍绑定原49模块profile及head；P5/其它OS范围不扩张。之后登记本任务与实际已合并候选integrated；工作区整体进度图/roadmap由协调角色据真实结果同步，不手改index/数据库。不运行OS/VM/AI CLI，不提交或推送。

## 可修改文件

- `lang/bootstrap/semantic_types.dg`
- `lang/bootstrap/program_ir.dg`
- `lang/bootstrap/lower_program.dg`
- `lang/bootstrap/nasm_program.dg`
- `lang/bootstrap/frontend_diagnostics.dg`
- `lang/bootstrap/native_assembler.dg`
- `lang/bootstrap/compiler_job.dg`
- `tools/g5_differential.py`
- `lang/tests/test_g5_full_native.py`
- `lang/tests/test_g5_closure_native.py`
- `lang/tests/test_g5_tagged_native.py`
- `lang/tests/test_g5_exec_native.py`
- `lang/tests/test_g5_alignment_native.py`
- `lang/tests/test_g5_panic_native.py`
- `lang/tests/g5/requirements.json`
- `lang/tests/test_bootstrap_semantic_runtime.py`
- `lang/tests/test_bootstrap_native_compiler.py`
- `lang/tests/test_bootstrap_guest_compile_image.py`
- `lang/tests/test_l3_sysv_native.py`
- `lang/tests/test_l3a_mainline_compatibility.py`
- `lang/tests/test_l3a_globals.py`
- `lang/tests/test_l3_for_native.py`
- `lang/tests/test_l3a_native_regression.py`
- `lang/tests/test_g5_runner_entry.py`
- `docs/g5-differential.md`
- `docs/g5-closure.md`
- `docs/language-l2-l3.md`
- `docs/remaining-plan.md`
- `docs/progress-map.md`
- `docs/l3-native-selfhost-progress.md`
- `README.md`
- `PLAN.md`
- `codex-works/reviews/2026-10-22-G5-integration.md`
- `codex-works/tests/test_g5_integration_regression.py`
- `codex-works/deliveries/G5INT1.md`

## 定向验收

- `module:lang.tests.test_g5_full_native`
- `module:lang.tests.test_g5_closure_native`
- `discover:codex-works/tests:test_g5_integration_regression.py`

交付：`codex-works/deliveries/G5INT1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
