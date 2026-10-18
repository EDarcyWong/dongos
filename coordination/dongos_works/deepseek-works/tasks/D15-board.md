# D15 — 接续C18：修复字符串表长度预检下溢

负责人：deepseek。状态：待领取。

接续原claude:C18，用户因Claude额度不足明确转交DeepSeek。原实物/历史保留，当前源文件和测试已迁到deepseek-works同名位置，只适配目录和build编号，尚未修复。不得修改claude-works原件。

## 本次必须完成的有限修复

原C18算术守卫if c>MAX-1-total在total==MAX时会先下溢。Codex提取同一算术片段的小标量见证：total=MAX,count=1，debug panic退出87、release返回OK并写1。这是算术级见证，不是巨大公共输入复现。让检查自身也不下溢，例如先短路total==MAX，再检查c>MAX-total-1。保留原公共接口、去重/输出算法和原3项测试；在私有测试桥接导出同一checked-add/helper，有限覆盖MAX-2/1→OK MAX、MAX-1/1和MAX/1→INVALID且输出不变，两模式；不巨大分配，不伪地址解引用，不扩新矩阵。详见claude-works/reviews/2026-10-18-C18-R1.md。

## 原完整功能契约（适配新目录）

模块bootstrap.string_table。Name{first:usize,count:usize}指向bytes切片；Result{used:usize,bytes:usize}。固定接口pub unsafe fn build(names:[]const Name,bytes:[]const u8,offsets:[]usize,table:[]u8,result:*Result)u64。每个名字非空、范围合法且不含00；其余字节按原样保存，不做UTF-8规范化。table首字节恒为00，其后按输入首次出现顺序追加不同名字及单个00结尾；相同字节名字共享首次偏移，offsets与names一一对应；used=names.len，bytes为table有效长度。空输入需要table至少1字节，offsets可空，结果0/1。先验证所有名字并通过独立预跑计算去重后长度/溢出，再检查offsets/table容量，最后写。允许O(n²乘比较字节数)，不需要堆或额外工作区，不按hash假定相等；只读names/bytes允许互相重叠，两个输出/结果对象必须与完整输入区间及彼此分离。Python独立字典构建表，覆盖共享原始子串、非ASCII字节、同长度不同内容、重复名字和末项非法/容量不足；坏实现至少按长度错误去重、重复项写新副本或预检失败前发布前缀。
本批仅实现独立的纯Dong工具，不修改已验收组件、lang/编译器/内核或Codex活动集成。只写本任务声明的同名源码、接口说明、定向测试和交付。不得自行验收、提交或推送，不运行OS/VM/完整回归。新源码先留在deepseek-works/src/bootstrap/。
公共契约：OK=0、INVALID=1、CAPACITY=2。借用非空指针、自然对齐、元素乘法及区间端点先验检查；空切片可NULL，有效结果对象仍必需。读输入前检查完整声明区间：只读输入可互相重叠，可写对象彼此及与所有输入不得重叠。数据INVALID检查完成后才检查CAPACITY。非OK不改整个输出与结果对象；成功只改有效前缀及明确字段，尾部/输入/双端保护不变。所有需要长度/偏移计算检查溢出，不以debug panic代替返回。unsafe调用方保证通过数值预检后实际访问的内存可访问。无分配、全局可变状态、OS调用；只做明确子集。
验收测试：独立Python期望，至少100个固定种子的小案例及边界；真实Dong→NASM→C/SysV，debug/release原生运行、ELF64/COFF组装、零skip。C每次调用检查输入全文、输出尾部、结果对象和真实双端guard，接口有只读输入参数时至少一组真实只读输入；C13仅有标量输入，无此项。至少两类错误Dong私有副本成功编译链接运行，并被预先指定的状态/字节/原子性断言拒绝；编译失败、崩溃和超时不算拒绝。伪地址仅走应拒绝的数值预检，须排除更早别名/对齐遮蔽，不做巨大分配。产物写deepseek-works/build/<任务号>/<唯一目录>/。交付写实际命令、数量/skip、hash、证据和限制；不能虚构未运行结果。CLI没有命令工具时只提交实现和可执行测试，明确未运行，由协调器执行，不绕过权限。


## 接续操作

只用DeepSeek MCP身份领取本任务，领取成功后再修改。源码在deepseek-works/src/bootstrap/、测试在deepseek-works/tests/；产物放deepseek-works/build/D15/唯一目录。原任务书/交付只读副本在deepseek-works/handoffs/D15/，来源指纹见provenance.json。保留历史说明，真实完成后写deepseek-works/deliveries/D15.md并通过MCP提交；未运行的命令必须明确未运行，不自行验收/集成/提交/推送，不跑OS/VM或全回归。Codex负责独立复验与后续集成。

## 可修改文件

- `deepseek-works/src/bootstrap/string_table.dg`
- `deepseek-works/src/bootstrap/string_table.md`
- `deepseek-works/tests/test_string_table.py`
- `deepseek-works/tests/string_table_probe*`
- `deepseek-works/deliveries/D15.md`

## 定向验收

- `discover:deepseek-works/tests:test_string_table.py`

交付：`deepseek-works/deliveries/D15.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
