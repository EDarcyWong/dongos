# bootstrap.nasm_sysv_indirect_invoke：从帧槽读取目标的 SysV 间接调用组合（C43）

完整的间接调用点片段：调用目标是一个存放在固定帧槽 `[rbp - target_offset]` 里的代码地址。它把五个已集成组件真正接起来：C34 建立实参 → CR12 把目标读进 R11 → C27 `call r11` → C34 清理同一次 setup 的栈区 → C40 保存返回值。每个组件都实际调用，本模块不重写它们的算法。不依赖 C41/C42，也不代表活动 IR 或完整 L3 已经完成。

```text
module bootstrap.nasm_sysv_indirect_invoke;
import bootstrap.nasm_sysv_call_args as args;        // C34（内部依赖 C8 sysv_integer_args、CR8、CR4）
import bootstrap.nasm_integer_memory_load as ld;     // CR12（内部依赖 CR8、CR4）
import bootstrap.nasm_indirect_call as ic;           // C27
import bootstrap.nasm_sysv_capture_return as cap;    // C40（内部依赖 C14 sysv_return_plan、CR8）
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const MAX_FRAME:usize=4080; pub const MAX_WORDS:usize=16;
pub unsafe fn emit(kinds:[]const u8, source_offsets:[]const usize, target_offset:usize, return_kind:u64,
                   frame_bytes:usize, low_offset:usize, high_offset:usize, out:[]u8, written:*usize)u64
```

## 输出顺序

严格按下面的顺序拼接，每一段都是对应组件的原样输出：

1. `args.setup(kinds, source_offsets, …)`：有栈实参时先 `sub rsp, N`，再按 C34 的顺序装栈字和寄存器字。
2. `ld.emit(11, 5, -target_offset, 64, false, …)`：`mov r11, qword [rbp - target]`。
3. `ic.emit(11, …)`：`call r11`。
4. `args.cleanup(setup.stack_bytes, …)`：为 0 时不输出，否则 `add rsp, N`。
5. `cap.emit(return_kind, frame_bytes, low_offset, high_offset, …)`：按 C40 保存 RAX/RDX，VOID 时不输出。

目标在 setup **之后**才读：setup 会用 RAX 做中转、写 rdi..r9，这样它们都不可能覆盖已读好的目标；R11 不是参数寄存器，setup 也不会用到它。目标槽可以和某个源槽相同（实参先读、目标后读，读的是同一个值），也可以和返回槽相同（call 之后才写结果）。目标槽里存的必须是调用前有效的代码地址，由上游保证，本组件不检查运行时地址。`add rsp` 会改 flags，所以 flags 不跨调用保持。运行时前提：setup 之前 `rsp % 16 == 0`，rbp 帧有效，callee 遵守 SysV 并正常返回。

## 参数校验（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕。
2. `source_offsets.len*8` 不溢出；`kinds`、`source_offsets`、`out` 的端点都不回绕，非空时指针不能为 NULL；`source_offsets` 非空时必须 8 对齐。
3. 别名：`written` 与完整 `out` 不重叠；`written` 和 `out` 都不能和任何一个完整输入重叠（按声明长度，包括尾部）。两个输入之间允许互相重叠。
4. `frame_bytes` 在 0..4080 之间，且是 16 的倍数。
5. `target_offset` 必须 8 对齐，且 `8 <= target_offset <= frame_bytes`。
6. kinds 沿用 C34：最多 16 个，每个只能是 0 或 1，展开后总字数 ≤ 16，`source_offsets.len` 必须等于总字数；每个源槽 8 对齐且 `8 <= offset <= frame_bytes`。
7. 返回值布局沿用 C40，由实际调用 C40 校验。

各组件在局部 scratch 中的任何非 OK 都按 INVALID 返回，此时用户 `out` 还没被碰过。所有校验都通过、局部组装完成后才判断容量，并且只发布一次精确前缀和 `*written`。任何失败都不改 `out`、`*written` 和任何输入，也不会发布任何一个子段。

## 局部 scratch 的上界证明

五段依次紧接着写进同一个 1280 字节的局部缓冲（任务允许最多 2048）。每个组件拿到的切片长度，都是它自己的契约已经证明足够的大小；组件最多只写到给它的切片末尾：

| 段 | 给组件的切片 | 组件自身的上界 | 写完后 `at` 的上界 |
| --- | --- | --- | --- |
| setup | 1024 | 13 + 16×55 = 893 | 1024 |
| 目标读取 | 64 | `mov r11, qword [rbp - 4080]\n` = 28 | 1088 |
| call | 16 | `call r11\n` = 9 | 1104 |
| cleanup | 32 | `add rsp, 128\n` = 13 | 1136 |
| capture | 64 | 56 | 1200 |

1200 ≤ 1280，所以任何一段都不会越过局部缓冲；合法输入在每一段都一定能放下，不会因内部容量不足而被拒绝。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_indirect_emit`。
