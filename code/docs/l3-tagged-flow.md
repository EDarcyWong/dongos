# L3 optional/result 解包与流程语义

2026-10-18，Codex在bootstrap.semantic_types接入try、orelse及其return/break/continue回退；不改宿主语言契约，不改Cursor/DeepSeek组件，不用宿主检查器代替Dong生产语义。

try要求当前函数返回result、操作数为result，禁止defer内错误传播，提取准确payload（包括!void）。普通调用语句拒绝丢弃result。orelse要求optional，回退值检查准确payload类型；return检查函数返回类型/void/noreturn，break/continue沿用既有循环出口初始化交集，仅在实际可达回退登记出口。不可变全局/局部const的已知标签控制短路，普通局部变量与未知参数不误当静态标签。逻辑短路、此前参数不返回、已知有值回退中的break不能制造虚假循环出口；死分支仍检查类型/初始化。

隐式payload与null包装通过Info位32记录已知标签，复用length字段，和长度位16互斥；清除包装前的scalar/place缓存。Info仍24字节、RuntimeWorkspace仍80字节，原24+5池、Result及公开调用ABI保持不变，无隐式分配、OS调用或实际错误传播指令。

7项定向测试全部通过、0skip，源码/测试稳定，耗时439.781秒。新95个单模块正反案例加1个跨模块const标签案例均独立对照宿主接受性，Dong debug/release实际执行；同步复验原调用/类型/初始化、切片、内存内建及工作区容量/INVALID守卫。C观察器保持输入/描述符真实只读页、29池guard、结果发布和原子性断言。既有完整语言回归未重跑。

两个真实坏Dong分别绕过try返回上下文检查、让已知有值orelse的死回退break制造出口；两模式共4次全部成功编译/链接/原生运行，再被指定status断言拒绝。同夹具先跑好实现。六个好/坏构建均组装ELF64/COFF，没有把构建失败、崩溃或无关拒绝当成功。

证据：`D:\projects\2026\dongos\code\build\test\language-priority\l3-tagged-flow-38d27454b13b`；原生构建、输入输出及坏源码：`D:\projects\2026\dongos\code\build\test\bootstrap-semantic-runtime\run-3fe7291bd6c8`。新增7项回执不等于全部语言回归，也不代表完整L3。方法/错误码声明和字面量、枚举构造与带标签match、完整聚合常量、目标I/O/诊断CLI、完整后端、defer清理lowering和stage1/stage2/DongOS自编译继续未完成。some/ok调用经宿主核对尚未定义，本轮没有擅自引入此语言扩展。无OS/VM、提交、推送或关机。
