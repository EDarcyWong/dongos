# C20 — 按前驱生成可交给C9的phi并行复制

负责人：claude。状态：待领取。

模块bootstrap.phi_copy_plan，只读导入主线bootstrap.parallel_moves的Move类型。Phi{dst:usize,first:usize,count:usize}，Input{pred:usize,src:usize}。固定接口pub unsafe fn plan(phis:[]const Phi,inputs:[]const Input,predecessor:usize,block_count:usize,slot_count:usize,out:[]moves.Move,used:*usize)u64。
block_count>0，predecessor<block_count；slot_count必须1..MAX-1，所有dst/src<slot_count。每个Phi的非空first/count范围合法，其引用的每个pred<block_count且同一Phi内pred不能重复；所有Phi的dst彼此不同。选中predecessor必须在每个Phi中恰好出现一次，否则INVALID；即使其它pred未被选择，其非法src/pred/重复也须拒绝。未被任何Phi引用的inputs尾部不解释；不同Phi可共享只读输入范围。成功按Phi输入顺序输出{dst,选中src}，包含自复制，used=phis.len；out至少phis.len，空phis在参数数值合法时成功used=0。不排序/调度、不验证完整CFG/类型/活跃性；输出可供C9 schedule进一步消环，临时id=slot_count不出现在输入。先全量验证、后容量、再写。允许O(phi²+各Phi输入数量平方)校验。Python独立字典挑选前驱，并至少一次真实调用C9对生成Moves调度后检查并行符号语义；覆盖缺前驱、未选前驱非法、重复dst/重复pred、共享范围和自复制。坏实现至少取首条而不看pred，或漏验证未选前驱。
仅维护本任务列出的claude-works源码、接口说明、定向测试与交付，不改code/lang、已验收组件、协调器或其它助手文件。依赖主线模块只读，用明确源码根导入，不复制旧组件制造重复模块。
公共契约：OK=0、INVALID=1、CAPACITY=2，需工作区时WORKSPACE=3。访问前校验完整声明区间、非空指针、自然对齐、元素乘法/地址端点；空切片可NULL，结果对象仍必需。只读输入可互相重叠，可写对象与彼此及所有输入完整区间分离。全部数据INVALID优先于CAPACITY，再WORKSPACE（需要时）。非OK out及结果对象全文不变；成功仅改明确前缀/字段，保留输入、尾部与双端guard。所有算术先验溢出；unsafe调用方保证实际访问有效，无分配/全局可变状态/OS调用。任务具体规则优先。
测试独立Python期望，至少100固定种子小案例及边界；真实Dong→NASM→C/SysV，debug/release原生、ELF64/COFF组装、零skip，逐调用检查输入、输出、结果对象及实际双端，含真实只读输入；至少两个真实坏董私有副本两模式编译链接执行后被指定断言拒绝，编译失败/崩溃/超时不算。别名预检夹具先保证其它条件合法，避免非法数据/未对齐遮住目标检查；伪地址只走必拒绝的数值路径。产物放claude-works/build/<编号>/<唯一运行目录>。CLI无命令工具时不绕权，只提交可执行测试并明确未编译/未运行，交付不虚构hash或结果，由协调器执行。保持待复验，不自行验收，不提交/推送，不运行OS/VM或全回归。


## 可修改文件

- `claude-works/src/bootstrap/phi_copy_plan.dg`
- `claude-works/src/bootstrap/phi_copy_plan.md`
- `claude-works/tests/test_phi_copy_plan.py`
- `claude-works/tests/phi_copy_plan_probe*`
- `claude-works/deliveries/C20.md`

## 定向验收

- `discover:claude-works/tests:test_phi_copy_plan.py`

交付：`claude-works/deliveries/C20.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。


## 2026-10-18 转交DeepSeek

用户因Claude额度不足转交，本任务暂停，由`deepseek:D18`接续。新任务书`deepseek-works/tasks/D18-board.md`；原实物、交付、返修和失败回执保留，不将转交视为验收。
