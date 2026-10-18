# bootstrap.switch_cases：常量分支表排序与重复值检查

```text
module bootstrap.switch_cases;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2; pub const WORKSPACE:u64=3;
pub struct Case { pub value:i64, pub label:usize }   // 16 字节；label 为不解释的目标编号，任何 usize 都允许
pub unsafe fn order(input:[]const Case, out:[]Case, work:[]Case, used:*usize)u64
```

成功时 `out[0..n)` 按有符号 i64 严格递增，每个 label 与其原 value 保持配对，`*used = n`。只做规划：不检查标签绑定、不生成分支。

## 检查顺序与内存

1. `INVALID`（描述符）：`used` 非空、8 字节对齐；input/out/work 8 字节对齐；元素乘法与端点不溢出；out、work、used 彼此不重叠，也不与 input 重叠；空切片可为 NULL。
2. `CAPACITY`：`out.len < input.len`。
3. `WORKSPACE`：`work.len < input.len`。
4. `INVALID`（数据）：存在重复 value（即使 label 相同）。按任务书补充，重复检查在拥有合法充足工作区、排序之后进行，不在缺少工作区时用 O(N²) 提前判重。

步骤：把 input 复制到 work，在 work 中原地堆排序（非递归，O(N log N)，不按键的数值大小遍历），排序后重复值必然相邻，线性扫描判重；没有重复才把 work 复制到 out 并写 used。非 OK 不改变 out 和 used；work 在通过描述符与容量检查后才被写入（重复值 INVALID 时 work 内容已改变，契约允许）。成功只写 `out[0..n)` 和 `*used`，out 尾部不变。空输入成功，`used=0`。

## 复杂度与限制

时间 O(N log N)，额外空间只有调用方的 work。下标运算 `2*parent+1` 中 parent < n ≤ usize最大/16，不会溢出。无分配、无全局可变状态、无 OS 调用。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_switch_order`。
