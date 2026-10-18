# CR4 — 无分配的定宽整数十进制文本

负责人：cursor。状态：待领取。

module bootstrap.decimal_integer。
固定接口 pub unsafe fn encode(raw:u64, width:usize, signed:bool, out:[]u8, written:*usize)u64；OK=0、INVALID=1、CAPACITY=2。
width 只允许 8/16/32/64。width<64 时 raw 必须小于 2^width，越界 INVALID，不截断。signed=false 按无符号解释；signed=true 按给定位宽二进制补码解释，输出规范十进制 ASCII，不带加号、前导零、空白、LF 或 NUL；零恰为 "0"，没有负零。i64 最小值必须正确输出，不能先在有符号 64 位中直接求负造成 debug 溢出。例 raw=255,width=8,signed=true 输出 "-1"；raw=128,width=8,signed=true 输出 "-128"；raw=256,width=8 即使 out 容量 0 也 INVALID。
written 非空、自然对齐、完整 8 字节范围有效；与完整 out 分离，所有地址/长度端点先验证。合法输入的 out 容量不足返回 CAPACITY；失败不改 out/written，成功只写文本前缀并记录长度。最大文本 20 字节，可使用固定局部数组，禁止分配。
用 Python 原生任意精度整数独立解释补码，覆盖四个位宽的 0、正最大、负最小、负一和无符号最大、容量恰好/少一/多余、非法位宽与 raw。实际董输出作为 NASM dq 操作数组装成 bin，与 Python 补码低 64 位比较；有符号窄值比较其符号扩展后的 64 位结果。负控必须覆盖错误最小负数处理或漏负号，以及失败提前改输出/计数。LM7 固定数据仅作可选补充，不依赖它完成、不修改其文件。

## 工作与交付约定

这是独立组件，不代表完整 L3 后端或自举完成。Cursor 继续由用户在客户端手动发起；通过自己的 coordination MCP 查看最新 rev、完整任务书并领取后再修改。不要调用 AI CLI 自动执行，不抢占 DeepSeek 已领取的 D14～D18，不改 Claude/DeepSeek/LM Studio 文件、code/lang/、编译器、活动内核或协调器。依赖只有在 accepted/integrated 后才能领取；需要额外归属时在交付中说明，不擅自扩范围。

生产实现必须是 Dong，模块自身不导出 C 符号；Python/C/NASM 仅作独立测试观察器。unsafe 调用方保证实际可用内存；先验证所有描述符、自然对齐、长度乘法和地址端点，再读取输入或写入。完整声明区间校验，不只检查有效前缀。INVALID 优先于 CAPACITY；所有失败必须立即确认输出及计数对象全文不变，成功只改指定前缀/字段，真实双端 guard、输入与输出尾部立即检查。无分配、全局可变状态、OS 调用或宿主生产实现。

编写自己的同名 Python 定向测试：实际编译/链接并执行 Dong debug/release，确认 ELF64/COFF 均能组装；有限固定边界加小规模确定性随机，以独立 Python/C 期望核对。至少两个真实错误 Dong 副本必须成功编译并原生执行，被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置正例拒绝均不算负控成功。不得放宽断言或伪造预检次数。对照输入必须满足所考察规则以外的其它条件，避免非法标签/未对齐/坏图遮蔽目标缺陷。不要求新大矩阵。

只运行本任务定向测试，所有产物在 cursor-works/build/CR4/<唯一目录>/。测试组装源码根时仅暂存当前组件及任务声明的只读依赖，再加 code/lang，避免历史 CR1 副本与主线同名模块冲突；临时包装器和坏实现只写自己的产物目录。除额外声明依赖外，各组件可独立实现。不运行 OS/VM、全回归、性能基准、定时器、关机、提交或推送。

完成后写 cursor-works/deliveries/CR4.md，列出源码/测试 SHA256、真实命令/结果/模式/skip、证据路径、坏实现命中和拒绝原因、剩余限制。未运行的命令必须明确未运行。通过 MCP submit_task 提交，等待 Codex 独立审查/复验；不得自行 accept/integrate。


## 可修改文件

- `cursor-works/src/bootstrap/decimal_integer.dg`
- `cursor-works/src/bootstrap/decimal_integer.md`
- `cursor-works/tests/test_decimal_integer.py`
- `cursor-works/deliveries/CR4.md`

## 定向验收

- `discover:cursor-works/tests:test_decimal_integer.py`

交付：`cursor-works/deliveries/CR4.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
