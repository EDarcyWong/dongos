# L3 原生内存内建语义

2026-10-18，Codex在bootstrap.semantic_types补齐9种内建的原生语义检查：volatile_load/store、read/write_unaligned、atomic_load/store/compare_exchange/fetch_add和compiler_fence。依据现有宿主Checker的同一语言契约，处理0/1/2/3参数数量、unsafe、元素类型、读写限定及返回类型。内建分支位于既有双参数wrapping/raw-slice路径之前，普通同名全局函数和局部函数指针不误认作内建。

volatile/非对齐读写只允许八种整数元素指针，原子只允许u32/u64，透明整数别名仍由既有类型层规范化。所有9种操作均要求unsafe，写入操作拒绝只读指针，值参数按准确元素类型检查；store/屏障为void，load/CAS/fetch_add返回元素类型。按源顺序分析参数并保留不正常返回的流程状态，死路径仍检查类型。原24池/5池工作区、Info、Result及公开调用ABI不变；不隐式分配，不在分析阶段执行或重排访存。

定向6项全部通过、0skip，受测Dong源码和测试身份稳定。85个固定生成/边界正反案例独立对照宿主接受性，Dong debug/release实际执行，覆盖八种整数、只读读取、u32/u64原子、CAS返回值、0/1/2/3参数、不合法指针/位宽/值、unsafe、只读写入、内建名遮蔽及参数不返回状态；原普通运行时、切片、确定初始化/控制流、容量/INVALID守卫同步通过。C观察器逐例检查只读输入/描述符、29池guard和结果发布，未替换或放宽断言。

两类实际坏Dong分别绕过unsafe检查、允许向只读指针原子写入，在两模式共4次成功编译、链接、原生执行，被指定status断言拒绝；每次先确认好实现拒绝同一输入。所有6个好/坏原生构建均组装ELF64/COFF。没有把编译失败、崩溃、超时当负控成功。本轮没有改动旧类型拒绝/分支交集/C3/C4逻辑，因此未重复构建它们的旧负控。

证据：`D:\projects\2026\dongos\code\build\test\language-priority\l3-memory-intrinsics-255689fc0458`，含before/tested-inputs/result.json、unittest.log及native-summary。原生构建/输入输出/坏源码在`D:\projects\2026\dongos\code\build\test\bootstrap-semantic-runtime\run-f171c358f633`。本次为全新构建的6项定向测试，未重新运行全部语言回归，不用历史443项替代本轮证据。

本轮只修改Codex的语义源码/说明、运行时测试和进度文档；Cursor CR8～CR11、DeepSeek D20及Claude预留模块均未占用。没有修改内核、宿主编译器后端、调度器状态或协作方实现，没有OS/VM、提交、推送或关机。

本增量仅推进原生语义前端。some/ok/err等带标签构造、try/orelse/exit、方法/错误码/枚举专项、聚合常量及defer清理、完整代码生成器/CLI/目标I/O、stage1/stage2及真正DongOS自举仍待完成。L3保持未验收；这些语义规则尚待目标后端接线。
