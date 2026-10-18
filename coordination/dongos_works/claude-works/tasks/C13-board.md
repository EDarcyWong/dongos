# C13 — 无分配的ULEB128/SLEB128编码

负责人：claude。状态：待领取。

模块bootstrap.leb128。固定接口：pub unsafe fn unsigned(value:u64,out:[]u8,written:*usize)u64；pub unsafe fn signed(value:i64,out:[]u8,written:*usize)u64。仅编码，不解码，不写DWARF/ELF节。使用最短标准ULEB128/SLEB128，每字节低7位为载荷，非末字节bit7=1；SLEB128末字节bit6表示符号，后续符号扩展不改变值时结束。0编码00，-1编码7F，64的signed编码C0 00，-65编码BF 7F；最多10字节。先计算需要长度和CAPACITY再写，written只在成功更新。覆盖0/127/128、±63/64/65、每个7位边界、u64 MAX和i64 MIN/MAX；Python独立编码并解码验证最短性。两类负控至少错误提前结束符号及错误继续位/容量前写入。
本批仅实现独立的纯Dong工具，不修改已验收组件、lang/编译器/内核或Codex活动集成。只写本任务声明的同名源码、接口说明、定向测试和交付。不得自行验收、提交或推送，不运行OS/VM/完整回归。新源码先留在claude-works/src/bootstrap/。
公共契约：OK=0、INVALID=1、CAPACITY=2。借用非空指针、自然对齐、元素乘法及区间端点先验检查；空切片可NULL，有效结果对象仍必需。读输入前检查完整声明区间：只读输入可互相重叠，可写对象彼此及与所有输入不得重叠。数据INVALID检查完成后才检查CAPACITY。非OK不改整个输出与结果对象；成功只改有效前缀及明确字段，尾部/输入/双端保护不变。所有需要长度/偏移计算检查溢出，不以debug panic代替返回。unsafe调用方保证通过数值预检后实际访问的内存可访问。无分配、全局可变状态、OS调用；只做明确子集。
验收测试：独立Python期望，至少100个固定种子的小案例及边界；真实Dong→NASM→C/SysV，debug/release原生运行、ELF64/COFF组装、零skip。C每次调用检查输入全文、输出尾部、结果对象和真实双端guard，接口有只读输入参数时至少一组真实只读输入；C13仅有标量输入，无此项。至少两类错误Dong私有副本成功编译链接运行，并被预先指定的状态/字节/原子性断言拒绝；编译失败、崩溃和超时不算拒绝。伪地址仅走应拒绝的数值预检，须排除更早别名/对齐遮蔽，不做巨大分配。产物写claude-works/build/<任务号>/<唯一目录>/。交付写实际命令、数量/skip、hash、证据和限制；不能虚构未运行结果。CLI没有命令工具时只提交实现和可执行测试，明确未运行，由协调器执行，不绕过权限。


## 可修改文件

- `claude-works/src/bootstrap/leb128.dg`
- `claude-works/src/bootstrap/leb128.md`
- `claude-works/tests/test_leb128.py`
- `claude-works/tests/leb128_probe*`
- `claude-works/deliveries/C13.md`

## 定向验收

- `discover:claude-works/tests:test_leb128.py`

交付：`claude-works/deliveries/C13.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
