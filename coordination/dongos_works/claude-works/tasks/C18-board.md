# C18 — 稳定去重的NUL结尾字符串表构建

负责人：claude。状态：待领取。

模块bootstrap.string_table。Name{first:usize,count:usize}指向bytes切片；Result{used:usize,bytes:usize}。固定接口pub unsafe fn build(names:[]const Name,bytes:[]const u8,offsets:[]usize,table:[]u8,result:*Result)u64。每个名字非空、范围合法且不含00；其余字节按原样保存，不做UTF-8规范化。table首字节恒为00，其后按输入首次出现顺序追加不同名字及单个00结尾；相同字节名字共享首次偏移，offsets与names一一对应；used=names.len，bytes为table有效长度。空输入需要table至少1字节，offsets可空，结果0/1。先验证所有名字并通过独立预跑计算去重后长度/溢出，再检查offsets/table容量，最后写。允许O(n²乘比较字节数)，不需要堆或额外工作区，不按hash假定相等；只读names/bytes允许互相重叠，两个输出/结果对象必须与完整输入区间及彼此分离。Python独立字典构建表，覆盖共享原始子串、非ASCII字节、同长度不同内容、重复名字和末项非法/容量不足；坏实现至少按长度错误去重、重复项写新副本或预检失败前发布前缀。
本批仅实现独立的纯Dong工具，不修改已验收组件、lang/编译器/内核或Codex活动集成。只写本任务声明的同名源码、接口说明、定向测试和交付。不得自行验收、提交或推送，不运行OS/VM/完整回归。新源码先留在claude-works/src/bootstrap/。
公共契约：OK=0、INVALID=1、CAPACITY=2。借用非空指针、自然对齐、元素乘法及区间端点先验检查；空切片可NULL，有效结果对象仍必需。读输入前检查完整声明区间：只读输入可互相重叠，可写对象彼此及与所有输入不得重叠。数据INVALID检查完成后才检查CAPACITY。非OK不改整个输出与结果对象；成功只改有效前缀及明确字段，尾部/输入/双端保护不变。所有需要长度/偏移计算检查溢出，不以debug panic代替返回。unsafe调用方保证通过数值预检后实际访问的内存可访问。无分配、全局可变状态、OS调用；只做明确子集。
验收测试：独立Python期望，至少100个固定种子的小案例及边界；真实Dong→NASM→C/SysV，debug/release原生运行、ELF64/COFF组装、零skip。C每次调用检查输入全文、输出尾部、结果对象和真实双端guard，接口有只读输入参数时至少一组真实只读输入；C13仅有标量输入，无此项。至少两类错误Dong私有副本成功编译链接运行，并被预先指定的状态/字节/原子性断言拒绝；编译失败、崩溃和超时不算拒绝。伪地址仅走应拒绝的数值预检，须排除更早别名/对齐遮蔽，不做巨大分配。产物写claude-works/build/<任务号>/<唯一目录>/。交付写实际命令、数量/skip、hash、证据和限制；不能虚构未运行结果。CLI没有命令工具时只提交实现和可执行测试，明确未运行，由协调器执行，不绕过权限。


## 可修改文件

- `claude-works/src/bootstrap/string_table.dg`
- `claude-works/src/bootstrap/string_table.md`
- `claude-works/tests/test_string_table.py`
- `claude-works/tests/string_table_probe*`
- `claude-works/deliveries/C18.md`

## 定向验收

- `discover:claude-works/tests:test_string_table.py`

交付：`claude-works/deliveries/C18.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## 2026-10-18 R1 返修要求

C18 R1：原3项正式测试虽通过，源码dry-run的if c>MAX-1-total自身会在total==MAX时先下溢；一个合法累计可达MAX的边界后，下个非空唯一名字必须INVALID，而现写法debug panic、release可把总长回绕到1。Codex提取原算术片段，以seed_total=MAX,count=1的小标量见证确认debug退出87、release返回OK且写1；这仅为算术级见证，未声称是public build()端到端巨大输入复现。修正守卫使检查自身也不会下溢，例如先短路total==MAX，再检查c>MAX-total-1；避免panic和回绕，失败前不写。将checked-add抽为私有小函数并在现有定向测试中用测试桥接覆盖MAX-2/1→OK MAX、MAX-1/1→INVALID、MAX/1→INVALID且out不变（两模式）；不要巨大分配/伪地址解引用或新增大矩阵。保留原接口、去重/输出顺序、原3项全部公共案例和坏董负控。只修本守卫及必要小测试/文档，追加deliveries/C18.md的R1真实说明；无命令工具必须明确未运行。详见claude-works/reviews/2026-10-18-C18-R1.md。不要修改已验收组件、lang主线或协调器。


## 2026-10-18 转交DeepSeek

用户因Claude额度不足转交，本任务暂停，由`deepseek:D15`接续。新任务书`deepseek-works/tasks/D15-board.md`；原实物、交付、返修和失败回执保留，不将转交视为验收。
