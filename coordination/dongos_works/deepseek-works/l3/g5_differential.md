# 有限 G5 源码差分执行器

本任务验收runner及明确有限矩阵，`scope_complete=false`。method、enum、error、try、orelse、defer、extern SysV/Win64逐项实际证实的差集保留为known-gap，不能计作支持成功、xfail或skip。完整L3/G5阶段保持partial。

## 两条实际目标路径

同一只读源码目录、入口与debug/release模式分别交给Python种子编译器和真正Dong frontend→lower→nasm。Python仅编排、引导编译器及独立观察，目标IR/NASM由对应编译器生成；原生失败立即failclosed，无seed fallback。复用已验收L3A的有界C/SysV桥和快照工具，重新构建当前生产Dong源码，保留全部只读闭包/候选/命令/对象/进程结果。

两后端的符号编码和可见性不同：种子普通符号局部、`__dg_m…_f/g…`；Dong发射`__dong_m…_n…`。仅观察端翻译确定的符号名，objcopy暴露种子已有符号。保留原`.private.obj`与原始目标汇编，逐COFF节要求所有原指令/数据字节完全不变，只容许BFD在原节末补零对齐；禁止改目标汇编、指令、ELF或静态指针。真实汇编ELF64和COFF；本机执行为明确SysV桥，不能把COFF组装叫Win64函数ABI覆盖。

## 有限支持矩阵

每模式执行audit、globals、多模块和固定PRNG种子20261022的12个数值向量，合计6条supported-pass记录。独立C固定数值/字节/canary/轨迹检查整数窄宽与符号、嵌套调用和20整数参数、slice双字整体返回/传参、全部6个callee-saved和RSP、单次求值lvalue、数组和结构体12字节padding、静态常量/可变全局量、跨模块同名符号、短路副作用与循环break/continue。两条路径完整观察相等外，还分别必须满足独立oracle。

另22条实际运行检查覆盖两模式checked/wrapping、负值溢出、窄运算、边界、非法移位和除法：seed由真实panic给出种类/源行，Dong由真实UD2守卫拒绝；Windows观察器只捕获异常码c000001d且故障字节恰为0f0b，打印精确标识并退出86，不能用其它崩溃冒作成功。release允许wrap的例子必须正常返回正确值，两模式本身的wrapping intrinsic均在正常oracle核验。两模式private global访问都必须由双方真实前端拒绝且原生输出不变。

## 缺口、负控与原生容器

8种构造每模式均由seed实际编译/原生执行或诊断，Dong实际记录精确frontend/lower阶段、status、detail、source/node/offset/line/column；前端定位来自真实Graph结果，lower定位只读取检查过的Unit/Node/Token数组。失败输出逐字保持，不合成目标图。16条known-gap和非空remaining单列，0测试退出不能关闭整个G5。

两种唯一Dong发射语义坏体：GLOBAL错址+8、窄store误为64位。完全构建/链接并正常返回，由精确wrong-global-address/narrow-store-canary oracle以2拒绝，每模式均有同输入好体先通过；构建失败、崩溃或超时不计语义负控。另真正运行一个坏Python runner，把真实拒绝的原生路径替换成seed成功，必须被native编译器/driver产物来源拒绝。至少一个完整native_assembler ELF在原0x400000实际映射执行静态指针读写，借用已审查L3A固定地址桥，不修改ELF或指针。

## 证据与边界

每轮唯一目录保存源、原始和可见性调整对象、C/ASM桥、完整命令/版本、允许的NASM/CC环境（不含密钥）、进程退出/超时、工具和产物SHA、期望/实际/首次语义差异。任何当前编译器/只读闭包变化即失败。缺工具不skip，不运行OS/VM/AI CLI、不提交推送、不直接写协调状态。开发缓存只读当前Dong对象的实验不是正式验收，独立正式检查必须从冷快照重新引导全部编译器。

开发轮run-222b7fae3df8已实际完成6条supported-pass、22运行检查、16条known-gap、2隐私诊断、4条正常返回坏Dong和1个真实fallback坏体拒绝，完整native容器固定地址静态指针实际执行也通过；source_stable=true。此轮复用已核对全部只读源的当前Dong对象以排查宿主桥，不计正式冷引导验收。最终实现另补明确主线/works根定位、完整工具版本和独立进程/产物路径绑定，正式3项门禁从冷快照重新执行全部矩阵。后续真实结果写入交付和协调验收回执；当前不自行宣布验收。


## 主动源稳定修复与最终门禁

独审发现首次提交仅把生产/闭包输入纳入最终清单，目标fixture源并非全部从创建时登记；因此主动通过协调器暂停7b0221ae，确认Windows托管作业全部子进程退出，保留failed/日志，不计任何验收。官方resume/rework/claim后，创建每一源码目录即登记每个目标DG的SHA，在seed与Dong执行前及finish共同核对。独立永久测试实际把7改为8，assert_inputs/seed/dong全部在编译前精确拒绝，恢复原字节后通过，开发1test/0skip/0.136s。新完整门禁为4tests，仍从冷快照重新引导全部矩阵，不拿旧缓存或中断轮次作正式结果。
