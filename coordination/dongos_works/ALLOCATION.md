# DongOS 客户端分工（2026-10-18）

## P2 优先，随后 P5（2026-10-23T02:55:00+08:00）

用户最新顺序：先完成 P2，再完成 P5。P2FLUSH11 已 integrated rev6，
正式独立作业64cf4d5d11454dfebd38a28ec54136b8通过3项、零skip；190原始
产物SHA及三正/三真坏ASM独审通过。P2仍partial：调度后多根大页/EXEC/WC
消费者、支持环境的AP PCIDE=1及物理WC性能仍须完成。普通多根变更协议和
BSP/逐CPU PCID已有实现，既有11项P2任务不重复派发。

P2PCID12、P2ROOT13、P2WC14和进度接续P2SYNC15在途，未提前验收。
ROOT13首轮因快照期间源变化而未执行测试，已保留记录并准备重排。
本检查点190项=161 integrated+24 accepted+4 in_progress+1 paused；
实时以MCP为准。G6PREP1宿主22项0skip已integrated6，未运行新G6来宾；
G6DOC1按用户优先级paused2。P5尚未开始本轮实现。没有运行OS/VM或提交推送。

详见[当前P2检查点](codex-works/reviews/2026-10-23-P2-current.md)。
以下带日期的数量、候选和“当前”均保留各自历史范围。


2026-10-23 用户授权G5收尾已完成：FULL1 integrated16、CLOSURE1
integrated21、INT1 integrated24，方法及两项文档收尾均integrated6。
最新正式70项零skip、源码稳定及原始产物独审通过；主线真实文件和
[完成回执](codex-works/reviews/2026-10-22-G5-completion.md)已落盘。
当前183项=159 integrated+24 accepted，其余活动状态为0；实时仍以MCP为准。

不重复派发旧method/enum/error/try/orelse/defer/双ABI八类G5差集。
后续按用户安排分别处理扩大编译器的新G6、内建assembler更广指令范围、
P5安全回收及其它OS/外部门禁；旧G6范围保持。没有启动外部AI CLI、
没有接管其它客户端已领取任务。一般派单偏好及下方历史记录保留。

本轮17份缺失任务书、CX6同号异义和CX14/CX15旧状态均已处理完成。CX14 integrated rev7，CX15 integrated rev8；CX6 integrated rev9，已恢复读取器契约，分离5条原NASM事件，耗时恢复为1轮/265秒，原始事件全部保留。协调器issues=0；核对时间2026-10-22T09:18:41+08:00。

本次恢复收尾没有新派单或接管其它客户端的新任务。已恢复组件及CX14/CX15不重复派发；后续继续按真实G5/P5/硬件差集及用户最新分工授权执行。其它客户端新增队列以MCP最新rev为准。来源见[恢复报告](reviews/2026-10-22-task-recovery/README.md)。

以下保留原有记录；其中日期、任务数量、机器路径和“当前/下一步”均属于各自历史检查点，最新状态以上述记录及协调器为准。

2026-10-21 用户明确要求给 Claude 分配任务：已通过协调器发布 [claude:P2EXEC1](claude-works/tasks/P2EXEC1-board.md)（动态执行别名真实降权、同步与授权事务）和 [claude:P2WC1](claude-works/tasks/P2WC1-board.md)（图形缓存类型撤映射、同步与 WC 重映射事务），发布时均 todo rev1。原 Claude 队列无未结在途；本次明确授权覆盖旧额度不足期间暂停新增偏好。两项实际执行既有 planner 和 live 页表 API，仅本人 works 各六文件，彼此及 Codex P2SMP3、DeepSeek L3/L3A 无写路径重叠；不重做纯规划器。本人客户端 worker MCP 手动领取/提交，无 AI CLI 自动启动、不建 PR。正常消费者 hook、硬件回调、实际客体正反例及最终复验/验收/本地集成由 Codex 接续；组件提交不代表整个 P2、动态 EXEC 或图形 WC 已完成，也不替代 WC 真实硬件性能验收。见 [完整任务和回执](reviews/2026-10-21-Claude-P2EXEC1-P2WC1-allocation.json)。

2026-10-21 用户明确要求让 DeepSeek 做 L3 和 L3A：已通过协调器发布 [deepseek:L3A](deepseek-works/tasks/L3A-board.md)（原生整程序可变全局量及真实产物闭环）和 [deepseek:L3](deepseek-works/tasks/L3-board.md)（语言/ABI 整程序差分执行与真实缺口回归），发布时均 todo rev1、尚未领取。先执行 L3A，其五项既有依赖已 integrated；L3 等待 L3A 独立验收后领取。两项只写本人 works，保留既有读取/栈/49 模块固定点成果，不重复派发，不代表整体 L3/L3A/G5 完成。方法、枚举、错误传播、defer、完整外部 ABI 等差集继续保留；本批先闭合全局量及差分框架。由 DeepSeek 本人客户端 worker MCP 手动领取/提交，未启动模型或 AI CLI；Codex 负责独立复验、验收及真实本地集成，全程不建 PR。Codex 的 P2SMP3 继续在途，两项路径与其无重叠。完整任务与发布回执见 [派单证据](reviews/2026-10-21-DeepSeek-L3-L3A-allocation.json)。本次明确授权覆盖旧的 DeepSeek 暂停新增偏好，其它队列保持原约定。

2026-10-20 接续派单：已通过协调器发布 [Cursor P5CTX1](cursor-works/tasks/P5CTX1-board.md)，所属 **P5：设备故障恢复 → 精确持有上下文接线**，todo rev1；仅本人works中7个声明文件，Cursor手动worker MCP读取、领取和执行。先关联真实DMA申请成功/失败、Catalog owner与设备/内存各自代际，再附已有退休及reset-hold观测；本项不回收DMA、不发布新token、不代表P5完成。不恢复归档CR43/CX6、不启动AI CLI。C52与CXNASM3已完成新正式独立复验及正常验收/集成，分别integrated rev14/rev6；当前122活动任务＝102 integrated、19 accepted、1 todo。G6既有runner的CI提案已准备但未安装或运行。证据见[本轮接续报告](reviews/2026-10-20-p5-g6-next-actions.md)；未来分配偏好保持下文约定，本轮Claude/DeepSeek/LM Studio无新增。

2026-10-20 合并接续：PR#8已合入main `244b18c`，源码已同步本机。已有本地UI与任务记录保留；异机161条原任务尚未导入当前调度库，CX6/CR43同号异义，禁止按rev覆盖或事件union。当前本机仍121活动任务；阶段及后续以[整体任务图](progress-map.md)为准。异机新增派单和交付历史保留在[固定PR8档案](https://github.com/EDarcyWong/dongos/blob/50ab7cf9cde101691774a8480bdb7fcc07c766be/coordination/dongos_works/ALLOCATION.md)，不作为本机当前待领取队列。

2026-10-20 主线补登记：C49/C50、CR38～CR42、D25/D27原36交付仍匹配独立验收指纹，实际主线生产/说明/永久测试已核对；9项通过MCP按最新rev登记integrated。主线10模块40项（含C52另6项）零skip且84输入稳定，C52与CXNASM3仍submitted等待正式结算。见[本轮核对报告](reviews/2026-10-20-code-task-sync.md)，下方旧“尚未集成”保留历史。

2026-10-20 跨电脑恢复优先：派单前先查[异机完成台账](reviews/2026-10-20-cross-machine-task-ledger.md)、[整体任务图](progress-map.md)及 PR8 `3a4704d:L3-RESUME.md`。P2大页/别名/PAT、P6调度/tickless/init DAG及L3输入输出/64KiB栈/单arena固定点已有实现与历史证据，不重派开发；缺口按差集集成、原始记录恢复、明确缺陷和真实验收分别处理。原 `pool:P2ALIAS1/P2HUGE1/P2PAT1` 已取消归档，不恢复凑数量。异机原CX6/CR43与本轮临时编号不同义，临时记录已官方暂停归档并备份；NASM维护单独使用 `codex:CXNASM3`。本轮不新增Cursor设计派单，P5按最新工程交接及已有PR7/别名补强继续，L3入口桥及宿主机器验证已随PR#8完成，下一步按原CX14/G6做新快照真实双启与持久输出验收，不重派桥修复；未来客户端分配偏好保持下文约定。

2026-10-19用户明确要求直接完成Cursor进行中及待领取任务，并确认是代码实现和测试：Codex已接管并完成CR38～CR42，保留原编号/任务书/历史。CR38保留正确生产实现并补两出口RBX负控，CR39～CR42新增生产、说明、永久测试及交付；正式隔离每项4测试、共20项0skip、源码稳定，全部已accepted（CR38 rev9、CR39 rev7、CR40 rev13、CR41 rev7、CR42 rev7），尚未集成主线。本轮覆盖下方本批“Cursor手动执行/待领取”的旧快照，不改变未来分配偏好；Cursor无需重复执行本批。未启动任何AI CLI。见[直接实现与最终验收](reviews/2026-10-19-Cursor-CR38-CR42-direct.md)。


2026-10-19用户要求给Cursor分配任务：通过协调器MCP新增[CR39 短路布尔真实调用](cursor-works/tasks/CR39-board.md)、[CR40 双字返回前的作用域清理](cursor-works/tasks/CR40-board.md)、[CR41 8/16/32位checked/wrapping算术](cursor-works/tasks/CR41-board.md)、[CR42 切片视图PAIR构造](cursor-works/tasks/CR42-board.md)，均属 **L3：Dong自举后端/完整函数运行时语义接线**。各四文件、互不依赖且不冲突，20项涉及依赖已逐项MCP确认integrated；发布时均todo rev1。查询期间其它协调会话刚发布的[CR38 接续D26的64位受检算术](cursor-works/tasks/CR38-board.md)保持原队列，不重建/抢占；CR41仅窄位宽，CR42只构造视图不做D27的元素访存，不修改Claude C51/C52。已有领取/返修优先，由用户在Cursor客户端手动worker MCP读最新rev/完整任务后领取，未启动Cursor CLI或任何AI CLI。各项明确真实双模式/双格式/完整安全寄存器捕获及坏体数值、轨迹、容量原子性要求，交付仍须Codex独立复验/验收/真实集成，不代表完整L3完成。完整契约、依赖版本、CR38保留快照与发布回执见[派单证据](reviews/2026-10-19-Cursor-CR39-CR42-allocation.json)。

2026-10-19用户明确要求“将d26给cursor执行”：DeepSeek D26已暂停归档（rev3），接续为[Cursor CR38：受检64位算术与错误返回的完整SysV函数接线](cursor-works/tasks/CR38-board.md)，发布todo rev1。完整保留原L3契约、10项已integrated只读依赖及定向验证要求；四个可写文件映射cursor-works，检查时来源/目标均无实现、测试或交付，无需复制。来源D26任务书SHA不变，原cursor:CR36仍归档；历史链CR36→D26→CR38。Cursor在本人客户端手动worker MCP读完整任务与最新rev后领取，不自动启动AI CLI；DeepSeek停止D26写入/提交，D24/D25/D27保持原队列。见[转派记录](reviews/2026-10-19-D26-Cursor-CR38-transfer.json)。

2026-10-19用户要求给Claude分配任务：已通过协调器MCP发布[C51 原生表达式AST到C48直线IR](claude-works/tasks/C51-board.md)、[C52 多函数NASM模块及可链接导出](claude-works/tasks/C52-board.md)，均属于 **L3：Dong自举后端**。C51推进原生lexer/parser树到IR的真实接线，C52推进C48完整函数到目标模块文本的接线；各四文件、互不依赖且不重叠，不抢DeepSeek D24～D27。C48已integrated rev13、CR3已integrated rev8；C51仅读已有前端/整数核心基线，C52不用尚未集成的C49/C50。发布时两项均todo rev1，由Claude本人客户端worker MCP读最新rev/完整任务后手动领取；先处理本人返修，未启动AI CLI。完整契约、依赖、只读核心SHA与回执见[派单证据](reviews/2026-10-19-Claude-C51-C52-allocation.json)。C52输出中的换行均按任务明确的真实单LF及22字节模块头定义，不输出反斜杠字符。

2026-10-19本聊天收尾状态：C48已实际复制生产/说明/路径适配永久测试到主线，主线4项0skip、输入稳定，登记integrated rev13；C49/C50 R1已分别正式4项0skip并独立核对40/32组原生好坏输出，已accepted rev10，尚未主线集成。见[集成与R1审查](reviews/2026-10-19-C48-integrated-C49-C50-R1.md)。新组件派单或验收不代表完整L3、stage1/stage2或客体自举完成，实时状态仍以MCP最新rev为准。

2026-10-19用户明确要求将Cursor任务转派DeepSeek：未完成的CR34～CR37已暂停并归档，后继依次为[DeepSeek D24 循环与真实回边](deepseek-works/tasks/D24-board.md)、[D25 switch多分支返回](deepseek-works/tasks/D25-board.md)、[D26 受检64位算术](deepseek-works/tasks/D26-board.md)、[D27 有界索引访存](deepseek-works/tasks/D27-board.md)。均属于L3：Dong自举后端/完整函数接线，发布todo rev1，完整继承原契约/18项已集成只读依赖/验证要求，各四文件改映射deepseek-works。CR34转交前in_progress rev2，其余todo rev1；检查时四项尚无实现或交付落盘，原任务书/领取/发布时间/事件保留，不继承验收。Cursor停止原编号写入/提交，DeepSeek在本人客户端手动worker MCP取最新rev、先处理本人领取/返修，再逐项执行；未启动AI CLI，不恢复原归档任务。此明确转派覆盖本批“Cursor执行”和DeepSeek少量新增的一般偏好，不改变其它队列；完整来源与回执见[转派证据](reviews/2026-10-19-Cursor-DeepSeek-transfer.json)。

2026-10-19用户要求给Cursor派单：已通过协调器MCP新增[CR34 有限循环与真实回边](cursor-works/tasks/CR34-board.md)、[CR35 switch及case结果关联](cursor-works/tasks/CR35-board.md)、[CR36 受检64位算术与错误返回](cursor-works/tasks/CR36-board.md)、[CR37 有界索引装入/存储](cursor-works/tasks/CR37-board.md)。均属于L3：Dong自举后端/完整函数接线，发布时todo rev1，各四文件、互不依赖，18项只读依赖已逐一查询integrated；不重写既有组件，与Claude C48/C49/C50无文件冲突。原CR30～CR33继续归档，不恢复、不转派Claude在途任务。本人已有领取/返修优先，Cursor在客户端手动worker MCP读取最新rev后领取，未启动AI CLI；交付仍需Codex独立复验、验收及真实集成，不能据此宣称L3完成。完整任务、依赖版本和发布回执见[本批派单记录](reviews/2026-10-19-Cursor-CR34-CR37-allocation.json)。

2026-10-19用户授权Codex直接修复D23：测试夹具内存/NULL协议/对齐与隔离问题已修，生产逻辑不变；正式及主线各3项零skip、SHA稳定，已验收并真实集成。见[D23修复与集成](reviews/2026-10-19-D23-fixed.md)。不等同已执行自编译产物比较。

2026-10-19用户授权Codex直接修复D22：原编号R1已补齐全GPR/RSP捕获、真实只读源页与完整快照及实际坏R11数值负控，生产逻辑不变。正式和主线各5项零skip、SHA稳定，已验收并真实集成；覆盖此前D22待返修状态。见[D22修复集成](reviews/2026-10-19-D22-R1-fixed.md)。

2026-10-19最新复验：C46/C47正式与主线各同6项零skip、SHA稳定，已验收并真实集成；原CR30/CR31继续归档。D22独立真实坏Dong证明R11保持检查缺口，原任务已退回DeepSeek R1，另须落实真实只读源页保护；先返修再领取新项，在途任务不抢占。见[本轮审查与集成](reviews/2026-10-19-C46-C47-D22-review.md)。

2026-10-19用户要求DeepSeek一个简单任务：新增[D23 编译产物逐字节比较与首差定位](deepseek-works/tasks/D23-board.md)，所属L3：Dong自举后端/产物一致性基础工具，发布todo rev1。仅四文件、无依赖/分配/I/O/VM，只比较内存切片并报告首差或长度差；实际Dong两模式、双格式、有限向量、只读/别名原子性和真实坏体验证。D21已integrated，D22已submitted；若本人收到返修则先返修再领取D23，不启动AI CLI。工具通过不代表已完成stage1/stage2自编译比较。

2026-10-19本轮L3复验收尾：C43、C44（原CR32）、C45（原CR33）、D21 R1、CX2、CX4、CX5均已完成独立源码/契约/有效测试审查并登记integrated（CX4/CX5状态由另客户端推进，本审查者补审并独立主线18项零skip）。C43/C44/C45/D21生产/说明及永久测试已真实复制适配主线，集成后对应4/5/4/5项均零skip，耗时60.124/47.885/23.228/66.719秒、文件前后SHA稳定。CX2优化版正式10项0skip1209.695秒，另19项两模式38次独立追加检查通过，主线现有文件与正式隔离输入一致后验收/集成。D21复制失败旧作业零测试不计通过，按最新rev显式重发布同一稳定交付并重新正式5项0skip67.678秒后才验收。CR30首交已退R1，后由其它客户端依用户要求归档转claude:C46；不继承验收，本轮未登记C46通过。后续新提交另行复验，不将本批收尾写成整个队列或完整L3已完成。证据见[ C43/CX2 ](reviews/2026-10-19-C43-CX2-independent.md)、[ C44/C45 ](reviews/2026-10-19-C44-C45-independent.md)、[ CR30/D21 ](reviews/2026-10-19-CR30-D21-independent.md)、[ CX4/CX5 ](reviews/2026-10-19-CX4-CX5-independent.md)。

2026-10-19用户要求再给Claude两项：新增[C49 条件比较/双分支返回整函数](claude-works/tasks/C49-board.md)和[C50 实参重排/跨函数调用整函数](claude-works/tasks/C50-board.md)，均属L3：Dong自举后端/整函数接线，发布todo rev1。依赖全部integrated、各四文件，与在途C48独立无文件重叠。先完成C48和本人返修，再领取；真实Dong生成完整函数并call/ret，数值与完整保持、容量原子性负控必需。只派单不启动AI CLI，不等同整个L3完成。

2026-10-19用户再次要求Claude派单：新增[C48 受限u64直线IR到完整SysV函数接线](claude-works/tasks/C48-board.md)，所属L3：Dong自举后端/整函数接线。八项依赖全部integrated，四文件无冲突，发布todo rev1；C46/C47已提交，其它既有提交继续独立审查，有返修先处理。C48须真实生成并call/ret完整函数，独立解释器核对结果、完整保持和原子性负控；不宣称完整AST/IR或自举完成，不启动AI CLI。

2026-10-19用户明确要求转交Cursor全部进行中/返修任务：cursor:CR30（rework rev4）→ [claude:C46](claude-works/tasks/C46-board.md)，cursor:CR31（in_progress rev2）→ [claude:C47](claude-works/tasks/C47-board.md)。原任务已暂停并归档，原历史/时间/审查/文件不变；新任务均待Claude领取，现有代码/测试已带入claude-works，C46必须继承R1全部返修意见，C47继续未交付开发。旧交付仅历史基线，须实际补齐并重新正式复验；不继承验收。证据[2026-10-19-Cursor-Claude-transfer-20261019T081242Z](reviews/2026-10-19-Cursor-Claude-transfer-20261019T081242Z/transfer.json)。Cursor停止原两项，Claude读取完整任务后手动领取，不启动AI CLI。

2026-10-19本轮L3审查最终进展：C43正式4项零skip59.802秒，独立直接4项零skip59.726秒；已验收并实际复制生产/说明/永久测试到主线，主线同4项零skip60.124秒、文件SHA稳定，已登记integrated rev6。见[审查集成记录](reviews/2026-10-19-C43-CX2-independent.md)。CR30/D21已原任务退回R1，缺口见[返修记录](reviews/2026-10-19-CR30-D21-independent.md)。CX2首轮正式作业由原负责人取消（非超时、源码稳定），原负责人仅优化坏体非本机格式构建后提交rev9并排新作业58621310cc104b8a8ba3f9676f219106，本轮未验收CX2新提交。期间新增CX4/CX5已由另客户端推进integrated rev6；本审查者亦实际补审源码/契约/测试并在主线独立18项零skip40.940秒，不重复写状态，见[补审证据及限制](reviews/2026-10-19-CX4-CX5-independent.md)。未运行OS/VM，完整L3/客体门禁未据此宣称完成。

2026-10-19本轮处理L3待复验：CR30、D21首交已实际审查生产/契约/永久测试，发现完整GPR保持观察缺口，CR30另有负控好侧使用Python汇编模板。仅取消两项queued复验，未中断运行作业，已原编号退回R1；不得重写已正确组合或移交给别人。详见[返修依据](reviews/2026-10-19-CR30-D21-independent.md)。C43独立直接4项零skip通过（59.726秒），CX2追加19项两模式共38次通过，正式作业仍运行/排队；这些中间结果不等同验收/集成，最终以协调器状态和后续审查记录为准。

2026-10-19用户明确要求CR32、CR33重新指派给Claude：已通过协调器将未领取、无作业/实现产物的cursor:CR32、cursor:CR33先暂停再归档（各rev3），完整原任务书和原发布时间/事件保留；正式后继为[claude:C44 接续CR32](claude-works/tasks/C44-board.md)、[claude:C45 接续CR33](claude-works/tasks/C45-board.md)，发布时均todo rev1。两项均属于L3：Dong自举后端；C44子阶段为后端基础组件组合接线，C45为目标产物静态ELF64镜像。各四文件已映射至claude-works，原接口/验证要求/依赖保留；新任务书记录来源与原任务书SHA256。Claude读取最新rev后手动领取，既有领取/返修优先，不自动启动CLI，不恢复Cursor原任务。转交后时间按各自事件保留和统计，不能将新发布时间覆盖原发布时间。

2026-10-19总门禁推进：C41/C42已真实集成（主线9项零skip），CX3合法静态指针重定位兼容修复已集成；CX2 optional/result match主线用例已通过但正式全模块负控复验中，尚未验收。Cursor新增[CR33 ELF64产物容器](cursor-works/tasks/CR33-board.md)，与现有CR30～CR32不重号/不冲突；按本人队列执行。完整L3剩余门禁见[实况记录](reviews/2026-10-19-L3-completion-progress.md)，不得以组件通过替代stage1/stage2/客体FLUSH及重启验收。

## 派单阶段标注（用户要求，2026-10-19起生效）

以后每项新任务必须在标题或任务书开头明确标注所属阶段，并在对用户的派单汇总中列出。标注采用项目既有阶段编号及名称（例如“L3：Dong自举后端”）；必要时追加子阶段和本项推进目标。不得将独立组件完成等同于整个阶段完成；涉及多个阶段时列明主阶段与关联阶段。

本批C43、CR30、CR31、CR32、D22均属于“L3：Dong自举后端”，子阶段为“后端基础组件组合接线”；这些任务尚不等同于活动IR接入或完整L3完成。

2026-10-19本轮按用户要求检测Claude并向三客户端补单：MCP查询时C41/C42均accepted rev5，正式复验分别4/5项、零skip，尚未登记integrated；本轮仅读取既有审查/复验状态，不冒充重新验收或集成。新增Claude [C43 间接调用组合](claude-works/tasks/C43-board.md)；Cursor [CR30 完整计数可变移位](cursor-works/tasks/CR30-board.md)、[CR31 门禁与除法组合](cursor-works/tasks/CR31-board.md)、[CR32 序言与入口捕获](cursor-works/tasks/CR32-board.md)；DeepSeek [D22 字节真值装入](deepseek-works/tasks/D22-board.md)。发布时均todo rev1、各四文件、依赖逐项确认integrated、文件互不重叠。DeepSeek D21查询时in_progress rev2，D22明确先完成D21及返修再领取。全部经worker MCP读取最新rev/领取后在本人客户端手动执行，不自动启动任何模型CLI；任务状态实时以MCP为准。

2026-10-19用户授权恢复DeepSeek派单：DeepSeek Harness desktop Cordis profile已加入coordination-tasks MCP，owner=deepseek、worker角色，实际stdio握手/8工具/本人todo查询通过，既有配置保留并备份。新增一项[D21 窄算术门禁与规范化组合](deepseek-works/tasks/D21-board.md)，依赖CR28/CR14均integrated，四文件，不与Claude C41/C42冲突；先只做本项。客户端重载后读取最新rev并自行claim，不自动启动模型CLI。旧“DeepSeek不可用/不派单”是历史状态，本条为当前用户授权。交付仍需Codex独立复验与实际集成。

2026-10-19最新推进：CR28窄算术范围门禁、CR29切片lo/hi/len门禁均已独立验收并真实集成；正式各3项零skip，主线各3项零skip（57.381秒/41.553秒），输入指纹稳定。审查者补跑正式实际Dong与坏体相同输入的精确路由对照，共8次正确拒绝。完整L3/IR接线仍未完成。Claude C41在途、C42待领取，以协调器实时状态为准。详见[CR28](reviews/2026-10-19-CR28-integration.md)、[CR29](reviews/2026-10-19-CR29-integration.md)。

2026-10-19按用户要求给Claude新增两项接线任务：[C41 直接调用及结果接收](claude-works/tasks/C41-board.md)、[C42 返回值装载与函数尾声](claude-works/tasks/C42-board.md)。依赖均已integrated，两项互不依赖、各四文件；必须实际复用既有组件，以真实Dong产出完成本机call/ret及数值负控。worker读取最新rev并领取后手动执行，不启动AI CLI。交付后由Codex独立复验并实际集成，不重复既有组件或宣称完整L3完成。

2026-10-19最新集成：C39/C40与CR24～CR27返修已完成独立验收、真实文件集成；正式独立与主线相同20项分别零skip通过，主线191.761秒且源码/永久测试/只读依赖/编译器前后指纹稳定。返回值装载/保存、原子store/CAS/fetch-add和重叠memmove均为独立组件，完整L3仍未完成。详见[本批集成证据](reviews/2026-10-19-L3-returns-atomics-integration.md)。历史返修/待领取文字为当时快照，以协调器最新状态为准。

2026-10-19最新审查：CR27正式3项零skip通过，但主原生路径执行Python模板且指针终值仅检查差值；独立实际坏Dong使两终值同时+1仍通过现有原生断言，两模式已实证。已原任务退回Cursor R1，详见[CR27复验记录](reviews/2026-10-19-CR27-independent.md)。CR24～CR27优先由原负责人完善返修；CR28在途、C39/C40待领取，均以MCP最新状态为准。不重复派单或恢复已验收/集成任务。

2026-10-19再次按用户要求补充Claude队列：新增[C40 调用返回值保存](claude-works/tasks/C40-board.md)，与已有[C39 返回值装载](claude-works/tasks/C39-board.md)分别处理caller/callee，文件互不冲突，不依赖尚未验收的新组件。两项均须worker MCP读取最新rev后领取，客户端手动执行，不启动AI CLI；完成后由Codex独立复验并决定验收/集成。

2026-10-19用户追加授权给Claude派单：已通过协调器发布C39「从固定帧槽发射SysV返回值及窄值扩展」，最新状态以MCP为准。仅四文件，依赖C14/CR8均已integrated，补齐入口/出站实参之后的返回值发射，不重复既有组件；完整任务书见[ C39 ](claude-works/tasks/C39-board.md)。原生测试须实际Dong产出、合计<=24、真实数值负控及完整保持检查，不启动AI CLI。CR24/CR25/CR26已原任务退回Cursor补测试契约，见对应2026-10-19独审记录。

2026-10-19补充：CR22 R2已独立验收并真实集成，正式/主线各3项零skip且来源稳定；与本批C35/C36/C37/C38/CR23合计6组件、26项主线定向测试通过。CR24/CR25审查发现原生观察及实际产出并发验证缺口，已原任务退回Cursor返修。完整L3仍未完成，最新状态以MCP为准。见[CR22 R2记录](reviews/2026-10-19-CR22-R2-integration.md)。

2026-10-19最新复验：C35/C36/C37/C38/CR23均已独立验收并真实集成，正式与主线同23项分别零skip通过、来源稳定；CR22原R1仍有48>24主要向量契约缺口，已有限R2退回并由原负责人领取。见[本批记录](reviews/2026-10-19-L3-latest-review-integration.md)。CR24新增交付继续独立审查，其余本人在途不抢占、不启动CLI；下方同编号返修描述为旧快照，最新以MCP为准。

2026-10-19继续推进：C34、CR21 R1亦已独立验收并真实集成，正式与主线同8项分别零skip通过、来源稳定；CR21交付文字在复验后变化曾被验收指纹关卡拒绝，重新正式复验后才验收。与下批C33/CR20合计4组件完成集成，见[后续证据](reviews/2026-10-19-C34-CR21-R1-integration.md)。其它任务按本人队列继续，最新状态以MCP为准。

2026-10-19后续复验：C33与CR20 R1已独立验收并真实集成，正式/主线同8项分别零skip通过，见[集成记录](reviews/2026-10-19-C33-CR20-R1-integration.md)。C37/C38正式各4项零skip通过但独立坏Dong证明完整输入尾部别名测试缺口，已原任务退回R1，见[逐项要求](reviews/2026-10-19-C37-C38-independent.md)。公共NASM警告能力检测已由Codex CX1修复并独立验收集成。下方“本批8项均返修”为早期状态，后续各项实时以MCP为准；原负责人继续本人返修，不重复派单或启动CLI。

2026-10-19复验更新：C33～C36、CR20～CR23本批8项已原任务退回R1，正式28测试0skip通过但独立实证测试契约尚有缺口，未验收集成；两客户端优先补本人返修，再领取剩余新项。无需重写已正确生产算法，不增加新任务或恢复归档任务。见[逐项复验依据](reviews/2026-10-19-Claude-Cursor-submitted-review.md)。

最新追加授权（2026-10-18）：用户要求多生成任务，已通过MCP再发布10项——Cursor CR24～CR29六项（原子store/CAS/fetch-add、重叠memmove、窄值范围、切片上下界），Claude C35～C38四项（switch分发、scope清理调用、incoming实参捕获、静态64位重定位）。每项四文件，依赖均已集成，彼此无依赖；原CR20～CR23、C33/C34保持原队列，先完成已领取/返修。客户端worker MCP手动执行，不启动CLI；DeepSeek/LM Studio本轮0新增。见[正式派单与完整任务链接](reviews/2026-10-18-Claude-C35-C38-Cursor-CR24-CR29-allocation.md)。

最新用户授权与本轮结果（2026-10-18）：复验并继续给Claude和Cursor派单。C30/C31/C32已全部验收并真实集成，主线13项0skip、来源稳定；C31首交长标签缺陷已由Claude原任务R1修复，16次独立合法边界重放正确。通过MCP新增Cursor CR20～CR23四项（边界/移位量/乘法/负号门禁）、Claude C33/C34两项（并行复制发射/SysV实参建立），全部依赖已集成、各四文件；CR20已由Cursor领取。原C31先返修条件已完成，Claude可继续新任务；Cursor客户端手动执行，不启动CLI，DeepSeek/LM Studio本轮0新增。见[本轮完整记录](reviews/2026-10-18-C30-C32-and-new-allocation.md)。此段覆盖下方早期批次摘要。

最新用户授权（2026-10-18）：复验C29/CR16～CR19同时继续向Claude派单，已发布C30～C32三项：缩放索引操作数、除法异常门禁、字节复制/清零发射。依赖已集成、各4文件、通过worker MCP手动执行，不启动CLI；原五项移交已归档不恢复。见[任务](reviews/2026-10-18-Claude-C30-C32-allocation.md)。

最新用户授权（2026-10-18）：继续给Claude派单，现通过coordination MCP新增C26～C29四项；C22～C25已集成，原移交五项已归档，不恢复。四项独立、依赖已集成，客户端领取执行，不启动CLI；Cursor原队列保留，DeepSeek/LM Studio本轮不新增。见[本批记录](reviews/2026-10-18-Claude-C26-C29-allocation.md)。

最新用户要求（2026-10-18）：继续向 Cursor 和 Claude 派单，统一使用 coordination MCP，不使用 CLI 派单或启动模型。已追加 Cursor CR16～CR19 四项、Claude C24/C25 两项；先前未完成任务继续有效，优先处理已领取/返修，不抢占其它文件。DeepSeek 暂不可用，不新增；LM Studio 本轮0新增。见[追加派单记录](reviews/2026-10-18-more-mcp-allocation.md)。

最新用户授权（2026-10-18）：Cursor继续主要新增开发，现发布CR12～CR15四项；Claude可以接单，现正式发布C22/C23两项。DeepSeek暂不可用，不再派单，D20已由Codex接手完成集成。Cursor先补CR11原R1仅剩端点夹具，再领取独立新项；LM Studio本轮0新增。见[本批记录](reviews/2026-10-18-next-emitters-allocation.md)。此段覆盖下方Claude尚未发布/DeepSeek继续新派的旧批次状态。
最新增量：D19 R1与LM8已验收并集成；本次仅给DeepSeek发布[D20](deepseek-works/tasks/D20-board.md)一项SLEB128有符号解码，依赖D19，未启动模型CLI。Cursor CR8～CR11继续原任务，Claude预留模块与延后派单安排保持原约定。下方D19/LM8待领取及D14～D18在途描述为此前批次历史。

当前批次：CR5已集成；新增Cursor CR8～CR11四项、DeepSeek D19一项、LM Studio LM8一项，均通过MCP发布待领取。只分配不启动模型。D14～D18现已集成，下方“未关闭/在途/本轮新增0”为旧批次历史。Claude延后候选及一次后续派单约定见[CLAUDE_NEXT.md](CLAUDE_NEXT.md)，不是当前已发布任务。暂停旧Claude任务未删除；新派单不得恢复已转交的原五项。

用户最新要求：尽量多给 Cursor，少给 DeepSeek，LM Studio 只做最简单任务。此约定替代此前“Claude 多分配”的偏好，只适用于 DongOS 项目，不修改其它项目的策略。

| 客户端 | 后续默认分配 | 执行方式 |
| --- | --- | --- |
| Cursor | 承担主要新增开发；有真实独立工作时每批约 4～6 项，按依赖领取 | 用户在 Cursor 客户端手动发起，通过 MCP 领取/提交，不启动 Agent CLI |
| DeepSeek | 少量补充，当前仅新增D20一项；先完成在途任务再加新任务 | 本人客户端通过MCP领取/交付，不复制成并行实现、不抢占 |
| LM Studio | 同一时刻最多 1 项；固定数据、小文档、简单整理为主，通常不超过两个可写文件（含交付） | worker MCP 查看/领取/提交，无文件工具时释放并说明，不以聊天正文冒充文件 |
| Claude | 当前可正常接单；C33/C34原队列及新增C35～C38四项，按已领取优先逐项完成 | 本人客户端worker MCP领取/交付；旧移交五项已归档，不自动启动CLI |
| Codex | 维护主线、任务契约、交付审查、独立复验及集成 | accepted 与 integrated 分开登记 |

当前 DeepSeek 五项是用户上一轮要求转交后已领取的在途任务，不为满足新批次数量强行中断或重复派给 Cursor；本轮新增 DeepSeek 任务为 0。未来按小批次补充。

只分配有明确用途、边界和可验证交付的任务，不为凑数量重写已验收组件。工作先放各自 works，新任务文件不与活动主线/其它负责人重叠；依赖已验收/集成才可领取。Cursor 当前新增 CR3～CR7，LM Studio 新增 LM7；任务状态由 MCP 提供，本文件仅记录分配偏好，不是自动调度程序或启动指令。

CR3：NASM 内部符号编码；CR4：定宽整数十进制文本；CR5：BSS 声明（依赖 CR4）；CR6：条件分支与落空边规划；CR7：SysV INTEGER 返回规划。LM7：八条给定十进制数据，独立检查由 Codex 提供。具体接口、失败语义、只读依赖和验证范围以任务书为准。


2026-10-22 最新用户授权：Codex正式接手P2WC1/P2EXEC1，两项组件已分别集成rev10/rev18。后续继续全部剩余任务；DeepSeek交付复验发现需返修则转Codex直接修，不再交回DeepSeek。L3A现由Codex接手rev7，原交付和7项正式零skip证据保留，尚未验收。全部任务、测试、验收及本地集成完成后提交完整代码至GitHub主分支，验证远端后关机；仍不建PR。旧分配历史保留，实际状态只以MCP为准。
