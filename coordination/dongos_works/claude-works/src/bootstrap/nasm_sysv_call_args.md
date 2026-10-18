# bootstrap.nasm_sysv_call_args

从固定帧槽 `[rbp - offset]` 建立 SysV INTEGER 调用实参（C34）。

## 依赖（只读、已集成）

- C8 `bootstrap.sysv_integer_args.plan`：在局部 `Location[16]` 与 `abi.Result` 上实际调用，决定每个 word 在寄存器还是栈、以及 `stack_bytes`。本模块不重新实现 ABI 分配。
- CR8 `bootstrap.nasm_memory_operand.encode`：源操作数 `encode(5, -offset)`（`[rbp - off]`），栈目的 `encode(4, location.index)`（`[rsp]` / `[rsp + idx]`）。
- CR4 `bootstrap.decimal_integer.encode`：`sub/add rsp, N` 的十进制。

## 接口

```
pub struct Result{pub written:usize,pub stack_bytes:usize}   // 16 字节
pub unsafe fn setup(kinds:[]const u8,source_offsets:[]const usize,out:[]u8,result:*Result)u64
pub unsafe fn cleanup(stack_bytes:usize,out:[]u8,written:*usize)u64
```

状态：`OK=0`，`INVALID=1`，`CAPACITY=2`。INVALID 先于 CAPACITY；失败时 `out` 与 `*result`/`*written` 完全不变（先在局部缓冲构建全文，最后一次性发布）。

### setup 校验顺序

1. `result` 非空、8 对齐、16 字节跨度不溢出。
2. `source_offsets.len <= MAX/8`；`kinds`、`source_offsets`（字节长度 8n，非空时 8 对齐）、`out` 跨度合法。
3. 重叠：`kinds`/`source_offsets` 之间可重叠；`out`、`result` 与两个输入都不得重叠，二者之间也不得重叠（按声明长度，包括 `out` 未写的尾部）。
4. `kinds.len <= 16`，每个 kind 为 0（标量 1 word）或 1（对 2 word）；总 word 数 `<= 16`；`source_offsets.len == words`。
5. 每个 offset 满足 `8 <= off <= 4096` 且 8 对齐。
6. C8 `plan` 返回 OK 且 `used == words`。

### 输出文本

- 有栈 word 时先 `sub rsp, <stack_bytes>\n`（stack_bytes 由 C8 给出，16 对齐）。
- 先按 word 顺序输出全部 STACK word：`mov rax, qword [rbp - off]\n` + `mov qword [rsp + idx], rax\n`（idx 为 C8 location.index，0 时为 `[rsp]`）。
- 再按 word 顺序输出全部 REGISTER word：`mov <rdi|rsi|rdx|rcx|r8|r9>, qword [rbp - off]\n`。
- 栈参数先写，RAX 临时值因此不会覆盖已装入的实参寄存器；对齐填充槽不写。

### cleanup

`written` 非空、8 对齐、跨度合法；`out` 跨度合法；`written` 与 `out` 不重叠；`stack_bytes <= 128` 且 16 的倍数，否则 INVALID。`0` 输出空串（written=0）；否则 `add rsp, N\n`。

## 长度证明

- STACK word：`mov rax, qword `(15) + `[rbp - 4096]`(12) + `\n`(1) = 28；`mov qword `(10) + `[rsp + 120]`(11) + `, rax\n`(6) = 27；合计 55。
- REGISTER word：`mov `(4) + `rdi`(3) + `, qword `(8) + 12 + 1 = 28 ≤ 55。
- `sub rsp, ` + 至多 3 位 + `\n` = 13。
- 总计 ≤ 13 + 16×55 = 893 < 局部缓冲 1024；每次追加仍做边界检查。实测最长（16 标量、offset 4096，10 个栈 word）为 712 字节，测试覆盖其 exact/−1/0 容量。
- cleanup 最长 `add rsp, 128\n` = 13 ≤ 32。

## 前置条件（调用方）

- 调用点 `rsp` 在 `sub rsp, N` 之前 16 对齐；`[rbp - off]` 槽已在帧内；setup 与 call 之间不再改变 `rsp`；call 后用同一 `stack_bytes` 调 cleanup。
- 发出的指令会破坏 RAX 与 6 个参数寄存器；不保存其他寄存器。
