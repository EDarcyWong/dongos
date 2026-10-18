# C1 / C2 独立验收 — 2026-10-18

结论：C1、C2 **已验收（独立组件）**，不代表已接入常量求值或完成 L3 自举。生产源码与既有测试均未由 Codex 修改。

## 审查与执行

逐项审查符号/规范零、除法向零截断与余数符号、Knuth 估商/乘减/回加、无限补码转换、负数右移舍入、巨大移位的有界拒绝，以及描述符/别名/对齐/溢出预检与失败输出原子性。未发现实质缺陷。

Codex 重新执行：

```text
python -m unittest lang.tests.test_bootstrap_bigint_div -v
python -m unittest lang.tests.test_bootstrap_bigint_bits -v
```

C1 3项通过（10.592秒），C2 4项通过（8.266秒），均0skip。debug/release实际原生执行、ELF64/COFF组装；原永久5类/4类坏董源码两模式共18次均完成编译/链接/执行后由指定值或存储原子性断言拒绝。复跑证据 `build/test/collaboration-review/run-b7a59cab5bbb/` 中对应日志与 `result.json`，包含源前后hash稳定记录。原生详情分别在 `build/test/claude-c1/run-13c882a93704/`、`build/test/claude-c2/run-d9ad3b11cdee/`。

额外使用新种子 `0xC1C2182026`、最高8192位输入与新构造的近倍数：C1每模式1500个DIV/REM用例，C2每模式3580个位运算/取反/左/右移用例（含usize最大移位），全部对照独立Python任意精度期望通过。证据 `build/test/collaboration-review/claude-extra-472a7c0ee943/result.json`，源前后稳定；原生输入/输出及构建分别在 `build/test/claude-c1/run-e95c2167c4c4/`、`build/test/claude-c2/run-5c9a182a7843/`。执行脚本 `build/test/collaboration-review/check_claude_extra.py` 保留。

## 验收身份与范围

- C1 实现 SHA256：`09f4ad05a36a763533b113cbb1512950bb534ffe75c48b871054563b71481612`
- C2 实现 SHA256：`4f2ea6942f7ca0357dca0cacc78596d363f228ea2abd0f18dcabfef9f20c35e0`
- 共享核心仍为 `6c63ed4b11051aff9477f04c643d0595184a881a6fbcc41284c3099ace257a3b`；测试及全部依赖身份详见上述回执。

仅本机原生SysV边界验证，ELF64仅组装，不声称Linux原生执行。没有系统构建、OS/VM启动、性能采样、提交、推送或关机。目标位宽溢出/移位限制仍由后续语义层检查；组件尚未自动集成到新 Dong 语义器。
