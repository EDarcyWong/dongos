# bootstrap.nasm_symbol：无碰撞的 NASM 内部符号编码

把模块名与条目名的原始字节编码为可嵌入 NASM 的内部符号文本。不做 UTF-8/标识符语义校验；允许 NUL、非 ASCII 与标点，逐字节编码。不散列、不截断、不依赖宿主。模块不导出 C 符号。

```text
module bootstrap.nasm_symbol;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn encode(module_name:[]const u8, item_name:[]const u8, out:[]u8, written:*usize)u64
```

## 输出格式

成功时严格为 ASCII：

```text
__dong_m<hex(module_name)>_n<hex(item_name)>
```

- `__dong_m` 与 `_n` 为字面前缀/分隔；十六进制字母 `a–f` 小写；每输入字节恰好两位。
- 无 NUL、LF、引号或其它装饰。
- 例：`(b"a", b"b")` → `b"__dong_m61_n62"`。
- 分隔不可省略，故 `(a,bc)` 与 `(ab,c)` 编码不同。
- 需要长度：`10 + 2*(module_name.len + item_name.len)`；两端输入均须非空。

## 检查顺序

1. `written` 非空、8 字节对齐、8 字节区间不回绕。
2. `module_name` / `item_name` / `out` 区间不回绕（空 `out` 可为 NULL；非空输入指针非 0）。
3. 别名：完整 `out` 与 `written` 彼此不重叠，且各自与两个完整输入不重叠。两输入可互叠。
4. 输入非空；需要长度逐步溢出检查 → `INVALID`。
5. `out.len` 不足 → `CAPACITY`。`INVALID` 先于 `CAPACITY`。

失败不改 `out`/`*written`/输入；成功只写精确前缀并设置 `*written`。无分配、无全局可变状态、无 OS/文件 I/O。此符号空间可与主线现有编码不同，不更换既有符号。
