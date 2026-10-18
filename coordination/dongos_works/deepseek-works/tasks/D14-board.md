# D14 — 接续C16：修正rel32向后跳转测试

负责人：deepseek。状态：待领取。

接续原claude:C16，用户因Claude额度不足明确转交DeepSeek。原实物/历史保留，当前源文件和测试已迁到deepseek-works同名位置，只适配目录和build编号，尚未修复。不得修改claude-works原件。

## 本次必须完成的有限修复

原C16生产源码未发现算法缺陷；原测试case(b'\xa5'*16,[(4,0)],status=INVALID)期望错误，合法位移为0-(4+4)=-8。只将该既有案例修为OK，验证[4:8]恰为f8 ff ff ff且其它字节不变，保留全部原案例和三类负控，不通过删除/换无效输入绕过。原3项测试必须零skip通过。原R1及Codex私有修正57个边界案例两模式证据见claude-works/reviews/2026-10-18-C16-R1.md。

## 原完整功能契约（适配新目录）

模块bootstrap.rel32_patch。Patch{at:usize,target:usize}，二者都是同一code缓冲区内偏移。固定接口pub unsafe fn apply(code:[]u8,patches:[]const Patch,applied:*usize)u64。每项写code[at..at+4)为target-(at+4)的有符号i32小端补码；target允许0..code.len（含末端标签），at+4须<=len且不能溢出，位移必须在[-2147483648,2147483647]。任意两项四字节区间重叠（含重复at）均INVALID，输入顺序可任意。不生成指令、不处理文件或真实地址重定位。先完整验证描述符、每项及所有区间冲突，再原位写四字节；失败code全文与applied不变，成功applied=patches.len，所有非补丁字节不变。时间可O(patches.len²)，不可按code.len无意义扫描或分配巨型缓冲。测试真实小缓冲前/后向及零位移、乱序/重复/部分重叠；i32溢出用数值合法、与真实元数据不别名的高位伪code区间，仅验证必拒绝路径且不解引用。负控至少位移基准错用at或遇到后续非法项前已经写入。
本批仅实现独立的纯Dong工具，不修改已验收组件、lang/编译器/内核或Codex活动集成。只写本任务声明的同名源码、接口说明、定向测试和交付。不得自行验收、提交或推送，不运行OS/VM/完整回归。新源码先留在deepseek-works/src/bootstrap/。
公共契约：OK=0、INVALID=1、CAPACITY=2。借用非空指针、自然对齐、元素乘法及区间端点先验检查；空切片可NULL，有效结果对象仍必需。读输入前检查完整声明区间：只读输入可互相重叠，可写对象彼此及与所有输入不得重叠。数据INVALID检查完成后才检查CAPACITY。非OK不改整个输出与结果对象；成功只改有效前缀及明确字段，尾部/输入/双端保护不变。所有需要长度/偏移计算检查溢出，不以debug panic代替返回。unsafe调用方保证通过数值预检后实际访问的内存可访问。无分配、全局可变状态、OS调用；只做明确子集。
验收测试：独立Python期望，至少100个固定种子的小案例及边界；真实Dong→NASM→C/SysV，debug/release原生运行、ELF64/COFF组装、零skip。C每次调用检查输入全文、输出尾部、结果对象和真实双端guard，接口有只读输入参数时至少一组真实只读输入；C13仅有标量输入，无此项。至少两类错误Dong私有副本成功编译链接运行，并被预先指定的状态/字节/原子性断言拒绝；编译失败、崩溃和超时不算拒绝。伪地址仅走应拒绝的数值预检，须排除更早别名/对齐遮蔽，不做巨大分配。产物写deepseek-works/build/<任务号>/<唯一目录>/。交付写实际命令、数量/skip、hash、证据和限制；不能虚构未运行结果。CLI没有命令工具时只提交实现和可执行测试，明确未运行，由协调器执行，不绕过权限。


## 接续操作

只用DeepSeek MCP身份领取本任务，领取成功后再修改。源码在deepseek-works/src/bootstrap/、测试在deepseek-works/tests/；产物放deepseek-works/build/D14/唯一目录。原任务书/交付只读副本在deepseek-works/handoffs/D14/，来源指纹见provenance.json。保留历史说明，真实完成后写deepseek-works/deliveries/D14.md并通过MCP提交；未运行的命令必须明确未运行，不自行验收/集成/提交/推送，不跑OS/VM或全回归。Codex负责独立复验与后续集成。

## 可修改文件

- `deepseek-works/src/bootstrap/rel32_patch.dg`
- `deepseek-works/src/bootstrap/rel32_patch.md`
- `deepseek-works/tests/test_rel32_patch.py`
- `deepseek-works/tests/rel32_patch_probe*`
- `deepseek-works/deliveries/D14.md`

## 定向验收

- `discover:deepseek-works/tests:test_rel32_patch.py`

交付：`deepseek-works/deliveries/D14.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
