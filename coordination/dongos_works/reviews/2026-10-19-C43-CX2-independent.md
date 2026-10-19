# L3：C43 / CX2 独立审查与复验

本记录由Codex审查者维护，验收/集成时间以协调器事件为准。未运行OS/VM、全项目回归或模型CLI，未修改原负责人实现与永久测试。

## C43：从帧槽读取目标的SysV间接调用组合

已阅读完整任务书、交付、生产源码、说明、永久测试及已集成依赖。生产实际委托C34 setup、CR12目标读取、C27 call、同一stack_bytes cleanup、C40 capture；描述符、完整输入别名、frame/槽/字数先检查，返回布局由局部C40调用检查，最后才判断用户容量并发布。五段scratch上界1200，实际1280有界，不重写既有ABI规划。

独立直接执行：在coordination/dongos_works下运行`python -m unittest discover -s claude-works/tests -p test_nasm_sysv_indirect_invoke.py -v`，4项通过、0skip、59.726秒。产物`claude-works/build/C43/run-cd388c4f8301/`。debug/release实际Dong产出、ELF64/COFF组装、显式SysV真实间接call/ret；12主要向量覆盖寄存器/栈实参、PAIR/窄返回及目标/源/返回同槽。检查完整帧与guard、入口对齐、栈恢复和callee-saved。异合法目标和PAIR保存槽互换在同输入好侧之后按原生返回槽数值拒绝，提前发布按完整原子性拒绝，四处输入尾部别名敏感性准确命中预检11..14。

正式协调器复验仍须完成且指纹稳定，才登记验收。队列回执、最终SHA及集成状态随后追加，不把上述直接复验冒充已完成正式作业。

### C43正式验收和真实集成

正式作业a94a8eb7e57e46358d224b6e69c1b20c完成：4项0skip、59.802秒、source_stable=true，协调器2026-10-19 16:04:23北京时间记录。源码/文档/永久测试/交付四文件指纹与验收时一致，已登记accepted rev5。

随后实际复制生产.dg/.md至code/lang/bootstrap，永久测试复制为code/lang/tests/test_bootstrap_nasm_sysv_indirect_invoke.py，仅适配ROOT/SOURCE/DOC和构建输出路径，不改断言/向量/算法。主线执行`python -m unittest -v lang.tests.test_bootstrap_nasm_sysv_indirect_invoke`：4项0skip、60.124秒。三个新文件复制后与测试后SHA一致；生产和说明与正式验收输入字节相同。证据`.local/reviews/C43-independent-20261019/integration-files.json`及code/build/test/bootstrap-nasm-sysv-indirect-invoke下本次run目录。集成登记另通过协调器最新rev进行。本项仍是L3独立调用组件，不等同于完整IR/自举完成。

## CX2：optional/result match类型与确定初始化语义

已阅读完整任务书/交付，及semantic_types.dg的rt_match、rt_tag、分支快照和初始化交集，以及永久测试的26项正反用例和真实坏Dong变体。明确区分optional的null/some与result的ok/err，err绑定u64，!void的ok无payload；重复、穷尽、不可达wildcard及错误payload均有路径，已知常量标签只合并活跃分支，运行时workspace ABI未改。

独立审查脚本`reviews/cx2_independent_probe.py`复用正式隔离作业已经构建的debug/release可执行体，使用19项追加用例（两模式共38次）检查u16/i8/bool/指针payload、部分return后初始化交集、未知分支缺初始化、丢弃payload绑定、已知false optional和ok result、嵌套/遮蔽绑定，并同输入补跑两个match负控的正式好侧。全部通过，源码与隔离构建输入SHA相同且前后稳定。证据`.local/reviews/CX2-independent-20261019/review.json`。此追加探针没有重新编译生产实现，不冒充独立主线全模块回归。

探索阶段曾试探4项宿主语法/类型阶段即拒绝的候选和1项绑定阶段即拒绝的越作用域变量，均不属于本runtime语义探针输入范围，已从最终19项中移除；不将绑定阶段的非零进程当作生产语义失败或负控成功。

正式作业323f94f151404be3982303a0b57421e5仍在运行全模块原生回归及坏Dong变体构建，最终结果必须另查。完整L3/活动IR/自举产物门禁未因此宣称完成。

### CX2正式作业最终结果

协调器于2026-10-19 16:03:11北京时间记录该作业失败：cancelled=true、timed_out=false、returncode=1、elapsed_seconds=1645.909，source_stable=true；unittest未打印整模块完成汇总，因此正式tests记0（日志中前9项已显示ok，不能据此宣称整套通过）。这不是已证实的生产语义失败，也不是超时。此次取消不是本审查者发起（本审查者只取消了CR30/D21的queued作业）。原负责人codex-l3-tagged-match随后重新领取，查询时CX2为in_progress rev8。本轮不验收/集成CX2，不抢占其在途返修；后续原编号提交并完成新的正式复验后再审。

随后原负责人于16:03:48提交CX2 rev9并排队新正式作业58621310cc104b8a8ba3f9676f219106。已检查新旧测试差异：仅改构建器，正式实现仍debug/release各组装ELF64和COFF，坏源码各模式保留本机格式的组装/链接/原生执行，省略坏源码的非本机格式对象；没有删用例或断言。生产.dg/.md内容SHA不变，永久测试新SHA f5b86d7a96f1800a4be6aa40341e39e5ba4463bf9a4e6644be71038e6eb92a2c。上述19项探针原生结论仍对应相同生产实现，但旧探针JSON的测试文件SHA属于上一提交。rev9的正式结果须单独完成，不继承已取消作业的通过状态。

审查者已针对新正式隔离作业58621310cc104b8a8ba3f9676f219106再次执行同19项追加探针（两模式38次），全部通过，当前生产/说明/新版永久测试与新隔离输入SHA相同且前后稳定；证据`.local/reviews/CX2-independent-20261019/58621310cc104b8a8ba3f9676f219106/review.json`。正式全模块尚在运行时，不提前登记验收。

### CX2 rev9正式通过与主线核对

新正式作业于2026-10-19 16:25:50北京时间完成：10项全部通过、0skip、1209.695秒（unittest内部1208.982秒），source_stable=true，cancelled=false、timed_out=false。覆盖原生正反语义、workspace/guard/图完整性、旧类型/flow/切片/unwrap回归及6类最后实际坏Dong变体。当前四个声明文件与新正式指纹一致。

实现和新版永久测试从交付开始即实际位于主线code/lang，无独立候选需覆盖；已真实阅读并核对当前主线生产/说明/测试与隔离输入一致。独立19项两模式38次探针再次验证同一当前生产实现（使用已构建的新正式二进制，不冒充另编译主线全模块），新正式10项承担完整编译/组装/链接/执行门禁。验收/集成分别由协调器CAS和指纹关卡登记。仍未宣称完整L3、枚举/方法语义或客体自举通过。
