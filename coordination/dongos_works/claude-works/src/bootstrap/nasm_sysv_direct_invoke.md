# bootstrap.nasm_sysv_direct_invoke：组合 SysV 直接调用及结果接收（C41）

把四个已集成组件真正拼成一个完整的调用点片段：C34 建立实参 → C25 直接调用 → C34 清理同一次 setup 的栈区 → C40 把返回值保存到固定帧槽。每个组件都实际调用，本模块不重写它们的算法。

```text
module bootstrap.nasm_sysv_direct_invoke;
import bootstrap.nasm_sysv_call_args as args;        // C34（内部依赖 C8 sysv_integer_args、CR8、CR4）
import bootstrap.nasm_direct_call as dc;             // C25（内部依赖 CR3 nasm_symbol）
import bootstrap.nasm_sysv_capture_return as cap;    // C40（内部依赖 C14 sysv_return_plan、CR8）
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const MAX_FRAME:usize=4080; pub const MAX_WORDS:usize=16; pub const NAME_LIMIT:usize=64;
pub unsafe fn emit(module_name:[]const u8, item_name:[]const u8, kinds:[]const u8, source_offsets:[]const usize,
                   return_kind:u64, frame_bytes:usize, low_offset:usize, high_offset:usize,
                   out:[]u8, written:*usize)u64
```

## 输出顺序

严格按下面的顺序拼接，每一段都是对应组件的原样输出：

1. `args.setup(kinds, source_offsets, …)`：有栈实参时先 `sub rsp, N`，再按 C34 的顺序输出所有栈字和寄存器字。
2. `dc.emit(module_name, item_name, …)`：`call __dong_m<hex>_n<hex>`。
3. `args.cleanup(setup.stack_bytes, …)`：用同一次 setup 返回的 `stack_bytes`；为 0 时不输出，否则输出 `add rsp, N`。
4. `cap.emit(return_kind, frame_bytes, low_offset, high_offset, …)`：按 C40 保存 RAX/RDX，VOID 时不输出。

capture 放在 cleanup 之后。`add rsp` 会改 flags，所以上游不能假设 flags 在调用前后保持。返回槽可以和实参的源槽相同：实参在 call 之前就已装载，结果在 call 之后才写回。

运行时前提（由上游保证）：setup 之前 `rsp % 16 == 0`，rbp 帧有效；callee 遵守 SysV、正常返回。只支持既有的 INTEGER ABI，不涉及 IR、寄存器分配或 Win64 桥。

## 参数校验（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕。
2. `source_offsets.len*8` 不溢出；四个输入和 `out` 的端点都不回绕，非空时指针不能为 NULL；`source_offsets` 非空时必须 8 对齐。
3. 别名：`written` 与完整 `out` 不重叠；`written` 与 `out` 都不能和任何一个完整输入重叠（按声明长度，包括尾部）。输入之间允许互相重叠。
4. `frame_bytes` 在 0..4080 之间，且是 16 的倍数。
5. 两个名字各 1..64 个原始字节（沿用 C25）。
6. kinds 沿用 C34：最多 16 个，每个只能是 0（单字）或 1（两字聚合），展开后总字数 ≤ 16，且 `source_offsets.len` 必须等于总字数。每个源槽 8 对齐，且 `8 <= offset <= frame_bytes`。
7. 返回值布局沿用 C40（kind、未使用的 offset 必须为 0、槽的范围、PAIR 两槽不同），由实际调用 C40 校验。

第 7 步以及各组件内部的任何非 OK，都发生在局部 scratch 中，按 INVALID 返回，此时用户的 `out` 还没被碰过。所有校验都通过、局部组装完成后才判断用户容量，并且只发布一次精确前缀和 `*written`。任何失败都不改 `out`、`*written` 和任何输入。

## 局部 scratch 的上界证明

四段依次紧接着写进同一个 1536 字节的局部缓冲。每个组件拿到的切片长度，都是它自己的契约已经证明足够的大小；组件最多只写到给它的切片末尾：

| 段 | 给组件的切片 | 组件自身的上界 | 写完后 `at` 的上界 |
| --- | --- | --- | --- |
| setup | 1024 | 13 + 16×55 = 893 | 1024 |
| call | 272 | `call ` + 266 字节符号 + LF = 272 | 1296 |
| cleanup | 32 | `add rsp, 128\n` = 13 | 1328 |
| capture | 64 | 56 | 1392 |

1392 ≤ 1536，所以任何一段都不会越过局部缓冲。合法输入在每一段都一定能放下，不会因为内部 scratch 不够而截断或 panic。实际最长的合法输出（两个 64 字节名字、16 个栈/寄存器字、offset 都是 4 位数、PAIR 返回）由测试计算并覆盖其精确容量。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_invoke_emit`。本组件只是一个调用点片段，不代表完整的 L3 代码生成已经完成。
