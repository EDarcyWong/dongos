# C16 — 受限的相对32位跳转补丁应用

负责人：claude。状态：待领取。

模块bootstrap.rel32_patch。Patch{at:usize,target:usize}，二者都是同一code缓冲区内偏移。固定接口pub unsafe fn apply(code:[]u8,patches:[]const Patch,applied:*usize)u64。每项写code[at..at+4)为target-(at+4)的有符号i32小端补码；target允许0..code.len（含末端标签），at+4须<=len且不能溢出，位移必须在[-2147483648,2147483647]。任意两项四字节区间重叠（含重复at）均INVALID，输入顺序可任意。不生成指令、不处理文件或真实地址重定位。先完整验证描述符、每项及所有区间冲突，再原位写四字节；失败code全文与applied不变，成功applied=patches.len，所有非补丁字节不变。时间可O(patches.len²)，不可按code.len无意义扫描或分配巨型缓冲。测试真实小缓冲前/后向及零位移、乱序/重复/部分重叠；i32溢出用数值合法、与真实元数据不别名的高位伪code区间，仅验证必拒绝路径且不解引用。负控至少位移基准错用at或遇到后续非法项前已经写入。
本批仅实现独立的纯Dong工具，不修改已验收组件、lang/编译器/内核或Codex活动集成。只写本任务声明的同名源码、接口说明、定向测试和交付。不得自行验收、提交或推送，不运行OS/VM/完整回归。新源码先留在claude-works/src/bootstrap/。
公共契约：OK=0、INVALID=1、CAPACITY=2。借用非空指针、自然对齐、元素乘法及区间端点先验检查；空切片可NULL，有效结果对象仍必需。读输入前检查完整声明区间：只读输入可互相重叠，可写对象彼此及与所有输入不得重叠。数据INVALID检查完成后才检查CAPACITY。非OK不改整个输出与结果对象；成功只改有效前缀及明确字段，尾部/输入/双端保护不变。所有需要长度/偏移计算检查溢出，不以debug panic代替返回。unsafe调用方保证通过数值预检后实际访问的内存可访问。无分配、全局可变状态、OS调用；只做明确子集。
验收测试：独立Python期望，至少100个固定种子的小案例及边界；真实Dong→NASM→C/SysV，debug/release原生运行、ELF64/COFF组装、零skip。C每次调用检查输入全文、输出尾部、结果对象和真实双端guard，接口有只读输入参数时至少一组真实只读输入；C13仅有标量输入，无此项。至少两类错误Dong私有副本成功编译链接运行，并被预先指定的状态/字节/原子性断言拒绝；编译失败、崩溃和超时不算拒绝。伪地址仅走应拒绝的数值预检，须排除更早别名/对齐遮蔽，不做巨大分配。产物写claude-works/build/<任务号>/<唯一目录>/。交付写实际命令、数量/skip、hash、证据和限制；不能虚构未运行结果。CLI没有命令工具时只提交实现和可执行测试，明确未运行，由协调器执行，不绕过权限。


## 可修改文件

- `claude-works/src/bootstrap/rel32_patch.dg`
- `claude-works/src/bootstrap/rel32_patch.md`
- `claude-works/tests/test_rel32_patch.py`
- `claude-works/tests/rel32_patch_probe*`
- `claude-works/deliveries/C16.md`

## 定向验收

- `discover:claude-works/tests:test_rel32_patch.py`

交付：`claude-works/deliveries/C16.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## 2026-10-18 R1 返修要求

C16 R1：原正式复验3项中边界测试失败，原因是test_directions_bounds_and_overlaps里的case(b'\xa5'*16,[(4,0)],status=INVALID)期望错误。at=4,target=0合法，rel32=0-(4+4)=-8，必须改为status=OK，保留该向后跳转案例，并验证仅[4:8]写F8 FF FF FF、其它字节不变。不要通过删除案例或把输入换成另一无效案例绕过。Codex私有内存测试仅修改这一期望，复用正式good产物debug/release跑57个边界案例均通过，未修改你的原测试/实现；这不替代原交付复验。原其余两项随机/实际坏董负控已通过。本次只修这一个测试期望；保留全部原案例和负控，源码无新缺陷不改；追加deliveries/C16.md的R1真实说明，不能运行命令就明确未运行。复验仍须原3项零skip及指纹稳定。详见claude-works/reviews/2026-10-18-C16-R1.md。不要修改已验收组件、lang主线或协调器。


## 2026-10-18 转交DeepSeek

用户因Claude额度不足转交，本任务暂停，由`deepseek:D14`接续。新任务书`deepseek-works/tasks/D14-board.md`；原实物、交付、返修和失败回执保留，不将转交视为验收。
