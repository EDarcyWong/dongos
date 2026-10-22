# L3DEFER1 候选契约

仅候选开发和复验，未集成生产 lower_program。现有主线方法接线由 L3METHODLOW1 另行冻结验收。

DEFER 只登记编译期清理链，不在登记时执行表达式。每个 DEFER 节点原本未使用的 node_slots 单元保存前一节点索引；Graph/ref/Info 和 program_ir ABI 均不变。局部变量扫描也扫描清理体，确保其局部槽先于临时量统一分配。

块正常离开执行本块新登记的清理，逆登记顺序；return 清理至函数根；break/continue 仅清理至当前循环入口的链头，保留外层块。分支和嵌套循环在编译离开时恢复外层链头/循环边界。不可达声明生成的清理不会越过已经发出的 return/jump 执行。前端禁止嵌套defer、清理内控制转移/捕获赋值和终止cleanup；此候选不绕过这些检查。

return 先完整求值并快照 scalar/pointer/slice，再临时提高临时槽基线，在清理结束前保护已求值返回值。清理调用可以破坏 caller-saved 寄存器及自身临时量，不会覆盖返回快照。容量不足仍只发布空 Program，输出与输入只读约束沿用原契约，node_slots 全范围保护不变。

测试独立 staging：逐字复制当前主线只读闭包，仅将 lower_program 替换成候选，并记录实际 origin/SHA。真实 Dong 编译目标，NASM 汇编 ELF/COFF，C 执行及独立 seed 差分；检查作用域逆序、延迟读取、清理内局部变量、标量/双字/指针返回、break/continue 与嵌套循环、不可达登记。真实错误董变体跳过 return 清理，必须成功编译链接执行后由值 oracle 拒绝。既有方法、8参数、whole-pair-on-stack及外部SysV方法也使用本候选编译器重跑。

此项不实现 enum/error/optional/result/try/orelse/asm/atomics，不声称完整 L3/L3A/G5 完成。主线 G5 fixture 的切换应在独立验收后真实集成任务内进行。
