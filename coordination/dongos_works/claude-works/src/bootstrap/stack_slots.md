# bootstrap.stack_slots：栈帧局部槽布局

```text
module bootstrap.stack_slots;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub struct Slot { pub size:usize, pub alignment:usize }   // 16 字节
pub unsafe fn plan(slots:[]const Slot, offsets:[]usize, frame_bytes:*usize)u64
```

依赖调用方提供 16 字节对齐的帧基址 base；槽 i 的地址是 `base - offsets[i]`。不处理过对齐、动态 alloca 或 ABI 保存寄存器，也从不解引用规划出的地址。

## 规则

```text
cursor = 0
对每个槽：end = align_up(cursor + size, alignment); offsets[i] = end; cursor = end
frame_bytes = align_up(cursor, 16)
```

- `alignment` 只允许 1/2/4/8/16，其它值 `INVALID`。因为 base 16 对齐且 offset 是 alignment 的倍数，槽地址按 alignment 对齐；非零槽占 `[base-offset, base-offset+size)`，互不重叠，都在帧内。
- `size=0` 允许，不占字节，但仍检查 alignment。空输入 `frame_bytes=0`。

## 检查顺序与内存

1. `INVALID`（描述符）：`frame_bytes` 非空、8 字节对齐；slots/offsets 8 字节对齐；元素乘法与端点不溢出；offsets 与 frame_bytes 彼此不重叠，也不与 slots 重叠；空切片可为 NULL。
2. `INVALID`（数据）：预跑全部布局。任一 alignment 不合法，或 `cursor+size`、任一 `align_up`、最终 16 字节取整超过 usize 最大值（先比较再相加）。
3. `CAPACITY`：`offsets.len < slots.len`。

预跑不写任何输出；通过后第二遍写出。非 OK 不改变 offsets 和 frame_bytes；成功只写 `offsets[0..n)` 和 `*frame_bytes`，尾部不变。O(n)，无分配、无全局可变状态、无 OS 调用。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_stack_slots`。
