# D16 — 接续C21：完成对齐常量池及完整交付

负责人：deepseek。状态：待领取。

接续原claude:C21，用户因Claude额度不足明确转交DeepSeek。原实物/历史保留，当前源文件和测试已迁到deepseek-works同名位置，只适配目录和build编号，尚未修复。不得修改claude-works原件。

## 本次必须完成的有限修复

原C21执行中因Claude额度429中断，已有源码、说明和语法完整的测试，缺正式交付，尚未验收。三个文件是未完成的接续起点，不把它们当正确实物；依照下方完整契约核对实现、运行定向测试和真实坏源码控制、修复实质问题后写D16交付。原C21未运行正式复验，不能虚构已通过。无需从零重写，不改其它任务/编译器/活动内核。

## 原完整功能契约（适配新目录）

模块bootstrap.data_pool_layout。Blob{first:usize,count:usize,alignment:usize}，Result{used:usize,bytes:usize}。固定接口pub unsafe fn build(blobs:[]const Blob,raw:[]const u8,offsets:[]usize,image:[]u8,result:*Result)u64。
每个Blob范围在raw内（count可0，first可等于raw.len），alignment仅1/2/4/8/16。去重键严格为(alignment,原始字节内容)，相同字节但对齐不同不合并；相同键复用第一次出现的offset。新键按输入首次出现顺序分配：start=align_up(cursor,alignment)，offset=start，cursor=start+count；即使count=0也按该公式更新cursor；所有间隙填00。没有固定首字节、没有NUL终止或UTF-8规范化。成功used=blobs.len，bytes=最终cursor，offsets与输入一一对应；空输入成功0/0且image/offsets可NULL。先验证全部Blob并预跑去重后的布局/溢出，再检查offsets和image容量，最后写；无需额外工作区，允许O(n²乘比较字节)时间。只读blobs/raw可互相重叠，两个输出及Result必须与完整输入区间/彼此分离。Python独立字典和任意精度布局对照，检查偏移对齐、稳定去重、padding、尾部与失败原子性；覆盖空Blob、重复子串、相同内容不同alignment、非UTF8二进制及末项非法。坏实现至少忽略alignment去重、错误向下对齐或不清零间隙。
仅维护本任务列出的deepseek-works源码、接口说明、定向测试与交付，不改code/lang、已验收组件、协调器或其它助手文件。依赖主线模块只读，用明确源码根导入，不复制旧组件制造重复模块。
公共契约：OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。访问前校验完整声明区间、非空指针、自然对齐、元素乘法/地址端点；空切片可NULL，结果对象仍必需。只读输入可互相重叠，可写对象与彼此及所有输入完整区间分离。全部数据INVALID优先于CAPACITY，再WORKSPACE（需要时）。非OK out及结果对象全文不变；成功仅改明确前缀/字段，保留输入、尾部与双端guard。所有算术先验溢出；unsafe调用方保证实际访问有效，无分配/全局可变状态/OS调用。任务具体规则优先。
测试独立Python期望，至少100固定种子小案例及边界；真实Dong→NASM→C/SysV，debug/release原生、ELF64/COFF组装、零skip，逐调用检查输入、输出、结果对象及实际双端，含真实只读输入；至少两个真实坏董私有副本两模式编译链接执行后被指定断言拒绝，编译失败/崩溃/超时不算。别名预检夹具先保证其它条件合法，避免非法数据/未对齐遮住目标检查；伪地址只走必拒绝的数值路径。产物放deepseek-works/build/<编号>/<唯一运行目录>。CLI无命令工具时不绕权，只提交可执行测试并明确未编译/未运行，交付不虚构hash或结果，由协调器执行。保持待复验，不自行验收，不提交/推送，不运行OS/VM或全回归。


## 接续操作

只用DeepSeek MCP身份领取本任务，领取成功后再修改。源码在deepseek-works/src/bootstrap/、测试在deepseek-works/tests/；产物放deepseek-works/build/D16/唯一目录。原任务书/交付只读副本在deepseek-works/handoffs/D16/，来源指纹见provenance.json。保留历史说明，真实完成后写deepseek-works/deliveries/D16.md并通过MCP提交；未运行的命令必须明确未运行，不自行验收/集成/提交/推送，不跑OS/VM或全回归。Codex负责独立复验与后续集成。

## 可修改文件

- `deepseek-works/src/bootstrap/data_pool_layout.dg`
- `deepseek-works/src/bootstrap/data_pool_layout.md`
- `deepseek-works/tests/test_data_pool_layout.py`
- `deepseek-works/tests/data_pool_layout_probe*`
- `deepseek-works/deliveries/D16.md`

## 定向验收

- `discover:deepseek-works/tests:test_data_pool_layout.py`

交付：`deepseek-works/deliveries/D16.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## 2026-10-18 Codex 有限返修 R1

正式四项零skip通过，但原case11的Blob对齐夹具被移位垃圾数据遮蔽。仅在saved快照前为arena+4填合法Blob[2]={{0,3,1},{1,2,4}}，保留原22预检/四项/负控，不改生产算法或扩大输入矩阵。两模式实际错误实现原夹具仍通过，有限修正后均在invalid preflight 11 status 0退出93。完整要求与8次原生证据见deepseek-works/reviews/2026-10-18-D16-R1.md；原交付追加真实R1及具体产物路径，MCP提交待复验，不自行验收。
