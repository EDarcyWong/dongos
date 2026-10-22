# L3FLOWINT1 主线合并交付

实际生产lower_program已合并两个已验收候选：defer SHA7fd2be...与for SHAe64ff2...，保留方法主线；两个原候选/测试/文档/交付均未修改。新增for入口/恢复自己的loop_cleanup，保证for/match内break/continue不清理外层注册。原defer cleanup helper、bool match helper逐字保留；for helper相对原候选仅加3处清理边界设置/恢复，预检已精确断言。nasm_program.dg与program_ir.dg保持原生产字节和ABI。

生产永久测试已接入：方法10项、defer6项、for9项，共25项唯一；defer/for脱离works/project.json及候选overlay，只从生产ROOT闭包构建。新增for/match/defer的循环控制/return-pair/cleanup中临时数组组合；实际Dong输出交原生汇编器生成ELF，预计入口69并检查exact/one-short/guard/源不变。没有以seed汇编或手工IR代替原生目标正文。

集成定向入口 `discover:codex-works/tests:test_l3_control_integration.py` 调用全部永久测试，共享一个冻结生产good编译器，各测试独立source目录/输入清单；分别真实构建坏callee、坏return清理、坏for步长三份Dong变体，要求编译链接正常后独立值oracle拒绝。共享仅构建对象，不共享不同测试的目标源和观察输出。动态发现25项，不重复加载导入的TestCase别名。

G5保留原8个探针，新增range/array/slice for和bool match四个探针；方法、普通defer、SysV和四种控制流共7条路径必须真实原生执行通过，enum/error/try/orelse/Win64五个原探针保留精确缺口。还有函数指针、内存内建/原子/asm、完整诊断/ABI和更广defer等完整G5工作，不把有限探针当作完整L3/L3A。

实际预检：Python编译通过；合并编译器47模块seed编译通过（6280226汇编字节）；新增组合/ELF/四G5目标seed编译通过。ELF fixture独立seed debug/release真实C观察均返回69，原生合并路径尚未运行，由正式独立冻结25项复验执行。标准语言发现998项，其中此25项唯一且loader错误0；不是998项全回归。

生产before备份与SHA在`code/build/test/l3-control-integration/before-b726d55e32/manifest.json`；合并预检记录`code/build/test/l3-control-integration/preflight.json`，lower当前SHA `2eb36a91291ce4293e89654a9f2b91e1edf9742e8b87c73624a701dc2e10241e`；nasm只读SHA `26076b3cc250ff61826776a7598342f347683e37627ca63318933337c3ef0349`。完整正式指纹以verification为准，验收前不修改冻结源或交付回填结果。

尚未执行最终生产25项、独立新输入主线复核或OS/VM/当前源码G4/G6；没有Git提交推送，未提前登记候选集成。待真实生产门禁通过后分别登记两个候选和集成任务integrated。

## R1：Windows观察器路径

首轮正式作业b8a7b10b53094f238ae8d9667c0773e5在构建阶段由协调器受管停止：独立实际探针确认294字符C可以编译，但296字符EXE启动报WinError206；原wrapper完整测试名目录可能造成267字符观察器路径。通过pause请求执行器停止，并确认任务paused/confirmed、进程退出后才resume/rework重新领取，未编辑运行中冻结源或人工跳过停止检查。

本次只把wrapper每例目录改为8字符稳定ID并保留完整测试名映射/碰撞断言，代表性EXE由267缩为211字符；同25永久测试与3真实董负控不变。所有Dong生产文件、永久25测试、G5及原候选保持本轮初始字节；R1将重新冻结执行，不能把旧停止回执当通过。


## AI交付 2026-10-22T05:27:08+00:00 · codex-mcp-8c76f5a25c8d4b71

两验收候选已真实合并生产lower，for清理边界新增且源码贡献逐项核对；生产永久25项+原生ELF组合接入，G5保留8增4探针要求7路径原生通过。已做47模块合并compiler seed预检、目标及ELF基准69两模式、标准998项发现(本25唯一)；最终生产25项尚未运行，由正式冻结独立复验执行，不冒充通过。原候选/历史不变、nasm/IR ABI未改；不运行OS/VM或提交推送、不关闭完整G5。


## AI交付 2026-10-22T05:31:40+00:00 · codex-mcp-8c76f5a25c8d4b71

R1仅缩短集成wrapper目录为8字符稳定ID，保留完整25测试名映射并断言无碰撞；代表性267字符观察器路径缩为211，实际C编译/启动211路径均退出0。生产Dong源码/永久25用例/G5及原候选字节未改；上轮正式受管停止回执保留不作通过。重新提交同25项、原生ELF及3真实董负控独立冻结复验，未降低门禁。
