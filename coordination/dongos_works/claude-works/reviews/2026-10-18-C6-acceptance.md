# C6 独立验收 — 2026-10-18

**已验收（独立源码位置组件）。** 源码、说明、测试及原交付已核对，原交付历史保留；C1～C5保持已验收。

源码审查确认：先验证out32字节的非空/8对齐/span、source span、两者别名及offset范围，再调用已验收D13严格验证整个source；内容UTF8错误优先于标量边界错误。按Unicode标量计列，仅LF换行，LF本身归前一行；BOM/CR/TAB/NUL均普通标量，EOF及尾LF空行符合任务书。非OK不写out，成功一次发布。非空合法span使source.len至多MAX-1，line/column至多len+1，加法不溢出；decode宽度及扫描端点有界。没有分配、全局可变状态或OS调用。未发现契约缺陷。

独立复跑 `python -m unittest lang.tests.test_bootstrap_source_position -v`：**3项通过、0skip、0失败/错误，6.766秒**。debug/release原生执行，ELF64/COFF组装；1100个源的每偏移41396例/模式、非法UTF8及长行886例/模式、每个原生进程12类描述符拒绝通过。C观察器立即检查每次源全文、普通输入32字节双端、out32字节和16字节双端，失败out不变；真实只读输入页覆盖。三种实际坏董实现（按字节计列、行尾包含LF、失败提前写out）两模式共6次成功构建/链接/执行并由准确position或guard/atomicity断言拒绝。没有用构建失败或崩溃充作负控。

正式原生证据 `build/test/claude-c6/run-250c915abc76/summary.json`；独立复跑及受测源码/说明/测试/D13前后hash回执 `build/test/collaboration-review/c6-review-8f95bc06042f/result.json`。

另用独立种子 `0x20261018C6`，生成**700个不同Unicode源**，含均匀抽取的合法Unicode标量、控制字符、BOM和组合符，覆盖每个字节偏移；补坏尾先于BOUNDARY、越界先于UTF8及空源/EOF。独立Python严格解码与字节分行作期望，每模式21597例、两模式**43194次原生执行全部通过**，包含真实只读页。脚本 `build/test/collaboration-review/check_claude_c6_extra.py`；证据 `build/test/claude-c6/independent-5d7487a3639e/independent.json`。hash前后稳定。

源码SHA256 `5f0fca19fbabdd0c3fc6e94dbd8aa54ac481370eaf080263ec499f4a2de7d7eb`；测试 `e76fe2ccddd15f28899836995de7401604ac8c3222a8aeee415b4fa3644592b1`；D13依赖保持 `76194ff8f26da346026c06a83ef77e32972253d7944710c2ff6854e572465cc3`。未代改Claude生产实现/测试，没有OS/VM构建、提交或推送。

C6尚未接入原生CLI，不据此关闭L3。当前主线回归开始时C6仍是待复验任务，已固定排除本组件；本次3项及扩展原生复验单独记录，不混入该回归的测试数。用户本次要求的新任务已发布给Cursor（CR1），不自动给Claude开启新任务。
