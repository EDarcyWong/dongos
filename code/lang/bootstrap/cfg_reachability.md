# bootstrap.cfg_reachability：控制流图合法性与可达性

```text
module bootstrap.cfg_reachability;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2; pub const WORKSPACE:u64=3;
pub struct Node { pub first:usize, pub count:usize }      // 16 字节；edges[first..first+count) 是该节点的后继
pub unsafe fn reachable(nodes:[]const Node, edges:[]const usize, entry:usize,
 out:[]u8, work:[]usize, used:*usize)u64
```

成功时 `out[i]` 为 1 表示节点 i 从 `entry` 可达，否则为 0；`*used` 为可达节点数（至少 1，entry 自身可达）。允许重复边、自环和环。

## 检查顺序

1. `INVALID`（描述符）：`used` 非空、8 字节对齐；nodes/edges/work 8 字节对齐；元素乘法和区间端点不溢出；可写的 out、work、used 彼此不重叠，也不与 nodes、edges 的完整声明区间重叠（两个输入之间可以重叠）；空切片可为 NULL。
2. `INVALID`（数据）：`nodes` 为空，或 `entry >= nodes.len`；**任一**节点（无论是否可达）的 `first > edges.len` 或 `count > edges.len-first`，或其引用的任一边目标 `>= nodes.len`。不被任何节点引用的 edges 部分不读取、不解释。
3. `CAPACITY`：`out.len < nodes.len`。
4. `WORKSPACE`：`work.len < nodes.len`。

所有非 OK 返回都不改变 out 和 used；当前实现在非 OK 时也不写 work。检查全部通过后才开始写：此后不会再失败，所以 out 前 n 字节直接用作访问标记，work 用作显式栈（每个节点最多入栈一次，栈深不超过 n），不递归。成功只写 `out[0..n)` 和 `*used`，out 尾部不变。

## 复杂度

验证 O(n + Σcount)，遍历 O(n + 可达节点的 Σcount)。只读取被节点引用的边，未引用的 edges 尾部或空洞不读。所有下标先比较再相加，不会溢出。

## 限制

无分配、无全局可变状态、无 OS 调用；unsafe 调用方保证通过数值预检的区间实际可访问。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_cfg_reachable`。
