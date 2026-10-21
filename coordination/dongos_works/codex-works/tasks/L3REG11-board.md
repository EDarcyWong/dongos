# L3REG11 — [L3A主线回归] 将GLOBAL与.data旧拒绝项更新为原生正例

负责人：codex。状态：待领取。

L3A已经独立正式验收rev10并实际主目录集成7文件，原主线test_bootstrap_native_compiler仍把GLOBAL列为unsupported，native assembler仍把section .data列为unknown；需明确更新为正例且保留extern/非法section failclosed。本任务仅更新两个既有测试的过时预期和新增便携定向门禁/说明，不修改已验收bootstrap生产代码或削弱负控。复用L3A已有便携实际Dong frontend/lower/nasm/assembler native桥，实际debug/release数值和字节oracle，原Linux专用完整测试保持Linux适用，不将Windows skip算验收。新测试必须在本机0skip，执行真正旧GLOBAL/.data样例并验证extern status3输出不变/非法section拒绝。保留原ABI/aggregate/trap/semantic mutation测试覆盖，不以删测绕过。源稳定正式复验与源码契约审查后验收/集成。

## 可修改文件

- `lang/tests/test_bootstrap_native_compiler.py`
- `lang/tests/test_bootstrap_native_assembler.py`
- `lang/tests/test_l3a_mainline_compatibility.py`
- `docs/l3a-mainline-compatibility.md`
- `codex-works/deliveries/L3REG11.md`

## 定向验收

- `module:lang.tests.test_l3a_mainline_compatibility`

交付：`codex-works/deliveries/L3REG11.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
