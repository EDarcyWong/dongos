# C17 — LF源码字节行索引与有界查找

负责人：claude。状态：待领取。

模块bootstrap.line_index。Position{line:usize,byte_column:usize}。固定接口pub unsafe fn build(source:[]const u8,starts:[]usize,used:*usize)u64；pub unsafe fn locate(starts:[]const usize,source_len:usize,offset:usize,result:*Position)u64。build输出[0]以及每个LF(0A)之后的偏移，含末尾LF产生的source.len；空源仍输出[0]。仅按原始LF字节分行，CR作为普通字节，不做UTF-8或Unicode列计算（不同于source_position的代码点语义），内嵌NUL普通处理。先计数/检查溢出和容量后写。locate要求非空starts、starts[0]=0、后续严格递增且<=source_len，offset<=source_len；使用最后一个<=offset的起点返回1基line与1基字节列，EOF及尾LF行为按此定义。输入索引完整数值校验后可二分查找，不要求凭空验证LF真实性；字节列+1溢出返回INVALID。结果对象不变/别名等遵守公共契约。Python独立split-LF/二分期望，覆盖CRLF、连续/尾LF、UTF-8多字节按字节计列、错误索引与EOF；坏实现至少漏末尾空行、错误选择相等offset的前一行。
本批仅实现独立的纯Dong工具，不修改已验收组件、lang/编译器/内核或Codex活动集成。只写本任务声明的同名源码、接口说明、定向测试和交付。不得自行验收、提交或推送，不运行OS/VM/完整回归。新源码先留在claude-works/src/bootstrap/。
公共契约：OK=0、INVALID=1、CAPACITY=2。借用非空指针、自然对齐、元素乘法及区间端点先验检查；空切片可NULL，有效结果对象仍必需。读输入前检查完整声明区间：只读输入可互相重叠，可写对象彼此及与所有输入不得重叠。数据INVALID检查完成后才检查CAPACITY。非OK不改整个输出与结果对象；成功只改有效前缀及明确字段，尾部/输入/双端保护不变。所有需要长度/偏移计算检查溢出，不以debug panic代替返回。unsafe调用方保证通过数值预检后实际访问的内存可访问。无分配、全局可变状态、OS调用；只做明确子集。
验收测试：独立Python期望，至少100个固定种子的小案例及边界；真实Dong→NASM→C/SysV，debug/release原生运行、ELF64/COFF组装、零skip。C每次调用检查输入全文、输出尾部、结果对象和真实双端guard，接口有只读输入参数时至少一组真实只读输入；C13仅有标量输入，无此项。至少两类错误Dong私有副本成功编译链接运行，并被预先指定的状态/字节/原子性断言拒绝；编译失败、崩溃和超时不算拒绝。伪地址仅走应拒绝的数值预检，须排除更早别名/对齐遮蔽，不做巨大分配。产物写claude-works/build/<任务号>/<唯一目录>/。交付写实际命令、数量/skip、hash、证据和限制；不能虚构未运行结果。CLI没有命令工具时只提交实现和可执行测试，明确未运行，由协调器执行，不绕过权限。


## 可修改文件

- `claude-works/src/bootstrap/line_index.dg`
- `claude-works/src/bootstrap/line_index.md`
- `claude-works/tests/test_line_index.py`
- `claude-works/tests/line_index_probe*`
- `claude-works/deliveries/C17.md`

## 定向验收

- `discover:claude-works/tests:test_line_index.py`

交付：`claude-works/deliveries/C17.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
