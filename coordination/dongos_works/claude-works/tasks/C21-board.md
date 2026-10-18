# C21 — 带对齐的稳定去重原始常量池

负责人：claude。状态：待领取。

模块bootstrap.data_pool_layout。Blob{first:usize,count:usize,alignment:usize}，Result{used:usize,bytes:usize}。固定接口pub unsafe fn build(blobs:[]const Blob,raw:[]const u8,offsets:[]usize,image:[]u8,result:*Result)u64。
每个Blob范围在raw内（count可0，first可等于raw.len），alignment仅1/2/4/8/16。去重键严格为(alignment,原始字节内容)，相同字节但对齐不同不合并；相同键复用第一次出现的offset。新键按输入首次出现顺序分配：start=align_up(cursor,alignment)，offset=start，cursor=start+count；即使count=0也按该公式更新cursor；所有间隙填00。没有固定首字节、没有NUL终止或UTF-8规范化。成功used=blobs.len，bytes=最终cursor，offsets与输入一一对应；空输入成功0/0且image/offsets可NULL。先验证全部Blob并预跑去重后的布局/溢出，再检查offsets和image容量，最后写；无需额外工作区，允许O(n²乘比较字节)时间。只读blobs/raw可互相重叠，两个输出及Result必须与完整输入区间/彼此分离。Python独立字典和任意精度布局对照，检查偏移对齐、稳定去重、padding、尾部与失败原子性；覆盖空Blob、重复子串、相同内容不同alignment、非UTF8二进制及末项非法。坏实现至少忽略alignment去重、错误向下对齐或不清零间隙。
仅维护本任务列出的claude-works源码、接口说明、定向测试与交付，不改code/lang、已验收组件、协调器或其它助手文件。依赖主线模块只读，用明确源码根导入，不复制旧组件制造重复模块。
公共契约：OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。访问前校验完整声明区间、非空指针、自然对齐、元素乘法/地址端点；空切片可NULL，结果对象仍必需。只读输入可互相重叠，可写对象与彼此及所有输入完整区间分离。全部数据INVALID优先于CAPACITY，再WORKSPACE（需要时）。非OK out及结果对象全文不变；成功仅改明确前缀/字段，保留输入、尾部与双端guard。所有算术先验溢出；unsafe调用方保证实际访问有效，无分配/全局可变状态/OS调用。任务具体规则优先。
测试独立Python期望，至少100固定种子小案例及边界；真实Dong→NASM→C/SysV，debug/release原生、ELF64/COFF组装、零skip，逐调用检查输入、输出、结果对象及实际双端，含真实只读输入；至少两个真实坏董私有副本两模式编译链接执行后被指定断言拒绝，编译失败/崩溃/超时不算。别名预检夹具先保证其它条件合法，避免非法数据/未对齐遮住目标检查；伪地址只走必拒绝的数值路径。产物放claude-works/build/<编号>/<唯一运行目录>。CLI无命令工具时不绕权，只提交可执行测试并明确未编译/未运行，交付不虚构hash或结果，由协调器执行。保持待复验，不自行验收，不提交/推送，不运行OS/VM或全回归。


## 可修改文件

- `claude-works/src/bootstrap/data_pool_layout.dg`
- `claude-works/src/bootstrap/data_pool_layout.md`
- `claude-works/tests/test_data_pool_layout.py`
- `claude-works/tests/data_pool_layout_probe*`
- `claude-works/deliveries/C21.md`

## 定向验收

- `discover:claude-works/tests:test_data_pool_layout.py`

交付：`claude-works/deliveries/C21.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## 2026-10-18 转交DeepSeek

用户因Claude额度不足转交，本任务暂停，由`deepseek:D16`接续。新任务书`deepseek-works/tasks/D16-board.md`；原实物、交付、返修和失败回执保留，不将转交视为验收。
