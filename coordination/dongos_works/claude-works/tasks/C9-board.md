# C9 — 并行复制循环消解组件

负责人：claude。状态：待领取。

模块bootstrap.parallel_moves。Move{dst:usize,src:usize}表达所有赋值同时读取旧值。slot_count为原始位置数量，必须1..MAX-1；所有输入src/dst<slot_count，重复dst为INVALID，允许重复src，dst==src可消除。
pub unsafe fn schedule(moves:[]const Move,slot_count:usize,out:[]Move,work:[]u8,used:*usize)u64。
保留临时位置id=slot_count，不得出现在输入中。输出顺序执行后的所有原始位置值必须等同于并行语义，临时值最终不作要求。out必须至少2*moves.len（检查乘法溢出），work至少moves.len；这是本组件固定充分/必要容量门槛，不要求最小化输出，used不超过2*n。空输入used=0。确定性选择输入索引最小的可处理项，确定性打破循环；输入不变，无递归。Python用唯一符号旧值对照，覆盖链、扇出、交换、三环、自复制、多个不连通环。坏实现至少直接顺序赋值破坏交换、打破循环后漏更新源位置。
本批是L3后端所需的独立纯Dong组件，不修改Codex活动语义/流程/后端，也不修改已验收C1～C6、D1～D13或Cursor CR1。仅写本任务列出的claude-works/src、tests和交付。新组件不放入lang/。不提交/推送，不运行OS/VM/全回归，不自行验收。
公共契约：公开OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。借用切片及结果对象先完整检查非空指针、自然对齐、元素乘法和端点溢出；读输入前完成描述符/完整声明区间别名预检。只读输入可互相重叠；可写输出/工作区/结果对象不得互相或与输入整段重叠。空切片可NULL，结果对象仍须有效独立。非OK保持整个输出及结果对象不变；work可在完成描述符预检后改变内部内容。成功只改有效输出前缀及明确字段，尾部/输入/实际双端保护不变。错误优先INVALID→CAPACITY→WORKSPACE（若需要），数据相关INVALID也不能让部分输出泄漏。所有算术先验溢出，debug/release不能以panic代替错误返回。unsafe调用方保证通过数值预检的区间真实可访问；无分配/全局可变状态/OS调用。
验收：独立Python期望，至少100个固定种子的小规模案例及接口边界；实际Dong→NASM→C/SysV，debug/release执行、ELF64/COFF组装，零skip。正向和失败逐次检查返回值、完整结果/输出尾部、输入和真实双端；至少一组真实只读输入。至少两类真实坏董副本成功编译链接运行，并被指定断言拒绝；构建失败/崩溃/超时不算拒绝。只跑本任务定向测试，产物放claude-works/build/<编号>/<唯一运行目录>/。交付附命令、数量/skip、hash、证据和限制，保持待复验。当前契约及测试源码由本任务负责人维护，独立验收由Codex完成。


## 可修改文件

- `claude-works/src/bootstrap/parallel_moves.dg`
- `claude-works/src/bootstrap/parallel_moves.md`
- `claude-works/tests/test_parallel_moves.py`
- `claude-works/tests/parallel_moves_probe*`
- `claude-works/deliveries/C9.md`

## 定向验收

- `discover:claude-works/tests:test_parallel_moves.py`

交付：`claude-works/deliveries/C9.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
