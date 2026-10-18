# bootstrap.string_table：稳定去重的 NUL 结尾字符串表

```text
module bootstrap.string_table;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub struct Name { pub first:usize, pub count:usize }   // 16 字节，指向 bytes[first..first+count)
pub struct Result { pub used:usize, pub bytes:usize }  // 16 字节
pub unsafe fn build(names:[]const Name, bytes:[]const u8, offsets:[]usize, table:[]u8, result:*Result)u64
```

## 输出

- `table[0]` 恒为 0x00。之后按输入中**首次出现**的顺序追加每个不同的名字，各跟一个 0x00。
- 两个名字字节完全相同（逐字节比较，不只比长度，也不用哈希）时共享首次出现的偏移；描述符不同但内容相同也算相同。
- `offsets[i]` 与 `names[i]` 一一对应；`result.used = names.len`，`result.bytes` 为表的有效长度。
- 名字字节原样保存，不做 UTF-8 校验或规范化。空输入成功：需要 `table.len >= 1`，offsets 可为空，结果为 used=0、bytes=1。

## 检查顺序与内存

1. `INVALID`（描述符）：`result` 非空、8 字节对齐；names/offsets 8 字节对齐；元素乘法与端点不溢出；offsets、table、result 彼此不重叠，也不与 names、bytes 的完整声明区间重叠（names 与 bytes 之间可以重叠）；空切片可为 NULL。
2. `INVALID`（数据）：任一名字为空、区间越界或包含 0x00（包括最后一项）。
3. `INVALID`（溢出）：独立预跑计算去重后的表长度，用 grow_ok(total,count) 先比较再相加；grow_ok 先短路 total==MAX 再检查 count<=MAX-total-1，因此比较自身也不会下溢。实际内存中不可达；测试经私有桥接导出 dong_strtab_grow_ok 直接覆盖 MAX-2/MAX-1/MAX 边界。
4. `CAPACITY`：`offsets.len < names.len` 或 `table.len` 小于表长度。

预跑不写任何输出；全部通过后才写 table、offsets 和 result。非 OK 不改变三个输出对象的任何字节；成功只写 `table[0..bytes)`、`offsets[0..n)` 和 result，尾部不变。

## 复杂度与限制

去重用两两逐字节比较，O(n² × 比较字节数)，不需要堆或额外工作区；预跑和写出各做一遍。无分配、无全局可变状态、无 OS 调用。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_string_table`。
