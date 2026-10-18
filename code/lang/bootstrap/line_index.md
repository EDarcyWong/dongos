# bootstrap.line_index

原始 LF 字节行索引与有界查找。只把字节 `0x0A` 当作行结束；CR、NUL、`0xA5`、UTF-8 多字节序列等全部是普通字节，列按字节计数（不同于 `bootstrap.source_position` 的 Unicode 标量列）。

```dong
pub const OK:u64=0;pub const INVALID:u64=1;pub const CAPACITY:u64=2;
pub struct Position{pub line:usize,pub byte_column:usize}   // 大小16，对齐8
pub unsafe fn build(source:[]const u8,starts:[]usize,used:*usize)u64;
pub unsafe fn locate(starts:[]const usize,source_len:usize,offset:usize,result:*Position)u64;
```

## build

输出 `starts[0]=0`，随后按出现顺序写每个 LF 之后的偏移 `i+1`；末尾 LF 产生 `source.len`，空源输出 `[0]`。成功时 `*used = LF个数+1`，只写 `starts[0..used)` 与 `*used`。

错误顺序：

1. INVALID（描述符）：`used` 为 NULL 或未按 8 对齐；`starts.len*8` 溢出；`source`/`starts`/`used` 任一非空区间指针为 NULL 或端点越过 2^64；非空 `starts` 未按 8 对齐；`starts`、`used`、`source` 三者任意两者重叠（`source` 只读，但仍不得与可写对象重叠）。空切片可为 NULL，不访问其存储。
2. 先完整扫描计数 LF；`LF个数+1 > starts.len`（包括 `starts.len==0`）返回 CAPACITY。build 没有数据 INVALID。
3. 第二遍写输出。

`i+1 <= source.len`，`LF个数 < starts.len <= 2^61`，偏移与 `used` 不会回绕。

## locate

先检查描述符：`result` 非 NULL、按 8 对齐、16 字节区间无回绕；`starts.len*8` 无溢出，非空 `starts` 指针非 NULL、按 8 对齐、端点无回绕；`result` 与 `starts` 不重叠。

随后数据 INVALID：`starts` 为空、`starts[0]!=0`、非严格递增、任一起点 `> source_len`、`offset > source_len`。不验证这些起点是否真对应 LF（函数不接收源文本）。

全量校验后二分查找最后一个 `starts[i] <= offset`（等于某起点时取该行），返回 `line=i+1`、`byte_column=offset-starts[i]+1`。若 `offset-starts[i] == 2^64-1`（仅可能 `starts=[0]` 等且 `offset=source_len=2^64-1`）则 `+1` 会溢出，返回 INVALID。

EOF：`offset==source_len` 合法。若源以 LF 结尾，索引末项为 `source_len`，EOF 位于空的末行第 1 列；否则 EOF 位于最后一行最后一字节之后一列。

## 存储契约

非 OK 时不改 `starts`/`used`/`result` 任一字节；成功只写有效前缀及明确字段，输出尾部、输入与区间外字节不变。无分配、无全局可变状态、无 OS 调用；unsafe 调用方须保证通过数值预检的区间实际可访问。复杂度 build O(source.len)、locate O(starts.len)（校验）+ O(log starts.len)（查找）。
