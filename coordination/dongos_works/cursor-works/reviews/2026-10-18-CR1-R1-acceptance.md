# CR1 R1 补交验收

2026-10-18，结论：R1 三项原契约覆盖缺口均补齐，CR1 通过独立组件验收，状态 accepted。源码未改，尚未集成。

1. 原 case5 改为自然对齐的 out+56；case4 的 source 只与未使用 out 尾部重叠。Codex再次构造仅检查 out 前 18 字节的坏董副本：正式程序两模式正常退出，坏程序两模式均退出 93，并明确报 `invalid preflight 4 status 0`。这次由完整声明区间的别名规则观察并拒绝，不再被未对齐检查遮住。
2. 所有实际董输出（包括空输出）均写 asm 再调用 NASM -f bin。独立运行生成 240 对同名 asm/bin，其中空 asm/bin 各 24；summary 的调用统计与产物数量一致，恢复字节逐条比较原输入。
3. 需要长度溢出夹具改用高位伪基址，source 端点数值合法且与实际低位 out/written 区间分离；case11、12分别覆盖 body 乘法及 body+overhead 的溢出，默认案例覆盖容量不足时 INVALID 优先。数值预检返回前不读伪区间。正式源码的提前拒绝顺序已审查。

| 任务 | 定向复验 | tests / skip | 回执 |
| --- | --- | --- | --- |
| cursor:CR1 | 通过，文件稳定 | 4 / 0 | [result.json](../../.local/runs/edcbc704ec4e4abfaed752bce172a70c/result.json) |

正式 4 tests 全通过、0 skip，debug/release 原生运行，ELF64/COFF 组装；四类既有坏源码在两模式的指定断言仍有效。Codex追加尾部别名控制共两次明确拒绝。追加证据：[Codex追加复验回执](../../.local/reviews/batch3-7776fff6c0f9/result.json)

已核对补交文件 hash；原 R1 返修记录保留，不以旧结果代替本轮证据。正式实现/测试未由 Codex 修改，坏源码仅在审查目录；无 OS/VM/全回归或提交推送。

## 验收文件指纹

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/deliveries/CR1.md` | `961fe4ae3d95f3533b3c3bb8463ceb11f144c5d322030f66943deae4fbbe7ffe` |
| `cursor-works/src/bootstrap/nasm_bytes.dg` | `1b3466b9520d1d8ba63088d7cb474e33bbe2e65d040ec145878f232c788f036f` |
| `cursor-works/src/bootstrap/nasm_bytes.md` | `17fd383eba45e684406cd2478afa6f3818c39b83676b44be334b2ef4ffd91f76` |
| `cursor-works/tests/test_nasm_bytes.py` | `318ffbdd9187ad985f461349733fb61a374dac9e75f8035a881714681f848526` |
