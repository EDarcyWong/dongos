# C12 — 词法作用域退出清理顺序组件

负责人：claude。状态：待领取。

模块bootstrap.cleanup_plan。Scope{parent:usize,first:usize,count:usize}；ROOT_PARENT=MAX，仅scope0.parent=MAX；其它parent是有效节点且所有父链必须最终到0，拒绝任意循环（包括不可达部分）。first/count为注册顺序cleanup_ids的有效切片，允许同一opaque cleanup id在不同注册处重复。
pub unsafe fn plan(scopes:[]const Scope,cleanup_ids:[]const usize,from_scope:usize,target_scope:usize,out:[]usize,used:*usize)u64。
scopes非空且from_scope有效；target_scope必须为from_scope本身/祖先或MAX（函数退出）。输出从from_scope沿父链到target_scope之前各层的cleanup id，每层按注册逆序；target不包含在清理范围，MAX则含根。from==target输出空。先验证全部scope描述符/父链、target祖先关系、需要长度和容量，再写输出；used是条数，尾部不变。允许有界O(scopes.len²+输出数)验证，写明复杂度。不执行清理体、不求值返回值、不处理panic，也不改变Codex的defer语义实现。Python祖先链独立对照，覆盖嵌套return/break/continue路径、空注册、错误目标、不可达父环。坏实现至少外层先于内层、错误包含target或层内顺序未反转。
本批是L3后端所需的独立纯Dong组件，不修改Codex活动语义/流程/后端，也不修改已验收C1～C6、D1～D13或Cursor CR1。仅写本任务列出的claude-works/src、tests和交付。新组件不放入lang/。不提交/推送，不运行OS/VM/全回归，不自行验收。
公共契约：公开OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。借用切片及结果对象先完整检查非空指针、自然对齐、元素乘法和端点溢出；读输入前完成描述符/完整声明区间别名预检。只读输入可互相重叠；可写输出/工作区/结果对象不得互相或与输入整段重叠。空切片可NULL，结果对象仍须有效独立。非OK保持整个输出及结果对象不变；work可在完成描述符预检后改变内部内容。成功只改有效输出前缀及明确字段，尾部/输入/实际双端保护不变。错误优先INVALID→CAPACITY→WORKSPACE（若需要），数据相关INVALID也不能让部分输出泄漏。所有算术先验溢出，debug/release不能以panic代替错误返回。unsafe调用方保证通过数值预检的区间真实可访问；无分配/全局可变状态/OS调用。
验收：独立Python期望，至少100个固定种子的小规模案例及接口边界；实际Dong→NASM→C/SysV，debug/release执行、ELF64/COFF组装，零skip。正向和失败逐次检查返回值、完整结果/输出尾部、输入和真实双端；至少一组真实只读输入。至少两类真实坏董副本成功编译链接运行，并被指定断言拒绝；构建失败/崩溃/超时不算拒绝。只跑本任务定向测试，产物放claude-works/build/<编号>/<唯一运行目录>/。交付附命令、数量/skip、hash、证据和限制，保持待复验。当前契约及测试源码由本任务负责人维护，独立验收由Codex完成。


## 可修改文件

- `claude-works/src/bootstrap/cleanup_plan.dg`
- `claude-works/src/bootstrap/cleanup_plan.md`
- `claude-works/tests/test_cleanup_plan.py`
- `claude-works/tests/cleanup_plan_probe*`
- `claude-works/deliveries/C12.md`

## 定向验收

- `discover:claude-works/tests:test_cleanup_plan.py`

交付：`claude-works/deliveries/C12.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
