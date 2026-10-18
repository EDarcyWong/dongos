# bootstrap.nasm_function_frame：受限 SysV 函数栈帧序言与尾声

生成受限的 NASM 函数序言/尾声文本，供 L3 后端拼接。数字文本由只读依赖 `bootstrap.decimal_integer`（CR4）编码。不引入 `section`/`global`/标签/NUL。模块不导出 C 符号。不声称完整函数生成或 Win64 ABI。

```text
module bootstrap.nasm_function_frame;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn prologue(frame_bytes:usize, saved_mask:u64, out:[]u8, written:*usize)u64
pub unsafe fn epilogue(frame_bytes:usize, saved_mask:u64, out:[]u8, written:*usize)u64
```

## 输入规则

- `frame_bytes`：局部区字节数，须 `0..4096` 且为 16 的倍数。
- `saved_mask`：仅低 5 位允许；依次 `rbx,r12,r13,r14,r15`。更高位 → `INVALID`。
- `n = popcount(mask)`；`padding = 8` 若 `n` 为奇数否则 `0`；`adjust = frame_bytes + padding`。
- 入口额外栈消耗 `total = 8 + 8*n + adjust`；`total > 4096` → `INVALID`。

约定 SysV 入口 `rsp%16=8`；上述序言后调用点 `rsp%16=0`；`rbp` 保留入口栈基准。只支持上述 5 个 callee-saved 整数寄存器。

## 输出格式

序言严格为：

```text
push rbp
mov rbp, rsp
push <reg>   ; 按 rbx→r15 顺序，仅置位者
sub rsp, <adjust>   ; 仅 adjust>0
```

尾声严格为：

```text
add rsp, <adjust>   ; 仅 adjust>0
pop <reg>    ; 逆序
pop rbp
ret
```

换行为真实单字节 `0x0A`。`<adjust>` 为 CR4 无符号 64 位规范十进制。

## 检查顺序

1. `written` 非空、8 字节对齐、区间不回绕。
2. `out` 区间不回绕（空 `out` 可为 NULL）。
3. 完整 `out` 与 `written` 彼此不重叠。
4. `frame_bytes` / `mask` / 栈预算规则；不合法 → `INVALID`。
5. 若需 `adjust` 文本，经 CR4 得到十进制长度并求总长；溢出 → `INVALID`。
6. `out.len` 不足 → `CAPACITY`。`INVALID` 先于 `CAPACITY`。
7. 成功一次写出；失败不改 `out` / `*written`。

CR4 先写入栈上暂存，再复制到用户 `out`，两接口各自预检后原子写。
