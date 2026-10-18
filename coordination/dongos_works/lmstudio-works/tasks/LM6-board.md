# LM6 — 简单数据：12条LEB128已知向量

负责人：lmstudio。状态：待领取。

只写一份固定12条LEB128已知向量JSON，不写实现代码，不改测试。文件lmstudio-works/fixtures/leb128-known-vectors.json，顶层只有version/cases，version整数1；cases恰好12项，每项只有id/signed/value/hex。signed是JSON布尔，value是十进制字符串，hex是无空格小写十六进制字符串、不加0x。
按给定顺序填写，未注明的signed均false：u0(value="0",hex="00")；u127("127","7f")；u128("128","8001")；u624485("624485","e58e26")；u64_max("18446744073709551615",hex为9个ff后接01，即"ffffffffffffffffff01")。随后七项signed均true：s0("0","00")；s_minus1("-1","7f")；s63("63","3f")；s64("64","c000")；s_minus64("-64","40")；s_minus65("-65","bf7f")；s_minus123456("-123456","c0bb78")。
这是给定测试数据，不增删案例、字段或规范化数值，不声称已运行测试/已完成自举。另写固定LM6交付，明确未运行测试及限制。只有JSON和交付两个文件；Codex提供独立整数编码结构检查，禁止修改测试。不自行验收、不提交推送、不运行OS/VM。

## 可修改文件

- `lmstudio-works/fixtures/leb128-known-vectors.json`
- `lmstudio-works/deliveries/LM6.md`

## 定向验收

- `discover:lmstudio-works/tests:test_leb128_vectors.py`

交付：`lmstudio-works/deliveries/LM6.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
