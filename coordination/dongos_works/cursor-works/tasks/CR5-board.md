# CR5 — 复用十进制组件的NASM BSS声明

负责人：cursor。状态：待领取。

module bootstrap.nasm_bss。
只读依赖 CR4 的 bootstrap.decimal_integer；在 CR4 accepted/integrated 后领取。可只读 cursor-works/src/bootstrap/decimal_integer.dg（或 Codex 已集成主线同名文件），不修改依赖。必须调用 CR4 编码数字，禁止再实现一套十进制算法。
固定接口 pub unsafe fn emit(label:[]const u8, byte_count:usize, alignment:usize, out:[]u8, written:*usize)u64；OK=0、INVALID=1、CAPACITY=2。
label 长度 8..128，前缀恰为 ASCII "__dong_"，非空后缀只含 A-Z/a-z/0-9/_。alignment 只能为 1..4096 的二次幂，byte_count 可 0..u64最大值。严格输出 b"alignb "+规范无符号 alignment 十进制+b"\n"+label+b": resb "+规范无符号 byte_count 十进制+b"\n"，其中换行是真实单字节 0A，不是反斜杠与字母 n；不含 section、global、额外空格或 NUL。byte_count=0 仍输出 resb 0。
先检查 label/out/written 所有描述符、别名与字段、总文本长度和容量，再写出，避免子调用失败留下半成品；label 只读，完整 out 与 written 彼此及与 label 分离，written 自然对齐。语义错误先于容量，非 OK 全部不变。byte_count 不需要在宿主分配相应 BSS，格式检查必须覆盖 u64 最大值而不试图生成巨型对象。
有限小 byte_count 的董实际输出放入 section .bss，在前置 resb 1 后真实 NASM ELF64/COFF 组装，独立读对象符号值和 BSS 节逻辑大小，检查声明标签对齐及保留大小；零和大边界只按适当范围验证，不巨大分配/链接。用 Python 独立格式字节验证，正常成功、非法 label/alignment、容量原子性和别名均覆盖。负控至少是漏/错 alignb 或大小文本，以及写标签后才报 CAPACITY，必须被对应断言拒绝。

## 工作与交付约定

这是独立组件，不代表完整 L3 后端或自举完成。Cursor 继续由用户在客户端手动发起；通过自己的 coordination MCP 查看最新 rev、完整任务书并领取后再修改。不要调用 AI CLI 自动执行，不抢占 DeepSeek 已领取的 D14～D18，不改 Claude/DeepSeek/LM Studio 文件、code/lang/、编译器、活动内核或协调器。依赖只有在 accepted/integrated 后才能领取；需要额外归属时在交付中说明，不擅自扩范围。

生产实现必须是 Dong，模块自身不导出 C 符号；Python/C/NASM 仅作独立测试观察器。unsafe 调用方保证实际可用内存；先验证所有描述符、自然对齐、长度乘法和地址端点，再读取输入或写入。完整声明区间校验，不只检查有效前缀。INVALID 优先于 CAPACITY；所有失败必须立即确认输出及计数对象全文不变，成功只改指定前缀/字段，真实双端 guard、输入与输出尾部立即检查。无分配、全局可变状态、OS 调用或宿主生产实现。

编写自己的同名 Python 定向测试：实际编译/链接并执行 Dong debug/release，确认 ELF64/COFF 均能组装；有限固定边界加小规模确定性随机，以独立 Python/C 期望核对。至少两个真实错误 Dong 副本必须成功编译并原生执行，被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置正例拒绝均不算负控成功。不得放宽断言或伪造预检次数。对照输入必须满足所考察规则以外的其它条件，避免非法标签/未对齐/坏图遮蔽目标缺陷。不要求新大矩阵。

只运行本任务定向测试，所有产物在 cursor-works/build/CR5/<唯一目录>/。测试组装源码根时仅暂存当前组件及任务声明的只读依赖，再加 code/lang，避免历史 CR1 副本与主线同名模块冲突；临时包装器和坏实现只写自己的产物目录。除额外声明依赖外，各组件可独立实现。不运行 OS/VM、全回归、性能基准、定时器、关机、提交或推送。

完成后写 cursor-works/deliveries/CR5.md，列出源码/测试 SHA256、真实命令/结果/模式/skip、证据路径、坏实现命中和拒绝原因、剩余限制。未运行的命令必须明确未运行。通过 MCP submit_task 提交，等待 Codex 独立审查/复验；不得自行 accept/integrate。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_bss.dg`
- `cursor-works/src/bootstrap/nasm_bss.md`
- `cursor-works/tests/test_nasm_bss.py`
- `cursor-works/deliveries/CR5.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_bss.py`

交付：`cursor-works/deliveries/CR5.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
