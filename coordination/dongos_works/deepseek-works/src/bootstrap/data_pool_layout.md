# bootstrap.data_pool_layout：带对齐的稳定去重原始常量池

```text
module bootstrap.data_pool_layout;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub struct Blob { pub first:usize, pub count:usize, pub alignment:usize }  // 24 字节，指向 raw[first..first+count)
pub struct Result { pub used:usize, pub bytes:usize }                     // 16 字节
pub unsafe fn build(blobs:[]const Blob, raw:[]const u8, offsets:[]usize, image:[]u8, result:*Result)u64
```

## 布局

- 去重键严格为 `(alignment, 原始字节内容)`：内容逐字节比较（不只比长度、不用哈希）；内容相同但 alignment 不同不合并；描述符不同而键相同则合并。
- 按输入中键的**首次出现**顺序分配，cursor 从 0 开始：`start = align_up(cursor, alignment)`，`offset = start`，`cursor = start + count`。`count = 0` 的新键同样按此公式推进 cursor（可能只产生对齐填充）。
- 键重复的 Blob 复用该键第一次出现时的 offset，不再推进 cursor。
- 所有对齐间隙填 0x00。没有固定首字节、没有 NUL 终止，也不做 UTF-8 校验或规范化；字节原样复制（含 0x00、0xFF 等）。
- 成功：`offsets[i]` 与 `blobs[i]` 一一对应，`result.used = blobs.len`，`result.bytes` = 最终 cursor。空输入成功为 0/0，offsets 与 image 可为空/NULL。

## 检查顺序与内存

1. `INVALID`（描述符）：`result` 非空、8 字节对齐；非空 blobs/offsets 8 字节对齐；元素乘法与地址端点不溢出；非空切片指针非 NULL（空切片可 NULL）。offsets、image、result 彼此不重叠，也不与 blobs、raw 的完整声明区间重叠；只读的 blobs 与 raw 之间可以重叠。
2. `INVALID`（数据）：任一 Blob 的 alignment 不是 1/2/4/8/16，或 `first > raw.len`，或 `count > raw.len - first`（`count` 可为 0，`first` 可等于 `raw.len`）。逐项检查全部 Blob，包括最后一项。
3. `INVALID`（溢出）：预跑去重后的布局；对齐填充与 `start + count` 都先比较、比较本身也不回绕（`fits`），任何一步超出 usize 即 INVALID。实际内存中不可达，测试通过私有桥接直接覆盖边界算术。
4. `CAPACITY`：`offsets.len < blobs.len` 或 `image.len < 最终 cursor`。

预跑不写任何输出；全部通过后才写 image、offsets 和 result。非 OK 不改变三个输出对象的任何字节；成功只写 `image[0..bytes)`、`offsets[0..blobs.len)` 和 result，尾部不变。

## 复杂度与限制

去重用两两比较，O(n² × 比较字节数)，预跑和写出各做一遍；不需要堆或额外工作区（不返回 WORKSPACE）。无分配、无全局可变状态、无 OS 调用，无 import。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_data_pool_layout`。
