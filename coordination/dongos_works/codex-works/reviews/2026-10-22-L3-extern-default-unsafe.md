# G5 新确认差异：无体 extern 默认 unsafe

真实冻结生产编译器（L3FLOWINT1作业f48ec24178864741a9a0b2d09290f546的good产物）与独立Python seed接受性复核。没有执行未解析的外部目标，没有构造AST/IR，也不将原生编译成功视为语言等价通过。

普通声明复现：`module probe;extern "sysv64" fn host()u64;pub fn f()u64{return host();}`。

方法声明复现：`module probe;struct S{x:u64}extern "sysv64"("host_method") fn(self:*S)get()u64;pub fn f()u64{var s=S{x:7};return (&s).get();}`。

两例各debug/release，共4次：seed均拒绝（CompileError: call to unsafe function requires an unsafe block），原生frontend/lower均接受并输出调用汇编，退出0。把调用包在unsafe中的两个对照例各两模式共4次，seed/原生均接受。完整源码、来源与命令产物在codex-works/build/L3-extern-unsafe-review/，summary.json保存8条记录及实际producer SHA。

源码审查线索：semantic_types.top_function仅从显式unsafe属性设置Type.flags&2，无体extern声明未隐式带unsafe；rt_call和rt_finish_method_call依赖该位。应由原前端负责人在独立候选返修，不能改写已验收pool:L3METHOD1 R1快照或混入当前冻结的lower合并任务。需要覆盖普通/方法/导入/同名候选/函数指针类型、ABI位与callee Info身份，并保留bodyful SysV定义的既有默认语义。

这是既有语义入口差异，L3FLOWINT1未修改semantic_types.dg。该任务的25项控制流/方法执行和有限G5探针通过不代表完整G5通过；本差异仍必须闭合。按AGENTS原负责人返修分工交Cursor，手动客户端执行，不自动启动AI CLI。
