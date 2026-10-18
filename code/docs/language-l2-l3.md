# L2 / L3 实施与验收记录

2026-10-18后端增量：C29、CR16～CR19均已验收集成，16组件与2真实组合共18项主线测试0skip通过、来源稳定，C29/CR16历史待修闭合。除法异常门禁另由Claude C31实现，不据此关闭完整L3；见[组件记录](bootstrap-backend-components.md)。

2026-10-18后端新增：C26～C28已验收集成，主线12组件+1真实shift/select/call组合共13项通过0skip、来源稳定；C29快照中止未执行测试，尚未集成。见[组件记录](bootstrap-backend-components.md)。活动后端未切换，完整L3继续未完成。

2026-10-18后端增量：CR11～CR15已按验收字节集成，主线同15项和真实frame/memory组合1项共16项通过0skip、来源稳定；历史CR11～CR13返修已闭，CR16仅补原生R8覆盖。详见[组件记录](bootstrap-backend-components.md)。这些独立组件和组合验证尚未取代活动后端，不关闭L3。

## 2026-10-18 比较/整数算术发射集成

C22～C24已按验收字节集成，主线12项组件与1项真实Dong片段组合共13项通过0skip、来源稳定。组合验证wrapping加法结果进入比较及signed/unsigned溢出分支，未代替完整代码生成器；见[组件记录](bootstrap-backend-components.md)。CR12只读输入夹具仍待修，CR11本次快照失败未跑测试，未以客户交付或未执行的测试标记验收。本轮不改原生语义源码。
## 2026-10-18 optional/result 解包流程增量

原生语义新增try、orelse及return/break/continue回退，拒绝丢弃result；已知const标签和不返回状态控制短路及循环出口，工作区ABI不变。95个单模块加1个跨模块案例两模式对照宿主，相关7项通过0skip、来源稳定，两种坏Dong共4次原生准确拒绝。见[解包与流程记录](l3-tagged-flow.md)。未重跑全语言回归，完整L3仍未验收。
## 2026-10-18 Cursor 后端组件增量

CR8～CR10的基址位移、整数装入、条件分支文本模块已按验收字节集成，永久主线9项通过0skip、来源稳定；CR10另12次原生布局观察通过。CR11/D20因验证漏检退回原任务R1，未集成；见[组件记录](bootstrap-backend-components.md)和[交付复验](../../coordination/dongos_works/reviews/2026-10-18-Cursor-DeepSeek-review.md)。本批没有宣称完整代码生成器或L3自举完成。
## 2026-10-18 原生内存内建语义增量

bootstrap.semantic_types补齐volatile/非对齐/原子/编译器屏障9种内建的参数、unsafe、只读和返回类型检查，工作区ABI不变。85个案例在Dong两模式实际对照宿主，运行时相关定向6项通过、0skip、来源稳定；两类坏Dong共4次原生执行准确拒绝。现有切片、类型/调用、确定初始化及容量/参数守卫亦通过。见[内存内建语义](l3-memory-intrinsics.md)。未运行全语言回归，完整L3继续未完成；下方9项等是此前切片批次的范围与回执。

## 2026-10-18 原生切片语义增量

bootstrap.semantic_types新增数组place/已有切片的切片表达式、只读限定、已知界限/长度传播和packed字段对齐检查，原工作区ABI保持不变。37个切片案例两模式实际对照宿主；运行时/声明定向9项通过、0skip，12次真实坏Dong被准确拒绝。最终核对源/wrapper/观察器身份复用本轮16个原生产物重跑断言，修正语料前的失败保留；不是新的443项全回归。证据与范围见[切片语义](l3-slice-semantics.md)，完整L3继续未完成。D19 R1和LM8亦已独立验收并集成，主线5项通过0skip，见[组件集成](bootstrap-backend-components.md)。

## 2026-10-18 后端规划组件集成

C7～C12与CR1已按验收字节集成到lang/bootstrap，并进入永久主线测试；真实董组合验证已覆盖七个模块之间的数据交接和NASM二进制恢复。相关回归38项通过、0skip，组合测试另1项通过；见[集成说明](bootstrap-backend-components.md)。完整Dong后端与L3自举仍待完成。下方443项等回执是此前范围的历史，不能替代本轮集成证据。

2026-10-18，用户要求先补语言线，再推进后续系统任务。L1 已验收；L2 本轮循环/普通内存优化的固定性能集合已通过，当前推进 L3。不能由 P7 桌面或 P5 文件持久化的通过替代语言验收；下方较早失败基线保留历史。

## 当前 L3 组件与分工

新增原生[运行时类型与流程子集](../lang/bootstrap/semantic_types.md)：普通调用、参数/返回兼容、推导、赋值与只读place、unsafe指针、数组/结构体及静态索引检查；确定初始化、可达分支交集、循环break出口、返回路径、bool match与普通defer捕获检查。入口为`analyze_program`，追加5组有界工作区，保留原24池ABI；任何未支持构造明确拒绝，成功时unchecked_initializers=0。defer清理lowering和完整标签/错误/方法语义仍未完成，L3继续保持未验收。

最终语言回归 **443项通过、0skip、0失败/错误，1330.860秒**；受测源码、编译器及已验收协作组件前后hash稳定。回执 `build/test/language-priority/l3-runtime-b5d6af31ddbe/result.json`，脚本 `build/test/language-priority/check_l3_runtime.py`；包含C1～C5、D12/D13永久测试，按启动时任务状态排除C6；该组件随后另行3项和43194次扩展原生复验验收，不混入本回归数量。Cursor CR1源码/测试隔离于cursor-works，不进入本轮主线语料。没有OS/VM构建或启动、提交、推送或关机。源码和证据封存于同目录checkpoint，完整语义及L3_selfhost_complete保持false。

运行时4项测试通过：类型/值/调用/只读及unsafe案例46个、初始化/分支/循环/返回案例105个、显式不支持/5池容量案例9个，各debug/release原生执行。合法性独立对照宿主语义；29池guard、只读输入/描述符和20类INVALID逐案例检查。两类实际坏董实现（删除类型拒绝、分支交集改并集）在两模式共4次完成构建/链接/执行并被状态断言准确拒绝；ELF64/COFF组装通过。证据 `build/test/bootstrap-semantic-runtime/run-9db978e0294e/summary.json`，源码SHA256 `4d6a842ad2ed4ce7243c6e63d57f42c10f29b0baead7748b60517b9bee85e4e9`。早期harness别名错误和源码冻结前的开发运行保留，不充作最终稳定回执。

本轮完整源码AST对照222个模块、实际提取表达式28236个，1093个组合、45个类型及73个坏标点案例通过；14个bootstrap入口模块图原生绑定通过。新证据`build/test/bootstrap-syntax/run-c15a8a498090/summary.json`、`build/test/bootstrap-expression/run-406492133b1c/summary.json`及`build/test/bootstrap-binding/run-e7823ca90344/summary.json`，均纳入checkpoint。

另用独立种子0x20261018F1生成200个不同的1～4层嵌套分支程序，独立宿主接受性作期望，两模式共400次原生执行全部通过；只读页/guard与INVALID预检沿用真实harness。证据`build/test/bootstrap-semantic-runtime/independent-eab1f420d902/result.json`及同目录corpus.json，源码hash与本轮受测版本一致。

Claude C5已验收：3项定向、5600次独立新种子执行及8次真实坏实现拒绝，见[验收记录](../claude-works/reviews/2026-10-18-C5-acceptance.md)。C6源码位置定位随后也已通过独立3项、两模式43194次扩展执行及6次坏董控制，见[C6验收](../claude-works/reviews/2026-10-18-C6-acceptance.md)。C1～C6与DeepSeek D1～D13均已验收。新任务[Cursor CR1字节常量编码](../cursor-works/tasks/CR1-nasm-byte-literals.md)发布到cursor-works，源码/测试也先隔离在该目录，避开主线和已验收组件。VS Code项目设置接入本地LM Studio Code，与编译器语义改动独立，API连接验证见`build/test/local-model-vscode/result.json`。

剩余顺序：完整运行时/聚合常量/方法/错误与标签语义及defer清理→目标模块I/O/诊断CLI→后端/工具链→宿主stage1/stage2→真正DongOS自编译、FLUSH及同盘重启比较。C5尚未接入原生CLI；D12生命周期/D13源码与诊断适配也不以独立组件验收代替集成。

### 此前声明类型阶段记录（历史）

新增[声明类型/标量常量/布局语义层](../lang/bootstrap/semantic_types.md)，真正接入已验收 C3 `constant_arithmetic.evaluate` 与 C4 `type_layout.calculate`。在已有模块/名称/绑定图上解析基础类型、别名及跨模块类型，求值标量常量依赖、数组长度、对齐和布局表达式，检查存储/payload类型、按值递归、整数范围/移位及函数ABI签名。调用方提供全部24组有界工作区，依旧没有隐式分配、宿主检查器或OS调用。

最终语言回归 **436项通过、0skip、0失败/错误，728.688秒**，受测编译器、全部已验收组件、标准库和测试前后hash稳定。回执 `build/test/language-priority/l3-semantic-types-b77c17dccbd5/result.json`，脚本 `check_l3_semantic_types.py`。本轮包含Claude C1～C4及DeepSeek D12/D13的永久测试，仅排除正在开发的C5；没有OS/VM构建/启动、提交或推送。实际完整模块AST对照221个、提取表达式27573个、1093个生成组合、45个类型及73个坏标点案例通过；13个bootstrap入口模块图的原生绑定通过。新AST证据 `build/test/bootstrap-expression/run-81addba07978/summary.json`、`bootstrap-syntax/run-5b295cbddb8e/summary.json`；绑定证据 `bootstrap-binding/run-717256c3979c/summary.json`（三者均在build/test下）。源码、说明和证据引用封存在该回归目录 `checkpoint/result.json`，保持 `complete_semantics=false`、`L3_selfhost_complete=false`。

该层4项原生测试通过：87个依赖/常量图、43个错误/容量/深度案例、111个typed值/布局/签名案例，两模式共482次正常/拒绝案例执行；其中80个布局独立对照宿主TypeSystem，11种INVALID预检逐案例执行。完整输入图、源码/路径、Workspace描述符放入真实只读页；24个scratch池逐一保护真实双端。将实际C3运算改错及C4字段偏移清零的董副本在debug/release共4次均成功编译链接执行，并准确被值/布局断言拒绝；ELF64/COFF均组装。证据 `build/test/bootstrap-semantic-types/run-5e64b38c2ac4/summary.json`，生产源码SHA256 `5068c8d625b6dcaad4f3d9e3c8457bc296c059bb344e72cbdec2b6358757472f`，组件及依赖hash前后稳定。

独审修正了固定尺寸间接类型的假布局环：宿主接受的 `align(sizeof(*S)) struct S{x:u8}` 和 `struct S{x:[sizeof([]S)]u8}` 原先被拒绝，现已加入永久测试。C4紧凑图只追踪按值布局依赖；指针/切片等固定尺寸描述符采用合法的opaque metadata目标，真实payload仍保留在语义Type中，全部声明及签名在最终发布前另行验证。真正的按值环继续拒绝。早期C观察器构建警告、测试输入语法与负控运算编号错误均保留在原运行目录，未把这些准备失败计为有效负控；发现假环后中断的回归保留在 `l3-semantic-types-18db0c5c8b89/interrupted.json`。

Claude 新任务[C5单行诊断格式化](../claude-works/tasks/C5-diagnostic-format.md)已发布，文件归属避开本类型层；C1～C4保持已验收。DeepSeek D13在第四次复验已验收，D12第五次补交的原rewind used及init256正文也已独立验收，现D1～D13均已关闭，见[D12验收](../deepseek-works/reviews/2026-10-18-D12-acceptance.md)和[D13验收](../deepseek-works/reviews/2026-10-18-D12-D13-fourth-followup.md)。没有代改协作方生产实现或测试。

声明阶段OK仍不等于完整语义通过：聚合/运行时初始化计入 `unchecked_initializers`，运行时类型推导、赋值/调用、聚合常量、方法/错误码专项、确定初始化和返回/分支流分析及defer仍待完成；目标模块I/O、后端/CLI、stage1/stage2和真正DongOS自举也仍待完成。D12工作区生命周期及D13源码/诊断适配尚未集成，不以独立组件验收代替它们。

### 此前绑定/语法阶段记录（历史）

新增[原生语义绑定层](../lang/bootstrap/binding.md)：类型名/导入成员连接到具体符号，参数与局部名字按词法作用域连接到声明节点；for/match/defer作用域、同层重名、未声明名字及控制转移上下文有独立拒绝。最近作用域和循环上下文的坏董源码两模式共4次准确拒绝，实际bootstrap模块图端到端绑定通过。字段/方法候选及类型别名后缀保留待类型分析，不把绑定成功当作完整类型兼容或确定初始化通过。

本轮411项语言回归通过、0skip（320.804秒），受测编译器/核心/测试前后hash稳定；回执 `build/test/language-priority/l3-binding-43e58df876c7/result.json`。绑定层4项测试含58个作用域/类型/导入用例、17个错误/容量/深度用例、10类逐进程INVALID拒绝，以及8个实际bootstrap入口模块图，两模式原生及双格式组装。实际源码AST对照扩大至220模块、26885个表达式，1093组合、45类型表达式和73坏标点模块仍通过。新证据为 `build/test/bootstrap-binding/run-d9c667bf62a3/summary.json`、`bootstrap-expression/run-6093b872fd9e/summary.json`、`bootstrap-syntax/run-0a2a1f224626/summary.json`（后两者也位于build/test）。六个协作测试模块在本次核心回归中单独排除，其独立复验见下方；不会用411项替代协作验收。源码/说明及证据hash封存在本轮回归目录 `checkpoint/result.json`；没有OS/VM构建或启动，完整语义和L3自举仍未完成。

新增原生[模块图](../lang/bootstrap/modules.md)与[模块名称语义](../lang/bootstrap/names.md)：显式源码目录、根/路径匹配、导入别名、共享依赖、循环/重名拒绝，经真正 Dong lexer/parser 建图；再检查顶层名称/成员重名及 pub/private，原子发布符号表。模块与名称层各3项定向测试通过，两模式/双格式均执行。模块图29个案例独立对照既有文件系统Resolver；名称层42个确定/生成案例及10个重名/容量/坏图案例通过，删除private检查的真实董负控被拒绝。模块提供的是预读目录接口，DongOS文件系统I/O适配器尚未完成，不据此声称目标环境模块加载或完整语义已完成。

Claude C3纯常量求值、C4已解析类型布局均已独立验收：8项定向通过、0skip，两项共16次实际坏董源码准确拒绝；新种子每模式600纯常量/360布局图也通过，见[验收记录](../claude-works/reviews/2026-10-18-C3-C4-acceptance.md)。Codex继续类型/初始化/流程语义和组件集成；C1/C2保持已验收。DeepSeek D12/D13三次补交的原6项通过，先前guard和pre容量已关闭；仅补原失败init存储观察、单字节逐调用guard和精确容量prefix等原剩余，见[最新复验](../deepseek-works/reviews/2026-10-18-D12-D13-third-followup.md)。未代改协作方实现/测试，不重开D1～D11。

上一模块/名称阶段：407项语言回归通过、0skip（248.968秒），编译器/核心/测试前后hash稳定。回执 `build/test/language-priority/l3-modules-names-599fb1ffa934/result.json`，排除C1/C2/C3/C4/D12/D13六个协作测试模块；独立协作复验另记。两模式各219个完整模块AST、26517个实际提取表达式、1093个生成组合、45个类型表达式和73个宿主拒绝的标点删除模块均通过。原始证据：`build/test/bootstrap-expression/run-f290721af2a4/summary.json`、`build/test/bootstrap-syntax/run-87c7d8c40d72/summary.json`、`build/test/bootstrap-modules/run-c26db4c1dc22/summary.json`、`build/test/bootstrap-names/run-9c55c9a6f265/summary.json`。没有OS/VM构建或启动；完整语义和自举仍未完成。

受测编译器、核心、测试及本轮说明实物快照位于该回归目录 `checkpoint/`；`checkpoint/result.json` 保存全部文件和证据hash，明确保持 `complete_semantics=false`、`L3_selfhost_complete=false`。

下面401项及217模块是此前声明/语句阶段的历史回执。

Codex 已补齐 `bootstrap.expression` 的类型转换、结构体字面量、sizeof/alignof/offsetof 与完整类型语法，并新增 `bootstrap.syntax` 的模块/导入、声明及语句AST。复用统一有界 token/Node 引擎，不依赖协作中的实现；支持函数/receiver/结构体/枚举/error/别名/全局声明、修饰符以及绑定/分支/循环/match/defer/unsafe/asm/赋值。说明见[表达式/类型](../lang/bootstrap/expression.md)、[声明/语句](../lang/bootstrap/syntax.md)。未据此实现名称/类型/常量检查或宣称L3自举完成。

本轮新增6项后语言回归401项通过、0skip（165.501秒），受测编译器、bootstrap核心及测试前后hash稳定；回执 `build/test/language-priority/l3-syntax-137e0e8a748a/result.json`。明确排除四个协作测试模块；之后的协作复验另记，不拿此401项替其验收。两模式各对照217个完整实际模块的声明/语句/表达式AST，26049个提取表达式、1093个生成/优先级组合、45个类型表达式和73个独立宿主拒绝的标点删除模块；真实只读页source/token无写入。5类表达式坏源码加2类语句/字段坏源码两模式共14次全部被对应断言拒绝，双格式均组装。原始证据 `build/test/bootstrap-expression/run-ba0354f9d843/summary.json`、`build/test/bootstrap-syntax/run-4f776ce2732f/summary.json`，保留早期诊断定位失败现场；没有构建/启动OS或虚拟机。

本轮源码实物、结果引用和范围封存于回归目录 `checkpoint/result.json`，SHA256 `cd8f535e78e1e4d202d13d8686f899f5268ee6d7a330b0af598955337799631b`；明确记录完整语义与L3自举仍未完成。封存前重新核对全部受测源身份，未代改协作方实现/测试。

以下为此前仅表达式核心的阶段记录，保留其源码快照和当时范围，不代表当前仍缺三类表达式：

本轮4项永久表达式测试通过：两模式各执行216个实际模块提取的22048个表达式、1093个固定/生成/运算符组合、31个错误/容量/深度用例；15类参数拒绝在每次原生进程中执行。三类坏董源码（优先级、比较链、失败发布树）两模式共6次实际编译/链接/执行，全部由相应断言拒绝；ELF64/COFF均组装。原始证据 `build/test/bootstrap-expression/run-f2ef827573ee/summary.json`，语料索引同目录 `corpus.json`；216个模块全部可由宿主语法器解析，明确排除四个协作中的DG文件。

语言回归395项通过、0skip，受测编译器/测试/表达式源码前后hash稳定，证据 `build/test/language-priority/l3-expression-99d4d594418f/result.json` 和 `unittest.log`。执行脚本 `check_l3_expression.py` 位于同一language-priority目录，明确排除 C1/C2/D12/D13 的四个在做测试模块，没有替其验收。本轮未改这些实现文件，未构建/启动OS或虚拟机。当前相同源码根与写文件方式生成的基准汇编，与前次五项安静通过的汇编逐字相同，记录同目录 `benchmark-codegen-identity.json`；未重新计时。

源码实物与验收引用封存于同一回归目录 `checkpoint/result.json`，SHA256 `1275182e83fc0fc254d9b628173b427cf6d31018769096d4b35b75db04db18fc`。记录明确保持 L3_selfhost_complete=false 和 OS_VM_built=false；未以 AST 组件或旧性能结果替代真正 stage1/stage2/客体自举。

`bootstrap.bigint` 已有符号/小端 u32 limb、规范零、任意长度整数解析及加/减/乘/比较；原生3项两模式测试包含4096位独立Python期望、描述符/失败原子性和实际坏carry负控，证据 `build/test/bootstrap-bigint/run-29372d6b40d3/summary.json`。没有以64位截断任意精度常量。

文件归属：Claude C1/C2 的 `bigint_div` / `bigint_bits` 已独立验收：永久7项及新种子最高8192位、C1每模式1500/C2每模式3580附加用例通过，见[验收记录](../claude-works/reviews/2026-10-18-C1-C2-acceptance.md)；C3/C4验收见上方。DeepSeek D12/D13 的 `core.arena` / `core.utf8` 补交仍有原共同项漏检，见[最新返修要求](../deepseek-works/reviews/2026-10-18-D12-D13-third-followup.md)，暂不验收。Codex 维护核心、语法/语义/集成；本轮未代改协作方实现或测试。

剩余顺序：模块I/O适配与类型/常量/布局/局部作用域及流分析（语法阶段保留未折叠长度和编号，尚不做目标正数/范围检查）→ 后端/CLI/产物发布 → 宿主 stage1/stage2 → 真正 DongOS 自编译、FLUSH 与同盘重启比较。运行环境限制和最终门槛见下方，L3仍未完成。

## L2 后续优化通过记录

循环 phi 干涉/合并、并行边复制、比较分支及常量处理已优化；普通指针地址与读取加法只作局部有序合并。读取仍是 DCE 根，不跨 store 复用、不移动/消除读取故障。volatile/原子/asm、需要检查的操作、双字ABI/Win64及未支持函数保留L1；debug与默认O0契约不变。

原固定五项在安静环境、相同默认规模、2次暖身、9对交错样本下全部通过1.20：sum0.974、LCG0.999、mix0.980、array_sum0.951、array_copy1.116；`--check`退出0，证据 `build/benchmarks/run-1183f35a9f06/result.json`。原失败和诊断记录不覆盖；这只是既定有限集合，不把报告中“尚未穷尽所有关键基准”字段改成已完成。

该轮388项语言回归（`build/test/language-priority/l2-full-final.log`）、16项O1原生ABI（`l2-abi-187f3680a2d0/result.json`）和17服务O1叶构建（`services-fb1891992aeb/result.json`，均在同一language-priority目录）通过；保护页探针真实观察未使用读取的故障及故障前store，坏DCE实际执行被拒绝。服务叶构建不等于新OS/VM验收，后续L3新增测试另记。

## 此前实施与失败基线（历史）

## 当前基线与优先级

开始本轮时，`lang/dongc` 是 Python 前端、语义检查器和直接 NASM 后端。L1 已有常量表达式计算，但没有 SSA 优化流水线、全局寄存器分配、源码 DWARF 或 Dong 编译器。修改前的 12 个编译器文件保存在 `build/test/language-priority/l1-before/`；323 项语言/标准库测试通过。新增开关默认关闭，14 个既有 fixture 的 debug/release 汇编、布局、manifest 已逐项与该副本比较相同，见 `build/test/language-priority/default-compat.json`。

本轮依次完成：L2 类型化 CFG/SSA 与验证器 → 优化/寄存器分配及真实差分执行 → 调试信息及真实 GDB 行为 → 预先固定的性能基准 → 完整 Dong 编译器与宿主阶段一致性 → DongOS 自编译和同盘重启。未通过的门禁继续保留。

## L2 本轮结果

新增显式 `--optimize 1`，首批仅在 release 模式优化 u64/i64/bool 的纯标量函数：局部赋值、分支、循环、范围 for、短路布尔表达式、有限纯返回函数内联和模整数运算。完整函数无法适配时继续使用原后端，manifest/`--emit-ir` 明确记录原因。内存、volatile、原子、asm、系统调用、除法/移位检查、defer、双字 ABI 和 Win64 入口不会被这一批优化绕过；debug 模式保留原检查。SSA 内部校验错误必须失败，不能被当作“不支持”静默回退。

新增显式 `--debug-info` 使用真实后端栈位置、代码标签和词法作用域生成 DWARF4。18 项检查包含真实 GDB 源码断点、单步、参数/局部/全局/数组/切片、跨调用、Win64 桥及 64B 对齐帧展开。未证明存储有效的变量显示 unavailable。独立审查先发现内层未初始化变量被外层值55冒充、声明前提前遮蔽两处缺陷；均已用原反例复验修复，声明前55→声明后unavailable→出scope55。ELF `.debug_*` 非ALLOC，`.text` 与无调试编译逐字相同；NASM COFF 宿主适配器的全部字节差异只在调试重定位类型/节flags。GDB 使用 C 兼容表达式模式，未声称完整 Dong GDB 插件或客体内核源码调试已复验。

调试记录 `build/test/l2-debug/evidence.json`；独立最终审查 `build/test/l2-debug-independent/r3/review.json`，SHA256 `5e2fd559ecbed43b39f7d1b28d7990ceb0ed3f7cc62cacf8e851d83bea8b07bc`。旧 NEEDS_FIX 与两次反例现场保留。

SSA核心22项及10个真实修改源码负控通过；整合原生测试对照独立C和L1执行4000组输入，并强制全部spill实际执行。独立审查另执行40函数×256组随机/边界输入。两处phi整合错误修复并回归：边复制助手被参数遮蔽，以及常量phi改写破坏剩余phi前缀。额外错误的加法lowering成功编译/链接后被C oracle拒绝，不能把构建失败当负控通过。

17 个当前服务均完成 O1 代码生成、NASM 与 PIE ELF 链接，合计25个SSA函数、1788个保守回退（各模块图分别计数，含重复依赖）。首轮严格源身份门禁因并行调试模块修订而失败，原结果保留；稳定源码再次完整代码生成，逐字比较原汇编/对象/ELF后封存于 `build/test/language-priority/services-recheck-7b3d5381210b/result.json`。这是叶构建，不是新内核或客体运行验收。

安静环境下固定五内核、两次暖身和九对交错样本全部完成，原门槛仍为1.20：累加3.918×、LCG1.107×、分支混合2.224×、数组求和6.611×、数组复制8.451×。仅LCG通过，整体 `passed:false`；数组两项明确走L1，未从集合删除。完整原始样本及源码实物快照见 `build/benchmarks/run-2907903c6eec/result.json`，SHA256 `40bd75c0551ce619df99dcfd37d04cf4fe55944ae3e0bd342a1d27c60c96b9ee`；三项实际编译执行的错误Dong/手写参考均被独立C值/数据检查拒绝。不得以单个最快样本关闭L2。

下一项先减少循环phi边复制与比较分支开销，再建立带明确副作用/别名契约的内存优化，保留debug、volatile、原子与故障语义。每次对同一固定集合复验；L2性能未达标前不标总验收。

## L3 正在实施

先实现真正 Dong 词法器，以调用方提供的 token 与字符串工作区处理 UTF-8、Unicode 标识符、全部运算符/关键字、整数拼写、字节字符串转义、错误位置和容量失败。宿主 C/NASM 差分执行对照原 Python 词法器。Unicode 分类表从固定 Unicode 数据生成后随 Dong 源码保存；运行时不调用 Python。

最终9项测试由root完整复跑通过，debug/release分别实际执行214个现有DG、17745个Unicode边界/随机源、坏语法/UTF-8及精确容量/重叠哨兵；原4个错误词法器均被拒绝。独立原生审查另遍历全部1114112码点分类、1112064有效UTF-8标量和65536双字节组合，以及13个参数/重叠/溢出守卫，生产词法器未发现实质缺陷。

独审确证旧容量测试只比较 `strings == reference[:used]`，会漏过未完成字符串提前发布。已强化所有原生结果的断言：已发布STRING的arena区间连续，最终尾恰等于used；无已完成字符串时used为0。新增实际坏源码在容量失败时提前发布used，debug/release、无完成串/已有完成串四次都成功编译执行，并只因准确的发布不变量拒绝。旧误通过现场保留，生产lexer/Unicode/生成器字节未改。root最终证据 `build/test/bootstrap-lexer/run-8b108737394b/summary.json`；独审报告 `build/test/bootstrap-independent/report.md`。这是完整词法组件，不能标记L3自举完成。

完整 L3 还需要 Dong 语法器、模块/名称/类型/常量/布局检查、流分析及 defer、后端与调试信息、工作内存/字符串/任意精度整数、CLI/产物发布，以及客体可运行的汇编/链接链或等价 ELF 后端。目前普通 file-app 只有只读 FS 权限、262144 字节 EXEC 上限、单 u64 参数和有界工作内存，不能把宿主 NASM 输出回传当作客体自举。接口审计见 `build/test/l3-selfhost-audit/report.md`；这些限制需要明确接线及复验，不能删除检查后宣称完成。

最终root完整语言/标准库复验：`python -m unittest discover -s lang/tests -q`，380项通过、0skip，日志 `build/test/language-priority/full-language-root-final.log`。包含旧323项及新增57项；先前378/379项记录保留，没有用它们覆盖之后发现的scope或测试oracle缺陷。

本轮组件checkpoint及源码实物快照：`build/test/language-priority/checkpoint-66c238241638/result.json`，SHA256 `d65d68dd6e7ffd13d6d19cd2eeea42c5220a5515dfdae86a417264faf7886a20`。封存明确记录L2/L3整体未完成、没有新OS构建/VM启动/关机；当前编译器生成的基准汇编与安静失败基线逐字相同，未因仅修改debug元数据而冒称性能已改变。

原 L3 门槛不变：宿主编译 Dong 编译器得到 stage1，stage1/stage2 再编译自身；真实 DongOS 从 FAT32 读取源码、编译并 FLUSH 新 ELF，运行它再生成下一阶段产物，独立比较规定产物，并在同盘重启后核对持久结果。

## 后续系统任务与关机

R6 GUI 全量复验 `run-2ebfc8ab03d4` 和首次启动观察 `run-0e7214c31cc6` 均失败并保留。前者文件操作仍有块 RPC 进展，不能记为成功或已证明死锁；后者未捕获满足原判据的并行启动快照。R6 R4 合并物理读取工具已封存待实际复验；R7 输入修复尚未应用。新编译器源不能沿用旧构建输入身份而宣称已验证新的系统镜像。

2026-10-18用户已取消此前的关机指令，不再安排或执行自动关机。当前优先完成L2循环与内存优化并通过原性能门槛，然后推进L3自举。P10仍按此前约定另定范围。
