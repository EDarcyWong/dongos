# bootstrap.phi_copy_plan：按前驱生成 phi 并行复制

```text
module bootstrap.phi_copy_plan;
import bootstrap.parallel_moves as moves;          // 主线 C9，只读，仅用 Move 类型
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub struct Phi   { pub dst:usize, pub first:usize, pub count:usize }   // 24 字节
pub struct Input { pub pred:usize, pub src:usize }                     // 16 字节
pub unsafe fn plan(phis:[]const Phi, inputs:[]const Input, predecessor:usize, block_count:usize,
                   slot_count:usize, out:[]moves.Move, used:*usize)u64
```

每个 Phi 的输入是 `inputs[first..first+count)`，每项给出“从前驱块 pred 进入时取 src”。成功时 `out[i] = {dst: phis[i].dst, src: 该 Phi 中 pred==predecessor 那一项的 src}`，按 Phi 顺序，自复制（dst==src）照常输出；`*used = phis.len`。输出是一组并行复制（所有 src 读旧值），本模块不排序、不调度；直接交给 `moves.schedule(out[0..used), slot_count, ...)` 消环，临时位置 id = `slot_count`，不会出现在本模块接受的任何 dst/src 中。

## 规则（全部为 INVALID）

- `block_count==0`、`predecessor>=block_count`、`slot_count==0` 或 `slot_count==usize最大`（即使 phis 为空）。
- 任一 Phi：`dst>=slot_count`；与其它 Phi 的 dst 相同；`count!=0` 而 `first>inputs.len` 或 `count>inputs.len-first`（不做加法，无溢出）。
- Phi 范围内任一输入（**无论是否被选中**）：`pred>=block_count`、`src>=slot_count`，或与同一 Phi 内另一输入 pred 相同。
- 选中的 `predecessor` 在某个 Phi 中不是恰好出现一次（`count==0` 的 Phi 因此总是 INVALID）。

未被任何 Phi 引用的 inputs 项不解释；不同 Phi 可以共享（或部分重叠）同一输入范围。不验证 CFG 完整性、类型或活跃性。

## 检查顺序与内存

1. INVALID（描述符）：`used` 非空且 8 字节对齐；phis、inputs、out 非空时指针非空、8 字节对齐，元素乘法（24/16/16 字节）与端点不溢出；out 与 used 彼此不重叠，且都不与 phis 或 inputs 的**整个声明区间**重叠（含未引用尾部）。phis 与 inputs 只读，可以互相重叠。空切片可为 NULL。
2. INVALID（数据）：上节全部规则。校验 O(phis² + Σ count²)，不需要工作区。
3. CAPACITY：`out.len < phis.len`。

INVALID 优先于 CAPACITY。检查全部通过后才写 `out[0..phis.len)` 与 `*used`，此后不会失败；非 OK 时 out 与 `*used` 完全不变，成功时 out 尾部不变。输入不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出。
