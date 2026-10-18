# bootstrap.cfg_postorder

控制流图从一个入口节点出发的确定性迭代 DFS 后序。只读导入主线 `bootstrap.cfg_reachability`（`lang/bootstrap/cfg_reachability.dg`）的 `Node{first:usize,count:usize}`，不复制该模块。

```text
pub struct Frame{pub node:usize,pub next:usize}
pub unsafe fn order(nodes:[]const cfg.Node,edges:[]const usize,entry:usize,
                    out:[]usize,marks:[]u8,work:[]Frame,used:*usize)u64
```

状态：`OK=0`、`INVALID=1`、`CAPACITY=2`、`WORKSPACE=3`。

## 图

节点 `i` 的后继为 `edges[nodes[i].first .. nodes[i].first+nodes[i].count)`，按该顺序访问。允许自环、重复边，以及不同节点的边区间互相重叠或共享。没有被任何节点引用的 `edges` 尾部（或中间空洞）不解释、不读取。

## 规则

1. 描述符（任一失败为 INVALID）：`used` 非 NULL 且 8 对齐；各切片完整字节区间 `ptr..ptr+len*size` 不回绕（`nodes` 16 字节/项、`edges`/`out` 8 字节、`marks` 1 字节、`work` 16 字节，长度乘法先验溢出），非空切片指针非 NULL；`nodes`/`edges`/`out`/`work` 非空时 8 对齐。只读的 `nodes` 与 `edges` 可互相重叠；`out`、`marks`、`work`、`used` 两两不重叠，且都不与 `nodes`、`edges` 重叠（相邻允许）。空切片可为 NULL。
2. 数据（INVALID）：`nodes` 非空、`entry<nodes.len`；**每个**节点（含不可达节点）满足 `first<=edges.len` 且 `count<=edges.len-first`，其区间内每条边 `<nodes.len`。
3. `out.len<nodes.len` → CAPACITY（固定门槛，与可达数无关）。
4. `marks.len<nodes.len` 或 `work.len<nodes.len` → WORKSPACE。

优先级 INVALID > CAPACITY > WORKSPACE。以上全部通过之前不写任何可写对象；非 OK 时 `out`、`marks`、`work`、`*used` 全部不变。

## 输出（OK）

- `out[0..*used)`：从 `entry` 可达节点的 DFS 后序，每个可达节点恰好一次，不含不可达节点；`out[*used..]` 不变。
- `marks[0..n)`：可达为 2、不可达为 0；`marks[n..]` 不变。
- `work[0..n)` 内容不作要求；`work[n..]` 不变。
- 输入不被修改。

## 算法

`marks` 先清零；入口标为 1 并压栈帧 `{entry, nodes[entry].first}`。循环查看栈顶帧：若还有未读边，`next` 前进一格；目标 `marks==0` 时**立即**标 1 并压入新帧，否则（在栈上的回边目标或已输出节点）跳过；无剩余边时标 2、写入 `out`、弹栈。因此节点只在其所有后继处理完后输出，回边不会再次进入在栈节点。

每个节点最多入栈一次，栈深 ≤ n，`work.len>=n` 足够，不使用宿主调用栈，深链也不会溢出宿主栈。`first+count` 已验证不超过 `edges.len`，帧内比较不回绕。

复杂度：验证 O(n + Σ所有节点 count)；DFS O(n + Σ可达节点 count)（清零 marks 为 O(n)）。只访问被引用的边，未引用尾部不计入。无分配、无全局可变状态、无 OS 调用。
