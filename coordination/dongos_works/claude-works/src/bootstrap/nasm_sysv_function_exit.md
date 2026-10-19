# bootstrap.nasm_sysv_function_exit：组合返回值装载与受保存寄存器函数尾声（C42）

函数出口片段：先用 C39 从固定帧槽把返回值装进 RAX/RDX，再接 CR11 的函数尾声（恢复 callee-saved 寄存器、`pop rbp`、`ret`）。两个组件都实际调用，本模块不重写规划、十进制或寄存器列表。本组件与 C41 互不依赖，文件也互相独立。

```text
module bootstrap.nasm_sysv_function_exit;
import bootstrap.nasm_sysv_return_values as rv;   // C39（内部依赖 C14、CR8、CR4）
import bootstrap.nasm_function_frame as ff;       // CR11（内部依赖 CR4）
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const MAX_EXTENT:usize=4080;
pub unsafe fn emit(kind:u64, frame_bytes:usize, saved_mask:u64, low_offset:usize, high_offset:usize,
                   out:[]u8, written:*usize)u64
```

## 帧模型（与 CR11 prologue 一致）

`push rbp; mov rbp, rsp; push <saved_mask 中的寄存器，按 rbx→r15>; sub rsp, frame_bytes+padding`。

- `n = popcount5(saved_mask)`，`padding = 8`（n 为奇数时）或 `0`，`extent = 8n + frame_bytes + padding`。
- 以 rbp 为基准：`(0, 8n]` 是保存区，`(8n, 8n+frame_bytes]` 是局部区，`(8n+frame_bytes, extent]` 是只用于对齐的底部 padding。
- 因为 `8n+padding` 是 16 的倍数，`extent` 也是 16 的倍数。

## 参数校验（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕；`out` 端点不回绕，非空时不能为 NULL；`written` 与完整 `out` 不重叠。
2. `frame_bytes` 在 0..4096 之间且是 16 的倍数；`saved_mask` 只允许低 5 位。
3. `extent ≤ 4080`。CR11 本身只要求 `8 + extent ≤ 4096`；这里更严，是因为 extent 要作为 C39 的 frame 参数。
4. **局部区窗口（本模块自己的检查）**：每个非零 offset 必须满足 `8n < offset ≤ 8n + frame_bytes`，不能读保存区或底部 padding。C39 只看到整个 extent，单靠它会接受这两类槽；测试里有一个删掉此检查的真实坏体，专门证明这一点。
5. 调用 C39 `emit(kind, extent, low_offset, high_offset)`：校验 kind、未使用 offset 必须为 0、8 对齐、PAIR 两槽不同，并生成装载文本。
6. 调用 CR11 `epilogue(frame_bytes, saved_mask)`（传原值）生成尾声。

第 5、6 步在局部 scratch 中完成，任何非 OK 都按 INVALID 返回，此时用户 `out` 还没被碰过。组装完成后才判断容量，并只发布一次精确前缀和 `*written`；任何失败都不改 `out` 和 `*written`。

## 输出

```text
<C39 装载：VOID 为空；单字一行；PAIR 为 RAX、RDX 两行>
add rsp, <frame_bytes+padding>   ; 仅当它非 0
pop <reg>                        ; 按 r15→rbx 逆序，仅 mask 中的寄存器
pop rbp
ret
```

唯一的 `ret` 来自 CR11 尾声；没有额外的标签、section 或 global。尾声的 `add`/`pop` 不改 RAX/RDX，所以装载好的返回值能保留到 `ret`；`add rsp` 会改 flags，这里不声称 flags 保持。运行时帧必须正是 CR11 prologue 建立的，本组件不校验运行时地址。

## 长度证明

- C39 装载：最长是 PAIR 的 56 字节，给它 64 字节。
- CR11 尾声：adjust ≤ extent ≤ 4080，十进制最多 4 位，所以是 `add rsp, 4080\n`（14）+ 5 个 pop × 8 + `pop rbp\nret\n`（12）= 66 字节，给它 128 字节。
- 两段紧接着写进 192 字节的局部缓冲（64 + 128 = 192），每个组件最多只写到给它的切片末尾，不会越界。实际最长的输出是 56 + 66 = 122 字节。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_exit_emit`（另外导出 CR11 `prologue`，用来给原生被调用函数建立真实的帧）。
