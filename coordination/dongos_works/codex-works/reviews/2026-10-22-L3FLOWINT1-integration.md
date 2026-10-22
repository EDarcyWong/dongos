# L3FLOWINT1 主线合并独审与集成记录

本轮完成普通defer、range/array/slice for和bool match的真实生产合并，保留已集成方法后端。整体L3/L3A/G5继续partial；外部声明默认unsafe新差异已按原负责人分工发布cursor:L3EXTUNSAFE1返修（手动客户端，不自动启动AI）。

实际源码/契约审查：生产lower采用已验收for候选e64ff2...与defer候选7fd2be...，清理helper及bool-match helper逐字保留，for helper只额外设置/恢复3处loop_cleanup边界；return先完整求值并保护snapshot，循环转移只清至本循环，不清外层注册。前端Graph/ref/Info及IR ABI未改。node_slots复用仅为编译期scratch，四池容量/别名/guard及空Program失败发布保持；nasm_program.dg与program_ir.dg生产字节保持原值。

正式R1作业 **f48ec24178864741a9a0b2d09290f546**：**25项、0skip**，1558.879s（unittest1557.141s），passed/source_stable/process_stopped/execution_exited均true。方法10、defer6、for9个永久主线用例唯一执行，共享冻结good编译器，各测试独立source目录和清单，分别真实构建bad-head/bad-return/bad-increment三个董变体。所有坏体都编译链接正常、在debug/release实际执行后由独立值oracle拒绝；未用编译失败冒充负控。25个短目录ID无碰撞且完整名称映射保留。

生产测试不依赖works/project.json或候选overlay；good的47模块provenance均为生产源码，实际lower SHA **2eb36a91291ce4293e89654a9f2b91e1edf9742e8b87c73624a701dc2e10241e**。标准语言发现998项，本25项唯一、loader错误0；这是发现检查，不是998项全回归。原两个候选及其全部4项冻结文件指纹均保持不变，正式生产13项指纹亦逐项重核一致。

真实跨功能组合覆盖for/match内break/continue、root及loop defer次序、cleanup内临时数组循环、pair返回经过清理仍保留完整快照。实际Dong生成的控制流NASM交由生产native_assembler生成两份ELF，在宿主实际执行均返回**69**，exact/one-short/guard/源不变通过；ELF均8200字节。独立读取程序头确认x86-64 ET_EXEC、入口位于RX、LOAD文件/虚拟范围有效且页不重叠、W/X分离。SHA为d48c92d8103e3baca1905f5b06c0ec00ca88ba369c0867718e74276c90197aef与d194571efddc1035aa02bad6b2feee4665113917e45d732cc057d4cb6eb8e0f6；详情L3FLOWINT1-native-elf-inspection.json。这是宿主执行，未运行DongOS/VM，也不当作新G4/G6。

独立于永久语料的新源码/C观察器全部针对正式真实产物并核对staged/source SHA：方法384值观察+2次真实坏体拒绝；defer1280值/指针/trace观察+2拒绝；for/match512观察+2拒绝；混合for/match/defer再256向量+4拒绝。混合负控分别漏return清理或错误for步长，均正常退出17并给出精确independent-control-value。四份summary/命令/产物指纹汇于L3FLOWINT1-result.json，build子目录run-da0643ee50ed保留，未构造目标AST/IR或seed回退。

G5保留原8探针，新增4个控制流探针；method/defer/SysV/三类for/bool-match共7路径的debug/release都必须实际原生执行通过，enum/error/try/orelse/Win64五原探针仍精确失败并保留输出。只读补充审计16个seed接受样例：旧5项×两模式已转原生编译成功，另11项×两模式仍明确失败；该审计严格标compile-only，真实行为由本门禁覆盖。更广函数指针、内存内建/原子/asm、完整ABI/诊断、终止清理及enum receiver等仍未完成，不以有限探针代替完整G5。

额外接受性复核发现旧semantic_types对无体SysV普通函数/方法未默认unsafe：4个安全上下文观察seed拒绝而原生接受，4个unsafe对照均接受。未执行外部目标，未修改本任务范围外semantic_types.dg（仍为d2165319...）；证据2026-10-22-L3-extern-default-unsafe.md和build/L3-extern-unsafe-review/summary.json，返修任务cursor:L3EXTUNSAFE1。此缺口不被本轮有限集成通过覆盖。

历史停止回执b8a7b10b53094f238ae8d9667c0773e5保留：0tests、cancelled=true、source_stable=true、process_stopped/execution_exited=true，130.475s。实际WinError206探针确认观察器路径过长后，经managed pause确认退出再resume/rework重新领取，仅将wrapper目录改短ID并追加交付，全部Dong/永久测试/G5字节未改。267→211字符实际C编译/启动通过，随后重建本R1全25项；没有跳过或篡改源码稳定检查。详见L3FLOWINT1-R1-path-fix.json。

真实合并已在声明生产文件和永久测试落盘并由上述正式作业直接冻结验证，可按最新rev依次登记L3FLOWINT1及两个原候选integrated。原历史/候选和停止回执不改写，不提交推送、不运行OS/VM、未重跑完整语言CI或新源码G4/G6。

最终协调器登记：codex:L3FLOWINT1 **integrated rev12**；codex:L3DEFER1 **integrated rev6**；codex:L3FOR1 **integrated rev6**。此前codex:L3METHODLOW1保持integrated rev6。cursor:L3EXTUNSAFE1已发布原负责人返修，auto_dispatch/auto_verify均false，等待Cursor手动执行。上述状态均由MCP按最新rev写入，未手改数据库或派生索引。
