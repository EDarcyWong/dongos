# CR7 — SysV整数返回值的窄值扩展规划

负责人：cursor。状态：待领取。

module bootstrap.sysv_return_plan。
仅规划 Dong x86-64 SysV INTEGER 类返回值，不支持浮点/SSE、大聚合、sret、Win64、可变参数；不冒充完整 ABI。固定 pub struct Plan { pub words:usize, pub width_bits:usize, pub extension:u64 }（24字节、8字节对齐）。pub unsafe fn plan(kind:u64,out:*Plan)u64；OK=0、INVALID=1，extension NONE=0、ZERO=1、SIGN=2。
kind 枚举和精确结果：0 VOID→(0,0,NONE)；1 BOOL→(1,8,ZERO)；2 U8→(1,8,ZERO)；3 I8→(1,8,SIGN)；4 U16→(1,16,ZERO)；5 I16→(1,16,SIGN)；6 U32→(1,32,ZERO)；7 I32→(1,32,SIGN)；8 U64、9 I64、10 PTR 均→(1,64,NONE)；11 INTEGER_PAIR→(2,64,NONE)。单字用RAX，双字低/高用RAX/RDX；BOOL的输入在上游已为0/1，本组件不把任意字节当bool或读取值。这里的扩展是后端统一值表示约定，不宣称 SysV 标准要求所有窄返回高位。
out 非空、8对齐、完整24字节地址端点有效；无效指针/枚举返回 INVALID 且全文不变。成功写全部字段。只做有限元数据规划，无分配、无寄存器发射、无输入数组。
原生 Dong debug/release 独立 C 结构读取验证全12项、非法kind及失败不变。另用 Python 独立补码解释和临时 NASM 返回探针，根据实际 Dong 规划字段生成扩展指令，检查 i8/i16/i32 最小值、负一及无符号高位、双字返回；探针不替代生产组件。两个有限坏源码控制至少覆盖把有符号窄值标成 ZERO，以及 PAIR 漏第二字，必须原生执行后被字段/返回值断言拒绝。不要引入完整 ABI 分类器或改 C8 参数规划。

## 工作与交付约定

这是独立组件，不代表完整 L3 后端或自举完成。Cursor 继续由用户在客户端手动发起；通过自己的 coordination MCP 查看最新 rev、完整任务书并领取后再修改。不要调用 AI CLI 自动执行，不抢占 DeepSeek 已领取的 D14～D18，不改 Claude/DeepSeek/LM Studio 文件、code/lang/、编译器、活动内核或协调器。依赖只有在 accepted/integrated 后才能领取；需要额外归属时在交付中说明，不擅自扩范围。

生产实现必须是 Dong，模块自身不导出 C 符号；Python/C/NASM 仅作独立测试观察器。unsafe 调用方保证实际可用内存；先验证所有描述符、自然对齐、长度乘法和地址端点，再读取输入或写入。完整声明区间校验，不只检查有效前缀。INVALID 优先于 CAPACITY；所有失败必须立即确认输出及计数对象全文不变，成功只改指定前缀/字段，真实双端 guard、输入与输出尾部立即检查。无分配、全局可变状态、OS 调用或宿主生产实现。

编写自己的同名 Python 定向测试：实际编译/链接并执行 Dong debug/release，确认 ELF64/COFF 均能组装；有限固定边界加小规模确定性随机，以独立 Python/C 期望核对。至少两个真实错误 Dong 副本必须成功编译并原生执行，被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置正例拒绝均不算负控成功。不得放宽断言或伪造预检次数。对照输入必须满足所考察规则以外的其它条件，避免非法标签/未对齐/坏图遮蔽目标缺陷。不要求新大矩阵。

只运行本任务定向测试，所有产物在 cursor-works/build/CR7/<唯一目录>/。测试组装源码根时仅暂存当前组件及任务声明的只读依赖，再加 code/lang，避免历史 CR1 副本与主线同名模块冲突；临时包装器和坏实现只写自己的产物目录。除额外声明依赖外，各组件可独立实现。不运行 OS/VM、全回归、性能基准、定时器、关机、提交或推送。

完成后写 cursor-works/deliveries/CR7.md，列出源码/测试 SHA256、真实命令/结果/模式/skip、证据路径、坏实现命中和拒绝原因、剩余限制。未运行的命令必须明确未运行。通过 MCP submit_task 提交，等待 Codex 独立审查/复验；不得自行 accept/integrate。


## 可修改文件

- `cursor-works/src/bootstrap/sysv_return_plan.dg`
- `cursor-works/src/bootstrap/sysv_return_plan.md`
- `cursor-works/tests/test_sysv_return_plan.py`
- `cursor-works/deliveries/CR7.md`

## 定向验收

- `discover:cursor-works/tests:test_sysv_return_plan.py`

交付：`cursor-works/deliveries/CR7.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
