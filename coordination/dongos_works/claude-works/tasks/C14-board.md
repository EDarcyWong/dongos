# C14 — 线性值活跃区间保守包络

负责人：claude。状态：待领取。

模块bootstrap.linear_intervals。Event{value:usize,position:usize}；Interval{first:usize,last:usize}；NONE=MAX。固定接口pub unsafe fn build(events:[]const Event,value_count:usize,out:[]Interval,used:*usize)u64。每个value输出所有事件position的闭区间最小/最大；未出现输出{first:NONE,last:0}。events可乱序和重复；value必须<value_count，position不得为MAX；used成功为value_count。out至少value_count，空events/value_count允许，不要求按首次出现压缩。先验证全部事件、value_count对应元素字节及容量，再初始化/写输出，O(value_count+events.len)。这是线性编号的保守包络，不声称CFG活跃分析/phi/跨函数寄存器分配。Python字典按value收集min/max，覆盖乱序/重复/空值、末尾非法事件与高位position；坏实现至少last只取最后遍历值、漏检查最后非法事件或未清除不存在值。
本批仅实现独立的纯Dong工具，不修改已验收组件、lang/编译器/内核或Codex活动集成。只写本任务声明的同名源码、接口说明、定向测试和交付。不得自行验收、提交或推送，不运行OS/VM/完整回归。新源码先留在claude-works/src/bootstrap/。
公共契约：OK=0、INVALID=1、CAPACITY=2。借用非空指针、自然对齐、元素乘法及区间端点先验检查；空切片可NULL，有效结果对象仍必需。读输入前检查完整声明区间：只读输入可互相重叠，可写对象彼此及与所有输入不得重叠。数据INVALID检查完成后才检查CAPACITY。非OK不改整个输出与结果对象；成功只改有效前缀及明确字段，尾部/输入/双端保护不变。所有需要长度/偏移计算检查溢出，不以debug panic代替返回。unsafe调用方保证通过数值预检后实际访问的内存可访问。无分配、全局可变状态、OS调用；只做明确子集。
验收测试：独立Python期望，至少100个固定种子的小案例及边界；真实Dong→NASM→C/SysV，debug/release原生运行、ELF64/COFF组装、零skip。C每次调用检查输入全文、输出尾部、结果对象和真实双端guard，接口有只读输入参数时至少一组真实只读输入；C13仅有标量输入，无此项。至少两类错误Dong私有副本成功编译链接运行，并被预先指定的状态/字节/原子性断言拒绝；编译失败、崩溃和超时不算拒绝。伪地址仅走应拒绝的数值预检，须排除更早别名/对齐遮蔽，不做巨大分配。产物写claude-works/build/<任务号>/<唯一目录>/。交付写实际命令、数量/skip、hash、证据和限制；不能虚构未运行结果。CLI没有命令工具时只提交实现和可执行测试，明确未运行，由协调器执行，不绕过权限。


## 可修改文件

- `claude-works/src/bootstrap/linear_intervals.dg`
- `claude-works/src/bootstrap/linear_intervals.md`
- `claude-works/tests/test_linear_intervals.py`
- `claude-works/tests/linear_intervals_probe*`
- `claude-works/deliveries/C14.md`

## 定向验收

- `discover:claude-works/tests:test_linear_intervals.py`

交付：`claude-works/deliveries/C14.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
