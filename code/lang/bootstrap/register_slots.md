# bootstrap.register_slots：确定性的有限寄存器与溢出槽规划

```text
module bootstrap.register_slots;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const REGISTER:u64=0; pub const SPILL:u64=1;
pub struct Interval { pub start:usize, pub end:usize }      // 16 字节，闭区间 [start,end]
pub struct Location { pub kind:u64, pub index:usize }       // 16 字节
pub struct Result   { pub used:usize, pub spill_slots:usize } // 16 字节
pub unsafe fn assign(input:[]const Interval, register_count:usize, out:[]Location, result:*Result)u64
```

这是明确的保守线性策略，不是最优分配：不驱逐、不拆分、不复用溢出槽、不考虑使用频率。

## 规则

```text
对每个区间 i（按输入顺序）：
  寄存器 r 空闲 ⇔ 从未占用，或其当前区间 end < start_i（end == start_i 仍占用）
  有空闲 → 取编号最小的 r：out[i] = {REGISTER, r}，r 改为占用到 end_i
  无空闲 → out[i] = {SPILL, spill_slots}，spill_slots += 1
result = {used: n, spill_slots}
```

- `register_count` 必须在 1..16；寄存器编号为 0..register_count-1，溢出槽编号从 0 递增，每个区间一个槽。
- input 必须按 start 非降序（允许相同起点），且每项 `start <= end`。端点允许 usize 最大值；`end == MAX` 的寄存器之后永不释放。只做比较，不对端点做加减，无溢出。
- 空输入成功，`used=0, spill_slots=0`。
- 性质：同一寄存器上的区间严格不相交；分到寄存器 r 时所有更小编号寄存器都与该区间相交；溢出时所有寄存器都与之相交。

## 检查顺序与内存

1. `INVALID`（描述符）：result 非空、8 字节对齐；input/out 非空时 8 字节对齐；`len*16` 与端点不溢出；out 与 result 彼此不重叠，也不与 input 的完整声明区间重叠。空切片可为 NULL。
2. `INVALID`（数据）：`register_count` 不在 1..16、任一 `start > end`、或 start 下降。
3. `CAPACITY`：`out.len < input.len`（数据 INVALID 优先）。

全部检查完成后才写输出。非 OK 不改 out 与 result；成功只写 `out[0..n)` 和整个 result，尾部不变，input 只读。局部固定 16 项状态（占用标记与当前 end），无工作区、分配、全局可变状态、OS 调用。时间 O(n·register_count)。模块不导出 C 符号，测试经临时 wrapper 导出 `dong_register_slots`。
