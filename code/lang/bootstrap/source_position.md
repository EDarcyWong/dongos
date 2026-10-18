# bootstrap.source_position：原生 UTF-8 源码位置定位

把源码中的字节偏移换算成 1 起始的行、列（按 Unicode 标量计）和当前行的字节范围，供 C5 诊断格式化使用。不输出文字、不做 I/O、不选错误码。

```text
module bootstrap.source_position;
import core.utf8;            // 已验收 D13，只读调用 validate/decode
pub const OK:u64=0; pub const INVALID:u64=1; pub const UTF8:u64=2; pub const BOUNDARY:u64=3;
pub struct Position { pub line:usize, pub column:usize, pub line_start:usize, pub line_end:usize }  // 32 字节，偏移 0/8/16/24
pub unsafe fn locate(source:[]const u8, byte_offset:usize, out:*Position)u64
```

编译根需要同时包含 `lang` 和 `lang/std`。

## 检查顺序

1. `INVALID`：`out` 为 NULL、未 8 字节对齐或 32 字节区间回绕；`source` 区间回绕（空切片可为 NULL）；`out` 与整个 `source` 重叠；`byte_offset > source.len`。这一步不读任何源码字节。
2. `UTF8`：用 `core.utf8.validate` 严格验证**整个** `source`，包括目标偏移之后的部分。只接受最短编码的 U+0000..U+10FFFF：过长编码、代理项、超界、孤立的续字节和截断都会被拒绝，不做替换解码。
3. `BOUNDARY`：源码合法，但偏移落在多字节标量内部。偏移等于某个标量起点或 `source.len`（EOF）时合法。

所有非 OK 返回都不改变 `out` 的 32 字节，输入也不变。成功时一次写入整个 Position。

## 计数规则

- `line`、`column` 从 1 开始。`column` 数 Unicode 标量，不数 UTF-8 字节，不展开 TAB，不按显示宽度计算，也不做规范化。
- 只有 LF 换行并把列重置为 1。CR、TAB、NUL、组合符、U+FEFF 等都各算 1 列。CRLF 中的 CR 算一列，随后 LF 换行。
- BOM 不特殊处理：开头的 U+FEFF 算一个标量。调用方若要与模块词法器对齐，应传入已剥离 BOM 的源码，本模块不会自动跳过。
- `line_start` 是当前逻辑行首字节偏移；`line_end` 是该行 LF 的字节位置，没有 LF 时为 `source.len`。范围 `[line_start,line_end)` 不含 LF，但保留 CR。
- 偏移指向 LF 本身时仍属前一行，`column` 是该 LF 之前一列的下一列；偏移在 LF 之后属于新行。
- EOF 可定位；末尾 LF 之后的 EOF 是新的空行（`line_start == line_end == source.len`）。空源码在偏移 0 返回 1/1/0/0。

## 内存与限制

- 输入只读，可以放在只读页。无分配、无全局可变状态、无 OS 调用；耗时与源码长度成正比（一次验证，加上从头到偏移、从偏移到行尾的两段扫描）。
- `line`、`column` 至多 `source.len+1`，不会回绕；所有比较在加法之前进行，debug/release 不会因溢出 panic。
- `unsafe`：调用方保证合法区间实际可访问；伪造的极端地址只会在第 1 步被拒绝，不会被读取。
- 模块本身不导出 C 符号；测试通过临时 wrapper 导出 `dong_source_locate`。
