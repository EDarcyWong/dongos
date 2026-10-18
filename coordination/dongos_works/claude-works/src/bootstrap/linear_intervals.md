# bootstrap.linear_intervals：线性值活跃区间保守包络

```text
module bootstrap.linear_intervals;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:usize=0xffff_ffff_ffff_ffff;
pub struct Event    { pub value:usize, pub position:usize }   // 16 字节，对齐 8
pub struct Interval { pub first:usize, pub last:usize }       // 16 字节，对齐 8
pub unsafe fn build(events:[]const Event, value_count:usize, out:[]Interval, used:*usize)u64
```

对线性编号的指令位置给出每个值的保守闭区间：`out[v] = [min position, max position]`，取值 v 的全部事件（定义或使用不区分）。从未出现的值输出 `{first:NONE, last:0}`。这只是线性编号上的包络，不做 CFG 活跃分析、不处理 phi/循环回边、不做跨函数寄存器分配。

## 规则

- events 可乱序、可重复；同一值的重复事件不改变结果。
- 每个事件 `value < value_count`，且 `position != NONE`（`position` 可取 `NONE-1` 等高位值）。
- 输出按值编号直接下标，`out[0..value_count)` 全部写出，不按首次出现压缩；成功时 `*used = value_count`。
- 空 events、`value_count = 0` 均允许；`value_count = 0` 时 out 可为空/NULL。

## 检查顺序与内存

1. `INVALID`（描述符）：`used` 非空且 8 字节对齐；events/out 非空时 8 字节对齐、非 NULL；`len*16` 与端点不溢出（先比较再乘/加）。out 的**整个声明区间**、used 彼此不重叠，也不与 events 重叠；空切片可为 NULL 且不参与重叠。
2. `INVALID`（数据）：遍历**全部**事件，含最后一个；任一 `value >= value_count` 或 `position == NONE`。
3. `INVALID`：`value_count * 16` 溢出（`value_count > MAX/16`）。
4. `CAPACITY`：`out.len < value_count`。

全部检查通过前不写任何字节。之后先把 `out[0..value_count)` 置为 `{NONE,0}`，再一遍折叠事件（`first=min`、`last=max`；由于 `position < NONE`，首个事件总会降低 first）。非 OK 时 out 整体与 `*used` 不变；成功只写 `out[0..value_count)` 与 `*used`，尾部与 events 不变。

时间 O(value_count + events.len)，无分配、无全局可变状态、无 OS 调用。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_linear_intervals`。
