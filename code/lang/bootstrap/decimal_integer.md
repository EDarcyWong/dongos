# bootstrap.decimal_integer：定宽整数规范十进制文本

将固定位宽原始位模式编码为规范十进制 ASCII。无分配、无全局可变状态、无 OS/文件 I/O。模块不导出 C 符号。

```text
module bootstrap.decimal_integer;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn encode(raw:u64, width:usize, signed:bool, out:[]u8, written:*usize)u64
```

## 解释规则

- `width` 只允许 `8` / `16` / `32` / `64`。
- `width < 64` 时 `raw` 必须严格小于 `2^width`；越界 `INVALID`，不截断。
- `signed=false`：按无符号解释，输出无符号十进制。
- `signed=true`：按该位宽二进制补码解释；负值带前导 `-`（ASCII `0x2D`）。
- 规范形式：无加号、无前导零、无空白/LF/NUL；零恰为 `"0"`，无负零。
- `i64` 最小值（`raw=0x8000_0000_0000_0000`, `width=64`, `signed=true`）输出 `"-9223372036854775808"`；幅度通过无符号 `wrapping_sub` 得到，不在有符号 64 位上直接求负。
- 例：`raw=255,width=8,signed=true` → `"-1"`；`raw=128,width=8,signed=true` → `"-128"`；`raw=256,width=8` 即使 `out` 容量为 0 也 `INVALID`。
- 最大文本长度 20 字节；实现可使用固定局部数组。

## 状态与检查顺序

1. `written` 非空、8 字节自然对齐、完整 8 字节区间不回绕。
2. `out` 完整声明区间不回绕（空 `out` 可为 NULL）。
3. `written` 的 8 字节与完整 `out` 不重叠。
4. `width` / `raw` 规则；不合法 → `INVALID`（优先于容量）。
5. 计算需要长度；`out.len` 不足 → `CAPACITY`。
6. 成功只写文本前缀并设置 `*written`；失败不改 `out` / `*written`。
