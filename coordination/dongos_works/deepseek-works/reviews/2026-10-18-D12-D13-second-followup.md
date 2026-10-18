# D12 / D13 二次补交复验 — 2026-10-18

结论：**两项继续返修，暂不验收**。二次补交有真实修复；上一轮指明的 out 原值和 Decode 后 guard 已关闭，但原逐调用完整观察仍未齐，且 D13 的一个 guard fixture 自身越界读取。未发现正式 arena/utf8 算法变化或新生产算法缺陷。只补原清单，不新增任务/API/输入矩阵，不重开已闭项。

## 本轮受测版本与结果

正式实现 SHA256 仍分别为 arena `a1786fe43d44651b6d369cd2a22d67ec023fd420ea741273bcea897217cf204e`、utf8 `76194ff8f26da346026c06a83ef77e32972253d7944710c2ff6854e572465cc3`。

新 C 探针：arena `d9b5a14e3bb853e42a487e5d8ef1621e8c63a0054ad58e2b81d61be5ffee532a`，utf8 `29da4ab93e2e7f01456082332a4519c36417a0d1ce9fb9439fa29fb16d714553`。Python 测试文件不变；全部6个实现/测试/探针文件前后hash稳定。

`python -m unittest lang.tests.test_std_arena lang.tests.test_std_utf8 -v`：6项通过、0skip，封存两次复跑分别8.850/8.734秒。两模式原生、双格式组装和原负控通过，不代替下面的观察器复验。

上一轮六类最小坏董源码（四个最早控制 + 极大alignment失败改out + 最大start改Decode后guard），debug/release共12次全部成功编译、链接、执行，各在 hit1 后被正确断言拒绝。证据 `build/test/collaboration-review/guards-0c732dea9b02/`。这些具体观察点全部保持关闭。

确认已落实：自然对齐 GArena/GOut/GDecode/GWritten；极值对象双端；D12失败out；D13失败padding和DECG；每个宽度空输出。保留原百万标量、双字节、单字节、随机串和模型序列。不要求重做这些部分。

## 原共同项仍有4次实际漏检

| 任务 | 原既有调用与私有最小坏写 | 两模式实际结果 | 原观察遗漏 |
| --- | --- | --- | --- |
| D12 | capacity256、alignment0 的失败 allocate，仅改真实 storage[-1] | 各 hit1、exit0、probes passed | `std_arena_probe.c:116` 只查Arena/out，未立即查storage前后guard；该坏写也没有在退出前被发现 |
| D13 | bytes.len3、start=usize最大值 的失败 decode，仅改真实 input[-1] | 各 hit1、exit0、probes passed | `std_utf8_probe.c:188` 只查输入正文与Decode guard，漏查实际输入前guard；不是已修复的Decode后guard |

证据 `build/test/collaboration-review/guards-98f02943c4f0/`，脚本 `check_guard_oracles_remaining.py` 位于其父目录。没有新输入或不同API；只检查原任务要求的所有对象/输入/存储双端。命中计数由私有董导出在 C 成功结束时实际读回，不把构建失败或静态推断当作负控。

## D13 guard fixture 自身越界

`std_utf8_probe.c:116` 分配 `pre[8+2+8]`，总18字节，pd=pre+8，实际输入长 `2+len`。第121行检查后guard到下标 `8+2+len+7`。首个非法输入 len=1 时就需要19字节，最后一次读 pre[18] 已越界；len更大更严重。这使宿主 C oracle 本身有未定义行为，即使原测试恰好通过也不能验收。

私有 C 副本只在原 guard 循环前加尺寸断言，正式董代码保持原样；两模式实际输出 `REVIEW_SPAN len=1 view=3 physical=18 required=19`，随后准确拒绝。证据 `build/test/collaboration-review/fixture-span-1dfa5c08d434/` 与脚本 `check_utf8_fixture_span.py`。这是 C fixture 范围诊断，**不计为董坏实现负控**。修复时按原最大输入为实际view和完整guard分配足够物理容量，不删除guard断言。

## 剩余有限修复要求

1. D12：补齐原所有返回点的storage正文/实际双端和保持字段，下一调用前完成。特别是`:98`单独rewind、`:116–124`非法alignment/精确容量组、`:175–185`初次分配和复用组；`:121`精确分配也需当次AG，不能等rewind；`:132`非对齐init后也要当次实际storage guard。初始化/rewind的保持字段按原清单核对。已有GArena/GOut及已拒绝控制保持不动。
2. D13：修正上述pre物理容量；所有原decode/validate返回点立即检查声明视图前后guard和完整输入。特别是`:112–113`的decode后guard不能延至validate，`:144–149`单字节段同理；`:180–194`起点段漏查sbuf双端，`:119–124`的前缀输入在decode后也须检查，`:234–238`最终v组需实际双端与逐次观察。后段`:212–231`成功encode补原完整预期前缀及ob双端；不能只核width与尾部。保留已新增的每宽度空输出和padding检查。
3. 两项补交记录仍写“全部逐调用已齐”，与源码不符。完成上述原剩余后追加真实位置、hash、命令及结果，再同步任务/索引为完整待复验；历史交付不覆盖。

没有全项目回归、QEMU/VMware、提交或推送。D1～D11不变；DeepSeek继续修自己的授权文件，Codex不代改。
