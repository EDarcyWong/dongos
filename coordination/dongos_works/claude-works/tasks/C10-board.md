# C10 — 栈帧局部槽布局组件

负责人：claude。状态：待领取。

模块bootstrap.stack_slots。Slot{size:usize,alignment:usize}；alignment只允许1/2/4/8/16，依赖调用方提供16字节对齐的帧基址，不处理过对齐/动态alloca/ABI保存寄存器。
pub unsafe fn plan(slots:[]const Slot,offsets:[]usize,frame_bytes:*usize)u64。
offsets[i]为从帧基址向下的正偏移，槽地址是base-offset：cursor初始0，end=align_up(cursor+size,alignment)，offset=end，cursor=end；frame_bytes=align_up(cursor,16)。size=0允许且不占实际字节，仍检查alignment。offsets至少slots.len，空输入frame_bytes=0。先预跑全部布局和溢出检查再写输出；全程不实际解引用规划出的地址。Python无限精度独立计算，检查每槽地址对齐、非零槽不重叠、最终帧大小和失败原子性。坏实现至少错误使用align_up(cursor)后加size、最终帧未16对齐或溢出先写部分结果。
本批是L3后端所需的独立纯Dong组件，不修改Codex活动语义/流程/后端，也不修改已验收C1～C6、D1～D13或Cursor CR1。仅写本任务列出的claude-works/src、tests和交付。新组件不放入lang/。不提交/推送，不运行OS/VM/全回归，不自行验收。
公共契约：公开OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。借用切片及结果对象先完整检查非空指针、自然对齐、元素乘法和端点溢出；读输入前完成描述符/完整声明区间别名预检。只读输入可互相重叠；可写输出/工作区/结果对象不得互相或与输入整段重叠。空切片可NULL，结果对象仍须有效独立。非OK保持整个输出及结果对象不变；work可在完成描述符预检后改变内部内容。成功只改有效输出前缀及明确字段，尾部/输入/实际双端保护不变。错误优先INVALID→CAPACITY→WORKSPACE（若需要），数据相关INVALID也不能让部分输出泄漏。所有算术先验溢出，debug/release不能以panic代替错误返回。unsafe调用方保证通过数值预检的区间真实可访问；无分配/全局可变状态/OS调用。
验收：独立Python期望，至少100个固定种子的小规模案例及接口边界；实际Dong→NASM→C/SysV，debug/release执行、ELF64/COFF组装，零skip。正向和失败逐次检查返回值、完整结果/输出尾部、输入和真实双端；至少一组真实只读输入。至少两类真实坏董副本成功编译链接运行，并被指定断言拒绝；构建失败/崩溃/超时不算拒绝。只跑本任务定向测试，产物放claude-works/build/<编号>/<唯一运行目录>/。交付附命令、数量/skip、hash、证据和限制，保持待复验。当前契约及测试源码由本任务负责人维护，独立验收由Codex完成。


## 可修改文件

- `claude-works/src/bootstrap/stack_slots.dg`
- `claude-works/src/bootstrap/stack_slots.md`
- `claude-works/tests/test_stack_slots.py`
- `claude-works/tests/stack_slots_probe*`
- `claude-works/deliveries/C10.md`

## 定向验收

- `discover:claude-works/tests:test_stack_slots.py`

交付：`claude-works/deliveries/C10.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
