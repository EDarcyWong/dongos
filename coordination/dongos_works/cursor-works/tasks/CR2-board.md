# CR2 — 复用CR1的受限NASM只读数据声明

负责人：cursor。状态：交付待复验（R1 已补交）。

模块bootstrap.nasm_rodata。使用已集成且只读的bootstrap.nasm_bytes（code/lang/bootstrap/nasm_bytes.dg），源码位于cursor-works/src/bootstrap/nasm_rodata.dg；测试根只给本目录src和主线lang，不复制/修改旧CR1模块。
固定接口pub unsafe fn emit(label:[]const u8,data:[]const u8,out:[]u8,written:*usize)u64。状态OK=0、INVALID=1、CAPACITY=2。label长度8..128，必须以ASCII "__dong_" 开头且后缀至少一个字符，后缀仅A-Z/a-z/0-9/_，不接受NUL、标点或非ASCII。成功字节严格为label原字节，随后单字节3A（冒号）及单字节0A（LF），最后接nasm_bytes.encode(data)的字节输出；不输出反斜杠或字母n。空data仍输出标签行并真实NASM -f bin为空，不引入节、对齐或额外字节。调用方以显式固定前缀避免寄存器/伪指令命名冲突；不做任意汇编文本拼接。
在读输入/写输出前验证全部描述符及完整声明区间：label/data只读可互相重叠，out和written须彼此以及与完整label/data分离；字节区间及written的8字节自然对齐/端点、整个长度逐步溢出检查。先验证label及需要长度，再检查容量；INVALID先于CAPACITY。非OK out全文/written不变，成功只改有效前缀/结果，尾部和输入不变。复用CR1编码逻辑，不另写十六进制生成器；调用CR1前已完成全部可能失败的预检，避免先写标签后因数据拒绝留下半成品。unsafe调用方保证有效内存，无分配/全局可变状态/OS调用。
只改本任务的源码/接口文档/测试及CR2交付；不改lang/、CR1、Claude、LM或协调器。Cursor手动领取和执行，不加入CLI自动写入队列。独立Python字节期望、至少100条小随机二进制及label边界，Dong原生debug/release、ELF64/COFF组装；实际董输出（包括空data标签）全部送NASM -f bin比较原data。逐调用校验真实输入/输出/结果双端guard及尾部，有真实只读输入；输出尾部别名不得被更早未对齐遮住。至少两个坏董副本实际编译链接执行并被指定字节/原子性断言拒绝，不接受编译失败/崩溃/超时。产物放cursor-works/build/CR2/<唯一目录>。记录真实命令、数量/skip、hash/证据和限制，保留待复验；不提交/推送/运行OS或VM/自行验收。


## 可修改文件

- `cursor-works/src/bootstrap/nasm_rodata.dg`
- `cursor-works/src/bootstrap/nasm_rodata.md`
- `cursor-works/tests/test_nasm_rodata.py`
- `cursor-works/tests/nasm_rodata_probe*`
- `cursor-works/deliveries/CR2.md`

## 定向验收

- `discover:cursor-works/tests:test_nasm_rodata.py`

交付：`cursor-works/deliveries/CR2.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## R1：Codex复验返修

正式3项复跑通过，但原case5的尾部label未初始化为合法标签，漏别名的坏实现仍通过原测试。仅在原case5快照前填入合法8字节标签，见[完整要求](../reviews/2026-10-18-CR2-R1.md)。保持原20项与原有限输入，不扩展矩阵或改算法。原交付追加R1，继续手动执行。
