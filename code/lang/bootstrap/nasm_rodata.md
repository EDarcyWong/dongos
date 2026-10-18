# bootstrap.nasm_rodata：受限 NASM 只读数据声明

在 CR1 `bootstrap.nasm_bytes` 之上生成带固定前缀标签的只读数据汇编文本。不引入节、对齐指令或任意文本拼接。

```text
module bootstrap.nasm_rodata;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(label:[]const u8, data:[]const u8, out:[]u8, written:*usize)u64
```

## 输出格式

成功时 `out` 前缀为：

```text
<label>:\n
<db lines from nasm_bytes.encode(data)>
```

- `label` 原样写出，随后恰好一字节 `0x3A`（冒号）与一字节 `0x0A`（LF）。
- 不输出反斜杠或字母 `n` 来表示换行；标签行后直接接 CR1 的 `db` 文本。
- `label` 长度 8～128，必须以 ASCII `__dong_` 开头，且前缀后至少一字符；后缀仅 `A–Z` / `a–z` / `0–9` / `_`。
- 空 `data` 仍输出标签行；其后无额外字节。整段经 NASM `-f bin` 后二进制应与原 `data` 一致（空则为空）。

需要长度：`label.len + 2 + need_encode(data)`，其中 `need_encode` 与 CR1 相同（N=0 时为 0，否则 `5*N + 3*ceil(N/16)`）。逐步检查溢出。

## 状态与检查顺序

1. `written` 非空、8 字节对齐、8 字节区间不回绕。
2. `label` / `data` / `out` 区间不回绕（空 `data` 可为 NULL）。
3. 别名：`out` 与 `written` 彼此不重叠，且各自与完整 `label`、完整 `data` 不重叠。`label` 与 `data` 允许重叠。
4. 校验 `label` 内容规则。
5. 计算需要长度（逐步溢出 → `INVALID`）。
6. `out.len` 不足 → `CAPACITY`。`INVALID` 先于 `CAPACITY`。
7. 先调用 `nasm_bytes.encode` 写入标签之后的尾部；成功后再写标签行，并设置 `*written = label.len + 2 + encode_written`。

预检保证 encode 在正常路径不会因容量或描述符失败；若仍非 OK，不写标签，保持失败原子性。

## 内存与依赖

- 只读依赖已集成的 `code/lang/bootstrap/nasm_bytes.dg`；不复制、不修改 CR1 工作区副本。
- 无分配、无全局可变状态、无 OS/文件 I/O。
- 模块不导出 C 符号；测试经临时 wrapper 调用。
