# L3SYSVREG1 — 旧负例预期同步

项目 dongos，2026-10-22。仅把 test_bootstrap_native_compiler.py 的旧 extern sysv64 不支持样本换成仍未支持的 extern win64；失败码、lower status=3 和输出不变断言保留，其他测试不变。

L3SYSV1 首轮6项真实执行测试已通过、0 skip，覆盖 Win64定义/声明失败和 SysV实际成功路径。最终新测试还加入了本旧负例的精确源文本 `module unsupported; extern "win64" fn f()u64;`，debug/release验证同一拒绝码、诊断和输出不变；最终结果由协调器独立隔离复验记录。不声称执行了完整旧 test_bootstrap_native_compiler 模块，其既有宿主平台限制未改。

`python -m unittest lang.tests.test_g5_runner_entry -v` 两项通过、0 skip。修改文件 diff 空白检查通过。未提交、推送、启动 OS/VM或标记验收集成。


## AI交付 2026-10-22T01:15:41+00:00 · codex-mcp-8c76f5a25c8d4b71

本轮实现及真实本机检查已完成，具体结果与未执行范围见本任务交付。最终文件已冻结，申请协调器独立隔离定向复验；submitted不等于验收。
