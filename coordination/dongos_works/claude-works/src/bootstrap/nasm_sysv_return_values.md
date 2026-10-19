# bootstrap.nasm_sysv_return_values：从固定帧槽发射 SysV 返回值（C39）

被调用者返回前，把固定帧槽 `[rbp - offset]` 里的值装进 SysV INTEGER 返回寄存器：单字放 RAX，`INTEGER_PAIR` 放 RAX/RDX。C37 负责捕获入口实参、C34 负责建立出站实参，本组件补上返回值这一段。

```text
module bootstrap.nasm_sysv_return_values;
import bootstrap.sysv_return_plan as rp;        // 已集成 C14
import bootstrap.nasm_memory_operand as mem;    // 已集成 CR8（其内部依赖 CR4 decimal_integer）
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const MAX_FRAME:usize=4080;
pub unsafe fn emit(kind:u64, frame_bytes:usize, low_offset:usize, high_offset:usize, out:[]u8, written:*usize)u64
```

## 依赖复用

- C14 `rp.plan(kind,&plan)` 在局部 `Plan` 上实际调用，得到 words / width_bits / extension。本模块不另写 kind 表：指令只按 width 和 extension 选择。
- CR8 `mem.encode(5, -offset)` 生成 `[rbp - N]`，空格格式原样保留；本模块只额外加宽度关键字和 LF。

## 参数校验（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕；`out` 端点不回绕，非空时不能为 NULL（空 out 可以是 NULL）；`written` 与完整声明的 `out` 不重叠，包括未使用的尾部。
2. `frame_bytes` 在 0..4080 之间，且是 16 的倍数。
3. `kind` 必须被 C14 接受（0..11）。
4. 槽规则：使用的槽必须 8 对齐，且 `8 <= offset <= frame_bytes`，于是 `[rbp-offset, rbp-offset+8)` 完全在帧内。不同 words 的要求：
   - words=0（VOID）：两个 offset 都必须是 0；`frame_bytes=0` 也合法。
   - words=1：`low_offset` 是合法槽，`high_offset` 必须是 0。
   - words=2（PAIR）：两个都是合法槽，且互不相同。

## 输出文本（严格 ASCII，单 LF；不含 ret、标签、section、global）

| kind | C14 plan | 文本 |
| --- | --- | --- |
| 0 VOID | words 0 | 空，written=0，out 不变 |
| 1 BOOL / 2 U8 | 8 位 ZERO | `movzx rax, byte [rbp - N]\n` |
| 3 I8 | 8 位 SIGN | `movsx rax, byte [rbp - N]\n` |
| 4 U16 | 16 位 ZERO | `movzx rax, word [rbp - N]\n` |
| 5 I16 | 16 位 SIGN | `movsx rax, word [rbp - N]\n` |
| 6 U32 | 32 位 ZERO | `mov eax, dword [rbp - N]\n`（写 EAX 时高 32 位自动清零） |
| 7 I32 | 32 位 SIGN | `movsxd rax, dword [rbp - N]\n` |
| 8 U64 / 9 I64 / 10 PTR | 64 位 NONE | `mov rax, qword [rbp - N]\n` |
| 11 INTEGER_PAIR | words 2 | `mov rax, qword [rbp - low]\n` 然后 `mov rdx, qword [rbp - high]\n` |

窄槽只按正确宽度读取，槽里的高位垃圾不影响结果，读出后按统一内部表示扩展到 64 位。BOOL 的低字节由上游保证已经是 0/1，本组件不再做归一化。

运行时效果：只改 RAX（PAIR 还改 RDX）。其它 GPR、flags（mov/movzx/movsx/movsxd 都不改 flags）、RSP、RBP，以及所有帧槽和 guard 都保持不变；VOID 不改任何寄存器。调用方保证运行时帧有效，发射器本身不访问这个帧。

## 长度证明

offset ≤ 4080，所以操作数最长是 `[rbp - 4080]`，共 12 字节。

- 单字：前缀最长的是 `movsxd rax, dword `（18 字节），一行最多 18 + 12 + 1 = 31 字节。
- PAIR：两行，每行 `mov rax, qword `/`mov rdx, qword `（15 字节）+ 12 + 1 = 28，合计 56 字节。

所以任何输出都 ≤ 56 字节，局部文本缓冲取 64 字节就够；CR8 单个操作数的暂存区是 24 字节（实际最多 12 字节）。每次追加仍然做边界检查。全部校验和局部组装完成后才检查用户容量，并且只发布一次 `out` 和 `*written`；任何失败都不改 `out` 和 `*written`。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_ret_emit`。
