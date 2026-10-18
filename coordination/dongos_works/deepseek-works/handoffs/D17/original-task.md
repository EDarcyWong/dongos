# C19 — 控制流图的确定性迭代DFS后序

负责人：claude。状态：待领取。

模块bootstrap.cfg_postorder，只读导入主线bootstrap.cfg_reachability的Node类型。Frame{node:usize,next:usize}。固定接口pub unsafe fn order(nodes:[]const cfg.Node,edges:[]const usize,entry:usize,out:[]usize,marks:[]u8,work:[]Frame,used:*usize)u64。
nodes非空且entry有效；验证所有节点first/count范围和每条被引用边（含不可达部分），未引用edges尾部无需解释，允许自环/重复边。以输入edges顺序做DFS，首次发现节点立即标记，所有子节点处理后才输出该节点；每个可达节点输出一次，不输出不可达节点。无递归。out须至少nodes.len（固定门槛）否则CAPACITY；marks及work各至少nodes.len否则WORKSPACE。所有描述符、图、容量检查通过后才写任何可写对象；非OK marks/work也不变。成功marks前n项不可达为0、可达为2；marks尾部不变，work前n项内部值不作要求、尾部不变，used为后序输出数。用显式栈避免深图宿主栈溢出，复杂度按实际引用边说明。Python独立DFS对照，覆盖后序与前序区别、回边/环、重复边、不同边顺序、不可达坏边和工作区不足；坏实现至少输出前序或错误把在栈回边再次递归。
仅维护本任务列出的claude-works源码、接口说明、定向测试与交付，不改code/lang、已验收组件、协调器或其它助手文件。依赖主线模块只读，用明确源码根导入，不复制旧组件制造重复模块。
公共契约：OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。访问前校验完整声明区间、非空指针、自然对齐、元素乘法/地址端点；空切片可NULL，结果对象仍必需。只读输入可互相重叠，可写对象与彼此及所有输入完整区间分离。全部数据INVALID优先于CAPACITY，再WORKSPACE（需要时）。非OK out及结果对象全文不变；成功仅改明确前缀/字段，保留输入、尾部与双端guard。所有算术先验溢出；unsafe调用方保证实际访问有效，无分配/全局可变状态/OS调用。任务具体规则优先。
测试独立Python期望，至少100固定种子小案例及边界；真实Dong→NASM→C/SysV，debug/release原生、ELF64/COFF组装、零skip，逐调用检查输入、输出、结果对象及实际双端，含真实只读输入；至少两个真实坏董私有副本两模式编译链接执行后被指定断言拒绝，编译失败/崩溃/超时不算。别名预检夹具先保证其它条件合法，避免非法数据/未对齐遮住目标检查；伪地址只走必拒绝的数值路径。产物放claude-works/build/<编号>/<唯一运行目录>。CLI无命令工具时不绕权，只提交可执行测试并明确未编译/未运行，交付不虚构hash或结果，由协调器执行。保持待复验，不自行验收，不提交/推送，不运行OS/VM或全回归。


## 可修改文件

- `claude-works/src/bootstrap/cfg_postorder.dg`
- `claude-works/src/bootstrap/cfg_postorder.md`
- `claude-works/tests/test_cfg_postorder.py`
- `claude-works/tests/cfg_postorder_probe*`
- `claude-works/deliveries/C19.md`

## 定向验收

- `discover:claude-works/tests:test_cfg_postorder.py`

交付：`claude-works/deliveries/C19.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
