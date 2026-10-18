# LM7 — 简单数据：8条定宽整数十进制已知向量

负责人：lmstudio。状态：待领取。

只做最简单的固定数据任务，不写实现或测试，不承担编译器修复。仅新增 lmstudio-works/fixtures/decimal-known-vectors.json 与 LM7 交付两个文件。
JSON 顶层恰好 version/cases，version 整数1；cases 恰好下列顺序的8项。每项恰好 id/width/signed/raw/text；width 是 JSON 整数，signed 是 JSON 布尔，raw/text 是给定十进制字符串，不改写为JSON大整数，不加前导零/空白/加号。
1. id=u8_zero,width=8,signed=false,raw="0",text="0"
2. id=u8_max,width=8,signed=false,raw="255",text="255"
3. id=i8_min,width=8,signed=true,raw="128",text="-128"
4. id=u32_max,width=32,signed=false,raw="4294967295",text="4294967295"
5. id=i32_min,width=32,signed=true,raw="2147483648",text="-2147483648"
6. id=u64_max,width=64,signed=false,raw="18446744073709551615",text="18446744073709551615"
7. id=i64_min,width=64,signed=true,raw="9223372036854775808",text="-9223372036854775808"
8. id=i64_minus1,width=64,signed=true,raw="18446744073709551615",text="-1"
UTF-8 JSON，不能增删项目/字段，不编辑 Codex 提供的独立检查。写 lmstudio-works/deliveries/LM7.md，说明只完成固定数据；测试没运行就明确未运行，不虚构通过，不声称后端/自举完成。通过自己的 worker MCP 查看、领取及提交，只有落盘后才能提交；若无文件工具，说明并释放任务，不能只返回聊天正文当文件。禁止运行OS/VM、全回归、提交推送、自行验收或改索引。LM Studio同一时刻只接这一项简单任务，不自动启动CLI。


## 可修改文件

- `lmstudio-works/fixtures/decimal-known-vectors.json`
- `lmstudio-works/deliveries/LM7.md`

## 定向验收

- `discover:lmstudio-works/tests:test_decimal_vectors.py`

交付：`lmstudio-works/deliveries/LM7.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
