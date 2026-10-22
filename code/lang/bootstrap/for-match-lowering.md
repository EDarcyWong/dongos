# 原生 for 与 bool match 降级

L3FOR1 经独立验收后在 L3FLOWINT1 与 L3DEFER1 真实合并，保留方法主线及两个原候选。for 设置/恢复自身 loop_cleanup，break/continue 仅清本循环；普通块、match arm 和 return 沿用已合并的 defer 链及返回快照。组合永久回归实际从生产源码独立重建。

for为每个AST节点在既有node_slots中记录3个隐藏持久槽（base/limit/index），循环变量另有独立不可变快照槽。范围上下界按左到右各求值一次；half-open循环先比较index<limit，再取元素/运行body，continue指向递增块，break指向end。只有满足index<limit时才递增，u64最大边界不会额外溢出。

数组place直接取原存储地址，切片表达式只快照descriptor，不复制底层数据。数组临时值在进入循环前构造，临时槽基线上移以保留整个迭代期间的对象，嵌套循环离开后恢复。每次迭代将元素复制到绑定变量，聚合元素沿用既有精确字节LOAD，不受随后原数组修改影响。

bool match先完整求值一次并保护快照，按true/false或末尾wildcard发分支，各arm运行自己块；使用前端已检查的穷尽/可见性/初始化结果。optional/result/enum match继续明确拒绝。IR/NASM/Graph ABI不变，隐藏槽与额外帧仍受4080及工作池容量约束。

测试分别由seed和实际Dong frontend/lower/NASM编译，同一独立C程序检查执行结果、u64边界、原存储修改、数组临时生命周期、聚合绑定快照、嵌套break/continue及match单次调用。全目标沿用exact/one-short/alias/guard/readonly输入与输出原子性驱动。真实错误董把for步长1改为2，须编译链接正常退出后由值oracle拒绝。没有OS/VM或完整L3/G5验收声明。

永久入口 `python -m unittest lang.tests.test_l3_for_native -v` 不依赖 works/project.json 或候选覆盖；包含 for/match/defer 的跨边界组合、cleanup 内数组临时循环、return-pair 稳定性及原生 ELF 生成/宿主执行。ELF 入口返回 69（先保存计算返回6、外层清理后全局9，再组合60+9），两模式均检查实际 Dong 输出、原生汇编器 exact/one-short、guard 和源不变。G5 新增四个控制流探针要求真实原生通过，不替代完整语言/ABI/诊断门禁。
