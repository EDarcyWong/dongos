# DeepSeek 最新结果复验

日期：2026-10-17。检查 08:39～08:59 的新局部补交，对照[上轮精确剩余清单](2026-10-17-activation-prep-check.md)及原合同。保持 D7/D8 R3、D9/D10 R2；不增加输入矩阵或修订号。DeepSeek 的正式源码、永久测试、交付记录均未由 Codex 修改。

## 实际执行

| 范围 | 永久测试 | 结果/耗时 |
| --- | --- | --- |
| D7 解析及进程回收 | 17 | 全过，1.031 秒 |
| D8 buddy | 2 | 全过，1.609 秒 |
| D9 map | 2 | 全过，1.375 秒 |
| D10 cache | 2 | 全过，1.172 秒 |

合计 **23项永久宿主测试通过、零skip**。D8～D10另独立确认debug/release wrapper各经ELF64/COFF组装，原生模型均覆盖两模式。负控结果单独记录，不把故意漏检的PASS算成任务验收。

**本轮QEMU执行数为0。** D7 runner、负控客体测试、Dong/NASM客体与标准库的六个文件hash均与07:57复验前后一致，沿用那轮十二个历史客体结果，不冒充本轮实跑。D8～D10生产实现也未变化。源文件/测试运行前后hash稳定；证据在 `build/test/review-deepseek-0900/assessment.json`、`root-results.json`、各任务子目录及assembly/result.json。不修改编译器、活动内核或页表，不提交/推送。

## D7：wait与最终JSON已闭，构建前失败状态还未被永久测试观察

当前两个回收测试记录wait参数、核对kill与第二次wait，并读取最终JSON与返回记录比较；新增stale-success测试核对返回失败及串口清空。原“移除回收wait”“移除全部negative JSON”的临时变体现在分别被2项断言和最终JSON观察拒绝，确认这些修复有效。

原清单的最后一个时间点仍漏检：**mock build入口之前**是否已经把旧成功文件改成passed:false/building。仅删去run_negative_control构建开始前那一次JSON写入，保留最后失败写入，三个新永久测试仍全过（零错误/零失败）。现有stale-success测试只在函数返回后读取，因此最终写入会掩盖开头漏写。

正式runner实现本身正确：Codex独立build入口观察实际看到`passed:false/status:building`且serial为空，返回后失败JSON等于返回记录。剩余是永久回归的观察时机，不是新的runner或硬件实现缺陷。

只需补现有 `test_negative_runner_clears_stale_success`（当前153行）：把直接抛异常的mock build side_effect改成先读取并断言该目录result为passed:false/building、serial为空，再抛既有异常。保留返回后的断言。无需新用例或矩阵；只要永久测试能拒绝 `omit_initial_building_status` 即可关闭D7。证据 `root-results.json` 和 `d7/omit_initial_building_status/tests.log`。

## D8：缓冲布局改好，但多数旧调用没有经过共同检查

原error、R1失败、R2快照及R3 held主缓冲已加入guard/超额尾部，快照范围加宽；两个原失败改写负控在debug/release均被原生断言拒绝。这些完成项保留。

原 `tests/test_phys_buddy.py` 剩余位置：

- 215～216随机init/add无逐次返回保护；364～378多实例init/add仍成对后才检查，错实例free缺实际接收者的完整失败快照。
- 266～315的EG只在块开头/结尾调用，多数原错误只比错误码；457～482的FG也未覆盖中间每次alloc/free/失败。
- 533～548 R2成功调用未逐次核guards/tail；572～578 held OOM后漏HG，随后free/alloc/free也未核HG。
- 609～617的st3/mt3仍为精确大小缓冲。

继续原共同全调用要求，不能以新增宏或块末尾检查代替每次操作。完整位置与证据见 `d8/assessment.json`。

## D9：四组局部已补，仍有原调用的正文/成功尾部漏检

已确认新修复：305～319 arena外重叠失败的raw正文及三缓冲双端；372～396 unknown/端点溢出的raw正文、scratch双端；399～415容量少一用独立out1核全部16B失败输出，两个容量调用都核raw不变。

独立20次定向负控中16次被原生断言拒绝，另两处原已有调用各在debug/release继续误PASS：

- 253～277哨兵块只核raw两端，不核正文；该次返回前修改被忽略的raw[16]，每模式实际一次仍退出0。
- 279～289非对齐raw例已核正文，但不核成功output整个尾部；只改out[result.value]一次，每模式仍退出0。

104～251、321～369尚未统一全部guards/结果保护；336～337大arena仍精确malloc；372～415的unknown/溢出缺raw/output双端，容量例无三缓冲guards。继续原R2，只接已有调用，不增加矩阵。见 `d9/assessment.json`、`result.json`。

## D10：实际c2快照已有效，owner隔离快照时机及基本payload仍漏检

新随机Cache guards、基本/边界Cache和metadata guards、四种原失败的整buffer快照已加入。441行失败调用前保存实际c2/m2/b2，442行核完整不变；临时只改c2.buffer的坏实现在两模式均被原生断言拒绝，原“核错接收对象”问题已关闭。

但444行的owner隔离检查仍是 **`US(); UC();`都在失败调用之后执行**。仅让该次失败free改写传入object所指的owner payload，c2/m2/b2不动，两个模式都实际触发一次坏写却仍PASS。应在441行调用前也保存owner的完整状态/metadata/buffer，返回后比较；保留实际c2的既有检查。

基本cycle的buffer虽然预填0x51，但只核地址、计数与guards；只在现有capacity64的alloc中把payload首字节写0，debug/release各实际触发96次，永久测试仍PASS。需要按原要求在每次init/alloc/free返回后比整个buffer与独立expected，再写入对象模式。BC只在分配/释放循环完成后调用，不能等同交付说明的“每次操作后核对”。原185～290失败/旧实例与325～358交错等共同保护也仍未全。

三个临时实现都只写在build目录，附命中计数，不以编译失败或未命中当作验证。见 `d10/negative-results.json`及各子目录result.json。未发现生产缓存算法的新缺陷。

## 后续

四项均保留原修订部分返修、未续派D11。D7只剩现有一个测试的build入口断言。D8～D10应把现有共享检查真正接到每一处原调用，整理现有C夹具/调用入口，避免继续追加只覆盖新小块的重复检查；该建议不改变原输入矩阵或算法合同。更新后的已关闭项与精确剩余位置均写回原任务书。
