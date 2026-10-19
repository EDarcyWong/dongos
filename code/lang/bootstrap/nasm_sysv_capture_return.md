# bootstrap.nasm_sysv_capture_return：把 SysV 调用返回值规范化保存到固定帧槽（C40）

调用者在 `call` 之后，把 SysV INTEGER 返回值（RAX；`INTEGER_PAIR` 是 RAX/RDX）存进固定帧槽 `[rbp - offset]`。存之前先统一成 64 位内部表示，再写满 8 字节，不会只写窄字节、把槽里的旧垃圾留在高位。C34 负责建立调用实参，C39 负责被调用者装载返回值，本组件负责调用者保存返回值。它和 C39 没有依赖关系，也不复用 C39 的代码。

```text
module bootstrap.nasm_sysv_capture_return;
import bootstrap.sysv_return_plan as rp;        // 已集成 C14
import bootstrap.nasm_memory_operand as mem;    // 已集成 CR8（其内部依赖 CR4 decimal_integer）
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const MAX_FRAME:usize=4080;
pub unsafe fn emit(kind:u64, frame_bytes:usize, low_offset:usize, high_offset:usize, out:[]u8, written:*usize)u64
```

## 依赖复用

- C14 `rp.plan(kind,&plan)` 在局部 `Plan` 上实际调用，得到 words / width_bits / extension。本模块不另写 kind 表：指令只按 width 和 extension 选择。
- CR8 `mem.encode(5, -offset)` 生成 `[rbp - N]`，空格格式原样保留。

## 参数校验（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕；`out` 端点不回绕，非空时不能为 NULL（空 out 可以是 NULL）；`written` 与完整声明的 `out` 不重叠，包括未使用的尾部。
2. `frame_bytes` 在 0..4080 之间，且是 16 的倍数。
3. `kind` 必须被 C14 接受（0..11）。
4. 槽规则：使用的槽必须 8 对齐，且 `8 <= offset <= frame_bytes`，于是完整 8 字节都在帧内。不同 words 的要求：
   - words=0（VOID）：两个 offset 都必须是 0；`frame_bytes=0` 也合法。
   - words=1：`low_offset` 是合法槽，`high_offset` 必须是 0。
   - words=2（PAIR）：两个都是合法槽，且互不相同。

## 输出文本（严格 ASCII，单 LF；不含 ret、标签、section、global）

| kind | C14 plan | 文本 |
| --- | --- | --- |
| 0 VOID | words 0 | 空，written=0，out 不变 |
| 1 BOOL / 2 U8 | 8 位 ZERO | `movzx r10, al\n` + `mov qword [rbp - N], r10\n` |
| 3 I8 | 8 位 SIGN | `movsx r10, al\n` + 同上 |
| 4 U16 | 16 位 ZERO | `movzx r10, ax\n` + 同上 |
| 5 I16 | 16 位 SIGN | `movsx r10, ax\n` + 同上 |
| 6 U32 | 32 位 ZERO | `mov r10d, eax\n`（写 R10D 时高 32 位自动清零）+ 同上 |
| 7 I32 | 32 位 SIGN | `movsxd r10, eax\n` + 同上 |
| 8 U64 / 9 I64 / 10 PTR | 64 位 NONE | `mov qword [rbp - N], rax\n` |
| 11 INTEGER_PAIR | words 2 | `mov qword [rbp - low], rax\n` 然后 `mov qword [rbp - high], rdx\n` |

返回寄存器里窄值的高位允许是垃圾；BOOL 的低字节由上游保证是 0/1，本组件不再归一化。

运行时效果：只有窄类型会改 R10（改成扩展后的 64 位值）。RAX、RDX 和其它所有 GPR、flags（mov/movzx/movsx/movsxd 都不改 flags）、RSP、RBP 都保持不变；VOID 完全不改任何东西。内存上只有完整的目标槽被写，其它帧内容和 guard 都不变。调用方保证运行时帧合法，发射器本身不访问这个帧。

## 长度证明

offset ≤ 4080，所以操作数最长是 `[rbp - 4080]`，共 12 字节。

- 存储行：`mov qword `（10）+ 12 + `, r10\n`（6，`, rax\n`/`, rdx\n` 也是 6）= 28 字节。
- 窄类型：最长的扩展行 `movsxd r10, eax\n`（16）+ 28 = 44 字节。
- 64 位单字是 28 字节；PAIR 是 28 + 28 = 56 字节。

所以任何输出都 ≤ 56 字节，局部文本缓冲取 64 字节就够；CR8 单个操作数的暂存区是 24 字节（实际最多 12 字节）。每次追加仍然做边界检查。全部校验和局部组装完成后才检查用户容量，并且只发布一次 `out` 和 `*written`；任何失败都不改 `out` 和 `*written`。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_cap_emit`。
