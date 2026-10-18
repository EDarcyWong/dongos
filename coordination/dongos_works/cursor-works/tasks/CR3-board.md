# CR3 — 无碰撞的NASM内部符号编码

负责人：cursor。状态：待领取。

module bootstrap.nasm_symbol。
固定接口 pub unsafe fn encode(module_name:[]const u8, item_name:[]const u8, out:[]u8, written:*usize)u64；OK=0、INVALID=1、CAPACITY=2。
两个输入均须非空；输入是原始名字字节，此组件不负责 UTF-8/标识符语义校验，允许 NUL、非 ASCII 和标点并逐字节编码。成功输出严格为 ASCII "__dong_m" + module_name 每字节两位小写十六进制 + "_n" + item_name 每字节两位小写十六进制，无 NUL/LF。例如 (b"a",b"b")→b"__dong_m61_n62"。两个名字的分隔不能省略，(a,bc) 与 (ab,c) 必须不同；不散列、不截断、不依赖宿主。
长度严格为 10+2*(module_name.len+item_name.len)，先以不溢出的检查计算；输入可相互重叠，完整 out 及 written 的 8 字节须彼此、与两个完整输入分离。written 非空且 8 字节对齐；空 out 可 NULL；输入/输出端点及长度不合法均 INVALID，容量不足 CAPACITY。成功 written 是精确字节数、尾部不变。此符号空间与当前主线编码可不同，不更换现有符号，只交付可供 L3 后端调用的新独立组件。
验证保留字 mov/rax、中文/非 UTF-8/NUL/下划线、歧义拼接对、空输入、容量边界、完整输出尾部别名和只读输入。实际生成符号定义及引用，真实 NASM ELF64/COFF 汇编通过，不仅正则检查；名字唯一性用原始字节对作为独立键。两个有限错误实现建议是漏模块/条目分隔编码或错误十六进制，以及提前 written 写入。

## 工作与交付约定

这是独立组件，不代表完整 L3 后端或自举完成。Cursor 继续由用户在客户端手动发起；通过自己的 coordination MCP 查看最新 rev、完整任务书并领取后再修改。不要调用 AI CLI 自动执行，不抢占 DeepSeek 已领取的 D14～D18，不改 Claude/DeepSeek/LM Studio 文件、code/lang/、编译器、活动内核或协调器。依赖只有在 accepted/integrated 后才能领取；需要额外归属时在交付中说明，不擅自扩范围。

生产实现必须是 Dong，模块自身不导出 C 符号；Python/C/NASM 仅作独立测试观察器。unsafe 调用方保证实际可用内存；先验证所有描述符、自然对齐、长度乘法和地址端点，再读取输入或写入。完整声明区间校验，不只检查有效前缀。INVALID 优先于 CAPACITY；所有失败必须立即确认输出及计数对象全文不变，成功只改指定前缀/字段，真实双端 guard、输入与输出尾部立即检查。无分配、全局可变状态、OS 调用或宿主生产实现。

编写自己的同名 Python 定向测试：实际编译/链接并执行 Dong debug/release，确认 ELF64/COFF 均能组装；有限固定边界加小规模确定性随机，以独立 Python/C 期望核对。至少两个真实错误 Dong 副本必须成功编译并原生执行，被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置正例拒绝均不算负控成功。不得放宽断言或伪造预检次数。对照输入必须满足所考察规则以外的其它条件，避免非法标签/未对齐/坏图遮蔽目标缺陷。不要求新大矩阵。

只运行本任务定向测试，所有产物在 cursor-works/build/CR3/<唯一目录>/。测试组装源码根时仅暂存当前组件及任务声明的只读依赖，再加 code/lang，避免历史 CR1 副本与主线同名模块冲突；临时包装器和坏实现只写自己的产物目录。除额外声明依赖外，各组件可独立实现。不运行 OS/VM、全回归、性能基准、定时器、关机、提交或推送。

完成后写 cursor-works/deliveries/CR3.md，列出源码/测试 SHA256、真实命令/结果/模式/skip、证据路径、坏实现命中和拒绝原因、剩余限制。未运行的命令必须明确未运行。通过 MCP submit_task 提交，等待 Codex 独立审查/复验；不得自行 accept/integrate。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_symbol.dg`
- `cursor-works/src/bootstrap/nasm_symbol.md`
- `cursor-works/tests/test_nasm_symbol.py`
- `cursor-works/deliveries/CR3.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_symbol.py`

交付：`cursor-works/deliveries/CR3.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
