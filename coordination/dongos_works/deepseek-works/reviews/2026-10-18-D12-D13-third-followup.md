# D12 / D13 三次补交复验 — 2026-10-18

结论：**继续返修原剩余，暂不验收**。三次补交修好了上次两个指定guard点和pre物理容量；这些点保持关闭。原逐调用观察仍有三个既有调用模式漏检，本轮没有增加API、输入矩阵或任务编号。

受测探针hash：arena `4b6f0d8adaa99598c461aa1618ed387c7ce6cbae56043dec80e5bb33ce5d2a2c`、utf8 `d2e1266a28db2dc56073de4ecdf5b64a4225cebb2ce711750cb1169d3b837bf4`。正式董实现及Python测试均未变，所有被审实现/测试/探针前后hash稳定。

原6项定向测试独立复跑通过、0skip（首次8.590秒，日志见下方目录）。D12非法alignment storage[-1]、D13最大start input[-1] 两类旧控制两模式共4次，均在hit1即拒绝，证据 `build/test/collaboration-review/guards-7013268caba9/`。不重做此前已关闭六类控制。

pre由18增为26字节，原最大输入所需完整视图和guard共22字节。私有C副本在原循环前增加尺寸断言，两模式全部原非法序列通过，打印实际len/view/physical/required；证据 `build/test/collaboration-review/fixture-span-c0f67ae4fd41/`，脚本 `check_utf8_fixture_span_fixed.py`。这是C尺寸诊断，不计为董坏实现负控。首轮因旧锚点现在出现两次导致脚本准备失败，未计入结果。

## 三个原观察模式仍漏检

| 任务 | 原调用模式/私有董坏写 | 两模式实际结果 | 剩余要求 |
| --- | --- | --- | --- |
| D12 | 原init(storage,溢出容量)失败分支写storage[-1] | 各hit1、exit0、probes passed | 失败init后完整storage正文及实际双端必须在离开fixture前检查；目前仅末尾正文memcmp，无SG |
| D13 | 原单字节NUL的decode写input[-1]，紧接的validate恢复该guard | 各hit2、exit0、probes passed | 单字节decode返回立即检查前guard，必须位于validate之前；不能等第二调用恢复后再检查 |
| D13 | 原U+10000、output.len4精确容量encode把首字节f0改为f1 | 各hit1、exit0、probes passed | wsc精确容量成功路径核独立预期完整前缀，不能只看written、尾部和WG。expect组已补prefix，wsc组仍缺 |

每个私有变体均成功编译、链接、实际运行。单字节控制的hit2明确表示一次写坏、一次恢复；pending指针仅在写坏分支设置，不存在空命中。证据 `build/test/collaboration-review/guards-117f29698578/`，脚本 `check_guard_oracles_third.py`。包含6项正式测试日志、私有源/C观察器、汇编/对象/可执行文件、逐模式日志和完整hash。

## 只补原剩余，不扩大任务

- D12：把原init组的成功/失败返回逐次接入相应真实storage SG和正文快照；overflow当前仍缺双端检查，init256成功后也不要等下一allocate才比正文。原rewind成功返回点按原要求核used/base/capacity保持（特别是独立rewind、精确容量组和复用组）。已有非法alignment/精确分配/复用SG与自然对齐fixture保持关闭。
- D13：单字节decode的正文与**前后guard**必须在validate之前；wsc精确成功路径加独立预期前缀和ob实际双端。原同类返回点保持即时观察。已关闭pre容量、最大start输入guard、padding/DECG、每宽度空输出、expect边界组完整prefix均不重开。
- 交付记录不要继续概括为“所有返回点全部已齐”；完成这三个具体模式及上面原保持字段后，追加位置/hash/结果，同步任务与索引为完整待复验。

未改DeepSeek实现/测试；没有全项目回归、OS/VM构建/启动、提交或推送。D1～D11保持已验收。
