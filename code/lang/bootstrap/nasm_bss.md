# bootstrap.nasm_bss：复用 CR4 的 NASM BSS 声明

生成受限的 NASM BSS 声明文本。数字文本由只读依赖 `bootstrap.decimal_integer`（CR4）编码，本模块不另写十进制算法。不引入 `section`/`global`、额外空格或 NUL。模块不导出 C 符号。

```text
module bootstrap.nasm_bss;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(label:[]const u8, byte_count:usize, alignment:usize, out:[]u8, written:*usize)u64
```

## 输出格式

成功时严格为：

```text
align <alignment>, resb 1\n
<label>: resb <byte_count>\n
```

- 换行为真实单字节 `0x0A`。
- `<alignment>` / `<byte_count>` 为 CR4 无符号 64 位规范十进制（无加号、无前导零）。
- `label` 长度 8～128，前缀恰为 ASCII `__dong_`，非空后缀仅 `A–Z` / `a–z` / `0–9` / `_`。
- `alignment` ∈ `{1,2,4,...,4096}`（二次幂）。
- `byte_count` 可为 0～`usize` 最大；`0` 仍输出 `resb 0`。不在宿主分配对应 BSS。
- `align <alignment>, resb 1` 使用未初始化字节填充，保留 BSS 对齐和大小语义，避免部分 NASM 2.x 的 `alignb` 宏展开不支持的 warning push/pop；仍启用严格警告。
- 总输出长度为 `23 + label.len + alignment 的十进制位数 + byte_count 的十进制位数`；容量检查包含新增的显式填充文本。

## 检查顺序

1. `written` 非空、8 字节对齐、区间不回绕。
2. `label` / `out` 区间不回绕（空 `out` 可为 NULL）。
3. 完整 `out` 与 `written` 彼此不重叠，且各自与完整 `label` 不重叠。
4. `label` / `alignment` 规则；不合法 → `INVALID`。
5. 经 CR4 得到两段十进制长度，逐步求总长；溢出 → `INVALID`。
6. `out.len` 不足 → `CAPACITY`。`INVALID` 先于 `CAPACITY`。
7. 成功一次写出；失败不改 `out` / `*written` / 输入。

CR4 先写入栈上暂存，再复制到用户 `out`，避免子调用失败留下半成品标签行。
