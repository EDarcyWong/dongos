# C7 — 控制流图合法性与可达性组件

负责人：claude。状态：待领取。

模块bootstrap.cfg_reachability。Node{first:usize,count:usize}描述edges中一段目标节点编号。
固定接口：pub unsafe fn reachable(nodes:[]const Node,edges:[]const usize,entry:usize,out:[]u8,work:[]usize,used:*usize)u64。
nodes非空，entry<n；所有节点的first/count端点及每条被节点引用的edge目标都须合法，包括不可达节点，未引用的edges尾部无需解释。允许重复边、自环及循环。out至少nodes.len，work至少nodes.len；used为可达节点数。成功out前n个字节仅0/1，entry可达，使用调用方work迭代遍历，不递归、不越界。清晰记录只遍历被引用边的复杂度。Python BFS独立对照，覆盖环、断连图、非法但不可达的节点/边及工作区不足。坏实现至少漏检查不可达坏边、错误跳过环或漏可达节点。
本批是L3后端所需的独立纯Dong组件，不修改Codex活动语义/流程/后端，也不修改已验收C1～C6、D1～D13或Cursor CR1。仅写本任务列出的claude-works/src、tests和交付。新组件不放入lang/。不提交/推送，不运行OS/VM/全回归，不自行验收。
公共契约：公开OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。借用切片及结果对象先完整检查非空指针、自然对齐、元素乘法和端点溢出；读输入前完成描述符/完整声明区间别名预检。只读输入可互相重叠；可写输出/工作区/结果对象不得互相或与输入整段重叠。空切片可NULL，结果对象仍须有效独立。非OK保持整个输出及结果对象不变；work可在完成描述符预检后改变内部内容。成功只改有效输出前缀及明确字段，尾部/输入/实际双端保护不变。错误优先INVALID→CAPACITY→WORKSPACE（若需要），数据相关INVALID也不能让部分输出泄漏。所有算术先验溢出，debug/release不能以panic代替错误返回。unsafe调用方保证通过数值预检的区间真实可访问；无分配/全局可变状态/OS调用。
验收：独立Python期望，至少100个固定种子的小规模案例及接口边界；实际Dong→NASM→C/SysV，debug/release执行、ELF64/COFF组装，零skip。正向和失败逐次检查返回值、完整结果/输出尾部、输入和真实双端；至少一组真实只读输入。至少两类真实坏董副本成功编译链接运行，并被指定断言拒绝；构建失败/崩溃/超时不算拒绝。只跑本任务定向测试，产物放claude-works/build/<编号>/<唯一运行目录>/。交付附命令、数量/skip、hash、证据和限制，保持待复验。当前契约及测试源码由本任务负责人维护，独立验收由Codex完成。


## 可修改文件

- `claude-works/src/bootstrap/cfg_reachability.dg`
- `claude-works/src/bootstrap/cfg_reachability.md`
- `claude-works/tests/test_cfg_reachability.py`
- `claude-works/tests/cfg_reachability_probe*`
- `claude-works/deliveries/C7.md`

## 定向验收

- `discover:claude-works/tests:test_cfg_reachability.py`

交付：`claude-works/deliveries/C7.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
