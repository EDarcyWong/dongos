# bootstrap.cleanup_plan：词法作用域退出清理顺序

```text
module bootstrap.cleanup_plan;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const ROOT_PARENT:usize=0xffff_ffff_ffff_ffff;
pub struct Scope { pub parent:usize, pub first:usize, pub count:usize }   // 24 字节
pub unsafe fn plan(scopes:[]const Scope, cleanup_ids:[]const usize, from_scope:usize, target_scope:usize,
 out:[]usize, used:*usize)u64
```

只规划清理顺序：不执行清理体、不求值返回值、不处理 panic，也不改变 Codex 的 defer 语义实现。

## 规则

- `scopes[0].parent == ROOT_PARENT`，只有 scope 0 是根；其它 parent 都是有效 scope，且所有父链最终都到达 0。任何环（包括从 from_scope 不可达的部分）都是 `INVALID`。
- `cleanup_ids[first..first+count)` 是该 scope 按注册顺序的清理项；同一个不透明 id 可在不同注册处重复。
- `target_scope` 必须是 `from_scope` 本身、它的祖先，或 `ROOT_PARENT`（函数退出）。
- 输出从 `from_scope` 沿父链到 `target_scope` 之前的每一层（不含 target；为 ROOT_PARENT 时包含根），由内到外，每层按注册**逆序**。`from == target` 时输出为空。`*used` 为条数。
- 例：`return` 用 target=ROOT_PARENT，`break`/`continue` 用循环所在 scope 作 target。

## 检查顺序与内存

1. `INVALID`（描述符）：`used` 非空、8 字节对齐；scopes/cleanup_ids/out 8 字节对齐；元素乘法与端点不溢出；out 与 used 彼此不重叠，也不与两个输入重叠；空切片可为 NULL。
2. `INVALID`（数据）：scopes 为空、from_scope 越界；任一 scope 的清理区间越界、根不唯一或不在 0、parent 越界；任一 scope 的父链 n 步内到不了 0（有环）；target 不是 from 本身、祖先或 ROOT_PARENT；所需条数求和溢出（先比较再相加）。
3. `CAPACITY`：`out.len` 小于所需条数。

全部检查通过后才写 out。非 OK 不改变 out 和 used；成功只写 `out[0..used)` 和 `*used`，尾部不变。

## 复杂度与限制

父链验证对每个 scope 最多走 n 步，O(scopes.len²)；之后两次沿 from 的父链求和与输出，O(深度 + 输出条数)。无分配、无全局可变状态、无 OS 调用。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_cleanup_plan`。
