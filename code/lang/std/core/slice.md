# core.slice — 字节切片辅助

对 `[]const u8` 的边界辅助、比较与查找。全部按原始字节处理：内嵌 NUL 和 UTF-8 内容没有特殊含义，不做分配或复制切片存储。

## 接口

```text
pub fn equal(a:[]const u8, b:[]const u8) bool
pub fn compare(a:[]const u8, b:[]const u8) i32
pub fn find_byte(bytes:[]const u8, value:u8, start:usize) usize
pub fn range_valid(length:usize, lower:usize, upper:usize) bool
```

## 语义与契约

- `equal`：长度相等且所有字节相等。
- `compare`：无符号字节字典序；公共前缀相同时较短切片更小，仅返回 `-1`、`0`、`1`。
- `find_byte`：从 `start` 向后查找第一个等于 `value` 的字节，返回其索引；找不到或 `start` 不小于长度时返回 `bytes.len`。空切片不访问底层指针。
- `range_valid`：判定 `lower <= upper <= length`，实现不做可能溢出的加法。

## 用法示例

```text
import core.slice as slice;
if slice.range_valid(data.len, begin, end) {
    let window = data[begin..end];
}
```

## 已验证

宿主测试用独立 C 的双字段描述符经 SysV 接口调用，覆盖空切片、只读数组视图、前缀/长度差异、0/255 字节、首尾匹配、未匹配、极大 `start` 及合法/非法区间；两种模式均通过。
