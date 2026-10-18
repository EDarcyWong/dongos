# bootstrap.diagnostic_format：原生单行诊断格式化

把调用方已经确定的诊断内容格式化成一行字节，供后续原生 CLI 输出。不推导源位置、不分类 UTF-8、不选择诊断类别，也不做源码行、颜色或终端 I/O。

```text
module bootstrap.diagnostic_format;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn render(path:[]const u8, line:usize, column:usize,
 code:[]const u8, message:[]const u8, out:[]u8, written:*usize)u64
```

## 输出

成功时 `out` 前缀逐字节为：

```text
path:line:column: CODE: message\n
```

- `line`、`column` 为十进制，无前导零，取值 1..usize 最大值（最多 20 位）。
- `CODE` 恰好 5 个 ASCII 字节：`E` 加 4 位数字。
- `path`、`message` 原样复制，不重编码、不规范化（调用方保证 UTF-8）。`path` 非空，`message` 可以为空（输出 `...: E0001: \n`）。
- 只有末尾一个 LF，没有 NUL 结尾。`*written` 为总字节数：`len(path)+len(message)+12+位数(line)+位数(column)`。

## 状态与检查顺序

全部检查都在写入之前完成，前 4 步不读任何输入字节：

1. `written` 非空、8 字节对齐、8 字节区间不回绕。
2. 四个切片的区间不回绕（空切片可为 NULL；非空切片指针非 0 且 `ptr+len` 不溢出）。
3. 别名：`out` 与 `written` 彼此不重叠，且都不与 path、code、message 的完整声明区间重叠。三个输入可以相互共享。
4. 值：`line`、`column` 非 0；`path.len` 非 0；`code.len == 5`；`path.len+message.len+固定部分` 用逐步比较检查，不先做会溢出的加法。
5. 读取内容：`code` 为 `E` 加 4 位 ASCII 数字；`path`、`message` 不含 NUL、CR、LF。
6. 总长度大于 `out.len` 为 `CAPACITY`。

1~5 任一不满足为 `INVALID`，因此 `INVALID` 总是先于 `CAPACITY`。

## 内存契约

- 输入只读，可以位于只读页，可以相互共享。
- `INVALID` 和 `CAPACITY` 不改变 `out` 和 `*written` 的任何字节；容量不足时不输出截断的诊断。
- 成功只写 `out[0..written)` 和 `*written`，`out` 尾部不变。
- 无分配、无全局状态、无宿主格式化、无 OS 调用；耗时与输入长度成正比（数字最多 20 位）。
- `unsafe`：调用方保证合法区间实际可访问；伪造的极端地址只在第 1~4 步被拒绝，不会被读取。

## 限制

- 只做格式化，不做 UTF-8 校验；`path`、`message` 中的其它控制字节（如 TAB）原样输出。
- 模块本身不导出 C 符号；测试通过临时 wrapper 导出 `dong_diagnostic_render`。
