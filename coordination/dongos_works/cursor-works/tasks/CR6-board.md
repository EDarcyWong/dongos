# CR6 — 确定性的条件分支与落空边规划

负责人：cursor。状态：待领取。

module bootstrap.branch_plan。
固定 pub struct Plan { pub has_cond:u64, pub condition:u64, pub cond_target:u64, pub has_jump:u64, pub jump_target:u64 }（40字节，8字节对齐）。
pub unsafe fn plan(condition:u64, yes:u64, no:u64, fallthrough:u64, out:*Plan)u64；OK=0、INVALID=1。condition 固定枚举：0 EQ、1 NE、2 ULT、3 ULE、4 UGT、5 UGE、6 SLT、7 SLE、8 SGT、9 SGE。输出 condition 用同一枚举，不是 x86 指令字节。逆谓词对应 0↔1、2↔5、3↔4、6↔9、7↔8。
yes/no 必须小于 u64最大值；fallthrough 可为普通块号，u64最大值表示没有落空块。先验证 out 非空、8对齐、完整40字节端点和所有枚举/目标，INVALID 时 out 全文不变。未使用的输出字段一律 0，has_cond/has_jump 为0或1。
规则：yes==no 时不输出条件分支，只在没有落空块或目标不等于 fallthrough 时输出一次无条件跳转。yes!=no 且 no==fallthrough：原条件跳 yes，无额外跳转。yes!=no 且 yes==fallthrough：用逆条件跳 no，无额外跳转。其余情况：原条件跳 yes，后接无条件跳 no。没有落空块时不能遗漏无条件边。不调整 CFG、不删除源比较副作用、不依赖块号连续。
用独立 Python 对 u64/i64 的真值计算模拟计划执行，覆盖全部10谓词、真假两条路径、yes/no相同、两种落空方向及无落空、符号位边界、非法枚举/目标/指针。用固定小随机输入，不扩展 CFG 算法。至少两种真实错误实现（错误有符号逆谓词、漏无落空的末尾跳转）须到达对应执行路径并被语义断言拒绝。无需接入活动编译器或OS。

## 工作与交付约定

这是独立组件，不代表完整 L3 后端或自举完成。Cursor 继续由用户在客户端手动发起；通过自己的 coordination MCP 查看最新 rev、完整任务书并领取后再修改。不要调用 AI CLI 自动执行，不抢占 DeepSeek 已领取的 D14～D18，不改 Claude/DeepSeek/LM Studio 文件、code/lang/、编译器、活动内核或协调器。依赖只有在 accepted/integrated 后才能领取；需要额外归属时在交付中说明，不擅自扩范围。

生产实现必须是 Dong，模块自身不导出 C 符号；Python/C/NASM 仅作独立测试观察器。unsafe 调用方保证实际可用内存；先验证所有描述符、自然对齐、长度乘法和地址端点，再读取输入或写入。完整声明区间校验，不只检查有效前缀。INVALID 优先于 CAPACITY；所有失败必须立即确认输出及计数对象全文不变，成功只改指定前缀/字段，真实双端 guard、输入与输出尾部立即检查。无分配、全局可变状态、OS 调用或宿主生产实现。

编写自己的同名 Python 定向测试：实际编译/链接并执行 Dong debug/release，确认 ELF64/COFF 均能组装；有限固定边界加小规模确定性随机，以独立 Python/C 期望核对。至少两个真实错误 Dong 副本必须成功编译并原生执行，被指定语义/原子性断言拒绝；构建失败、崩溃、超时、无关前置正例拒绝均不算负控成功。不得放宽断言或伪造预检次数。对照输入必须满足所考察规则以外的其它条件，避免非法标签/未对齐/坏图遮蔽目标缺陷。不要求新大矩阵。

只运行本任务定向测试，所有产物在 cursor-works/build/CR6/<唯一目录>/。测试组装源码根时仅暂存当前组件及任务声明的只读依赖，再加 code/lang，避免历史 CR1 副本与主线同名模块冲突；临时包装器和坏实现只写自己的产物目录。除额外声明依赖外，各组件可独立实现。不运行 OS/VM、全回归、性能基准、定时器、关机、提交或推送。

完成后写 cursor-works/deliveries/CR6.md，列出源码/测试 SHA256、真实命令/结果/模式/skip、证据路径、坏实现命中和拒绝原因、剩余限制。未运行的命令必须明确未运行。通过 MCP submit_task 提交，等待 Codex 独立审查/复验；不得自行 accept/integrate。


## 可修改文件

- `cursor-works/src/bootstrap/branch_plan.dg`
- `cursor-works/src/bootstrap/branch_plan.md`
- `cursor-works/tests/test_branch_plan.py`
- `cursor-works/deliveries/CR6.md`

## 定向验收

- `discover:cursor-works/tests:test_branch_plan.py`

交付：`cursor-works/deliveries/CR6.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
