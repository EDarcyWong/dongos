# bootstrap.nasm_sysv_incoming_args

函数入口把 incoming SysV INTEGER 参数完整捕获到局部帧槽（C37）。它是被调用者一侧的组件，和 C34（调用者建立 outgoing 参数）互不替代。

## 依赖（只读、已集成）

- C8 `bootstrap.sysv_integer_args.plan`：在局部 `Location[16]` 与 `abi.Result` 上实际调用，决定每个展开字在哪个参数寄存器或第几个栈字。
- CR8 `bootstrap.nasm_memory_operand.encode`：目标 `encode(5, -destination_offset)`，源 `encode(5, 16 + stack_index)`；空格格式原样保留，本模块只添加 `qword` 和 LF。
- CR4 `bootstrap.decimal_integer`：经 CR8 间接使用（位移十进制）。
- CR11 只作为帧约定参照（等价于 `prologue(frame_bytes, saved_mask=0)`），不导入。

## 接口

```
pub unsafe fn emit(kinds:[]const u8,destination_offsets:[]const usize,
 frame_bytes:usize,out:[]u8,written:*usize)u64
```

状态 `OK=0`、`INVALID=1`、`CAPACITY=2`。

### 校验顺序（全部先于 CAPACITY）

1. `written` 非空、8 对齐、8 字节端点不回绕。
2. kinds 字节区间、destination_offsets（8n 字节，乘法不溢出，非空时 8 对齐）、out 的端点与非空非 NULL。
3. 两个输入之间可重叠；out、written 与两个输入都不重叠，二者之间也不重叠（包括 out 未使用尾部）。
4. `frame_bytes` 在 0..4080 且是 16 的倍数。
5. `kinds.len <= 16`，kind 只能是 0（1 字）或 1（2 字），展开字数 ≤ 16，`destination_offsets.len` 等于展开字数。
6. 每个 offset 满足 `8 <= offset <= frame_bytes` 且 8 对齐，并且两两不同（同宽同对齐时不同即不重叠）。
7. C8 `plan` 返回 OK 且 `used` 等于展开字数。

失败时 out 与 `*written` 全文不变，输入不变；成功只写精确前缀，尾部不变。空参数且 frame_bytes 合法时成功，`written = 0`。

### 输出

先按展开字顺序输出全部 REGISTER 位置：

```
mov qword [rbp - <offset>], <rdi|rsi|rdx|rcx|r8|r9>
```

再按展开字顺序输出每个 STACK 位置两行：

```
mov rax, qword [rbp + <16 + stack_index>]
mov qword [rbp - <offset>], rax
```

参数寄存器在 RAX 被用作中转之前就已存好。

## 运行时约定

- 函数 SysV 入口 rsp ≡ 8 (mod 16)，已执行 `push rbp; mov rbp, rsp; [sub rsp, frame_bytes]`，RBP 作为基准不变；目标槽 `[rbp-offset, rbp-offset+8)` 都在已分配帧内。不支持非零 saved_mask 帧（rbp 以下的保存寄存器会与目标槽冲突）。
- incoming 第一个栈字在 `[rbp + 16]`，与负偏移目标帧分离。
- 调用者已把机器字规范化；不做窄值扩展、sret、SSE、Win64 或 varargs。
- 没有 STACK 字时 RAX 不变；有 STACK 字时 RAX 可变。六个参数寄存器、RBP/RSP、其它 GPR 和 flags 保持；只写目标帧字，相邻内存不变。

## 长度证明

- REGISTER 字：`mov qword `(10) + `[rbp - 4080]`(12) + `, `(2) + `rdi`(3) + `\n`(1) = 28。
- STACK 字：`mov rax, qword `(15) + `[rbp + 136]`(11) + `\n`(1) = 27，加上 `mov qword `(10) + 12 + `, rax\n`(6) = 28，共 55。栈序号至多 15×8 = 120，所以源位移 ≤ 136。
- 总长 ≤ 16×55 = 880 ≤ 局部文本缓冲 1024；单个 CR8 操作数 ≤ 12 ≤ 暂存 24。每次追加仍检查边界。实测最长合法输入（16 标量，offset 4080 起递减）706 字节，测试覆盖其精确/少 1/0 容量。
