# bootstrap.parallel_moves：并行复制循环消解

```text
module bootstrap.parallel_moves;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2; pub const WORKSPACE:u64=3;
pub struct Move { pub dst:usize, pub src:usize }   // 16 字节
pub unsafe fn schedule(moves:[]const Move, slot_count:usize, out:[]Move, work:[]u8, used:*usize)u64
```

输入 moves 表示一组同时发生的赋值（所有 src 读取旧值）。成功时 `out[0..used)` 按顺序执行后，每个原始位置（`< slot_count`）的值与并行语义相同。临时位置 id 固定为 `slot_count`，最终值不作要求。

## 规则

- `slot_count` 必须在 1..usize最大−1；每个 src、dst 都 `< slot_count`（因此临时 id 不会出现在输入中）。重复 dst 为 `INVALID`，重复 src 允许，`dst==src` 直接消除。
- 确定性：每步输出**输入下标最小**的、目标不再被任何待处理移动读取的待处理项。没有这样的项时只剩环：取下标最小的待处理项，输出 `temp <- 它的 dst`，再把读取该 dst 的待处理项改为读取 temp，然后它就可以输出。
- 一个只剩纯环的分量在下一个环被打破之前会完整消解，所以单个临时位置足够。输出条数 = 非自赋值的移动数 + 环数 ≤ 1.5n ≤ 2n。例如交换 `{0<-1, 1<-0}` 输出 `2<-0, 0<-1, 1<-2`。

## 检查顺序与内存

1. `INVALID`（描述符）：`used` 非空、8 字节对齐；moves/out 8 字节对齐；元素乘法与端点不溢出；out、work、used 彼此不重叠，也不与 moves 重叠；空切片可为 NULL。
2. `INVALID`（数据）：`slot_count` 为 0 或 usize 最大；任一 src/dst 越界；重复 dst（两两比较，O(n²)，不需要工作区，因此不会因工作区不足而漏报 INVALID）。
3. `CAPACITY`：`out.len < 2*moves.len`（先比较 `n > MAX/2` 防溢出）。这是固定的充分门槛，不按实际条数缩小。
4. `WORKSPACE`：`work.len < moves.len`。

检查全部通过后才写 work（每项一个状态字节：待处理 / 已完成 / 待处理且改读 temp）和 out，此后不会失败。非 OK 不改变 out 和 used（当前实现在非 OK 时也不写 work）。成功只写 `out[0..used)`、`work[0..n)` 和 `*used`，out 尾部不变。输入不变，不递归。

## 复杂度与限制

时间 O(n³)（每输出一条需扫描待处理项，每项再扫描一遍判断目标是否被读取），空间仅 n 字节 work；适合编译器中单个并行复制组的规模。无分配、无全局可变状态、无 OS 调用。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_parallel_moves`。
