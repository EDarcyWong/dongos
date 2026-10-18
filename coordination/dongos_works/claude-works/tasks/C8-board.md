# C8 — SysV整数参数位置规划组件

负责人：claude。状态：待领取。

模块bootstrap.sysv_integer_args。只规划x86-64 SysV的INTEGER类：kinds[i]=0表示一个u64/i64/指针机器字，1表示含两个INTEGER机器字的聚合；其它值INVALID。不支持SSE/浮点/大聚合/返回值/varargs，不据此声称完整ABI。
Location{kind:u64,index:usize}：kind=0寄存器，index0..5分别RDI/RSI/RDX/RCX/R8/R9；kind=1栈，index是从首个栈参数槽开始的字节偏移。Result{used:usize,stack_bytes:usize}。
pub unsafe fn plan(kinds:[]const u8,out:[]Location,result:*Result)u64。
按参数顺序输出展开后的每个机器字位置。双字聚合需同时有两个寄存器，否则整体上栈，且不占用剩余的单个寄存器，后续标量仍可用该寄存器；栈槽按参数/字顺序递增8字节。stack_bytes向上取整16。out容量按实际机器字总数，空输入成功used/stack_bytes=0。先检查全部kind和计数/栈大小再写任何输出。Python独立状态模型对照，尤其5个标量后双字聚合再标量的寄存器回退。
本批是L3后端所需的独立纯Dong组件，不修改Codex活动语义/流程/后端，也不修改已验收C1～C6、D1～D13或Cursor CR1。仅写本任务列出的claude-works/src、tests和交付。新组件不放入lang/。不提交/推送，不运行OS/VM/全回归，不自行验收。
公共契约：公开OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。借用切片及结果对象先完整检查非空指针、自然对齐、元素乘法和端点溢出；读输入前完成描述符/完整声明区间别名预检。只读输入可互相重叠；可写输出/工作区/结果对象不得互相或与输入整段重叠。空切片可NULL，结果对象仍须有效独立。非OK保持整个输出及结果对象不变；work可在完成描述符预检后改变内部内容。成功只改有效输出前缀及明确字段，尾部/输入/实际双端保护不变。错误优先INVALID→CAPACITY→WORKSPACE（若需要），数据相关INVALID也不能让部分输出泄漏。所有算术先验溢出，debug/release不能以panic代替错误返回。unsafe调用方保证通过数值预检的区间真实可访问；无分配/全局可变状态/OS调用。
验收：独立Python期望，至少100个固定种子的小规模案例及接口边界；实际Dong→NASM→C/SysV，debug/release执行、ELF64/COFF组装，零skip。正向和失败逐次检查返回值、完整结果/输出尾部、输入和真实双端；至少一组真实只读输入。至少两类真实坏董副本成功编译链接运行，并被指定断言拒绝；构建失败/崩溃/超时不算拒绝。只跑本任务定向测试，产物放claude-works/build/<编号>/<唯一运行目录>/。交付附命令、数量/skip、hash、证据和限制，保持待复验。当前契约及测试源码由本任务负责人维护，独立验收由Codex完成。


## 可修改文件

- `claude-works/src/bootstrap/sysv_integer_args.dg`
- `claude-works/src/bootstrap/sysv_integer_args.md`
- `claude-works/tests/test_sysv_integer_args.py`
- `claude-works/tests/sysv_integer_args_probe*`
- `claude-works/deliveries/C8.md`

## 定向验收

- `discover:claude-works/tests:test_sysv_integer_args.py`

交付：`claude-works/deliveries/C8.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
