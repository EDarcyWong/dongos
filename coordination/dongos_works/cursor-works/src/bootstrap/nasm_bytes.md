# bootstrap.nasm_bytes：原生 NASM 字节常量编码器

把调用方借用的任意字节编码成 NASM `db` 文本行，供 L3 后端嵌入二进制常量。不做 UTF-8 校验或替换，不生成标签、重定位、节、字符串结束符或完整汇编文件。

```text
module bootstrap.nasm_bytes;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn encode(source:[]const u8, out:[]u8, written:*usize)u64
```

## 输出格式

成功时 `out` 前缀为按行分组的 ASCII：

```text
db 0xHH,0xHH,...,0xHH\n
```

- 每行最多 16 个字节；不足 16 的最后一行同样以 LF 结束。
- `db ` 与 `0x` 均为小写；十六进制字母 A～F 大写；每字节恰好两位；逗号后无空格。
- 无 BOM、NUL、引号、标签或注释。空输入成功时 `*written=0`，不写 `out`。
- 例：`[0,10,255]` → `db 0x00,0x0A,0xFF\n`。16 字节恰好一行；17 字节两行，第二行只有末字节。

需要长度：`N=0` 时为 0，否则为 `5*N + 3*ceil(N/16)`。乘法、加法及端点均先检查溢出；不用未检查的 `(N+15)/16`。

## 状态与检查顺序

全部检查在读输入或写任何对象之前完成：

1. `written` 非空、自然 8 字节对齐、8 字节区间不回绕。
2. `source` / `out` 区间不回绕（空切片可为 NULL；非空指针非 0 且 `ptr+len` 不溢出）。
3. 别名：整个 `source`、整个 `out` 描述区间与 `written` 的 8 字节彼此不重叠（即使 `out` 有未使用容量也不允许）。
4. 需要长度的逐步溢出检查；不可表示为 `usize` 时为 `INVALID`，且不读输入。
5. `out.len` 小于需要长度 → `CAPACITY`。

1～4 任一不满足为 `INVALID`，因此 `INVALID` 总是先于 `CAPACITY`。

## 内存契约

- 输入只读，可以位于只读页。
- `INVALID` 与 `CAPACITY` 不改变 `out`、`*written` 与输入的任何字节。
- 成功只写 `out[0..written)` 与 `*written`，`out` 尾部不变。
- 无分配、无全局可变状态、无 OS/文件 I/O；`O(N)`；debug/release 无溢出 panic。
- `unsafe`：调用方保证通过预检的区间真实可访问；伪造极端地址只在预检阶段被拒绝。
- 模块本身不导出 C 符号；测试通过临时 wrapper 导出调用入口。
