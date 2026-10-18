# C11 — 常量分支表排序与重复值检查组件

负责人：claude。状态：待领取。

模块bootstrap.switch_cases。Case{value:i64,label:usize}；label为不解释的目标编号，所有usize均允许。本组件仅规划，不检查标签绑定、不生成实际分支，也不修改语义层。
pub unsafe fn order(input:[]const Case,out:[]Case,work:[]Case,used:*usize)u64。
成功out前n项按有符号i64严格递增，label与原value配对保持，used=n。重复value为INVALID（即使label相同）；用work完成排序/重复检查后才能写out，失败out/used不变。out/work各至少input.len。使用非递归O(N log N)算法，禁止按键数值大小遍历。空输入used=0。独立Python sorted和set判重，覆盖MIN/MAX、正负零邻接、反序、重复值与任意标签。坏实现至少把i64当u64排序、只比较相邻输入而漏掉非相邻重复或破坏value-label配对。
本批是L3后端所需的独立纯Dong组件，不修改Codex活动语义/流程/后端，也不修改已验收C1～C6、D1～D13或Cursor CR1。仅写本任务列出的claude-works/src、tests和交付。新组件不放入lang/。不提交/推送，不运行OS/VM/全回归，不自行验收。
公共契约：公开OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。借用切片及结果对象先完整检查非空指针、自然对齐、元素乘法和端点溢出；读输入前完成描述符/完整声明区间别名预检。只读输入可互相重叠；可写输出/工作区/结果对象不得互相或与输入整段重叠。空切片可NULL，结果对象仍须有效独立。非OK保持整个输出及结果对象不变；work可在完成描述符预检后改变内部内容。成功只改有效输出前缀及明确字段，尾部/输入/实际双端保护不变。错误优先INVALID→CAPACITY→WORKSPACE（若需要），数据相关INVALID也不能让部分输出泄漏。所有算术先验溢出，debug/release不能以panic代替错误返回。unsafe调用方保证通过数值预检的区间真实可访问；无分配/全局可变状态/OS调用。
验收：独立Python期望，至少100个固定种子的小规模案例及接口边界；实际Dong→NASM→C/SysV，debug/release执行、ELF64/COFF组装，零skip。正向和失败逐次检查返回值、完整结果/输出尾部、输入和真实双端；至少一组真实只读输入。至少两类真实坏董副本成功编译链接运行，并被指定断言拒绝；构建失败/崩溃/超时不算拒绝。只跑本任务定向测试，产物放claude-works/build/<编号>/<唯一运行目录>/。交付附命令、数量/skip、hash、证据和限制，保持待复验。当前契约及测试源码由本任务负责人维护，独立验收由Codex完成。


## 可修改文件

- `claude-works/src/bootstrap/switch_cases.dg`
- `claude-works/src/bootstrap/switch_cases.md`
- `claude-works/tests/test_switch_cases.py`
- `claude-works/tests/switch_cases_probe*`
- `claude-works/deliveries/C11.md`

## 定向验收

- `discover:claude-works/tests:test_switch_cases.py`

交付：`claude-works/deliveries/C11.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


本任务错误优先补充（优先于批次笼统描述）：先做描述符/别名/可计算长度INVALID检查，再检查CAPACITY、WORKSPACE；拥有合法充足工作区后排序判重，重复值返回INVALID且out/used不变。不要求在缺少工作区时用O(N²)方式提前判重，保留整体O(N log N)要求。
