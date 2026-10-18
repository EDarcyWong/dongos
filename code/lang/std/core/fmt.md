# core.fmt / core.errors — 缓冲区格式化与共享错误码

`core.fmt` 是面向调用者缓冲区的格式化模块，无全局输出设备、无隐式分配、无可变参数或格式字符串解释器。它依赖 `core.errors` 中的共享错误码。

## core.errors

```text
module core.errors;
pub error BufferTooSmall = 0x0100_0001;
```

`BufferTooSmall`（0x0100_0001）是本次明确分配的标准库错误编号。其他库需要失败状态时必须导入复用此码，不得另行声明重复编号，以保证最终程序内错误码唯一。

## core.fmt 接口

```text
pub fn decimal(value:u64, output:[]u8) !usize
pub fn signed_decimal(value:i64, output:[]u8) !usize
pub fn hexadecimal(value:u64, output:[]u8) !usize
pub fn write(bytes:[]const u8, output:[]u8) !usize
pub unsafe fn emit(bytes:[]const u8, sink:fn([]const u8)!void) !void
```

## 语义与契约

- 返回值为实际写入字节数，**不附加 NUL**。十六进制使用小写、不加 `0x`、不补零；0 输出一个 `0`。
- `signed_decimal` 正确输出负号，并通过无符号 wrapping 处理 `i64` 最小值（避免取绝对值溢出）。
- 容量不足返回 `error.errors.BufferTooSmall`，且**保持输出缓冲区不变**：先计算所需容量再写入，绝不部分写入后报告成功或截断。
- `write` 按字节复制，保留 UTF-8 和内嵌 NUL；源与目标可重叠（复用 `core.mem.move` 语义）。
- `emit` 调用调用者提供的有效 SysV 回调 `sink`（`fn([]const u8)!void`）并原样传播其错误结果；调用函数指针属 `unsafe`，因此 `emit` 标记 `unsafe`。

## 用法示例

```text
import core.fmt as fmt;
import core.errors as errors;

var buffer: [64]u8 = [0; 64];
let written = try fmt.decimal(12345, buffer[..]);
// buffer[0..written] == "12345"
```

```text
import core.fmt as fmt;
fn sink(bytes: []const u8) !void {
    // 消费 bytes，失败返回错误
    return;
}
unsafe { try fmt.emit(data, sink); }
```

## 已验证

宿主测试用独立 C 参考（`snprintf` 的 `%llu`/`%lld`/`%llx`）交叉核对各整数极值、每种容量边界（恰好、少一字节、空输出）、失败时缓冲区不变、错误码 `0x0100_0001` 传播、`write` 的 NUL 保留与重叠复制，以及 `emit` 的回调次数、原始字节一致性和错误传播；debug/release 两模式均通过。ELF64 与 COFF 均组装。
