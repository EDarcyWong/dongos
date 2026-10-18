# L3 原生切片语义检查

2026-10-18，Codex补齐bootstrap.semantic_types中的切片表达式检查，不占用Cursor CR8～CR11或DeepSeek的任务文件。原24池及5池运行时工作区、Info和Result ABI均保持不变。

支持已有切片、字符串和可寻址数组的[lo..hi]，允许省略上下界。维持元素类型和只读限定，拒绝非法base、数组临时值和未初始化数组；边界按usize检查，已知上下界拒绝倒序，已知长度拒绝越界（允许末端空视图），结果已知长度继续约束嵌套索引。UTF-8字符串按字节计长，运行时界限不冒充常量。字段偏移和嵌套数组索引递归降低对齐保证，packed数组place不足元素自然对齐时拒绝；嵌在正常对齐容器内且实际对齐的packed字段可接受。上下界noreturn传播不被视图构造抹掉。

定向验证覆盖运行时与声明类型两模块，共9项通过、0skip。37个切片正反案例均独立对照宿主接受性并在Dong debug/release实际执行；既有类型/调用、确定初始化/控制流、容量/参数守卫、C3/C4布局与常量桥均复验。4类运行时坏Dong（类型拒绝、分支交集、切片越界、只读限定）与2类声明坏Dong（C3算术、C4字段偏移）共12次原生执行被指定status或value/layout断言拒绝，所有构建均覆盖ELF64/COFF。

证据：`D:\projects\2026\dongos\code\build\test\language-priority\l3-slicing-04463dca8bfc`。初次单项/组合运行暴露的是准备语料写法问题：packed与align不能并用、嵌套数组类型拼写及不能把切片作为独立表达式语句；均按宿主语言规则修正，失败现场未覆盖。生产Dong源码在修正语料期间保持一致。最终用check_l3_slices.py按完整源文件、wrapper与C观察器逐字身份核对复用本轮已编译的16个好/坏原生程序，重新执行修正后的完整9项断言，final-unittest.log与result.json记录全通过。并非重复构建或把初次失败说成通过；首轮targeted-unittest.log保留。

源码实物和hash在checkpoint/。只运行相关定向验证，没有重新运行443项完整语言回归；旧全回归不替代本轮证据。没有构建/运行OS/VM、提交、推送、关机或启动其它模型。

这只是原生语义前端进展。全局静态切片物化、其它聚合常量、方法/错误/标签语义、defer清理、完整代码生成器/CLI、目标I/O及stage1/stage2/DongOS真正自举仍待完成，L3保持未验收。当前宿主Python后端未由本轮替换。
