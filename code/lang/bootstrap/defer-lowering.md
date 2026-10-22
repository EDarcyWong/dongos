# 原生普通 defer 降级

L3DEFER1 经独立验收后，在 L3FLOWINT1 中与 L3FOR1 真实合并到生产 lower_program；保留原候选及历史证据。方法接线沿用已集成 L3METHODLOW1。for 与 while/loop 一样设置并恢复自己的清理边界，match arm 的控制转移清到相应循环，不越过外层注册。

DEFER 只登记编译期清理链，不在登记时执行表达式。每个 DEFER 节点原本未使用的 node_slots 单元保存前一节点索引；Graph/ref/Info 和 program_ir ABI 均不变。局部变量扫描也扫描清理体，确保其局部槽先于临时量统一分配。

块正常离开执行本块新登记的清理，逆登记顺序；return 清理至函数根；break/continue 仅清理至当前循环入口的链头，保留外层块。分支和嵌套循环在编译离开时恢复外层链头/循环边界。不可达声明生成的清理不会越过已经发出的 return/jump 执行。前端禁止嵌套defer、清理内控制转移/捕获赋值和终止cleanup；此候选不绕过这些检查。

return 先完整求值并快照 scalar/pointer/slice，再临时提高临时槽基线，在清理结束前保护已求值返回值。清理调用可以破坏 caller-saved 寄存器及自身临时量，不会覆盖返回快照。容量不足仍只发布空 Program，输出与输入只读约束沿用原契约，node_slots 全范围保护不变。

永久测试 `python -m unittest lang.tests.test_l3_defer_native -v` 仅从生产闭包 staging，不依赖 works/project.json 或候选 overlay，记录实际 origin/SHA。真实 Dong 编译目标，NASM 汇编 ELF/COFF，C 执行及独立 seed 差分；检查作用域逆序、延迟读取、清理内局部变量、标量/双字/指针返回、break/continue 与嵌套循环、不可达登记。真实错误董变体跳过 return 清理，必须成功编译链接执行后由值 oracle 拒绝。既有方法、8参数、whole-pair-on-stack及外部SysV方法也使用同一生产编译器重跑。for 永久模块另外覆盖清理体内数组临时、for/match 的 break/continue/return-pair 组合，以及实际原生汇编器生成 ELF 的宿主执行。

此项不实现 enum/error/optional/result/try/orelse/asm/atomics，不声称完整 L3/L3A/G5 完成。原 G5 defer 夹具保留并改为必须实际原生执行通过；终止型 cleanup 仍受现有前端限制。
