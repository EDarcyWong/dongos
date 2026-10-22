# L3DEFER1 — L3/L3A defer 作用域清理整程序降级候选

负责人：codex。状态：待领取。

在独立候选文件补齐 lower_program 的 defer；生产主线先由 L3METHODLOW1 冻结复验。支持块正常退出及 return/break/continue 时逆注册顺序执行正确范围清理，注册不提前求值，返回 scalar/pointer/pair 在清理前快照保护；覆盖嵌套作用域/分支/循环和 cleanup 局部变量。使用调用方 node_slots 编译期清理链，不改 Graph/IR ABI。前端现有嵌套defer/清理内控制转移/捕获赋值/终止cleanup禁令保持。真实 native 执行、独立 C+seed 差分、容量/别名/guard/源稳定和错误董负控。仅候选开发复验，等待 L3METHODLOW1 集成后另任务真实集成，不提前登记集成。

## 可修改文件

- `codex-works/l3-defer/src/bootstrap/lower_program.dg`
- `codex-works/l3-defer/docs/defer-lowering.md`
- `codex-works/tests/test_l3_defer_native.py`
- `codex-works/deliveries/L3DEFER1.md`

## 定向验收

- `discover:codex-works/tests:test_l3_defer_native.py`

交付：`codex-works/deliveries/L3DEFER1.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
